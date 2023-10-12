from dataclasses import dataclass, field
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


@dataclass(eq=True, frozen=True)
class BoardId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_board(cls, board: Board):
        return cls(board.id)


@dataclass
class Room:
    id: UUID  # pylint: disable=C0103
    players: list[PlayerId] = field(init=False, default_factory=list)
    boards: dict[PlayerId, BoardId] = field(init=False, default_factory=dict)


@dataclass
class PublicRoom(Room):
    pass


@dataclass(eq=True, frozen=True)
class PublicRoomId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_room(cls, public_room: PublicRoom):
        return cls(public_room.id)


@dataclass
class PrivateRoom(Room):
    join_code: str


@dataclass(eq=True, frozen=True)
class PrivateRoomId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_room(cls, private_room: PrivateRoom):
        return cls(private_room.id)


@dataclass(eq=True)
class BearingPlayerAuth:
    auth_token: UUID


# API args below


@dataclass
class PlayerCreateArgs:
    name: str


@dataclass
class PrivateRoomJoinArgs(BearingPlayerAuth):
    join_code: str
