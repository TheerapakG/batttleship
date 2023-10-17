"AUTOGENERATED BY battleship.server.generate_client DO NOT MANUALLY EDIT"
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from tsocket.client import Client, Route, subscribe
from tsocket.shared import Empty
from ..shared import models


@dataclass
class BattleshipClient(Client):
    @Route.simple
    async def ping(self, _: Empty) -> Empty:
        raise NotImplementedError()

    @Route.simple
    async def online(self, _: Empty) -> int:
        raise NotImplementedError()

    @Route.simple
    async def player_create(self, args: models.PlayerCreateArgs) -> models.Player:
        raise NotImplementedError()

    @Route.simple
    async def player_get(self, args: models.BearingPlayerAuth) -> models.Player:
        raise NotImplementedError()

    @Route.simple
    async def player_info_get(self, args: models.PlayerId) -> models.PlayerInfo:
        raise NotImplementedError()

    @Route.simple
    async def player_delete(self, args: models.BearingPlayerAuth) -> models.Player:
        raise NotImplementedError()

    @subscribe
    def on_room_join(self) -> AsyncIterator[models.PlayerInfo]:
        raise NotImplementedError()

    @subscribe
    def on_room_leave(self) -> AsyncIterator[models.PlayerInfo]:
        raise NotImplementedError()

    @subscribe
    def on_room_player_ready(self) -> AsyncIterator[models.PlayerId]:
        raise NotImplementedError()

    @subscribe
    def on_room_ready(self) -> AsyncIterator[Empty]:
        raise NotImplementedError()

    @Route.simple
    async def room_match(self, args: models.BearingPlayerAuth) -> models.RoomInfo:
        raise NotImplementedError()

    @Route.simple
    async def room_leave(self, args: models.RoomId) -> Empty:
        raise NotImplementedError()

    @Route.simple
    async def room_ready(self, args: models.RoomId) -> Empty:
        raise NotImplementedError()

    @Route.simple
    async def private_room_create(
        self, args: models.BearingPlayerAuth
    ) -> models.PrivateRoomCreateResults:
        raise NotImplementedError()

    @Route.simple
    async def private_room_join(
        self, args: models.PrivateRoomJoinArgs
    ) -> models.RoomInfo:
        raise NotImplementedError()

    @Route.simple
    async def private_room_unlock(self, args: models.RoomId) -> Empty:
        raise NotImplementedError()
