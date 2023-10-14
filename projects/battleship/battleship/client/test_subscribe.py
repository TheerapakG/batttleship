import asyncio
import contextlib
import logging
import os
import ssl

from dotenv import load_dotenv

from .client import BattleshipClient
from ..shared import models
from ..shared.logging import setup_logging

log = logging.getLogger(__name__)


async def run_client(host: str | None, port: int | str | None):
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_verify_locations(os.environ["SSL_CERT"])
    ssl_context.check_hostname = False
    client_1 = BattleshipClient()
    await client_1.connect(host, port, ssl=ssl_context)
    client_2 = BattleshipClient()
    await client_2.connect(host, port, ssl=ssl_context)

    player_1 = await client_1.player_create(models.PlayerCreateArgs("player 1"))
    player_2 = await client_2.player_create(models.PlayerCreateArgs("player 2"))

    with await client_1.room_join() as room_join_queue_msg_1, await client_2.room_join() as room_join_queue_msg_2:
        room_1 = await client_1.public_room_match(player_1)
        room_2 = await client_2.public_room_match(player_2)

        with contextlib.suppress(asyncio.TimeoutError):
            while True:
                async with asyncio.timeout(1.0):
                    log.info("join 1 %s", await anext(room_join_queue_msg_1))

        log.info("join 1 finished")

        with contextlib.suppress(asyncio.TimeoutError):
            while True:
                async with asyncio.timeout(1.0):
                    log.info("join 2 %s", await anext(room_join_queue_msg_2))

        log.info("join 2 finished")

    log.info("room 1 %s", room_1)
    log.info("room 2 %s", room_2)

    await client_1.disconnect()
    await client_2.disconnect()


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    asyncio.run(run_client("localhost", 60000))
