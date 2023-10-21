import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tsocket.shared import Empty
from tgraphics.style import c, text_c, hover_c, disable_c, w, h, r_b, r_t, r_l, r_r, g

from .. import store
from ..client import BattleshipClient
from ..component import create_player_modal
from ...shared import models


@Component.register("MainMenu")
def main_menu(
    window: Window, client: BattleshipClient, name: str | None = None, **kwargs
):
    try:
        store.user.load()
    except FileNotFoundError:
        pass

    online_count = Ref(None)
    code = Ref("")

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
            from .private_lobby import private_lobby

            await window.set_scene(
                private_lobby(window, client, room.join_code, room.room)
            )

    async def on_private_room_join_button(_e):
        if (user := unref(store.user.store)) is not None:
            room = await client.private_room_join(
                models.PrivateRoomJoinArgs(user.auth_token, unref(code))
            )
            from .lobby import lobby

            await window.set_scene(lobby(window, client, room))

    async def on_profile_button(_e):
        from .profile import profile
        await window.set_scene(profile(window,client))

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted">
            <Layer>
                <Pad pad_right="800">
                    <Pad pad_bottom="440">
                        <RoundedRectLabelButton 
                            text="'Profile'"
                            font_size="20"
                            t-style="c['teal'][300] | hover_c['teal'][400] | disable_c['slate'][500] | text_c['white'] | w[24] | h[10]"
                            handle-ClickEvent="on_profile_button"
                        />
                    </Pad>
                </Pad>
            </Layer>
            <Column 
                t-style="w['full'](window) | h['full'](window) | g[12]"
            >
                <Column t-style="g[2]">
                    <Pad pad_top="90">
                        <Label text="f'There are currently {unref(online_count)} player(s) online.'" text_color="colors['white']" />
                    </Pad>
                    <Layer>
                        <Pad pad_bottom="20">
                            <Pad pad_right="310">
                                <RoundedRectLabelButton 
                                    text="'+'"
                                    font_size="20"
                                    t-style="c['teal'][300] | hover_c['teal'][400] | disable_c['slate'][500] | text_c['white'] | w[10] | h[10]"
                                    handle-ClickEvent="on_private_room_create_button"
                                />
                            </Pad>
                        </Pad>
                        <Pad t-if="len(unref(code)) == 0" pad_right="130"> 
                            <Pad pad_bottom="20">
                                <Label text="'Password'" italic="True" text_color="colors['slate'][400]" />
                            </Pad>
                        </Pad>
                        <Pad pad_bottom="20"> 
                            <Pad pad_right="65">
                                <RoundedRect t-style="c['teal'][100] | w[48] | h[12] | r_r[0]"/>
                            </Pad>
                        </Pad>
                        <Row t-style="g[5]">
                            <Pad pad_left="11">
                                <Input
                                    t-model-text="code"
                                    caret_color="colors['black']"
                                    selection_background_color="colors['teal'][300]"
                                    t-style="text_c['black'] | w[40] | h[8]"
                                />
                            </Pad>
                            <Pad pad_bottom="20"> 
                                <RoundedRectLabelButton 
                                    text="'Join'"
                                    t-style="c['teal'][300] | hover_c['teal'][400] | disable_c['slate'][500] | text_c['white'] | w[16] | h[12] | r_l[0]"
                                    handle-ClickEvent="on_private_room_join_button"
                                />
                            </Pad>
                        </Row>    
                    </Layer>
                    <Layer>
                        <Pad pad_top="25">
                            <RoundedRectLabelButton 
                                text="'Public Match'"
                                t-style="c['teal'][400] | hover_c['teal'][500] | disable_c['slate'][500] | text_c['white'] | w[64] | h[12]"
                                handle-ClickEvent="on_public_room_match_button"
                            />
                        </Pad>
                    </Layer>
                </Column>
                    <Label text="'BATTLESHIP'" bold="True" text_color="colors['white']" font_size="88" />
                <Column t-style="g[1]">
                    <Label text="f'Your current rating is {unref(store.user.rating)}'" text_color="colors['white']" />
                    <Label text="f'Welcome, {unref(store.user.name)}'" />
                </Column>
            </Column>
            <CreatePlayerModal t-if="unref(store.user.store) is None" window="window" client="client" />
        </Layer>
        """,
        **kwargs,
    )
