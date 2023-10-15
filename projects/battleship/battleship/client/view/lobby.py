import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref

from .. import store
from ..client import BattleshipClient
from ...shared import models


@Component.register("Lobby")
def lobby(window: Window, client: BattleshipClient, room: models.RoomInfo, **kwargs):
    player_ids = Ref(room.players)

    async def subscribe_player_join():
        async for player_id in client.on_room_join():
            player_ids.value.append(player_id)
            player_ids.trigger()

    async def subscribe_player_leave():
        async for player_id in client.on_room_leave():
            player_ids.value.remove(player_id)
            player_ids.trigger()

    async def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_join()),
                asyncio.create_task(subscribe_player_leave()),
            ]
        )

    return Component.render_xml(
        """
        <Column 
            gap="16"
            width="window.width"
            height="window.height"
            handle-ComponentMountedEvent="on_mounted"
        >
            <Label 
                t-for="player_id in player_ids"
                text="str(player_id)" 
                color="colors['white']" 
            />
        </Column>
        """,
        **kwargs,
    )
