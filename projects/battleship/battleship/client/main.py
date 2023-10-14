import os
import ssl

from dotenv import load_dotenv
import pyglet

from tgraphics.component import Window, loop
from tgraphics.reactivity import ComputedFuture, computed, unref
from tsocket.shared import Empty


from .client import BattleshipClient
from . import store
from ..shared.logging import setup_logging


if __name__ == "__main__":
    load_dotenv()
    setup_logging()

    window = Window(resizable=True)

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_verify_locations(os.environ["SSL_CERT"])
    ssl_context.check_hostname = False
    client = BattleshipClient()
    loop.run_until_complete(client.connect("localhost", 60000, ssl=ssl_context))

    try:
        store.user.load()

        from .view.main_menu import main_menu

        window.scene = main_menu(window=window, client=client)
    except Exception:  # pylint: disable=W0718
        from .view.create_player import create_player

        window.scene = create_player(window=window, client=client)
    pyglet.app.run()
    loop.run_until_complete(client.disconnect())
    loop.close()
