import asyncio
import contextlib
from dataclasses import dataclass, field
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Generic, Sequence, TypeVar
from uuid import UUID, uuid4

from cattrs.preconf.json import JsonConverter

from .shared import Session
from .utils import ResponseError

log = logging.getLogger(__name__)

converter = JsonConverter()
converter.register_structure_hook(UUID, lambda d, t: UUID(d))
converter.register_unstructure_hook(UUID, str)

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class Route(Generic[T]):
    func: Callable[["Server", Session, T], Awaitable[U]]


def route(func: Callable[["Server", Session, T], Awaitable[U]]):
    return Route(func)


@dataclass
class Server:
    routes: dict[
        str,
        Route[Any],
    ] = field(default_factory=dict)
    sessions: dict[UUID, Session] = field(default_factory=dict)

    def __post_init__(self):
        for name, route in inspect.getmembers(self, lambda x: isinstance(x, Route)):
            self.add_route(name, route)

    def add_route(self, name: str, route: Route):
        self.routes[name] = route

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        session = Session(uuid4(), reader, writer)
        self.sessions[session.id] = session
        await session.write("hello", json.dumps({"id": str(session.id)}))
        while True:
            if msg := await session.read():
                if msg.method == "close":
                    await session.write("ok", "ok", msg_id=msg.id)
                    break
                try:
                    if route := self.routes.get(msg.method):
                        params = [*inspect.signature(route.func).parameters.values()]
                        ret_data = await route.func(
                            self,
                            session,
                            converter.loads(msg.data, params[-1].annotation),
                        )
                        await session.write(
                            "ok", converter.dumps(ret_data), msg_id=msg.id
                        )
                    else:
                        await session.write("error", "method not found", msg_id=msg.id)
                except ResponseError as e:
                    await session.write(e.method, e.data, msg_id=msg.id)
                except Exception:
                    await session.write("error", "server error", msg_id=msg.id)
            else:
                break

        writer.write_eof()
        await writer.drain()
        writer.close()
        del self.sessions[session.id]

    async def run(self, host: str | Sequence[str] | None, port: int | str | None):
        # TODO: SSL
        server = await asyncio.start_server(self.handle_client, host, port)
        with contextlib.suppress(asyncio.CancelledError):
            async with server:
                await server.serve_forever()
