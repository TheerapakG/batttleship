import pyglet

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import Ref, ComputedFuture, Watcher, computed, unref
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
        room_id_future_ref = Ref[ComputedFuture[models.RoomId | None] | None](None)

        def set_room_id_future(player: models.Player | None):
            if player is not None:
                room_id_future_ref.value = ComputedFuture(
                    client.public_room_match(
                        models.BearingPlayerAuth.from_player(player)
                    )
                )
                player_watcher.unwatch()

        player_watcher = Watcher.ifref(
            store.user.store,
            lambda player: pyglet.clock.schedule_once(
                lambda: set_room_id_future(player)
            ),
            trigger_init=True,
        )

        room_id_ref = computed(lambda: unref(unref(room_id_future_ref)))

        room_future_ref = Ref[ComputedFuture[models.Room | None] | None](None)

        def set_room_future(room_id: models.RoomId | None):
            if room_id is not None:
                room_future_ref.value = ComputedFuture(client.public_room_get(room_id))
                room_id_watcher.unwatch()

        room_id_watcher = Watcher.ifref(
            room_id_ref,
            lambda room_id: pyglet.clock.schedule_once(
                lambda: set_room_future(room_id)
            ),
            trigger_init=True,
        )

        room_ref = computed(lambda: unref(unref(room_future_ref)))

        def to_lobby(room: models.Room | None):
            if room is not None:
                from .lobby import lobby

                window.scene = lobby(window, client, room)
                room_watcher.unwatch()

        room_watcher = Watcher.ifref(
            room_ref,
            lambda room: pyglet.clock.schedule_once(lambda: to_lobby(room)),
            trigger_init=True,
        )

    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Label text="user_text" color="colors['white']" />
            <Label text="online_text" color="colors['white']" />
        </Column>
        """,
        **kwargs,
    )
