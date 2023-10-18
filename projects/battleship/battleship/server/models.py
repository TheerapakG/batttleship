import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from tsocket.shared import Session, Empty

from ..shared import models

if TYPE_CHECKING:
    from .server import BattleshipServer


@dataclass
class Room:
    id: UUID  # pylint: disable=C0103
    server: "BattleshipServer"
    lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    players: set[models.PlayerInfo] = field(init=False, default_factory=set)
    readies: set[models.PlayerId] = field(init=False, default_factory=set)
    boards: dict[models.PlayerId, models.BoardId] = field(
        init=False, default_factory=dict
    )

    def __contains__(self, player: models.PlayerId):
        return player in {models.PlayerId.from_player_info(p) for p in self.players}

    async def remove_session(self, session: Session):
        await self.remove_player(self.server.known_player_session_rev[session])

    async def add_player(self, player_id: models.PlayerId):
        async with self.lock:
            session = self.server.known_player_session[player_id]
            self.server.on_session_leave(session, self.remove_session)
            player_info = await self.server.player_info_get(session, player_id)
            async with asyncio.TaskGroup() as tg:
                for other_player_info in self.players:
                    tg.create_task(
                        self.server.on_room_join(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(other_player_info)
                            ],
                            player_info,
                        )
                    )
            self.players.add(player_info)

    async def remove_player(self, player_id: models.PlayerId):
        async with self.lock:
            session = self.server.known_player_session[player_id]
            self.server.off_session_leave(session, self.remove_session)
            if len(self.players) < 2 or len(self.readies) == len(self.players):
                room_id = self.to_room_id()
                del self.server.rooms[room_id]
                with contextlib.suppress(KeyError):
                    self.server.match_rooms.remove(room_id)
                with contextlib.suppress(KeyError):
                    join_code = self.server.private_room_codes_rev[room_id]
                    del self.server.private_room_codes[join_code]
                    del self.server.private_room_codes_rev[room_id]
            player_info = await self.server.player_info_get(session, player_id)
            self.players.remove(player_info)
            with contextlib.suppress(KeyError):
                self.readies.remove(player_id)
            async with asyncio.TaskGroup() as tg:
                for other_player_info in self.players:
                    tg.create_task(
                        self.server.on_room_leave(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(other_player_info)
                            ],
                            player_info,
                        )
                    )

    async def add_ready(self, player_id: models.PlayerId):
        async with self.lock:
            self.readies.add(player_id)
            async with asyncio.TaskGroup() as tg:
                for player_info in self.players:
                    tg.create_task(
                        self.server.on_room_player_ready(
                            self.server.known_player_session[
                                models.PlayerId.from_player_info(player_info)
                            ],
                            player_id,
                        )
                    )
                if len(self.players) > 1 and len(self.readies) == len(self.players):
                    for player_info in self.players:
                        tg.create_task(
                            self.server.on_room_ready(
                                self.server.known_player_session[
                                    models.PlayerId.from_player_info(player_info)
                                ],
                                Empty(),
                            )
                        )

    def to_room_id(self):
        return models.RoomId(self.id)

    def to_room_info(self):
        return models.RoomInfo(self.id, [*self.players], [*self.readies], self.boards)
