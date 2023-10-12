from concurrent.futures import Future
from dataclasses import dataclass
import logging
from uuid import UUID

from cattrs.preconf.json import JsonConverter
from tsocket.client_thread import ClientThread, Route
from tsocket.shared import Empty

from ..shared import models

log = logging.getLogger(__name__)

converter = JsonConverter()

converter.register_structure_hook(UUID, lambda d, t: UUID(hex=d))


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

    @Route.simple
    def public_room_get(self, args: models.PublicRoomId) -> Future[models.PublicRoom]:
        raise NotImplementedError()

    @Route.simple
    def public_room_match(
        self, args: models.BearingPlayerAuth
    ) -> Future[models.PublicRoomId]:
        raise NotImplementedError()
