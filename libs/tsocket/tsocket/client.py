import asyncio
from collections.abc import Awaitable, AsyncIterator, Callable
from dataclasses import dataclass, field
from functools import wraps
import inspect
import logging
import ssl
from typing import (
    Any,
    ClassVar,
    Generic,
    Protocol,
    TypeVar,
    get_args,
    runtime_checkable,
)
from uuid import UUID, uuid4

from cattrs.preconf.cbor2 import Cbor2Converter

from .shared import (
    Channel,
    ConnectedError,
    DisconnectedError,
    Message,
    MessageFlag,
    ResponseError,
    Session,
)

log = logging.getLogger(__name__)

converter = Cbor2Converter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)

T = TypeVar("T")
U = TypeVar("U")


@runtime_checkable  # yikes?
class _Route(Protocol):
    def get_fake_route(self, name: str) -> Callable[["Client", Any], Any]:
        ...


async def simple_writer(channel: Channel, name: str, data: T):
    await channel.write(Message(name, converter.dumps(data)))


async def stream_writer(channel: Channel, name: str, data: AsyncIterator[T]):
    try:
        async for content in data:
            await channel.write(
                Message(name, converter.dumps(content), MessageFlag.NONE)
            )
        await channel.write(Message(name, b""))
    except Exception:  # pylint: disable=W0718
        await channel.write(
            Message("", b"client error", MessageFlag.ERROR | MessageFlag.END)
        )


async def simple_reader(channel: Channel, cls: type[T]):
    msg = await channel.read()
    return converter.loads(msg.to_content(), cls)


async def stream_reader(channel: Channel, cls: type[T]):
    while True:
        msg = await channel.read()
        content = msg.to_content()
        if content:
            yield converter.loads(content, cls)
        if MessageFlag.END in msg.flag:
            break


@dataclass
class _SimpleRoute(Generic[T, U]):
    func: Callable[["Client", T], Awaitable[U]]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(self: "Client", data: T) -> U:
            with self.session.create_channel() as channel:
                write_task = asyncio.create_task(simple_writer(channel, name, data))
                try:
                    content = await simple_reader(
                        channel, inspect.signature(func).return_annotation
                    )
                    await write_task
                    return content
                except ResponseError as err:
                    await write_task
                    raise ResponseError(err.method, err.content) from None

        return fake_route

    async def __call__(self, data: T) -> U:
        # For tricking LSP / type checker
        raise NotImplementedError()


@dataclass
class _StreamInRoute(Generic[T, U]):
    func: Callable[["Client", AsyncIterator[T]], U]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(self: "Client", data: AsyncIterator[T]) -> U:
            with self.session.create_channel() as channel:
                write_task = asyncio.create_task(stream_writer(channel, name, data))
                try:
                    content = await simple_reader(
                        channel, inspect.signature(func).return_annotation
                    )
                    await write_task
                    return content
                except ResponseError as err:
                    await write_task
                    raise ResponseError(err.method, err.content) from None

        return fake_route

    async def __call__(self, data: AsyncIterator[T]) -> U:
        # For tricking LSP / type checker
        raise NotImplementedError()


@dataclass
class _StreamOutRoute(Generic[T, U]):
    func: Callable[["Client", T], AsyncIterator[U]]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(self: "Client", data: T) -> AsyncIterator[U]:
            with self.session.create_channel() as channel:
                write_task = asyncio.create_task(simple_writer(channel, name, data))
                try:
                    async for content in stream_reader(
                        channel, get_args(inspect.signature(func).return_annotation)[0]
                    ):
                        yield content
                    await write_task
                except ResponseError as err:
                    await write_task
                    raise ResponseError(err.method, err.content) from None

        return fake_route

    async def __call__(self, data: T) -> AsyncIterator[U]:
        # For tricking LSP / type checker
        raise NotImplementedError()


@dataclass
class _StreamInOutRoute(Generic[T, U]):
    func: Callable[["Client", T], AsyncIterator[U]]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(
            self: "Client", data: AsyncIterator[T]
        ) -> AsyncIterator[U]:
            with self.session.create_channel() as channel:
                write_task = asyncio.create_task(stream_writer(channel, name, data))
                try:
                    async for content in stream_reader(
                        channel, get_args(inspect.signature(func).return_annotation)[0]
                    ):
                        yield content
                    await write_task
                except ResponseError as err:
                    await write_task
                    raise ResponseError(err.method, err.content) from None

        return fake_route

    async def __call__(self, data: AsyncIterator[T]) -> AsyncIterator[U]:
        # For tricking LSP / type checker
        raise NotImplementedError()


class Route:
    @classmethod
    def simple(cls, func: Callable[["Client", T], Awaitable[U]]) -> _SimpleRoute[T, U]:
        return _SimpleRoute[T, U](func)

    @classmethod
    def stream_in(
        cls, func: Callable[["Client", AsyncIterator[T]], Awaitable[U]]
    ) -> _StreamInRoute[T, U]:
        return _StreamInRoute[T, U](func)

    @classmethod
    def stream_out(
        cls, func: Callable[["Client", T], AsyncIterator[U]]
    ) -> _StreamOutRoute[T, U]:
        return _StreamOutRoute[T, U](func)

    @classmethod
    def stream_in_out(
        cls, func: Callable[["Client", AsyncIterator[T]], AsyncIterator[U]]
    ) -> _StreamInOutRoute[T, U]:
        return _StreamInOutRoute[T, U](func)


@dataclass
class ClientSession:
    session: Session
    client: "Client"
    read_task: asyncio.Task = field(init=False)

    def __post_init__(self):
        self.read_task = asyncio.create_task(self.reader())

    def create_channel(self):
        return self.session.create_channel()

    def destroy_channel(self, channel: Channel):
        self.session.destroy_channel(channel)

    async def reader(self):
        while True:
            if channel_method := await self.session.read():
                channel, _ = channel_method
                self.destroy_channel(channel)
                msg = await channel.read()
                await self.client.emit(msg.method, msg.content)
            else:
                break


class ClientMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        routes = {
            name: route for name, route in attrs.items() if isinstance(route, _Route)
        }
        attrs["routes"] = routes
        attrs.update(
            {name: route.get_fake_route(name) for name, route in routes.items()}
        )
        return super().__new__(mcs, name, bases, attrs)


@dataclass
class Client(metaclass=ClientMeta):
    routes: ClassVar[
        dict[
            str,
            _Route,
        ]
    ]
    session: ClientSession | None = field(init=False, default=None)

    async def connect(
        self,
        host: str | None,
        port: int | str | None,
        ssl: ssl.SSLContext | bool | None = None,  # pylint: disable=W0621
    ):
        if self.session is not None:
            raise ConnectedError()
        reader, writer = await asyncio.open_connection(host, port, ssl=ssl)
        self.session = ClientSession(Session(uuid4(), reader, writer), self)

    async def disconnect(self):
        if self.session is None:
            raise DisconnectedError()
        session = self.session
        self.session = None
        with session.create_channel() as channel:
            await channel.write(Message("close", b""))
            await channel.read()
        await session.read_task

    async def emit(self, msg_method: str, data: bytes):
        log.info("EMIT: %s %s", msg_method, data)
        # TODO
