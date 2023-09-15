import asyncio
from collections.abc import Awaitable, AsyncIterator, Callable, Sequence
import contextlib
from dataclasses import dataclass, field
import inspect
import logging
import ssl
from typing import Generic, Protocol, TypeVar, get_args, runtime_checkable
from uuid import UUID, uuid4

from cattrs.preconf.cbor2 import Cbor2Converter

from .shared import Channel, Message, MessageFlag, ResponseError, Session, SessionId

log = logging.getLogger(__name__)

converter = Cbor2Converter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)

T = TypeVar("T")
U = TypeVar("U")


@runtime_checkable  # yikes?
class _Route(Protocol):
    async def run(self, server: "Server", channel: Channel):
        ...


@contextlib.asynccontextmanager
async def handle_channel_exc(channel: Channel):
    try:
        yield
    except ResponseError as err:
        await channel.write(
            Message(
                err.method,
                err.content,
                MessageFlag.RESPONSE | MessageFlag.ERROR | MessageFlag.END,
            )
        )
    except Exception as err:  # pylint: disable=W0718
        log.exception("%s", err)
        await channel.write(
            Message(
                "",
                b"server error",
                MessageFlag.RESPONSE | MessageFlag.ERROR | MessageFlag.END,
            )
        )


@dataclass
class _SimpleRoute(Generic[T, U]):
    func: Callable[["Server", Session, T], Awaitable[U]]

    async def run(self, server: "Server", channel: Channel):
        async with handle_channel_exc(channel):
            params = [*inspect.signature(self.func).parameters.values()]
            msg = await channel.read()
            content = await self.func(
                server,
                channel.session,
                converter.loads(msg.to_content(), params[-1].annotation),
            )
            await channel.write(
                Message(
                    "", converter.dumps(content), MessageFlag.RESPONSE | MessageFlag.END
                )
            )


async def gen_content_from_channel(channel: Channel, cls: type[T]) -> AsyncIterator[T]:
    while True:
        msg = await channel.read()
        yield converter.loads(msg.to_content(), cls)
        if MessageFlag.END in msg.flag:
            break


@dataclass
class _StreamInRoute(Generic[T, U]):
    func: Callable[["Server", Session, AsyncIterator[T]], Awaitable[U]]

    async def run(self, server: "Server", channel: Channel):
        async with handle_channel_exc(channel):
            params = [*inspect.signature(self.func).parameters.values()]
            content = await self.func(
                server,
                channel.session,
                gen_content_from_channel(channel, get_args(params[-1].annotation)[0]),
            )
            await channel.write(
                Message(
                    "", converter.dumps(content), MessageFlag.RESPONSE | MessageFlag.END
                )
            )


@dataclass
class _StreamOutRoute(Generic[T, U]):
    func: Callable[["Server", Session, T], AsyncIterator[U]]

    async def run(self, server: "Server", channel: Channel):
        async with handle_channel_exc(channel):
            params = [*inspect.signature(self.func).parameters.values()]
            msg = await channel.read()
            async for content in self.func(
                server,
                channel.session,
                converter.loads(msg.content, params[-1].annotation),
            ):
                await channel.write(
                    Message("", converter.dumps(content), MessageFlag.RESPONSE)
                )
            await channel.write(
                Message("", b"", MessageFlag.RESPONSE | MessageFlag.END)
            )


@dataclass
class _StreamInOutRoute(Generic[T, U]):
    func: Callable[["Server", Session, AsyncIterator[T]], AsyncIterator[U]]

    async def run(self, server: "Server", channel: Channel):
        async with handle_channel_exc(channel):
            params = [*inspect.signature(self.func).parameters.values()]
            async for content in self.func(
                server,
                channel.session,
                gen_content_from_channel(channel, get_args(params[-1].annotation)[0]),
            ):
                await channel.write(
                    Message("", converter.dumps(content), MessageFlag.RESPONSE)
                )
            await channel.write(
                Message("", b"", MessageFlag.RESPONSE | MessageFlag.END)
            )


class Route:
    @classmethod
    def simple(
        cls, func: Callable[["Server", Session, T], Awaitable[U]]
    ) -> _SimpleRoute[T, U]:
        return _SimpleRoute[T, U](func)

    @classmethod
    def stream_in(
        cls, func: Callable[["Server", Session, AsyncIterator[T]], Awaitable[U]]
    ) -> _StreamInRoute[T, U]:
        return _StreamInRoute[T, U](func)

    @classmethod
    def stream_out(
        cls, func: Callable[["Server", Session, T], AsyncIterator[U]]
    ) -> _StreamOutRoute[T, U]:
        return _StreamOutRoute[T, U](func)

    @classmethod
    def stream_in_out(
        cls, func: Callable[["Server", Session, AsyncIterator[T]], AsyncIterator[U]]
    ) -> _StreamInOutRoute[T, U]:
        return _StreamInOutRoute[T, U](func)


@dataclass
class Server:
    routes: dict[str, _Route] = field(default_factory=dict)
    sessions: dict[UUID, Session] = field(default_factory=dict)

    def __post_init__(self):
        for name, rte in inspect.getmembers(self, lambda x: isinstance(x, _Route)):
            self.add_route(name, rte)

    def add_route(self, name: str, rte: Route):
        self.routes[name] = rte

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        session = Session(uuid4(), reader, writer)
        self.sessions[session.id] = session
        with session.create_channel() as channel:
            await channel.write(
                Message(
                    "hello",
                    converter.dumps(SessionId.from_session(session)),
                    MessageFlag.RESPONSE | MessageFlag.END,
                )
            )
        while True:
            if channel_method := await session.read():
                channel, msg_method = channel_method
                if msg_method == "close":
                    await channel.write(
                        Message("", b"", MessageFlag.RESPONSE | MessageFlag.END)
                    )
                    break
                elif rte := self.routes.get(msg_method):
                    await rte.run(self, channel)
                else:
                    await channel.write(
                        Message(
                            "",
                            b"no method found",
                            MessageFlag.RESPONSE | MessageFlag.ERROR | MessageFlag.END,
                        )
                    )
            else:
                break

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
