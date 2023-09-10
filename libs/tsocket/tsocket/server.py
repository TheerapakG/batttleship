import asyncio
import contextlib
from dataclasses import dataclass, field
import inspect
import logging
import ssl
from typing import Any, Awaitable, Callable, Generic, Sequence, TypeVar
from uuid import UUID, uuid4

from cattrs.preconf.cbor2 import Cbor2Converter

from .shared import Message, ResponseError, Session, SessionId

log = logging.getLogger(__name__)

converter = Cbor2Converter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)

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
        for name, rte in inspect.getmembers(self, lambda x: isinstance(x, Route)):
            self.add_route(name, rte)

    def add_route(self, name: str, rte: Route):
        self.routes[name] = rte

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        session = Session(uuid4(), reader, writer)
        self.sessions[session.id] = session
        await session.write(
            Message("hello", converter.dumps(SessionId.from_session(session)))
        )
        while True:
            if msg := await session.read():
                if msg.method == "close":
                    await session.write(msg.response("ok", b"ok"))
                    break
                try:
                    if rte := self.routes.get(msg.method):
                        params = [*inspect.signature(rte.func).parameters.values()]
                        ret_data = await rte.func(
                            self,
                            session,
                            converter.loads(msg.data, params[-1].annotation),
                        )
                        await session.write(
                            msg.response("ok", converter.dumps(ret_data))
                        )
                    else:
                        await session.write(msg.response("error", b"method not found"))
                except ResponseError as err:
                    await session.write(msg.response(err.method, err.data))
                except Exception:  # pylint: disable=W0718
                    await session.write(msg.response("error", b"server error"))
            else:
                break

        writer.write_eof()
        await writer.drain()
        writer.close()
        del self.sessions[session.id]

    async def run(
        self,
        host: str | Sequence[str] | None,
        port: int | str | None,
        ssl: ssl.SSLContext | None,  # pylint: disable=W0621
    ):
        server = await asyncio.start_server(self.handle_client, host, port, ssl=ssl)
        with contextlib.suppress(asyncio.CancelledError):
            async with server:
                await server.serve_forever()
