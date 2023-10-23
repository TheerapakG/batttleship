import argparse
import asyncio
import contextlib
import os
import ssl

from dotenv import load_dotenv
import pyglet

from tgraphics.component import Window, loop


from .client import BattleshipClient
from .view.main_menu import main_menu
from ..shared.logging import setup_logging


if __name__ == "__main__":
    load_dotenv()
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--name")
    args = parser.parse_args()

    window = Window(resizable=True)

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_verify_locations(os.environ["SSL_CERT"])
    ssl_context.check_hostname = False
    client = BattleshipClient()
    loop.run_until_complete(client.connect("localhost", 60000, ssl=ssl_context))

    loop.run_until_complete(
        window.set_scene(main_menu(window=window, client=client, name=args.name))
    )

    pyglet.app.run()
    loop.run_until_complete(client.disconnect())

    async def cleanup():
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                await task

    loop.run_until_complete(cleanup())
    loop.close()
