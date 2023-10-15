import asyncio
import contextlib
from dataclasses import dataclass, field
import os
import random
import ssl
import string
from uuid import UUID, uuid4

from dotenv import load_dotenv
from tsocket.server import Server, Route, emit
from tsocket.shared import Empty, ResponseError, Session
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from . import db
from ..shared import models
from ..shared.logging import setup_logging


@dataclass
class RoomServer(models.Room):
    server: "BattleshipServer"
    lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    players: dict[UUID, models.PlayerId] = field(init=False, default_factory=dict)
    boards: dict[models.PlayerId, models.BoardId] = field(
        init=False, default_factory=dict
    )

    async def add_player(
        self,
        session: Session,
        player_id: models.PlayerId,
    ):
        async with self.lock:
            self.server.on_session_leave(session, self.remove_player)
            async with asyncio.TaskGroup() as tg:
                for other_session_id in self.players.keys():
                    tg.create_task(
                        self.server.on_room_join(
                            self.server.sessions[other_session_id], player_id
                        )
                    )
            self.players[session.id] = player_id

    async def remove_player(self, session: Session):
        async with self.lock:
            self.server.off_session_leave(session, self.remove_player)
            player_id = self.players[session.id]
            del self.players[session.id]
            async with asyncio.TaskGroup() as tg:
                for other_session_id in self.players.keys():
                    tg.create_task(
                        self.server.on_room_leave(
                            self.server.sessions[other_session_id], player_id
                        )
                    )
            if not self.players:
                room_id = models.RoomId.from_room(self)
                del self.server.rooms[room_id]
                with contextlib.suppress(KeyError):
                    self.server.match_rooms.remove(room_id)
                with contextlib.suppress(KeyError):
                    join_code = self.server.private_room_codes_rev[room_id]
                    del self.server.private_room_codes[join_code]
                    del self.server.private_room_codes_rev[room_id]


@dataclass
class BattleshipServer(Server):
    db_session_maker: async_sessionmaker[AsyncSession]
    rooms: dict[models.RoomId, RoomServer] = field(default_factory=dict)
    match_rooms: set[models.RoomId] = field(default_factory=set)
    private_room_codes: dict[str, models.RoomId] = field(default_factory=dict)
    private_room_codes_rev: dict[models.RoomId, str] = field(default_factory=dict)

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
    async def player_get(
        self, _session: Session, args: models.BearingPlayerAuth
    ) -> models.Player:
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
    async def on_room_join(self, _session: Session, args: models.PlayerId):
        raise NotImplementedError()

    @emit
    async def on_room_leave(self, _session: Session, args: models.PlayerId):
        raise NotImplementedError()

    @Route.simple
    async def room_get(self, _session: Session, args: models.RoomId) -> models.RoomInfo:
        if room := self.rooms.get(args, None):
            return models.RoomInfo.from_room(room)
        raise ResponseError("not_found", b"")

    async def session_leave_room(self, session: Session):
        raise NotImplementedError()

    @Route.simple
    async def room_match(
        self, session: Session, args: models.BearingPlayerAuth
    ) -> models.RoomId:
        player = await self.player_get(session, args)
        player_id = models.PlayerId.from_player(player)
        try:
            room_id = self.match_rooms.pop()
            room = self.rooms[room_id]
        except KeyError:
            room = RoomServer(uuid4(), self)
            room_id = models.RoomId.from_room(room)
            self.rooms[room_id] = room
        await room.add_player(session, player_id)
        self.match_rooms.add(room_id)
        return room_id

    @Route.simple
    async def room_leave(self, session: Session, args: models.RoomId) -> Empty:
        if (room := self.rooms.get(args, None)) and (session.id in room.players.keys()):
            await room.remove_player(session)
            return Empty()
        raise ResponseError("not_found", b"")

    @Route.simple
    async def private_room_create(
        self, session: Session, args: models.BearingPlayerAuth
    ) -> models.PrivateRoomCreateResults:
        player = await self.player_get(session, args)
        player_id = models.PlayerId.from_player(player)
        room = RoomServer(uuid4(), self)
        room_id = models.RoomId.from_room(room)
        self.rooms[room_id] = room
        join_code = "".join(random.choice(string.ascii_lowercase) for _ in range(6))
        self.private_room_codes[join_code] = room_id
        await room.add_player(session, player_id)
        return models.PrivateRoomCreateResults(room_id, join_code)

    @Route.simple
    async def private_room_join(
        self, session: Session, args: models.PrivateRoomJoinArgs
    ) -> models.RoomId:
        player = await self.player_get(session, args)
        player_id = models.PlayerId.from_player(player)
        if room_id := self.private_room_codes.get(args.join_code, None):
            room = self.rooms[room_id]
            await room.add_player(session, player_id)
            return room_id
        raise ResponseError("not_found", b"")

    @Route.simple
    async def private_room_unlock(self, session: Session, args: models.RoomId) -> Empty:
        if (room := self.rooms.get(args, None)) and (session.id in room.players.keys()):
            self.match_rooms.add(args)
            return Empty()
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
