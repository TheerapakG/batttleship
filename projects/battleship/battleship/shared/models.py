from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class Player:
    id: UUID
    name: str

    def serialize_id(self):
        return {"id": str(self.id)}

    def serialize_all(self):
        return {"id": str(self.id), "name": self.name}


@dataclass
class Board:
    id: UUID
    player: UUID  # Player.id

    def serialize_id(self):
        return {"id": str(self.id)}

    def serialize_all(self):
        return {"id": str(self.id), "player": str(self.player)}


@dataclass
class Room:
    id: UUID
    name: str
    players: list[UUID] = field(default_factory=list)  # list[Player.id]
    boards: dict[UUID, UUID] = field(default_factory=dict)  # dict[Player.id, Board.id]


@dataclass
class RoomId:
    id: UUID

    @classmethod
    def from_room(cls, room: Room):
        return cls(room.id)


# API args below


@dataclass
class RoomCreateArgs:
    name: str = field(default="<unnamed>")


@dataclass
class RoomGetArgs:
    id: str


@dataclass
class RoomDeleteArgs:
    id: str
