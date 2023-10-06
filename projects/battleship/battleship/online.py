import os
import ssl

from dotenv import load_dotenv
import pyglet

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import ComputedFuture, computed, unref
from tsocket.shared import Empty


from .client_thread import BattleshipClientThread
from .shared.logging import setup_logging


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

    window.scene = Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Label text="text" color="colors['white']" />
        </Column>
        """
    )

    online_count.add_done_callback(
        lambda _: pyglet.clock.schedule_once(
            lambda _: online_count.set_future(client.online(Empty())), 1.0
        )
    )
    pyglet.app.run()
