import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import Ref

from .. import store
from ..client import BattleshipClient
from ...shared import models


@Component.register("Lobby")
def lobby(window: Window, client: BattleshipClient, room: models.RoomInfo, **kwargs):
    player_ids = Ref(room.players)

    # TODO: non hack this
    room_join_it_ctx = client.room_join()
    room_join_it = room_join_it_ctx.__enter__()

    room_leave_it_ctx = client.room_leave()
    room_leave_it = room_leave_it_ctx.__enter__()

    async def try_add_player_id():
        async for player_id in room_join_it:
            player_ids.value.append(player_id)
            player_ids.trigger()

    asyncio.create_task(try_add_player_id())

    async def try_remove_player_id():
        async for player_id in room_leave_it:
            player_ids.value.remove(player_id)
            player_ids.trigger()

    asyncio.create_task(try_remove_player_id())

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
