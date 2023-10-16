from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(eq=True, frozen=True)
class PlayerId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_player(cls, player: "Player"):
        return cls(player.id)

    @classmethod
    def from_player_info(cls, player_info: "PlayerInfo"):
        return cls(player_info.id)


@dataclass(eq=True, frozen=True)
class PlayerInfo(PlayerId):
    name: str = field(compare=False)
    rating: int = field(compare=False)

    @classmethod
    def from_player(cls, player: "Player"):
        return cls(player.id, player.name, player.rating)


@dataclass(eq=True, frozen=True)
class Player(PlayerInfo):
    admin: bool = field(compare=False)
    auth_token: UUID = field(compare=False)
    transfer_code: UUID | None = field(compare=False)

    def expected_win(self, other: "Player"):
        self_q = 10 ** (self.rating / 400)
        other_q = 10 ** (other.rating / 400)
        return self_q / (self_q + other_q)


@dataclass(eq=True, frozen=True)
class Board:
    id: UUID  # pylint: disable=C0103
    player: PlayerId = field(compare=False)
    room: "RoomId" = field(compare=False)


@dataclass(eq=True, frozen=True)
class BoardId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_board(cls, board: Board):
        return cls(board.id)


@dataclass(eq=True, frozen=True)
class RoomId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_room_info(cls, room_info: "RoomInfo"):
        return cls(room_info.id)


@dataclass(eq=True, frozen=True)
class RoomInfo(RoomId):
    players: list[PlayerInfo] = field(compare=False, default_factory=list)
    boards: dict[PlayerId, BoardId] = field(compare=False, default_factory=dict)


# API args below


@dataclass
class BearingPlayerAuth:
    auth_token: UUID

    @classmethod
    def from_player(cls, player: Player):
        return cls(player.auth_token)


@dataclass
class PlayerCreateArgs:
    name: str


@dataclass
class PrivateRoomCreateResults:
    room: RoomInfo
    join_code: str


@dataclass
class PrivateRoomJoinArgs(BearingPlayerAuth):
    join_code: str
