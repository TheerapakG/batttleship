import pyglet

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import ComputedFuture, Watcher, computed, unref
from tsocket.shared import Empty

from .. import store
from ..client_thread import BattleshipClientThread
from ...shared import models


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

    def on_public_room_match_button(_e):
        room_id_ref = computed(
            lambda: unref(
                ComputedFuture(
                    client.public_room_match(
                        models.BearingPlayerAuth.from_player(player.auth_token)
                    )
                )
            )
            if (player := unref(store.user.store)) is not None
            else None
        )
        room_ref = computed(
            lambda: unref(ComputedFuture(client.public_room_get(unref(room_id))))
            if (room_id := unref(room_id_ref)) is not None
            else None
        )

        def to_lobby():
            if (room := unref(room_ref)) is not None:
                from .lobby import lobby

                window.scene = lobby(window, client, room)
                watcher.unwatch()

        watcher = Watcher([room_ref], to_lobby)

    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Label text="user_text" color="colors['white']" />
            <Label text="online_text" color="colors['white']" />
        </Column>
        """,
        **kwargs,
    )
