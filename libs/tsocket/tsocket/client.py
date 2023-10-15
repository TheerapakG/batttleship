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

ClientT_contra = TypeVar("ClientT_contra", bound="Client", contravariant=True)
T = TypeVar("T")
U = TypeVar("U")


@runtime_checkable  # yikes?
class _Route(Protocol[ClientT_contra]):
    def get_fake_route(self, name: str) -> Callable[[ClientT_contra, Any], Any]:
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
class _SimpleRoute(Generic[ClientT_contra, T, U]):
    func: Callable[[ClientT_contra, T], Awaitable[U]]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(self: ClientT_contra, data: T) -> U:
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
class _StreamInRoute(Generic[ClientT_contra, T, U]):
    func: Callable[[ClientT_contra, AsyncIterator[T]], Awaitable[U]]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(self: ClientT_contra, data: AsyncIterator[T]) -> U:
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
class _StreamOutRoute(Generic[ClientT_contra, T, U]):
    func: Callable[[ClientT_contra, T], AsyncIterator[U]]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(self: ClientT_contra, data: T) -> AsyncIterator[U]:
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
class _StreamInOutRoute(Generic[ClientT_contra, T, U]):
    func: Callable[[ClientT_contra, T], AsyncIterator[U]]

    def get_fake_route(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_route(
            self: ClientT_contra, data: AsyncIterator[T]
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
    def simple(cls, func: Callable[[ClientT_contra, T], Awaitable[U]]):
        return _SimpleRoute(func)

    @classmethod
    def stream_in(
        cls, func: Callable[[ClientT_contra, AsyncIterator[T]], Awaitable[U]]
    ):
        return _StreamInRoute(func)

    @classmethod
    def stream_out(cls, func: Callable[[ClientT_contra, T], AsyncIterator[U]]):
        return _StreamOutRoute(func)

    @classmethod
    def stream_in_out(
        cls, func: Callable[[ClientT_contra, AsyncIterator[T]], AsyncIterator[U]]
    ):
        return _StreamInOutRoute(func)


@dataclass
class _Subscribe(Generic[ClientT_contra, T]):
    func: Callable[[ClientT_contra], AsyncIterator[T]]

    def get_fake_subscribe(self, name: str):
        func = self.func

        @wraps(func)
        async def fake_subscribe(self: ClientT_contra):
            queue = self.cbs.get(name, asyncio.Queue())
            self.cbs[name] = queue
            while True:
                yield converter.loads(
                    await queue.get(),
                    get_args(inspect.signature(func).return_annotation)[0],
                )

        return fake_subscribe

    def __call__(self) -> AsyncIterator[T]:
        # For tricking LSP / type checker
        raise NotImplementedError()


def subscribe(func: Callable[[ClientT_contra], AsyncIterator[T]]):
    return _Subscribe(func)


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
                queue = self.client.cbs.get(msg.method, asyncio.Queue())
                self.client.cbs[msg.method] = queue
                log.debug("EMIT: %s %s", msg.method, msg.content)
                await queue.put(msg.content)
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
        subscribes = {
            name: subscribe
            for name, subscribe in attrs.items()
            if isinstance(subscribe, _Subscribe)
        }
        attrs["subscribes"] = subscribes
        attrs.update(
            {name: route.get_fake_subscribe(name) for name, route in subscribes.items()}
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
    subscribes: ClassVar[
        dict[
            str,
            _Subscribe,
        ]
    ]
    session: ClientSession | None = field(init=False, default=None)
    cbs: dict[str, asyncio.Queue[bytes]] = field(init=False, default_factory=dict)

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
        log.info("client started on %s:%s", host, port)

    async def disconnect(self):
        if self.session is None:
            raise DisconnectedError()
        session = self.session
        self.session = None
        with session.create_channel() as channel:
            await channel.write(Message("close", b""))
            await channel.read()
        await session.read_task
