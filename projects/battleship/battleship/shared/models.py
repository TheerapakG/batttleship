from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass
class Player:
    id: UUID  # pylint: disable=C0103
    name: str
    rating: int
    admin: bool
    auth_token: UUID
    transfer_code: UUID | None

    def expected_win(self, other: "Player"):
        self_q = 10 ** (self.rating / 400)
        other_q = 10 ** (other.rating / 400)
        return self_q / (self_q + other_q)


@dataclass
class PlayerInfo:
    id: UUID  # pylint: disable=C0103
    name: str
    rating: int

    @classmethod
    def from_player(cls, player: Player):
        return cls(player.id, player.name, player.rating)


@dataclass(eq=True, frozen=True)
class PlayerId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_player(cls, player: Player):
        return cls(player.id)

    @classmethod
    def from_player_info(cls, player_info: PlayerInfo):
        return cls(player_info.id)


@dataclass
class Board:
    id: UUID  # pylint: disable=C0103
    player: PlayerId
    room: "RoomId"


@dataclass(eq=True, frozen=True)
class BoardId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_board(cls, board: Board):
        return cls(board.id)


@dataclass
class RoomInfo:
    id: UUID  # pylint: disable=C0103
    players: list[PlayerId] = field(default_factory=list)
    boards: dict[PlayerId, BoardId] = field(default_factory=dict)


@dataclass(eq=True, frozen=True)
class RoomId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_room_info(cls, room_info: RoomInfo):
        return cls(room_info.id)


@dataclass(eq=True, frozen=True)
class BearingPlayerAuth:
    auth_token: UUID

    @classmethod
    def from_player(cls, player: Player):
        return cls(player.auth_token)


# API args below


@dataclass
class PlayerCreateArgs:
    name: str


@dataclass
class PrivateRoomCreateResults:
    room: RoomId
    join_code: str


@dataclass(order=True, frozen=True)
class PrivateRoomJoinArgs(BearingPlayerAuth):
    join_code: str
