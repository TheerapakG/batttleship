import asyncio
from tgraphics.animation import ease_out
from tgraphics.color import colors, with_alpha
from tgraphics.component import Component, ClickEvent
from tgraphics.event import ComponentMountedEvent
from tgraphics.style import *
from tgraphics.reactivity import Ref, Watcher, computed, unref

from tsocket.shared import ResponseError

from . import modal
from .. import store


@Component.register("GameEndOverlay")
def game_end_overlay(**kwargs):
    window = store.ctx.use_window()

    duration = Ref[float](0)
    duration_in_clamped_ratio = computed(
        lambda: (min(max(unref(duration), 3), 6) - 3) / 3
    )
    duration_zoom_clamped_ratio = computed(
        lambda: (min(max(unref(duration), 6), 7) - 6) / 1
    )

    async def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_watchers.update(
            [
                Watcher.ifref(event.instance.mount_duration, duration.set_value),
            ]
        )
        store.game.ready_players.value = {}
        if unref(store.user.is_player(unref(store.game.result).win)):
            store.game.media_player.queue(store.game.win_sound)
        else:
            store.game.media_player.queue(store.game.lose_sound)
        store.game.media_player.play()

    win_player = computed(
        lambda: unref(store.game.round_players).get(player)
        if (player := unref(store.game.result).win) is not None
        else None
    )

    async def on_rematch_button(event: ClickEvent):
        from ..view.rematch_lobby import rematch_lobby

        await store.game.room_reset()
        asyncio.create_task(store.ctx.set_scene(rematch_lobby()))

    async def on_return_button(event: ClickEvent):
        if (
            (client := unref(store.ctx.client)) is not None
            and (room := unref(store.game.room)) is not None
            and not unref(store.game.room_delete)
        ):
            try:
                await client.room_leave(room)
            except ResponseError:
                pass  # happens if room closes server side while we were sending

        from ..view.main_menu import main_menu

        asyncio.create_task(store.ctx.set_scene(main_menu()))

    return Component.render_xml(
        """
        <Overlay handle-ComponentMountedEvent="on_mounted">
            <Layer>
                <Column>
                    <Column t-style="h[36]">
                        <Offset offset_x="unref(unref(window).width) * (1 - unref(ease_out(duration_in_clamped_ratio)))">
                            <Scale scale_y="unref(ease_out(duration_zoom_clamped_ratio)) * 0.5 + 0.5">
                                <Rect t-style="w['full'](window) | h[36]" color="with_alpha(colors['white'], 223)" />
                            </Scale>
                        </Offset>
                    </Column>
                    <Column t-style="h[36]">
                        <Offset offset_x="-unref(unref(window).width) * (1 - unref(ease_out(duration_in_clamped_ratio)))">
                            <Scale scale_y="unref(ease_out(duration_zoom_clamped_ratio)) * 0.5 + 0.5">
                                <Rect t-style="w['full'](window) | h[36]" color="with_alpha(colors['white'], 223)" />
                            </Scale>
                        </Offset>
                    </Column>
                    <Column t-style="h[36]">
                        <Offset offset_x="unref(unref(window).width) * (1 - unref(ease_out(duration_in_clamped_ratio)))">
                            <Scale scale_y="unref(ease_out(duration_zoom_clamped_ratio)) * 0.5 + 0.5">
                                <Rect t-style="w['full'](window) | h[36]" color="with_alpha(colors['white'], 223)" />
                            </Scale>
                        </Offset>
                    </Column>
                </Column>
                <Column t-if="unref(duration) > 7" t-style="g[16]">
                    <Column t-style="g[8]">
                        <Row t-style="g[4]">
                            <RoundedRectLabelButton 
                                text="'Rematch'"
                                t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                                handle-ClickEvent="on_rematch_button"
                                disabled="store.game.room_delete"
                            />
                            <RoundedRectLabelButton 
                                text="'Return to Menu'"
                                t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                                handle-ClickEvent="on_return_button"
                            />
                        </Row>
                        <Label 
                            text="f'Coins: {r.new_stat.coins} ({r.coin_change:+})' if (r := unref(store.game.result)) is not None else ''" 
                            text_color="colors['black']" 
                        />
                        <Label 
                            text="f'New rating: {r.new_stat.rating} ({r.rating_change:+})' if (r := unref(store.game.result)) is not None else ''" 
                            text_color="colors['black']" 
                        />
                        <Row t-style="g[4]">
                            <Label
                                t-for="player_id, player_info in unref(store.game.round_players).items()"
                                t-style="text_c['black']"
                                text="f'{player_info.name}: {unref(store.game.get_player_point(player_id))} ({unref(store.game.get_player_score(player_id))})'"
                            />
                        </Row>
                        <Label 
                            text="f'{unref(win_player).name} won'" 
                            text_color="colors['black']" 
                        />
                    </Column>
                    <Label 
                        text="f'You Won' if (r := unref(store.game.result)) and unref(store.user.is_player(r.win)) else 'You Lose'" 
                        text_color="colors['black']"
                        font_size="64"
                    />
                </Column>
            </Layer>
        </Overlay>
        """,
        **kwargs,
    )
