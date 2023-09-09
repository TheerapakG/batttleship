import asyncio
from dataclasses import dataclass, field
from functools import wraps
import inspect
import logging
from typing import Any, Awaitable, Callable, ClassVar, Generic, TypeVar
from uuid import UUID, uuid4

from cattrs.preconf.json import JsonConverter

from .shared import Session

log = logging.getLogger(__name__)

converter = JsonConverter()

converter.register_structure_hook(UUID, lambda d, t: UUID(d))
converter.register_unstructure_hook(UUID, str)

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


class ClientSession:
    session: Session
    client: "Client"
    read_task: asyncio.Task

    def __init__(self, session: Session, client: "Client"):
        self.session = session
        self.client = client
        self.read_task = asyncio.create_task(self.reader())

    async def write(
        self,
        msg_method: str,
        data: str,
        *,
        msg_id: UUID | None = None,
        wait: bool = True,
    ):
        return await self.session.write(msg_method, data, msg_id=msg_id, wait=wait)

    async def reader(self):
        while True:
            if msg := await self.session.read():
                await self.client.emit(msg.method, msg.data)
            else:
                break


def get_fake_route(name: str, route: Route[T, U]):
    @wraps(route.func)
    async def fake_route(self: "Client", data: T) -> U:
        return await self.request(
            name,
            converter.dumps(data),
            inspect.signature(route.func).return_annotation,
        )

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

    async def connect(self, host: str | None, port: int | str | None):
        # TODO: SSL
        reader, writer = await asyncio.open_connection(host, port)
        self.session = ClientSession(Session(uuid4(), reader, writer), self)

    async def disconnect(self):
        await self.write("close", "close")
        await self.session.read_task
        self.session = None

    async def write(
        self,
        msg_method: str,
        data: str,
        *,
        msg_id: UUID | None = None,
        wait: bool = True,
    ):
        return await self.session.write(msg_method, data, msg_id=msg_id, wait=wait)

    async def request(self, msg_method: str, data: str, cl: type[T]):
        return converter.loads(await self.write(msg_method, data), cl)

    async def emit(self, msg_method, data):
        log.info("EMIT: %s %s", msg_method, data)
        pass  # TODO
