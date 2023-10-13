import queue

import pyglet

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import Ref, ComputedFuture, Watcher, computed, unref
from tsocket.shared import Empty

from .. import store
from ..client_thread import BattleshipClientThread
from ...shared import models


@Component.register("Lobby")
def lobby(
    window: Window, client: BattleshipClientThread, room: models.RoomInfo, **kwargs
):
    player_ids = Ref(room.players)

    # TODO: non hack this
    room_join_queue_ctx = client.room_join().result()
    room_join_queue = room_join_queue_ctx.__enter__()

    room_leave_queue_ctx = client.room_leave().result()
    room_leave_queue = room_leave_queue_ctx.__enter__()

    def try_add_player_id():
        try:
            player_id = room_join_queue.get_nowait().result()
            player_ids.value.append(player_id)
            player_ids.trigger()
        except queue.Empty:
            pass

    def try_remove_player_id():
        try:
            player_id = room_leave_queue.get_nowait().result()
            player_ids.value.remove(player_id)
            player_ids.trigger()
        except queue.Empty:
            pass

    pyglet.clock.schedule(lambda _dt: try_add_player_id())
    pyglet.clock.schedule(lambda _dt: try_remove_player_id())

    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Label 
                t-for="player_id in player_ids"
                text="str(player_id)" 
                color="colors['white']" 
            />
        </Column>
        """,
        **kwargs,
    )
