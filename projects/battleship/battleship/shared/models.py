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
    name: str = field(hash=False, compare=False)
    rating: int = field(hash=False, compare=False)

    @classmethod
    def from_player(cls, player: "Player"):
        return cls(player.id, player.name, player.rating)


@dataclass(eq=True, frozen=True)
class Player(PlayerInfo):
    admin: bool = field(hash=False, compare=False)
    auth_token: UUID = field(hash=False, compare=False)
    transfer_code: UUID | None = field(hash=False, compare=False)

    def expected_win(self, other: "Player"):
        self_q = 10 ** (self.rating / 400)
        other_q = 10 ** (other.rating / 400)
        return self_q / (self_q + other_q)

    def rating_changes(self, other: "Player", win: bool):
        return round(32 * ((1 if win else 0) - self.expected_win(other)))


@define
class Tile:
    hit: bool = a_field(default=False)


@define
class EmptyTile(Tile):
    pass


@dataclass(eq=True, frozen=True)
class ShipVariantId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_ship_variant(cls, ship_variant: "ShipVariantId"):
        return cls(ship_variant.id)


@dataclass(eq=True, frozen=True)
class ShipId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_ship(cls, ship: "Ship"):
        return cls(ship.id)


@dataclass(eq=True, frozen=True)
class Ship(ShipId):
    ship_variant: ShipVariantId = field(hash=False)
    tile_position: list[tuple[int, int]] = field(hash=False)
    orientation: int = field(hash=False)


@define
class ShipTile(Tile):
    ship: ShipId | None
    hit: bool = a_field(default=False)


@dataclass(eq=True, frozen=True)
class ObstacleVariantId:
    id: UUID  # pylint: disable=C0103


@define
class ObstacleTile(Tile):
    obstacle_variant: ObstacleVariantId
    hit: bool = a_field(default=False)


@dataclass(eq=True, frozen=True)
class MineVariantId:
    id: UUID  # pylint: disable=C0103


@define
class MineTile(Tile):
    mine_variant: MineVariantId
    hit: bool = a_field(default=False)


@dataclass(eq=True, frozen=True)
class BoardId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_board(cls, board: "Board"):
        return cls(board.id)


@dataclass(eq=True, frozen=True)
class Board(BoardId):
    id: UUID  # pylint: disable=C0103
    player: PlayerId = field(hash=False)
    room: "RoomId" = field(hash=False)
    grid: list[list[EmptyTile | ShipTile | ObstacleTile | MineTile]] = field(hash=False)
    ship: list[Ship] = field(hash=False)


@dataclass(eq=True, frozen=True)
class RoomId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_room_info(cls, room_info: "RoomInfo"):
        return cls(room_info.id)


@dataclass(eq=True, frozen=True)
class RoomInfo(RoomId):
    players: list[PlayerInfo] = field(hash=False, compare=False, default_factory=list)
    readies: list[PlayerId] = field(hash=False, compare=False, default_factory=list)


@dataclass(eq=True, frozen=True)
class ShotVariantId:
    id: UUID  # pylint: disable=C0103

    @classmethod
    def from_shot_variant(cls, ship_variant: "ShotVariantId"):
        return cls(ship_variant.id)


@dataclass(eq=True, frozen=True)
class Shot:
    shot_variant: ShotVariantId
    tile_position: tuple[int, int]
    orientation: int
    board: BoardId


@dataclass(eq=True, frozen=True)
class Reveal:
    loc: tuple[int, int]
    tile: EmptyTile | ShipTile | ObstacleTile | MineTile


@dataclass(eq=True, frozen=True)
class ShotResult:
    player: PlayerId
    board: BoardId
    reveal: list[Reveal] = field(hash=False, compare=False)
    reveal_ship: list[Ship] = field(hash=False, compare=False)


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
class RoomPlayerSubmitData:
    player: PlayerId
    board: BoardId


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
