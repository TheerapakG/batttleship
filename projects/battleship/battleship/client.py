import asyncio
from dataclasses import dataclass
import inspect
from uuid import UUID

from cattrs.preconf.json import JsonConverter
from rich.prompt import Prompt
from tsocket.client import Client, route
from tsocket.utils import Empty

from .shared import models
from .shared.logging import setup_logging

converter = JsonConverter()

converter.register_structure_hook(UUID, lambda d, t: UUID(d))
converter.register_unstructure_hook(UUID, str)


@dataclass
class BattleshipClient(Client):
    @route
    async def ping(self, _: Empty) -> Empty:
        raise NotImplementedError()

    @route
    async def room_create(self, args: models.RoomCreateArgs) -> models.RoomId:
        raise NotImplementedError()

    @route
    async def room_get(self, args: models.RoomGetArgs) -> models.Room:
        raise NotImplementedError()

    @route
    async def room_delete(self, args: models.RoomDeleteArgs) -> models.RoomId:
        raise NotImplementedError()

    @route
    async def room_list(self, _: Empty) -> list[models.RoomId]:
        raise NotImplementedError()


client = BattleshipClient()


async def run_client(host: str | None, port: int | str | None):
    await client.connect(host, port)
    while True:
        data = Prompt.ask(">")
        if data:
            method, data = data.split(None, 1)
            data = converter.loads(
                data,
                [*inspect.signature(client.routes[method].func).parameters.values()][
                    -1
                ].annotation,
            )
            await getattr(client, method)(data)
        else:
            await client.disconnect()
            return


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run_client("0.0.0.0", 60000))
