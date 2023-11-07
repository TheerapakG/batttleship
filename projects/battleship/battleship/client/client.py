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
    def on_room_delete(self) -> AsyncIterator[Empty]:
        raise NotImplementedError()

    @subscribe
    def on_room_player_ready(self) -> AsyncIterator[models.PlayerId]:
        raise NotImplementedError()

    @subscribe
    def on_room_ready(self) -> AsyncIterator[Empty]:
        raise NotImplementedError()

    @subscribe
    def on_room_player_submit(self) -> AsyncIterator[models.RoomPlayerSubmitData]:
        raise NotImplementedError()

    @subscribe
    def on_room_submit(self) -> AsyncIterator[Empty]:
        raise NotImplementedError()

    @subscribe
    def on_game_board_display(self) -> AsyncIterator[models.BoardId]:
        raise NotImplementedError()

    @subscribe
    def on_game_board_shot(self) -> AsyncIterator[models.ShotResult]:
        raise NotImplementedError()

    @subscribe
    def on_game_turn_start(self) -> AsyncIterator[models.PlayerInfo]:
        raise NotImplementedError()

    @subscribe
    def on_game_turn_end(self) -> AsyncIterator[models.PlayerInfo]:
        raise NotImplementedError()

    @subscribe
    def on_game_player_lost(self) -> AsyncIterator[models.PlayerInfo]:
        raise NotImplementedError()

    @subscribe
    def on_game_end(self) -> AsyncIterator[models.GameEndData]:
        raise NotImplementedError()

    @subscribe
    def on_game_reset(self) -> AsyncIterator[Empty]:
        raise NotImplementedError()

    @subscribe
    def on_emote_display(self) -> AsyncIterator[models.EmoteDisplayData]:
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

    @Route.simple
    async def board_submit(self, args: models.Board) -> Empty:
        raise NotImplementedError()

    @Route.simple
    async def display_board(self, args: models.DisplayBoardArgs) -> Empty:
        raise NotImplementedError()

    @Route.simple
    async def shot_submit(self, args: models.ShotSubmitArgs) -> models.ShotResult:
        raise NotImplementedError()

    @Route.simple
    async def emote_display(self, args: models.EmoteDisplayArgs) -> Empty:
        raise NotImplementedError()

    @Route.simple
    async def gacha(self, args: models.BearingPlayerAuth) -> models.GachaResult:
        raise NotImplementedError()
