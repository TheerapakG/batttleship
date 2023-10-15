import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from tsocket.shared import Session

from ..shared import models

if TYPE_CHECKING:
    from .server import BattleshipServer


@dataclass
class Room:
    id: UUID  # pylint: disable=C0103
    server: "BattleshipServer"
    lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    players: set[models.PlayerId] = field(init=False, default_factory=set)
    boards: dict[models.PlayerId, models.BoardId] = field(
        init=False, default_factory=dict
    )

    async def remove_session(self, session: Session):
        await self.remove_player(self.server.known_player_session_rev[session])

    async def add_player(self, player_id: models.PlayerId):
        async with self.lock:
            self.server.on_session_leave(
                self.server.known_player_session[player_id], self.remove_session
            )
            async with asyncio.TaskGroup() as tg:
                for other_player_id in self.players:
                    tg.create_task(
                        self.server.on_room_join(
                            self.server.known_player_session[other_player_id], player_id
                        )
                    )
            self.players.add(player_id)

    async def remove_player(self, player_id: models.PlayerId):
        async with self.lock:
            self.server.off_session_leave(
                self.server.known_player_session[player_id], self.remove_session
            )
            self.players.remove(player_id)
            async with asyncio.TaskGroup() as tg:
                for other_player_id in self.players:
                    tg.create_task(
                        self.server.on_room_leave(
                            self.server.known_player_session[other_player_id], player_id
                        )
                    )
            if not self.players:
                room_id = self.to_room_id()
                del self.server.rooms[room_id]
                with contextlib.suppress(KeyError):
                    self.server.match_rooms.remove(room_id)
                with contextlib.suppress(KeyError):
                    join_code = self.server.private_room_codes_rev[room_id]
                    del self.server.private_room_codes[join_code]
                    del self.server.private_room_codes_rev[room_id]

    def to_room_id(self):
        return models.RoomId(self.id)

    def to_room_info(self):
        return models.RoomInfo(self.id, [*self.players], self.boards)
