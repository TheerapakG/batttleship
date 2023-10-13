from concurrent.futures import Future
from contextlib import AbstractContextManager
from dataclasses import dataclass
import queue
from tsocket.client_thread import ClientThread, Route, subscribe
from tsocket.shared import Empty

from ..shared import models


@dataclass
class BattleshipClientThread(ClientThread):
    @Route.simple
    def ping(self, _: Empty) -> Future[Empty]:
        raise NotImplementedError()

    @Route.simple
    def online(self, _: Empty) -> Future[int]:
        raise NotImplementedError()

    @Route.simple
    def player_create(self, args: models.PlayerCreateArgs) -> Future[models.Player]:
        raise NotImplementedError()

    @Route.simple
    def player_get(self, args: models.BearingPlayerAuth) -> Future[models.Player]:
        raise NotImplementedError()

    @Route.simple
    def player_info_get(self, args: models.PlayerId) -> Future[models.PlayerInfo]:
        raise NotImplementedError()

    @Route.simple
    def player_delete(self, args: models.BearingPlayerAuth) -> Future[models.Player]:
        raise NotImplementedError()

    @subscribe
    def room_join(
        self,
    ) -> Future[AbstractContextManager[queue.SimpleQueue[Future[models.PlayerId]]]]:
        raise NotImplementedError()

    @subscribe
    def room_leave(
        self,
    ) -> Future[AbstractContextManager[queue.SimpleQueue[Future[models.PlayerId]]]]:
        raise NotImplementedError()

    @Route.simple
    def public_room_get(self, args: models.RoomId) -> Future[models.Room]:
        raise NotImplementedError()

    @Route.simple
    def public_room_match(
        self, args: models.BearingPlayerAuth
    ) -> Future[models.RoomId]:
        raise NotImplementedError()

    @Route.simple
    def private_room_create(
        self, args: models.BearingPlayerAuth
    ) -> Future[models.PrivateRoom]:
        raise NotImplementedError()

    @Route.simple
    def private_room_get(
        self, args: models.PrivateRoomId
    ) -> Future[models.PrivateRoom]:
        raise NotImplementedError()

    @Route.simple
    def private_room_join(
        self, args: models.PrivateRoomJoinArgs
    ) -> Future[models.PrivateRoom]:
        raise NotImplementedError()

    @Route.simple
    def private_room_unlock(self, args: models.PrivateRoomUnlockArgs) -> Future[Empty]:
        raise NotImplementedError()
