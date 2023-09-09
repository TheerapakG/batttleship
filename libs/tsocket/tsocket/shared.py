import asyncio
from dataclasses import dataclass, field
import logging
from uuid import UUID, uuid4

from .utils import ResponseError

log = logging.getLogger(__name__)


@dataclass
class Message:
    id: UUID
    method: str
    data: str


@dataclass
class Session:
    id: UUID
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    wait: dict[UUID, asyncio.Future[str]] = field(default_factory=dict)

    async def write(
        self,
        msg_method: str,
        data: str,
        *,
        msg_id: UUID | None = None,
        wait: bool = False,
    ):
        if msg_id is None:
            msg_id = uuid4()
        log.info("SEND %s: %s %s", msg_id, msg_method, data)
        s = f"{msg_method} {data}".encode()
        self.writer.write(msg_id.bytes)
        self.writer.write(len(s).to_bytes(16))
        self.writer.write(s)
        await self.writer.drain()
        if wait:
            future = asyncio.Future[str]()
            self.wait[msg_id] = future
            return await future

    async def read(self):
        while True:
            try:
                msg_id_bytes = await self.reader.readexactly(16)
                msg_id = UUID(bytes=msg_id_bytes)
                size_bytes = await self.reader.readexactly(16)
                size = int.from_bytes(size_bytes)
                msg_method, data = (
                    (await self.reader.readexactly(size)).decode().split(None, 1)
                )
                log.info("RECV %s: %s %s", msg_id, msg_method, data)
                if fut := self.wait.get(msg_id):
                    if msg_method == "ok":
                        fut.set_result(data)
                    else:
                        fut.set_exception(ResponseError(msg_method, data))
                else:
                    return Message(msg_id, msg_method, data)
            except asyncio.exceptions.IncompleteReadError:
                break
