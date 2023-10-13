import contextlib
import logging
import os
import queue
import ssl

from dotenv import load_dotenv

from .client_thread import BattleshipClientThread
from ..shared import models
from ..shared.logging import setup_logging

log = logging.getLogger(__name__)


def run_client(host: str | None, port: int | str | None):
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_verify_locations(os.environ["SSL_CERT"])
    ssl_context.check_hostname = False
    client_1 = BattleshipClientThread()
    client_1.connect(host, port, ssl=ssl_context)
    client_2 = BattleshipClientThread()
    client_2.connect(host, port, ssl=ssl_context)

    player_1 = client_1.player_create(models.PlayerCreateArgs("player 1")).result()
    player_2 = client_2.player_create(models.PlayerCreateArgs("player 2")).result()

    with client_1.room_join().result() as room_join_queue_msg_1, client_2.room_join().result() as room_join_queue_msg_2:
        room_1 = client_1.public_room_match(player_1).result()
        room_2 = client_2.public_room_match(player_2).result()

        with contextlib.suppress(queue.Empty):
            while True:
                log.info("join 1 %s", room_join_queue_msg_1.get(timeout=1.0).result())

        log.info("join 1 finished")

        with contextlib.suppress(queue.Empty):
            while True:
                log.info("join 2 %s", room_join_queue_msg_2.get(timeout=1.0).result())

        log.info("join 2 finished")

    log.info("room 1 %s", room_1)
    log.info("room 2 %s", room_2)

    client_1.disconnect()
    client_2.disconnect()


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    run_client("localhost", 60000)
