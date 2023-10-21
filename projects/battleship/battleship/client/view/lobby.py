import asyncio
import contextlib
from dataclasses import replace

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tgraphics.style import c, text_c, hover_c, disable_c, w, h, r_b, r_t, r_l, r_r, g

from .. import store
from ..client import BattleshipClient
from ...shared import models


@Component.register("Lobby")
def lobby(window: Window, client: BattleshipClient, room: models.RoomInfo, **kwargs):
    player_infos = Ref(room.players)
    player_readies = Ref(set(room.readies))

    ready = Ref(False)
    class_ready = Ref(False)

    def get_player_ready_text(player_id: models.PlayerId):
        return computed(
            lambda: "ready" if player_id in unref(player_readies) else "not ready"
        )

    async def subscribe_player_join():
        async for player_info in client.on_room_join():
            player_infos.value.append(player_info)
            player_infos.trigger()

    async def subscribe_player_leave():
        async for player_info in client.on_room_leave():
            player_infos.value.remove(player_info)
            player_infos.trigger()
            with contextlib.suppress(KeyError):
                player_readies.value.remove(
                    models.PlayerId.from_player_info(player_info)
                )
                player_readies.trigger()

    async def subscribe_room_player_ready():
        async for player_id in client.on_room_player_ready():
            player_readies.value.add(player_id)
            player_readies.trigger()

    async def subscribe_room_ready():
        async for _ in client.on_room_ready():
            from .ship_setup import ship_setup

            await window.set_scene(
                ship_setup(window, client, replace(room, players=unref(player_infos)))
            )

    def on_mounted(event: ComponentMountedEvent):
        # TODO: async component
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_join()),
                asyncio.create_task(subscribe_player_leave()),
                asyncio.create_task(subscribe_room_player_ready()),
                asyncio.create_task(subscribe_room_ready()),
            ]
        )

    async def on_ready_button(_e):
        ready.value = True
        await client.room_ready(models.RoomId.from_room_info(room))

    async def class_select(_e):
        class_ready.value = True
        # TODO: assign class to player

    return Component.render_xml(
        """
        <Row 
            t-style="w['full'](window) | h['full'](window) | g[4]"
            handle-ComponentMountedEvent="on_mounted"
        >
            <Column t-for="player_info in player_infos" t-style="g[3]">
                    <RoundedRectLabelButton
                        t-if="store.user.is_player(models.PlayerId.from_player_info(player_info))"
                        text="'Ready'"
                        disable="not(unref(ready)^unref(class_ready))"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disable_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                        handle-ClickEvent="on_ready_button"
                    />
                    <Row t-if="store.user.is_player(models.PlayerId.from_player_info(player_info))" t-style="g[4]">
                        <RoundedRectLabelButton 
                            text="'NAVY'"
                            disable="class_ready"
                            t-style="c['teal'][300] | hover_c['teal'][400] | disable_c['slate'][500] | text_c['white'] | w[12] | h[12]"
                            handle-ClickEvent="class_select"
                        />
                        <RoundedRectLabelButton 
                            text="'Scout'"
                            disable="class_ready"
                            t-style="c['teal'][300] | hover_c['teal'][400] | disable_c['slate'][500] | text_c['white'] | w[12] | h[12]"
                            handle-ClickEvent="class_select"
                        />
                        <RoundedRectLabelButton 
                            text="'Pirate'"
                            disable="class_ready"
                            t-style="c['teal'][300] | hover_c['teal'][400] | disable_c['slate'][500] | text_c['white'] | w[12] | h[12]"
                            handle-ClickEvent="class_select"
                        />
                    </Row>
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
        </Row>
        """,
        **kwargs,
    )
