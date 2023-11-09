import asyncio

from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tsocket.shared import Empty
from tgraphics.style import *

from .. import store
from ..component import create_player_modal
from ...shared import models


@Component.register("MainMenu")
def main_menu(name: str | None = None, **kwargs):
    window = store.ctx.use_window()

    online_count = Ref(None)
    code = Ref("")

    async def set_online_count():
        if (client := unref(store.ctx.client)) is not None:
            while True:
                online_count.value = await client.online(Empty())
                await asyncio.sleep(1.0)

    async def on_mounted(event: ComponentMountedEvent):
        store.bgm.set_music(store.bgm.menu_bgm)
        if (client := unref(store.ctx.client)) is not None and name is not None:
            player = await client.player_create(models.PlayerCreateArgs(name))
            store.user.save(player)
        event.instance.bound_tasks.update([asyncio.create_task(set_online_count())])

    async def on_public_room_match_button(_e):
        if (client := unref(store.ctx.client)) is not None and (
            user := unref(store.user.player)
        ) is not None:
            room = await client.room_match(models.BearingPlayerAuth.from_player(user))
            store.game.room.value = models.RoomId.from_room_info(room)
            store.game.players.value = {
                models.PlayerId.from_player_info(player_info): player_info
                for player_info in room.players
            }
            store.game.ready_players.value = set(room.readies)

            from .lobby import lobby

            await store.ctx.set_scene(lobby())

    async def on_private_room_create_button(_e):
        if (client := unref(store.ctx.client)) is not None and (
            user := unref(store.user.player)
        ) is not None:
            room = await client.private_room_create(
                models.BearingPlayerAuth.from_player(user)
            )
            store.game.room.value = models.RoomId.from_room_info(room.room)
            store.game.players.value = {
                models.PlayerId.from_player_info(player_info): player_info
                for player_info in room.players
            }
            store.game.ready_players.value = set(room.room.readies)

            from .private_lobby import private_lobby

            await store.ctx.set_scene(private_lobby(room.join_code))

    async def on_private_room_join_button(_e):
        if (client := unref(store.ctx.client)) is not None and (
            user := unref(store.user.player)
        ) is not None:
            room = await client.private_room_join(
                models.PrivateRoomJoinArgs(user.auth_token, unref(code))
            )
            store.game.room.value = models.RoomId.from_room_info(room)
            store.game.players.value = {
                models.PlayerId.from_player_info(player_info): player_info
                for player_info in room.players
            }
            store.game.ready_players.value = set(room.readies)

            from .lobby import lobby

            await store.ctx.set_scene(lobby())

    async def on_profile_button(_e):
        from .profile import profile

        await store.ctx.set_scene(profile())

    async def on_gacha_button(_e):
        from .gacha import gacha

        await store.ctx.set_scene(gacha())

    async def on_setting_button(_e):
        from .settings import settings

        await store.ctx.set_scene(settings())

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted">
            <Layer>
                <Pad pad_right="800">
                    <Pad pad_bottom="440">
                        <RoundedRectLabelButton 
                            text="'Profile'"
                            font_size="20"
                            t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[24] | h[10]"
                            handle-ClickEvent="on_profile_button"
                        />
                    </Pad>
                </Pad>
            </Layer>
            <Column 
                t-style="w['full'](window) | h['full'](window) | g[8]"
            >
                <Label text="f'There are currently {unref(online_count)} player(s) online.'" text_color="colors['white']" />
                <Column t-style="g[2]">
                    <Layer>
                        <Pad pad_bottom="20">
                            <Pad pad_right="310">
                                <RoundedRectLabelButton 
                                    text="'+'"
                                    font_size="20"
                                    t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[10] | h[10]"
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
                                    t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[16] | h[12] | r_l[0]"
                                    handle-ClickEvent="on_private_room_join_button"
                                />
                            </Pad>
                        </Row>    
                    </Layer>
                    <RoundedRectLabelButton 
                        text="'Public Match'"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[64] | h[12]"
                        handle-ClickEvent="on_public_room_match_button"
                    />
                    <RoundedRectLabelButton 
                        text="'Setting'"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[64] | h[12]"
                        handle-ClickEvent="on_setting_button"
                    />
                    <RoundedRectLabelButton 
                        text="'Gacha'"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[64] | h[12]"
                        handle-ClickEvent="on_gacha_button"
                    />
                </Column>
                <Label text="'BATTLESHIP'" bold="True" text_color="colors['white']" font_size="88" />
                <Label text="f'Welcome, {unref(store.user.name)}'" />
            </Column>
            <CreatePlayerModal t-if="unref(store.user.player) is None" />
        </Layer>
        """,
        **kwargs,
    )
