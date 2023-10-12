import os
import ssl

from dotenv import load_dotenv
import pyglet

from tgraphics.component import Window
from tgraphics.reactivity import ComputedFuture, computed, unref
from tsocket.shared import Empty


from .client_thread import BattleshipClientThread
from . import store
from ..shared.logging import setup_logging


if __name__ == "__main__":
    load_dotenv()
    setup_logging()

    window = Window(resizable=True)

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_verify_locations(os.environ["SSL_CERT"])
    ssl_context.check_hostname = False
    client = BattleshipClientThread()
    client.connect("0.0.0.0", 60000, ssl=ssl_context)

    online_count = ComputedFuture(client.online(Empty()))
    text = computed(lambda: f"online: {unref(online_count)}")

    try:
        store.user.load()

        from .view.main_menu import main_menu

        window.scene = main_menu(window=window, client=client)
    except Exception:
        from .view.create_player import create_player

        window.scene = create_player(window=window, client=client)
    pyglet.app.run()
    client.disconnect()
