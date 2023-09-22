import asyncio
from dataclasses import dataclass, field
import os
import ssl
from uuid import UUID, uuid4

from dotenv import load_dotenv
from tsocket.server import Server, Route
from tsocket.shared import Empty, ResponseError, Session

from .shared import models
from .shared.logging import setup_logging


@dataclass
class BattleshipServer(Server):
    # TODO: actual db?
    rooms: dict[UUID, models.Room] = field(default_factory=dict)

    @Route.simple
    async def ping(self, _session: Session, _: Empty) -> Empty:
        return Empty()

    @Route.simple
    async def online(self, _session: Session, _: Empty) -> int:
        return len(self.sessions)

    @Route.simple
    async def room_create(
        self, _session: Session, args: models.RoomCreateArgs
    ) -> models.RoomId:
        room = models.Room(uuid4(), args.name)
        self.rooms[room.id] = room
        return models.RoomId.from_room(room)

    @Route.simple
    async def room_get(
        self, _session: Session, args: models.RoomGetArgs
    ) -> models.Room:
        if room := self.rooms.get(UUID(args.id), None):
            return room
        raise ResponseError("not_found", b"")

    @Route.simple
    async def room_delete(
        self, _session: Session, args: models.RoomDeleteArgs
    ) -> models.RoomId:
        if room := self.rooms.pop(UUID(args.id), None):
            return models.RoomId.from_room(room)
        raise ResponseError("not_found", b"")

    @Route.simple
    async def room_list(self, _session: Session, _: Empty) -> list[models.RoomId]:
        return [models.RoomId.from_room(room) for room in self.rooms.values()]


server = BattleshipServer()


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(os.environ["SSL_CERT"], os.environ["SSL_KEY"])
    asyncio.run(
        server.run(
            "0.0.0.0",
            60000,
            ssl=ssl_context,
        )
    )
