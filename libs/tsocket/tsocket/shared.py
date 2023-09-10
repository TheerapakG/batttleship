import asyncio
from dataclasses import dataclass, field
import logging
from uuid import UUID, uuid4

log = logging.getLogger(__name__)


class ConnectedError(Exception):
    pass


class DisconnectedError(Exception):
    pass


@dataclass
class ResponseError(Exception):
    method: str
    data: bytes


@dataclass
class Message:
    method: str
    data: bytes
    id: UUID = field(default_factory=uuid4)  # pylint: disable=C0103

    def response(self, method: str, data: bytes):
        return Message(method, data, self.id)


@dataclass
class Session:
    id: UUID  # pylint: disable=C0103
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    wait: dict[UUID, asyncio.Future[bytes]] = field(default_factory=dict)

    async def write(
        self,
        msg: Message,
        *,
        wait: bool = False,
    ):
        log.info("SEND %s: %s %s", msg.id, msg.method, msg.data)
        msg_bytes = b" ".join([msg.method.encode(), msg.data])
        self.writer.write(msg.id.bytes)
        self.writer.write(len(msg_bytes).to_bytes(16))
        self.writer.write(msg_bytes)
        await self.writer.drain()
        if wait:
            future = asyncio.Future[bytes]()
            self.wait[msg.id] = future
            return await future

    async def read(self):
        while True:
            try:
                msg_id_bytes = await self.reader.readexactly(16)
                msg_id = UUID(bytes=msg_id_bytes)
                size_bytes = await self.reader.readexactly(16)
                size = int.from_bytes(size_bytes)
                msg_method_bytes, data = (await self.reader.readexactly(size)).split(
                    b" ", 1
                )
                msg_method = msg_method_bytes.decode()
                log.info("RECV %s: %s %s", msg_id, msg_method, data)
                if fut := self.wait.get(msg_id):
                    if msg_method == "ok":
                        fut.set_result(data)
                    else:
                        fut.set_exception(ResponseError(msg_method, data))
                else:
                    return Message(msg_method, data, msg_id)
            except asyncio.exceptions.IncompleteReadError:
                break


@dataclass
class SessionId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_session(cls, session: Session):
        return cls(session.id)


@dataclass
class Empty:
    pass
