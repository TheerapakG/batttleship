from attrs import evolve
import asyncio
import contextlib
from dataclasses import dataclass, field, replace
from enum import Enum, auto
import random
from typing import TYPE_CHECKING
from uuid import UUID

from tsocket.shared import Session, Empty

from ..shared import models, shot_type
from ..shared.utils import add, mat_mul_vec

if TYPE_CHECKING:
    from .server import BattleshipServer


class RoomPhase(Enum):
    LOBBY = auto()
    SHIPSETUP = auto()
    PLAYING = auto()


@dataclass
class Room:
    id: UUID  # pylint: disable=C0103
    server: "BattleshipServer"
    start_private: bool
    lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    phase: RoomPhase = field(init=False, default=RoomPhase.LOBBY)
    players: dict[models.PlayerId, models.PlayerInfo] = field(
        init=False, default_factory=dict
    )
    alive_players: list[models.PlayerInfo] = field(init=False, default_factory=list)
    lost_players: list[models.PlayerInfo] = field(init=False, default_factory=list)
    last_round_placement: list[models.PlayerInfo] = field(
        init=False, default_factory=list
    )
    readies: set[models.PlayerId] = field(init=False, default_factory=set)
    boards: dict[models.BoardId, models.Board] = field(init=False, default_factory=dict)
    next_player_task: asyncio.Task | None = field(init=False, default=None)

    def __contains__(self, player: models.PlayerId):
        return player in self.players.keys()

    @property
    def should_start(self):
        return len(self.players) > 1 and len(self.readies) == len(self.players)

    async def remove_session(self, session: Session):
        await self.remove_player(self.server.known_player_session_rev[session])

    async def add_player(self, player_id: models.PlayerId):
        async with self.lock:
            session = self.server.known_player_session[player_id]
            self.server.on_session_leave(session, self.remove_session)
            player_info = await self.server.player_info_get(session, player_id)
            async with asyncio.TaskGroup() as tg:
                for other_player_info in self.players.values():
                    tg.create_task(
                        self.server.on_room_join(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(other_player_info)
                            ],
                            player_info,
                        )
                    )
            self.players[player_id] = player_info

    async def do_cancel_next_player_task(self):
        if (n_task := self.next_player_task) is not None:
            n_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await n_task
        self.next_player_task = None

    async def do_room_reset(self, hard=False):
        self.phase = RoomPhase.SHIPSETUP
        if not self.lost_players or hard:
            self.alive_players = [p for p in self.players.values()]
            random.shuffle(self.alive_players)
            self.lost_players = []
        else:
            self.alive_players = [
                p_info
                for p in self.lost_players
                if (p_info := self.players.get(models.PlayerId.from_player_info(p)))
                is not None
            ]
            self.lost_players = []
        self.boards = dict()
        await self.do_cancel_next_player_task()
        if hard:
            async with asyncio.TaskGroup() as tg:
                for player_info in self.players.values():
                    tg.create_task(
                        self.server.on_game_reset(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(player_info)
                            ],
                            Empty(),
                        )
                    )

    async def _player_update_ranking(self, player_id: models.PlayerId, changes: int):
        new_info = models.PlayerInfo.from_player(
            await self.server._player_update_ranking(player_id, changes)
        )
        if player_id in self.players:
            self.players[player_id] = new_info

    async def do_player_lost(self, player_id: models.PlayerId, remove: bool = False):
        player = self.players[player_id]
        if remove:
            del self.players[player_id]
        if player in self.alive_players:
            self.alive_players.remove(player)
            self.lost_players.append(player)
        async with asyncio.TaskGroup() as tg:
            for player_info in self.players.values():
                tg.create_task(
                    self.server.on_game_player_lost(
                        self.server.known_player_session[
                            models.PlayerId.from_player_info(player_info)
                        ],
                        player,
                    )
                )
        if len(self.alive_players) == 1:
            self.lost_players.append(self.alive_players.pop())
            changes = {}
            if not self.start_private:
                async with asyncio.TaskGroup() as tg:
                    for i, player in enumerate(self.lost_players):
                        change = sum(
                            [
                                player.rating_changes(p, win=True)
                                for p in self.lost_players[:i]
                            ]
                        ) + sum(
                            [
                                player.rating_changes(p, win=False)
                                for p in self.lost_players[i + 1 :]
                            ]
                        )
                        changes[models.PlayerId.from_player_info(player)] = change
                        tg.create_task(
                            self._player_update_ranking(
                                models.PlayerId.from_player_info(player), change
                            )
                        )
            async with asyncio.TaskGroup() as tg:
                for player_id, player_info in self.players.items():
                    tg.create_task(
                        self.server.on_game_end(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(player_info)
                            ],
                            models.GameEndData(
                                models.PlayerId.from_player_info(self.lost_players[-1]),
                                changes.get(player_id, 0),
                                player_info,
                            ),
                        )
                    )
            await self.do_room_reset()

    async def remove_player(self, player_id: models.PlayerId):
        async with self.lock:
            session = self.server.known_player_session[player_id]
            player_info = await self.server.player_info_get(session, player_id)
            should_delete = False
            match self.phase:
                case RoomPhase.LOBBY:
                    with contextlib.suppress(KeyError):
                        self.readies.remove(player_id)
                    del self.players[models.PlayerId.from_player_info(player_info)]
                    should_delete = len(self.players) < 1
                case RoomPhase.SHIPSETUP | RoomPhase.PLAYING:
                    await self.do_player_lost(player_id, remove=True)
                    should_delete = len(self.players) < 2

            self.server.off_session_leave(session, self.remove_session)

            if should_delete:
                room_id = self.to_room_id()
                with contextlib.suppress(KeyError):
                    del self.server.rooms[room_id]
                with contextlib.suppress(KeyError):
                    self.server.match_rooms.remove(room_id)
                with contextlib.suppress(KeyError):
                    join_code = self.server.private_room_codes_rev[room_id]
                    del self.server.private_room_codes[join_code]
                    del self.server.private_room_codes_rev[room_id]

            async with asyncio.TaskGroup() as tg:
                for other_player_info in self.players.values():
                    tg.create_task(
                        self.server.on_room_leave(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(other_player_info)
                            ],
                            player_info,
                        )
                    )
                    if should_delete:
                        tg.create_task(
                            self.server.on_room_delete(
                                self.server.known_player_session[
                                    models.PlayerId.from_player_info(other_player_info)
                                ],
                                Empty(),
                            )
                        )

    async def add_ready(self, player_id: models.PlayerId):
        async with self.lock:
            self.readies.add(player_id)
            async with asyncio.TaskGroup() as tg:
                for player_info in self.players.values():
                    tg.create_task(
                        self.server.on_room_player_ready(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(player_info)
                            ],
                            player_id,
                        )
                    )
            if self.should_start:
                async with asyncio.TaskGroup() as tg:
                    room_id = self.to_room_id()
                    with contextlib.suppress(KeyError):
                        self.server.match_rooms.remove(room_id)
                    with contextlib.suppress(KeyError):
                        join_code = self.server.private_room_codes_rev[room_id]
                        del self.server.private_room_codes[join_code]
                        del self.server.private_room_codes_rev[room_id]
                    for player_info in self.players.values():
                        tg.create_task(
                            self.server.on_room_ready(
                                self.server.known_player_session[
                                    models.PlayerId.from_player_info(player_info)
                                ],
                                Empty(),
                            )
                        )
                await self.do_room_reset()

    async def to_next_player_timeout(self):
        await asyncio.sleep(10)
        await self.to_next_player(is_task=True)

    async def to_next_player(self, end_turn=True, is_task=False):
        async with self.lock:
            if not is_task and self.next_player_task is not None:
                self.next_player_task.cancel()
            if end_turn:
                async with asyncio.TaskGroup() as tg:
                    for player_info in self.players.values():
                        tg.create_task(
                            self.server.on_game_turn_end(
                                self.server.known_player_session[
                                    models.PlayerId.from_player_info(player_info)
                                ],
                                self.alive_players[0],
                            )
                        )

            await asyncio.sleep(5)

            player = self.alive_players.pop()
            self.alive_players.insert(0, player)
            async with asyncio.TaskGroup() as tg:
                for player_info in self.players.values():
                    tg.create_task(
                        self.server.on_game_turn_start(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(player_info)
                            ],
                            player,
                        )
                    )
            self.next_player_task = asyncio.create_task(self.to_next_player_timeout())

    async def add_board_submit(self, board: models.Board):
        board_id = models.BoardId.from_board(board)
        async with self.lock:
            self.boards[board_id] = board
            # TODO: board check??
            async with asyncio.TaskGroup() as tg:
                for player_info in self.players.values():
                    tg.create_task(
                        self.server.on_room_player_submit(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(player_info)
                            ],
                            models.RoomPlayerSubmitData(board.player, board_id),
                        )
                    )
                if len(self.boards) == len(self.players):
                    self.phase = RoomPhase.PLAYING
                    for player_info in self.players.values():
                        tg.create_task(
                            self.server.on_room_submit(
                                self.server.known_player_session[
                                    models.PlayerId.from_player_info(player_info)
                                ],
                                Empty(),
                            )
                        )
                    self.next_player_task = asyncio.create_task(
                        self.to_next_player(end_turn=False, is_task=True)
                    )

    async def display_board(self, player: models.PlayerId, board: models.BoardId):
        async with self.lock:
            if player == models.PlayerId.from_player_info(self.alive_players[0]):
                async with asyncio.TaskGroup() as tg:
                    for player_info in self.players.values():
                        tg.create_task(
                            self.server.on_game_board_display(
                                self.server.known_player_session[
                                    models.PlayerId.from_player_info(player_info)
                                ],
                                board,
                            )
                        )
            else:
                # TODO:
                raise Exception()

    async def do_shot_submit(self, player: models.PlayerId, shot: models.Shot):
        if player == models.PlayerId.from_player_info(self.alive_players[0]):
            shot_variant = shot_type.SHOT_VARIANTS[shot.shot_variant.id]
            shot_locations = [
                add(
                    shot.tile_position,
                    mat_mul_vec(
                        shot_type.ORIENTATIONS[shot.orientation],
                        offset,
                    ),
                )
                for offset in shot_variant.placement_offsets.keys()
            ]
            pick_locations = random.sample(shot_locations, shot_variant.number_of_shot)
            board = self.boards[shot.board]
            location_result = [
                models.Reveal((col, row), board.grid[col][row])
                for col, row in pick_locations
                if not board.grid[col][row].hit
            ]
            if shot_variant.reveal:
                reveal_ship_tile = [
                    r.tile
                    for r in location_result
                    if isinstance(r.tile, models.ShipTile)
                ]
                reveal_ship_id = set(st.ship for st in reveal_ship_tile)
                reveal_ship = [
                    s
                    for s in board.ship
                    if models.ShipId.from_ship(s) in reveal_ship_id
                ]
                res = models.ShotResult(
                    player,
                    models.BoardId.from_board(board),
                    location_result,
                    reveal_ship,
                )
            else:
                for r in location_result:
                    r.tile.hit = True
                res = models.ShotResult(
                    player,
                    models.BoardId.from_board(board),
                    [
                        (
                            replace(r, tile=evolve(r.tile, ship=None))
                            if isinstance(r.tile, models.ShipTile)
                            else r
                        )
                        for r in location_result
                    ],
                    [],
                )
                other_res = models.ShotResult(
                    player,
                    models.BoardId.from_board(board),
                    [
                        replace(r, tile=evolve(r.tile, ship=None))
                        for r in location_result
                        if isinstance(r.tile, models.ShipTile)
                    ],
                    [],
                )

                async with asyncio.TaskGroup() as tg:
                    for player_info in self.players.values():
                        tg.create_task(
                            self.server.on_game_board_shot(
                                self.server.known_player_session[
                                    models.PlayerId.from_player_info(player_info)
                                ],
                                other_res,
                            )
                        )
                if all(
                    t.hit or not isinstance(t, models.ShipTile)
                    for c in board.grid
                    for t in c
                ):
                    await self.do_player_lost(board.player)
            asyncio.create_task(self.to_next_player())
            return res

        else:
            # TODO
            raise Exception()

    async def do_emote_display(
        self, player: models.PlayerId, emote: models.EmoteVariantId
    ):
        async with asyncio.TaskGroup() as tg:
            for player_info in self.players.values():
                tg.create_task(
                    self.server.on_emote_display(
                        self.server.known_player_session[
                            models.PlayerId.from_player_info(player_info)
                        ],
                        models.EmoteDisplayData(player, emote),
                    )
                )

    def to_room_id(self):
        return models.RoomId(self.id)

    def to_room_info(self):
        return models.RoomInfo(self.id, [*self.players.values()], [*self.readies])
