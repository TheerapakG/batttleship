import asyncio
from dataclasses import dataclass
import inspect
import logging
import os
import ssl
from uuid import UUID

from cattrs.preconf.json import JsonConverter
from dotenv import load_dotenv
from rich.prompt import Prompt
from tsocket.client import Client, Route
from tsocket.shared import Empty

from .shared import models
from .shared.logging import setup_logging

log = logging.getLogger(__name__)

converter = JsonConverter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)


@dataclass
class BattleshipClient(Client):
    @Route.simple
    async def ping(self, _: Empty) -> Empty:
        raise NotImplementedError()

    @Route.simple
    async def room_create(self, args: models.RoomCreateArgs) -> models.RoomId:
        raise NotImplementedError()

    @Route.simple
    async def room_get(self, args: models.RoomGetArgs) -> models.Room:
        raise NotImplementedError()

    @Route.simple
    async def room_delete(self, args: models.RoomDeleteArgs) -> models.RoomId:
        raise NotImplementedError()

    @Route.simple
    async def room_list(self, _: Empty) -> list[models.RoomId]:
        raise NotImplementedError()


client = BattleshipClient()


async def run_client(host: str | None, port: int | str | None):
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_verify_locations(os.environ["SSL_CERT"])
    ssl_context.check_hostname = False
    await client.connect(host, port, ssl=ssl_context)
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
                print(await getattr(client, method)(data))
            except Exception as err:  # pylint: disable=W0718
                log.exception("%s", err)
        else:
            await client.disconnect()
            return


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    asyncio.run(run_client("0.0.0.0", 60000))
