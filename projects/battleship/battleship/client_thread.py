from concurrent.futures import Future
from dataclasses import dataclass
import inspect
import logging
import os
import ssl
from uuid import UUID

from cattrs.preconf.json import JsonConverter
from dotenv import load_dotenv
from rich.prompt import Prompt
from tsocket.client_thread import ClientThread, Route
from tsocket.shared import Empty

from .shared import models
from .shared.logging import setup_logging

log = logging.getLogger(__name__)

converter = JsonConverter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)


@dataclass
class BattleshipClientThread(ClientThread):
    @Route.simple
    def ping(self, _: Empty) -> Future[Empty]:
        raise NotImplementedError()

    @Route.simple
    def online(self, _: Empty) -> Future[int]:
        raise NotImplementedError()

    @Route.simple
    def room_create(self, args: models.RoomCreateArgs) -> Future[models.RoomId]:
        raise NotImplementedError()

    @Route.simple
    def room_get(self, args: models.RoomGetArgs) -> Future[models.Room]:
        raise NotImplementedError()

    @Route.simple
    def room_delete(self, args: models.RoomDeleteArgs) -> Future[models.RoomId]:
        raise NotImplementedError()

    @Route.simple
    def room_list(self, _: Empty) -> Future[list[models.RoomId]]:
        raise NotImplementedError()


def run_client(host: str | None, port: int | str | None):
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_verify_locations(os.environ["SSL_CERT"])
    ssl_context.check_hostname = False
    client = BattleshipClientThread()
    client.connect(host, port, ssl=ssl_context)
    while True:
        data = Prompt.ask(">")
        if data:
            try:
                method, data = data.split(None, 1)
                data = converter.loads(
                    data,
                    [
                        *inspect.signature(
                            client.routes[method].func
                        ).parameters.values()
                    ][-1].annotation,
                )
                print(getattr(client, method)(data).result())
            except Exception as err:  # pylint: disable=W0718
                log.exception("%s", err)
        else:
            client.disconnect()
            return


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    run_client("0.0.0.0", 60000)
