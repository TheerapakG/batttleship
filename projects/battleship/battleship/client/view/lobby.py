import asyncio
import contextlib
from dataclasses import replace
from functools import partial

from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tgraphics.style import *

from ..component import emote_picker
from .. import store
from ...shared import models, ship_type

player_infos = Ref([])
player_readies = Ref(set())


@Component.register("Lobby")
def lobby(room: models.RoomInfo, **kwargs):
    window = store.ctx.use_window()

    store.game.room.value = models.RoomId.from_room_info(room)

    player_infos.value = room.players.copy()
    player_readies.value = set(room.readies)

    ready = Ref(False)

    def get_player_ready_text(player_id: models.PlayerId):
        return computed(
            lambda: "ready" if player_id in unref(player_readies) else "not ready"
        )

    async def subscribe_player_join():
        if (client := unref(store.ctx.client)) is not None:
            async for player_info in client.on_room_join():
                player_infos.value.append(player_info)
                player_infos.trigger()

    async def subscribe_player_leave():
        if (client := unref(store.ctx.client)) is not None:
            async for player_info in client.on_room_leave():
                player_infos.value.remove(player_info)
                player_infos.trigger()
                with contextlib.suppress(KeyError):
                    player_readies.value.remove(
                        models.PlayerId.from_player_info(player_info)
                    )
                    player_readies.trigger()

    async def subscribe_room_player_ready():
        if (client := unref(store.ctx.client)) is not None:
            async for player_id in client.on_room_player_ready():
                player_readies.value.add(player_id)
                player_readies.trigger()

    async def subscribe_room_ready():
        if (client := unref(store.ctx.client)) is not None:
            async for _ in client.on_room_ready():
                from .ship_setup import ship_setup

                store.game.players.value = {
                    models.PlayerId.from_player_info(player_info): player_info
                    for player_info in unref(player_infos)
                }
                store.game.players.trigger()

                await store.game.room_reset()
                await store.ctx.set_scene(ship_setup())
                store.game.player_points.value = {
                    models.PlayerId.from_player_info(player): Ref(0)
                    for player in unref(store.game.alive_players)
                }

    def on_mounted(event: ComponentMountedEvent):
        store.bgm.set_music(store.bgm.game_bgm)
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_join()),
                asyncio.create_task(subscribe_player_leave()),
                asyncio.create_task(subscribe_room_player_ready()),
                asyncio.create_task(subscribe_room_ready()),
                asyncio.create_task(store.game.subscribe_emote_display()),
            ]
        )

    async def return_button(_e):
        if (client := unref(store.ctx.client)) is not None:
            await client.room_leave(models.RoomId.from_room_info(room))

            from .main_menu import main_menu

            await store.ctx.set_scene(main_menu())

    async def on_ready_button(_e):
        if (client := unref(store.ctx.client)) is not None:
            ready.value = True
            await client.room_ready(models.RoomId.from_room_info(room))

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted">
            <Pad pad_right="800" pad_bottom="440">
                <RoundedRectLabelButton 
                    text="'Return'"
                    font_size="20"
                    t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[24] | h[10]"
                    handle-ClickEvent="return_button"
                />
            </Pad>
            <Column t-style="w['full'](window) | h['full'](window) | g[4]">
                <EmotePicker />
                <Row t-style="g[4]">
                    <Layer t-for="player_info in player_infos">
                        <Column t-style="w[48] | h[64] | g[3]">
                            <RoundedRectLabelButton
                                t-if="store.user.is_player(models.PlayerId.from_player_info(player_info))"
                                text="'Ready'"
                                disabled="ready"
                                t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                                handle-ClickEvent="on_ready_button"
                            />
                            <Label
                                text="get_player_ready_text(models.PlayerId.from_player_info(player_info))" 
                                text_color="colors['white']" 
                            />
                            <Label
                                text="f'rating: {str(player_info.rating)}'" 
                                text_color="colors['white']" 
                            />
                            <Label
                                text="player_info.name" 
                                text_color="colors['white']" 
                            />
                        </Column>
                        <Image 
                            t-if="unref(store.game.get_player_emote(models.PlayerId.from_player_info(player_info))) is not None" 
                            texture="unref(store.game.get_player_emote(models.PlayerId.from_player_info(player_info)))"
                        />
                    </Layer>
                </Row>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
