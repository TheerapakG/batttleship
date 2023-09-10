import asyncio
from dataclasses import dataclass, field
from functools import wraps
import inspect
import logging
import ssl
from typing import Any, Awaitable, Callable, ClassVar, Generic, TypeVar
from uuid import UUID, uuid4

from cattrs.preconf.cbor2 import Cbor2Converter

from .shared import DisconnectedError, Message, ResponseError, Session

log = logging.getLogger(__name__)

converter = Cbor2Converter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class Route(Generic[T, U]):
    func: Callable[["Client", T], Awaitable[U]]

    async def __call__(self, data: T) -> U:
        # For tricking LSP / type checker
        raise NotImplementedError()


def route(func: Callable[["Client", T], Awaitable[U]]):
    return Route(func)


@dataclass
class ClientSession:
    session: Session
    client: "Client"
    read_task: asyncio.Task = field(init=False)

    def __post_init__(self):
        self.read_task = asyncio.create_task(self.reader())

    async def write(
        self,
        msg: Message,
        *,
        wait: bool = True,
    ):
        return await self.session.write(msg, wait=wait)

    async def reader(self):
        while True:
            if msg := await self.session.read():
                await self.client.emit(msg.method, msg.data)
            else:
                break


def get_fake_route(name: str, rte: Route[T, U]):
    @wraps(rte.func)
    async def fake_route(self: "Client", data: T) -> U:
        try:
            return await self.request(
                name,
                converter.dumps(data),
                inspect.signature(rte.func).return_annotation,
            )
        except ResponseError as err:
            raise ResponseError(err.method, err.data) from None

    return fake_route


class ClientMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        routes = {
            name: route for name, route in attrs.items() if isinstance(route, Route)
        }
        attrs["routes"] = routes
        attrs.update(
            {name: get_fake_route(name, route) for name, route in routes.items()}
        )
        return super().__new__(mcs, name, bases, attrs)


@dataclass
class Client(metaclass=ClientMeta):
    routes: ClassVar[
        dict[
            str,
            Route[Any, Any],
        ]
    ]
    session: ClientSession | None = field(default=None)

    async def connect(
        self,
        host: str | None,
        port: int | str | None,
        ssl: ssl.SSLContext | bool | None = None,  # pylint: disable=W0621
    ):
        reader, writer = await asyncio.open_connection(host, port, ssl=ssl)
        self.session = ClientSession(Session(uuid4(), reader, writer), self)

    async def disconnect(self):
        if self.session is None:
            raise DisconnectedError()
        session = self.session
        self.session = None
        await session.write(Message("close", b"close"))
        await session.read_task

    async def write(
        self,
        msg: Message,
        *,
        wait: bool = True,
    ):
        if self.session is None:
            raise DisconnectedError()
        try:
            return await self.session.write(msg, wait=wait)
        except ResponseError as err:
            raise ResponseError(err.method, err.data) from None

    async def request(self, msg_method: str, data: bytes, cls: type[T]):
        try:
            return converter.loads(await self.write(Message(msg_method, data)), cls)
        except ResponseError as err:
            raise ResponseError(err.method, err.data) from None

    async def emit(self, msg_method: str, data: bytes):
        log.info("EMIT: %s %s", msg_method, data)
        # TODO
