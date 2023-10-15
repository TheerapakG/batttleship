import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tsocket.shared import Empty

from .. import store
from ..client import BattleshipClient
from ..component import create_player_modal
from ...shared import models


@Component.register("MainMenu")
def main_menu(window: Window, client: BattleshipClient, **kwargs):
    try:
        store.user.load()
    except FileNotFoundError:
        pass

    not_have_user = computed(lambda: unref(store.user.store) is None)

    user_text = computed(
        lambda: f"user: {unref(store.user.name)} rating: {unref(store.user.rating)}"
    )

    online_count = Ref(None)
    online_text = computed(lambda: f"online: {unref(online_count)}")

    async def set_online_count():
        while True:
            online_count.value = await client.online(Empty())
            await asyncio.sleep(1.0)

    async def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_tasks.update([asyncio.create_task(set_online_count())])

    async def on_public_room_match_button(_e):
        if (user := unref(store.user.store)) is not None:
            room_id = await client.room_match(
                models.BearingPlayerAuth.from_player(user)
            )

            room = await client.room_info_get(room_id)

            from .lobby import lobby

            await window.set_scene(lobby(window, client, room))

    return Component.render_xml(
        """
        <Layer>
            <Column 
                gap="16" 
                width="window.width" 
                height="window.height" 
                handle-ComponentMountedEvent="on_mounted"
            >
                <Label 
                    text="'Public Match'" 
                    color="colors['white']" 
                    handle-MousePressEvent="on_public_room_match_button"
                />
                <Label text="user_text" color="colors['white']" />
                <Label text="online_text" color="colors['white']" />
                <Label text="'BATTLESHIP'" color="colors['white']" font_size="72" />
            </Column>
            <CreatePlayerModal t-if="not_have_user" window="window" client="client" />
        </Layer>
        """,
        **kwargs,
    )
