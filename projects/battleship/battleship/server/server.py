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
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from . import db
from . import models as server_models
from ..shared import models, emote_type
from ..shared.ship_type import NORMAL_NAVY_SHIP_VARIANT
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
                return await db_player.to_shared(db_session)
            else:
                raise ResponseError("not_found", b"")

    async def _player_update(
        self, player: models.PlayerId, rating_changes: int, coin_changes: int
    ) -> models.Player:
        async with self.db_session_maker() as db_session:
            stmt = (
                update(db.Player)
                .where(db.Player.id == player.id)
                .values(
                    rating=db.Player.rating + rating_changes,
                    coins=db.Player.coins + coin_changes,
                )
                .returning(db.Player)
            )
            result = await db_session.execute(stmt)
            await db_session.commit()

            if db_player := result.scalars().one_or_none():
                return await db_player.to_shared(db_session)
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
                if known_session.id != session.id:
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
            db_player = db.Player(name=args.name)
            db_player.ships = [
                db.Ship(variant_id=NORMAL_NAVY_SHIP_VARIANT.id) for _ in range(4)
            ]

            db_session.add(db_player)
            await db_session.commit()
            return await db_player.to_shared(db_session)

    @Route.simple
    @ensure_session_player
    async def player_avatar_set(
        self, _session: Session, args: models.PlayerAvatarSetArgs
    ) -> models.Player:
        async with self.db_session_maker() as db_session:
            stmt = (
                update(db.Player)
                .where(db.Player.auth_token == args.auth_token)
                .values(
                    avatar=args.avatar.id,
                )
                .returning(db.Player)
            )
            result = await db_session.execute(stmt)
            await db_session.commit()

            if db_player := result.scalars().one_or_none():
                return await db_player.to_shared(db_session)
            else:
                raise ResponseError("not_found", b"")

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
                return models.PlayerInfo.from_player(
                    await db_player.to_shared(db_session)
                )
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
                return await db_player.to_shared(db_session)
            else:
                raise ResponseError("not_found", b"")

    @emit
    async def on_room_join(self, _session: Session, args: models.PlayerInfo):
        raise NotImplementedError()

    @emit
    async def on_room_leave(self, _session: Session, args: models.PlayerInfo):
        raise NotImplementedError()

    @emit
    async def on_room_delete(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @emit
    async def on_room_player_ready(self, _session: Session, args: models.PlayerId):
        raise NotImplementedError()

    @emit
    async def on_room_ready(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @emit
    async def on_room_player_submit(
        self, _session: Session, args: models.RoomPlayerSubmitData
    ):
        raise NotImplementedError()

    @emit
    async def on_room_submit(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @emit
    async def on_game_board_display(self, _session: Session, args: models.BoardId):
        raise NotImplementedError()

    @emit
    async def on_game_board_shot(self, _session: Session, args: models.ShotResult):
        raise NotImplementedError()

    @emit
    async def on_game_turn_start(self, _session: Session, args: models.PlayerInfo):
        raise NotImplementedError()

    @emit
    async def on_game_turn_end(self, _session: Session, args: models.PlayerInfo):
        raise NotImplementedError()

    @emit
    async def on_game_player_lost(self, _session: Session, args: models.PlayerInfo):
        raise NotImplementedError()

    @emit
    async def on_game_end(self, _session: Session, args: models.GameEndData):
        raise NotImplementedError()

    @emit
    async def on_game_reset(self, _session: Session, args: Empty):
        raise NotImplementedError()

    @emit
    async def on_emote_display(self, _session: Session, args: models.EmoteDisplayData):
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
    async def room_surrender(self, session: Session, args: models.RoomId) -> Empty:
        if (room := self.rooms.get(args, None)) and (
            (player_id := self.known_player_session_rev[session]) in room
        ):
            await room.do_player_lost(player_id)
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
    ) -> Empty:
        if (room := self.rooms.get(args.room, None)) and (
            (player_id := self.known_player_session_rev[session]) in room
        ):
            await room.display_board(player_id, args.board)
            return Empty()
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

    @Route.simple
    async def emote_display(
        self, session: Session, args: models.EmoteDisplayArgs
    ) -> Empty:
        if (room := self.rooms.get(args.room, None)) and (
            (player_id := self.known_player_session_rev[session]) in room
        ):
            await room.do_emote_display(player_id, args.emote)
            return Empty()
        raise ResponseError("not_found", b"")

    def _gacha(self, db_session: AsyncSession, db_player: db.Player):
        emote = random.choice([*emote_type.EMOTE_VARIANTS.keys()])
        db_player.coins -= 100
        db_player.emotes.append(db.Emote(variant_id=emote))
        db_session.add(db_player)
        return emote

    @Route.simple
    @ensure_session_player
    async def gacha(
        self, session: Session, args: models.BearingPlayerAuth
    ) -> models.GachaResult:
        async with self.db_session_maker() as db_session:
            stmt = (
                select(db.Player)
                .where(db.Player.auth_token == args.auth_token, db.Player.coins >= 100)
                .limit(1)
            )
            result = await db_session.execute(stmt)

            if (db_player := result.scalars().one_or_none()) is not None:
                emote = await db_session.run_sync(
                    lambda _: self._gacha(db_session, db_player)
                )
                await db_session.commit()
                return models.GachaResult(
                    await db_player.to_shared(db_session), models.EmoteVariantId(emote)
                )
            else:
                raise ResponseError("not_found", b"")
