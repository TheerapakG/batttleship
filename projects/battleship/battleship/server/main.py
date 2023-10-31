import argparse
import asyncio
import os
import ssl

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker

from . import db
from .server import BattleshipServer
from .view.main_menu import main_menu
from ..shared.logging import setup_logging


if __name__ == "__main__":
    load_dotenv()
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--ui", action="store_true")
    args = parser.parse_args()

    ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(os.environ["SSL_CERT"], os.environ["SSL_KEY"])

    if args.ui:
        import contextlib
        import pyglet
        from tgraphics.component import Window, loop

        window = Window(resizable=True)

        engine = loop.run_until_complete(db.create_dev_engine())
        server = BattleshipServer(async_sessionmaker(engine, expire_on_commit=False))
        loop.create_task(
            server.run(
                "0.0.0.0",
                60000,
                ssl=ssl_context,
            )
        )
        loop.run_until_complete(
            window.set_scene(main_menu(window=window, server=server))
        )

        pyglet.app.run()

        async def cleanup():
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                    await task

        loop.run_until_complete(cleanup())
        loop.close()
    else:

        async def amain():
            engine = await db.create_dev_engine()
            server = BattleshipServer(
                async_sessionmaker(engine, expire_on_commit=False)
            )
            await server.run(
                "0.0.0.0",
                60000,
                ssl=ssl_context,
            )

        asyncio.run(amain())
