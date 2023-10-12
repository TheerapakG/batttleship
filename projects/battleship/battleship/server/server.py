import asyncio
from dataclasses import dataclass, field
import os
import random
import ssl
import string
from uuid import UUID, uuid4

from dotenv import load_dotenv
from tsocket.server import Server, Route
from tsocket.shared import Empty, ResponseError, Session
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from . import db
from ..shared import models
from ..shared.logging import setup_logging


@dataclass
class BattleshipServer(Server):
    db_session_maker: async_sessionmaker[AsyncSession]
    public_rooms: dict[models.PublicRoomId, models.PublicRoom] = field(
        default_factory=dict
    )
    private_rooms: dict[models.PrivateRoomId, models.PrivateRoom] = field(
        default_factory=dict
    )
    private_room_codes: dict[str, models.PrivateRoom] = field(default_factory=dict)

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

    @Route.simple
    async def public_room_get(
        self, _session: Session, args: models.PublicRoomId
    ) -> models.PublicRoom:
        if room := self.public_rooms.get(args, None):
            return room
        raise ResponseError("not_found", b"")

    @Route.simple
    async def public_room_match(
        self, session: Session, args: models.BearingPlayerAuth
    ) -> models.PublicRoomId:
        player = await self.player_get(session, args)
        if room_tup := self.public_rooms.popitem():
            room_id, room = room_tup
            room.players.append(player)
            self.public_rooms[room_id] = room
            return room_id
        else:
            room = models.PublicRoom(uuid4())
            room.players.append(player)
            room_id = models.PublicRoomId.from_room(room)
            self.public_rooms[room_id] = room
            return room_id

    @Route.simple
    async def private_room_create(
        self, session: Session, args: models.BearingPlayerAuth
    ) -> models.PrivateRoom:
        player = await self.player_get(session, args)
        room = models.PrivateRoom(
            uuid4(),
            join_code="".join(random.choice(string.ascii_lowercase) for _ in range(6)),
        )
        room.players.append(player)
        room_id = models.PrivateRoomId.from_room(room)
        self.private_rooms[room_id] = room
        self.private_room_codes[room.join_code] = room
        return room_id

    @Route.simple
    async def private_room_get(
        self, _session: Session, args: models.PrivateRoomId
    ) -> models.PrivateRoom:
        if room := self.private_rooms.get(args, None):
            return room
        raise ResponseError("not_found", b"")

    @Route.simple
    async def private_room_join(
        self, session: Session, args: str
    ) -> models.PrivateRoom:
        player = await self.player_get(session, args)
        if room := self.private_room_codes.get(args, None):
            room.players.append(player)
            return room
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
