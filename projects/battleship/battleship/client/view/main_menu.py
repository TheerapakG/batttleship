import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tsocket.shared import Empty
from tgraphics.template import c, text_c, hover_c, disable_c, w, h, r_b, r_t

from .. import store
from ..client import BattleshipClient
from ..component import create_player_modal
from ...shared import models


@Component.register("MainMenu")
def main_menu(window: Window, client: BattleshipClient, name: str | None, **kwargs):
    try:
        store.user.load()
    except FileNotFoundError:
        pass

    online_count = Ref(None)

    async def set_online_count():
        while True:
            online_count.value = await client.online(Empty())
            await asyncio.sleep(1.0)

    async def on_mounted(event: ComponentMountedEvent):
        # TODO: async component
        if name is not None:
            player = await client.player_create(models.PlayerCreateArgs(name))
            store.user.save(player)
        event.instance.bound_tasks.update([asyncio.create_task(set_online_count())])

    async def on_public_room_match_button(_e):
        if (user := unref(store.user.store)) is not None:
            room = await client.room_match(models.BearingPlayerAuth.from_player(user))

            from .lobby import lobby

            await window.set_scene(lobby(window, client, room))

    async def on_private_room_create_button(_e):
        if (user := unref(store.user.store)) is not None:
            room = await client.private_room_create(
                models.BearingPlayerAuth.from_player(user)
            )
            from .lobby import lobby

            await window.set_scene(lobby(window, client, room))

    async def on_private_room_join_button(_e, code: str):
        if (user := unref(store.user.store)) is not None:
            room = await client.private_room_join(
                models.PrivateRoomJoinArgs(user.auth_token, code)
            )
            from .lobby import lobby

            await window.set_scene(lobby(window, client, room))

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted">
            <Column 
                gap="50" 
                width="window.width" 
                height="window.height"
            >
                <Column gap="10">
                    <Label text="f'There are currently {unref(online_count)} player(s) online.'" color="colors['white']" />
                    <LabelButton 
                        text="'Public Match'"
                        t-template="c['teal'][400] | hover_c['teal'][500] | disable_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                        handle-ClickEvent="on_public_room_match_button"
                    />
                </Column>
                <Label text="'BATTLESHIP'" bold="True" color="colors['white']" font_size="88" />
                <Column gap="0">   
                    <Label text="f'Your current rating is {unref(store.user.rating)}'" color="colors['white']" />
                    <Label text="f'Welcome, {unref(store.user.name)}'" /> 
                </Column>
            </Column>
            <CreatePlayerModal t-if="unref(store.user.store) is None" window="window" client="client" />
        </Layer>
        """,
        **kwargs,
    )

    return Component.render_xml(
        """
        <Layer>
            <Column 
                gap="0" 
                width="window.width" 
                height="window.height" 
                handle-ComponentMountedEvent="on_mounted"
            >
                <Pad pad_bottom="100">
                    <Label text="'BATTLESHIP'" bold="True" color="colors['white']" font_size="88" />
                </Pad>
            </Column>

            <Layer>
                <Pad pad_top="150">
                    <Column gap="10">
                        <Label text="f'There are currently {unref(online_count)} player(s) online.'" color="colors['white']" />
                        <LabelButton 
                            text="'Public Match'"
                            t-template="c['teal'][400] | hover_c['teal'][500] | disable_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                            handle-ClickEvent="on_public_room_match_button"
                        />
                    </Column>
                </Pad>
            </Layer> 

            <Layer>
                <Pad pad_bottom="400">
                    <Column gap="0">   
                        <Label text="f'Your current rating is {unref(store.user.rating)}'" color="colors['white']" />
                        <Label text="f'Welcome, {unref(store.user.name)}'" /> 
                    </Column>
                </Pad>
            </Layer>
            <CreatePlayerModal t-if="unref(store.user.store) is None" window="window" client="client" />
        </Layer>
        """,
        **kwargs,
    )
