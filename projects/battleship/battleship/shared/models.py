from attrs import define, field as a_field
from dataclasses import dataclass, field
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


@define
class Tile:
    hit: bool = a_field(False)


@define
class EmptyTile(Tile):
    pass


@dataclass
class ShipVariantId:
    id: UUID  # pylint: disable=C0103


@dataclass(eq=True, frozen=True)
class ShipId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_ship(cls, ship: "Ship"):
        return cls(ship.id)


@dataclass(eq=True, frozen=True)
class Ship(ShipId):
    ship_variant: ShipVariantId
    tile_position: list[tuple[int, int]]
    orientation: int


@define
class ShipTile(Tile):
    ship: ShipId


@dataclass(eq=True, frozen=True)
class ObstacleVariantId:
    id: UUID  # pylint: disable=C0103


@define
class ObstacleTile(Tile):
    obstacle_variant: ObstacleVariantId


@dataclass(eq=True, frozen=True)
class MineVariantId:
    id: UUID  # pylint: disable=C0103


@define
class MineTile(Tile):
    mine_variant: MineVariantId


@dataclass(eq=True, frozen=True)
class BoardId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_board(cls, board: "Board"):
        return cls(board.id)


@dataclass(eq=True, frozen=True)
class Board(BoardId):
    id: UUID  # pylint: disable=C0103
    player: PlayerId = field(compare=False)
    room: "RoomId" = field(compare=False)
    grid: list[list[EmptyTile | ShipTile | ObstacleTile | MineTile]] = field(
        compare=False
    )
    ship: list[Ship] = field(compare=False)


@dataclass(eq=True, frozen=True)
class RoomId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_room_info(cls, room_info: "RoomInfo"):
        return cls(room_info.id)


@dataclass(eq=True, frozen=True)
class RoomInfo(RoomId):
    players: list[PlayerInfo] = field(compare=False, default_factory=list)
    readies: list[PlayerId] = field(compare=False, default_factory=list)
    boards: dict[PlayerId, BoardId] = field(compare=False, default_factory=dict)


@dataclass
class ShotTypeVariantId:
    id: UUID  # pylint: disable=C0103


@dataclass(eq=True, frozen=True)
class Shot:
    shot_variant: ShotTypeVariantId
    tile_position: tuple[int, int]
    orientation: int
    board: BoardId


@dataclass(eq=True, frozen=True)
class ShotResult:
    reveal: dict[
        tuple[int, int], EmptyTile | ShipTile | ObstacleTile | MineTile
    ] = field(compare=False)
    reveal_ship: list[Ship] = field(compare=False)
    hit: dict[tuple[int, int], EmptyTile | ShipTile | ObstacleTile | MineTile] = field(
        compare=False
    )


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


@dataclass
class DisplayBoardArgs:
    room: RoomId
    board: BoardId


@dataclass
class ShotSubmitArgs:
    room: RoomId
    shot: Shot
