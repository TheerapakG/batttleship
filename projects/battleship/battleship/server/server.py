import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
import os
import random
import ssl
import string
from typing import Any, TypeVar
from uuid import uuid4

from dotenv import load_dotenv
from tsocket.server import Server, Route, emit
from tsocket.shared import Empty, ResponseError, Session
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from . import db
from . import models as server_models
from ..shared import models
from ..shared.logging import setup_logging


BearingPlayerAuthT = TypeVar("BearingPlayerAuthT", bound=models.BearingPlayerAuth)


@dataclass
class BattleshipServer(Server):
    db_session_maker: async_sessionmaker[AsyncSession]
    known_player_session: dict[models.PlayerId, Session] = field(default_factory=dict)
    known_player_session_rev: dict[Session, models.PlayerId] = field(
        default_factory=dict
    )
    rooms: dict[models.RoomId, server_models.Room] = field(default_factory=dict)
    match_rooms: set[models.RoomId] = field(default_factory=set)
    private_room_codes: dict[str, models.RoomId] = field(default_factory=dict)
    private_room_codes_rev: dict[models.RoomId, str] = field(default_factory=dict)

    async def _player_get(self, args: models.BearingPlayerAuth) -> models.Player:
        async with self.db_session_maker() as db_session:
            stmt = (
                select(db.Player)
                .where(db.Player.auth_token == args.auth_token)
                .limit(1)
            )
            result = await db_session.execute(stmt)

            if db_player := result.scalars().one_or_none():
                return db_player.to_shared()
            else:
                raise ResponseError("not_found", b"")

    async def remove_session(self, session: Session):
        player_id = self.known_player_session_rev[session]
        del self.known_player_session_rev[session]
        del self.known_player_session[player_id]

    @staticmethod
    def ensure_session_player(
        func: Callable[["BattleshipServer", Session, BearingPlayerAuthT], Any]
    ):
        @wraps(func)
        async def checker(
            self: "BattleshipServer", session: Session, args: BearingPlayerAuthT
        ):
            player = await self._player_get(args)
            player_id = models.PlayerId.from_player(player)
            if (
                known_session := self.known_player_session.get(player_id, None)
            ) is not None:
                if known_session != session:
                    raise ResponseError("player_in_other_session", b"")
            else:
                self.known_player_session[player_id] = session
                self.known_player_session_rev[session] = player_id
                self.on_session_leave(session, self.remove_session)
            return await func(self, session, args)

        return checker

    @Route.simple
    async def ping(self, _session: Session, _: Empty) -> Empty:
        return Empty()

    @Route.simple
    async def online(self, _session: Session, _: Empty) -> int:
        return len(self.sessions)

    @Route.simple
    async def player_create(
        self, _session: Session, args: models.PlayerCreateArgs
    ) -> models.Player:
        async with self.db_session_maker() as db_session:
            stmt = insert(db.Player).values(name=args.name).returning(db.Player)
            result = await db_session.execute(stmt)
            await db_session.commit()

            if db_player := result.scalars().one_or_none():
                return db_player.to_shared()
            else:
                raise ResponseError("not_create", b"")

    @Route.simple
    @ensure_session_player
    async def player_get(
        self, _session: Session, args: models.BearingPlayerAuth
    ) -> models.Player:
        return await self._player_get(args)

    @Route.simple
    async def player_info_get(
        self, _session: Session, args: models.PlayerId
    ) -> models.PlayerInfo:
        async with self.db_session_maker() as db_session:
            stmt = select(db.Player).where(db.Player.id == args.id).limit(1)
            result = await db_session.execute(stmt)

            if db_player := result.scalars().one_or_none():
                return models.PlayerInfo.from_player(db_player.to_shared())
            else:
                raise ResponseError("not_found", b"")

    @Route.simple
    @ensure_session_player
    async def player_delete(
        self, _session: Session, args: models.BearingPlayerAuth
    ) -> models.Player:
        async with self.db_session_maker() as db_session:
            stmt = (
                delete(db.Player)
                .where(db.Player.auth_token == args.auth_token)
                .returning(db.Player)
            )
            result = await db_session.execute(stmt)
            await db_session.commit()

            if db_player := result.scalars().one_or_none():
                return db_player.to_shared()
            else:
                raise ResponseError("not_found", b"")

    @emit
    async def on_room_join(self, _session: Session, args: models.PlayerInfo):
        raise NotImplementedError()

    @emit
    async def on_room_leave(self, _session: Session, args: models.PlayerInfo):
        raise NotImplementedError()

    @emit
    async def on_room_player_ready(self, _session: Session, args: models.PlayerId):
        raise NotImplementedError()

    @emit
    async def on_room_ready(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @emit
    async def on_room_player_submit(self, _session: Session, args: models.PlayerId):
        raise NotImplementedError()

    @emit
    async def on_room_submit(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @emit
    async def on_board_display(self, _session: Session, args: models.BoardId):
        raise NotImplementedError()

    @emit
    async def on_turn_start(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @emit
    async def on_turn_end(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @Route.simple
    @ensure_session_player
    async def room_match(
        self, _session: Session, args: models.BearingPlayerAuth
    ) -> models.RoomInfo:
        player = await self._player_get(args)
        player_id = models.PlayerId.from_player(player)
        try:
            room_id = self.match_rooms.pop()
            room = self.rooms[room_id]
        except KeyError:
            room = server_models.Room(uuid4(), self, start_private=False)
            room_id = room.to_room_id()
            self.rooms[room_id] = room
        await room.add_player(player_id)
        self.match_rooms.add(room_id)
        return room.to_room_info()

    @Route.simple
    async def room_leave(self, session: Session, args: models.RoomId) -> Empty:
        if (room := self.rooms.get(args, None)) and (
            (player_id := self.known_player_session_rev[session]) in room
        ):
            await room.remove_player(player_id)
            return Empty()
        raise ResponseError("not_found", b"")

    @Route.simple
    async def room_ready(self, session: Session, args: models.RoomId) -> Empty:
        if (room := self.rooms.get(args, None)) and (
            (player_id := self.known_player_session_rev[session]) in room
        ):
            await room.add_ready(player_id)
            return Empty()
        raise ResponseError("not_found", b"")

    @Route.simple
    @ensure_session_player
    async def private_room_create(
        self, _session: Session, args: models.BearingPlayerAuth
    ) -> models.PrivateRoomCreateResults:
        player = await self._player_get(args)
        player_id = models.PlayerId.from_player(player)
        room = server_models.Room(uuid4(), self, start_private=True)
        room_id = room.to_room_id()
        self.rooms[room_id] = room
        join_code = "".join(random.choice(string.ascii_lowercase) for _ in range(6))
        self.private_room_codes[join_code] = room_id
        await room.add_player(player_id)
        return models.PrivateRoomCreateResults(room.to_room_info(), join_code)

    @Route.simple
    @ensure_session_player
    async def private_room_join(
        self, _session: Session, args: models.PrivateRoomJoinArgs
    ) -> models.RoomInfo:
        player = await self._player_get(args)
        player_id = models.PlayerId.from_player(player)
        if room_id := self.private_room_codes.get(args.join_code, None):
            room = self.rooms[room_id]
            await room.add_player(player_id)
            return room.to_room_info()
        raise ResponseError("not_found", b"")

    @Route.simple
    async def private_room_unlock(self, session: Session, args: models.RoomId) -> Empty:
        if (room := self.rooms.get(args, None)) and (
            self.known_player_session_rev[session] in room
        ):
            self.match_rooms.add(args)
            return Empty()
        raise ResponseError("not_found", b"")

    @Route.simple
    async def board_submit(self, session: Session, args: models.Board) -> Empty:
        if (
            (room := self.rooms.get(args.room, None))
            and ((player_id := self.known_player_session_rev[session]) == args.player)
            and player_id in room
        ):
            await room.add_board_submit(args)
            return Empty()
        raise ResponseError("not_found", b"")

    @Route.simple
    async def display_board(
        self, session: Session, args: models.DisplayBoardArgs
    ) -> models.ShotResult:
        if (room := self.rooms.get(args.room, None)) and (
            (player_id := self.known_player_session_rev[session]) in room
        ):
            return await room.display_board(player_id, args.board)
        raise ResponseError("not_found", b"")

    @Route.simple
    async def shot_submit(
        self, session: Session, args: models.ShotSubmitArgs
    ) -> models.ShotResult:
        if (room := self.rooms.get(args.room, None)) and (
            (player_id := self.known_player_session_rev[session]) in room
        ):
            return await room.do_shot_submit(player_id, args.shot)
        raise ResponseError("not_found", b"")


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(os.environ["SSL_CERT"], os.environ["SSL_KEY"])

    async def amain():
        engine = await db.create_dev_engine()
        server = BattleshipServer(async_sessionmaker(engine, expire_on_commit=False))
        await server.run(
            "0.0.0.0",
            60000,
            ssl=ssl_context,
        )

    asyncio.run(amain())
