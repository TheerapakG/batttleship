import asyncio
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from tsocket.server import Server, route
from tsocket.shared import Session
from tsocket.utils import Empty, ResponseError

from .shared import models
from .shared.logging import setup_logging


@dataclass
class BattleshipServer(Server):
    # TODO: actual db?
    rooms: dict[UUID, models.Room] = field(default_factory=dict)

    @route
    async def ping(self, sess: Session, _: Empty) -> Empty:
        return Empty()

    @route
    async def room_create(
        self, sess: Session, args: models.RoomCreateArgs
    ) -> models.RoomId:
        room = models.Room(uuid4(), args.name)
        self.rooms[room.id] = room
        return models.RoomId.from_room(room)

    @route
    async def room_get(self, sess: Session, args: models.RoomGetArgs) -> models.Room:
        if room := self.rooms.get(UUID(args.id), None):
            return room
        raise ResponseError("not_found", "")

    @route
    async def room_delete(
        self, sess: Session, args: models.RoomDeleteArgs
    ) -> models.RoomId:
        if room := self.rooms.pop(UUID(args.id), None):
            return models.RoomId.from_room(room)
        raise ResponseError("not_found", "")

    @route
    async def room_list(self, sess: Session, _: Empty) -> list[models.RoomId]:
        return [models.RoomId.from_room(room) for room in self.rooms.values()]


server = BattleshipServer()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(server.run("0.0.0.0", 60000))
