import pyglet

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import ComputedFuture, computed, unref
from tsocket.shared import Empty

from .. import store
from ..client_thread import BattleshipClientThread


@Component.register("MainMenu")
def main_menu(window: Window, client: BattleshipClientThread, **kwargs):
    user_text = computed(
        lambda: f"user: {unref(store.user.name)} rating: {unref(store.user.rating)}"
    )

    online_count = ComputedFuture(client.online(Empty()))
    online_text = computed(lambda: f"online: {unref(online_count)}")

    online_count.add_done_callback(
        lambda _: pyglet.clock.schedule_once(
            lambda _: online_count.set_future(client.online(Empty())), 1.0
        )
    )
    def start(event):
        nonlocal window
        nonlocal client
        from .lobby import lobby
        window.scene = lobby(window,client)
        ComputedFuture(client.public_room_match(models.BearingPlayerAuth(unref(store.user.value.auth_token))))


    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Label text="user_text" color="colors['white']" />
            <Label text="online_text" color="colors['white']" />
        </Column>
        """,
        **kwargs,
    )
