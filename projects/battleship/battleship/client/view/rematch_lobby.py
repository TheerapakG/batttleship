import asyncio
import contextlib
from dataclasses import replace
from functools import partial

from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, Watcher, computed, unref
from tgraphics.style import *
from tsocket.shared import ResponseError

from ..component import emote_picker
from .. import store
from ...shared import models, ship_type, avatar_type


@Component.register("RematchLobby")
def rematch_lobby(**kwargs):
    window = store.ctx.use_window()

    duration = Ref[float](0)

    dots = computed(lambda: "." * (int(unref(duration) % 3) + 1))

    def get_player_ready_color(player_id: models.PlayerId):
        return computed(
            lambda: colors["green"][500]
            if player_id in unref(store.game.ready_players)
            else colors["red"][500]
        )

    async def subscribe_player_leave():
        if (client := unref(store.ctx.client)) is not None:
            async for player_info in client.on_room_leave():
                del store.game.players.value[
                    models.PlayerId.from_player_info(player_info)
                ]
                store.game.players.trigger()
                with contextlib.suppress(KeyError):
                    store.game.ready_players.value.remove(
                        models.PlayerId.from_player_info(player_info)
                    )
                    store.game.ready_players.trigger()
                if len(store.game.players.value) < 2:
                    try:
                        await client.room_leave(unref(store.game.room))
                    except ResponseError:
                        pass

                    from .main_menu import main_menu

                    asyncio.create_task(store.ctx.set_scene(main_menu()))

    async def subscribe_room_player_ready():
        if (client := unref(store.ctx.client)) is not None:
            async for player_id in client.on_room_player_ready():
                store.game.ready_players.value.add(player_id)
                store.game.ready_players.trigger()

    async def subscribe_room_ready():
        if (client := unref(store.ctx.client)) is not None:
            async for _ in client.on_room_ready():
                from .ship_setup import ship_setup

                asyncio.create_task(store.ctx.set_scene(ship_setup()))

    async def on_mounted(event: ComponentMountedEvent):
        store.bgm.set_music(store.bgm.game_bgm)
        event.instance.bound_watchers.update(
            [
                Watcher.ifref(event.instance.mount_duration, duration.set_value),
            ]
        )
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_leave()),
                asyncio.create_task(subscribe_room_player_ready()),
                asyncio.create_task(subscribe_room_ready()),
                asyncio.create_task(store.game.subscribe_emote_display()),
            ]
        )
        if (client := unref(store.ctx.client)) is not None:
            await client.room_ready(unref(store.game.room))

    async def return_button(_e):
        if (client := unref(store.ctx.client)) is not None:
            try:
                await client.room_leave(unref(store.game.room))
            except ResponseError:
                pass

            from .main_menu import main_menu

            asyncio.create_task(store.ctx.set_scene(main_menu()))

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
                    <Layer>
                        <Column t-style="w[48] | h[64] | g[3]">
                            <Label
                                text="f'rating: {str(unref(store.user.rating))}'" 
                                text_color="colors['white']" 
                            />
                            <Image texture="unref(store.user.avatar).name" />
                            <Label
                                text="store.user.name" 
                                text_color="get_player_ready_color(models.PlayerId.from_player(unref(store.user.player)))" 
                            />
                        </Column>
                        <Image 
                            t-if="unref(store.game.get_player_emote(models.PlayerId.from_player(unref(store.user.player)))) is not None" 
                            texture="unref(store.game.get_player_emote(models.PlayerId.from_player(unref(store.user.player))))"
                        />
                    </Layer>
                    <Column t-style="w[48] | g[4]">
                        <Label
                            t-if="not unref(store.game.players_not_user)"
                            text="f'waiting{unref(dots)}'" 
                            text_color="colors['white']" 
                        />
                        <Row 
                            t-for="player_id, player_info in unref(store.game.players_not_user).items()"
                            t-style="h[6] | g[6]"
                        >
                            <Image t-style="w[8] | h[8]" texture="avatar_type.AVATAR_VARIANTS[player_info.avatar.id].name" />
                            <Label
                                text="player_info.name" 
                                text_color="get_player_ready_color(player_id)" 
                            />
                            <Label
                                text="f'rating: {str(player_info.rating)}'" 
                                text_color="colors['white']" 
                            />
                            <Image 
                                t-if="unref(store.game.get_player_emote(player_id)) is not None" 
                                t-style="w[8] | h[8]"
                                texture="unref(store.game.get_player_emote(player_id))"
                            />
                        </Row>
                    </Column>
                </Row>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
