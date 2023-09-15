import asyncio
from enum import IntFlag, auto
from dataclasses import dataclass, field
import logging
from uuid import UUID, uuid4

log = logging.getLogger(__name__)

PROTOCOL_NAME = b"tsocket\x00\x00\x00\x00\x00\x00\x00\x00\x00"
PROTOCOL_VER = b"\x00\x00\x00\x00\x00\x01\x00\x00"


class ConnectedError(Exception):
    pass


class DisconnectedError(Exception):
    pass


class RespondResponseError(Exception):
    pass


class RespondRequestError(Exception):
    pass


class MessageFlag(IntFlag):
    NONE = 0
    RESPONSE = auto()
    ERROR = auto()
    END = auto()


@dataclass
class ResponseError(Exception):
    method: str
    content: bytes


@dataclass
class Message:
    method: str
    content: bytes
    flag: MessageFlag = field(default=MessageFlag.END)

    def to_content(self):
        if MessageFlag.ERROR in self.flag:
            raise ResponseError(self.method, self.content)
        return self.content


@dataclass
class Channel:
    session: "Session"
    id: UUID = field(default_factory=uuid4)  # pylint: disable=C0103
    queue: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.session.destroy_channel(self)

    async def write(self, msg: Message):
        log.info("SEND %s: %s %s %s", self.id, msg.flag, msg.method, msg.content)
        if MessageFlag.RESPONSE in msg.flag:
            if MessageFlag.END in msg.flag or MessageFlag.ERROR in msg.flag:
                self.session.destroy_channel(self)
        msg_method_bytes = msg.method.encode()
        self.session.writer.write(PROTOCOL_NAME)
        self.session.writer.write(PROTOCOL_VER)
        self.session.writer.write(self.id.bytes)
        self.session.writer.write(msg.flag.to_bytes(8))
        self.session.writer.write(len(msg_method_bytes).to_bytes(8))
        self.session.writer.write(len(msg.content).to_bytes(8))
        self.session.writer.write(msg_method_bytes)
        self.session.writer.write(msg.content)
        await self.session.writer.drain()

    async def read(self):
        msg = await self.queue.get()
        log.info("RECV %s: %s %s %s", self.id, msg.flag, msg.method, msg.content)
        return msg


@dataclass
class Session:
    id: UUID  # pylint: disable=C0103
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    channels: dict[UUID, Channel] = field(default_factory=dict)

    def create_channel(self):
        channel = Channel(self)
        self.channels[channel.id] = channel
        return channel

    def destroy_channel(self, channel: Channel):
        self.channels.pop(channel.id, None)

    async def read(self):
        while True:
            try:
                proto_name = await self.reader.readexactly(16)
                if proto_name != PROTOCOL_NAME:
                    return None
                proto_ver = await self.reader.readexactly(8)
                if proto_ver != PROTOCOL_VER:
                    return None
                channel_id_bytes = await self.reader.readexactly(16)
                channel_id = UUID(bytes=channel_id_bytes)
                msg_flag_bytes = await self.reader.readexactly(8)
                msg_flag = MessageFlag.from_bytes(msg_flag_bytes)
                msg_method_size_bytes = await self.reader.readexactly(8)
                msg_method_size = int.from_bytes(msg_method_size_bytes)
                msg_content_size_bytes = await self.reader.readexactly(8)
                msg_content_size = int.from_bytes(msg_content_size_bytes)
                msg_method = (await self.reader.readexactly(msg_method_size)).decode()
                msg_content = await self.reader.readexactly(msg_content_size)
                if channel := self.channels.get(channel_id):
                    await channel.queue.put(Message(msg_method, msg_content, msg_flag))
                    if MessageFlag.RESPONSE in msg_flag:
                        if MessageFlag.END in msg_flag or MessageFlag.ERROR in msg_flag:
                            self.destroy_channel(channel)
                elif MessageFlag.RESPONSE not in msg_flag:
                    channel = Channel(self, channel_id)
                    await channel.queue.put(Message(msg_method, msg_content, msg_flag))
                    self.channels[channel.id] = channel
                    return channel, msg_method
                else:
                    log.info(
                        "DROP %s: %s %s %s",
                        channel_id,
                        msg_flag,
                        msg_method,
                        msg_content,
                    )
            except asyncio.exceptions.IncompleteReadError:
                return None


@dataclass
class SessionId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_session(cls, session: Session):
        return cls(session.id)


@dataclass
class Empty:
    pass
