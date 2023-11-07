from tgraphics.color import colors, with_alpha
from tgraphics.component import Component, ClickEvent
from tgraphics.event import Event
from tgraphics.style import *
from tgraphics.reactivity import computed, unref

from tsocket.shared import ResponseError

from . import modal
from .. import store


class PlayerCreatedEvent(Event):
    pass


@Component.register("GameEndModal")
def game_end_modal(**kwargs):
    win_player = computed(
        lambda: unref(store.game.players).get(player)
        if (player := unref(store.game.result).win) is not None
        else None
    )

    async def on_rematch_button(event: ClickEvent):
        from ..view.ship_setup import ship_setup

        await store.ctx.set_scene(ship_setup())
        await store.game.room_reset()

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

        await store.ctx.set_scene(main_menu())

    return Component.render_xml(
        """
        <Modal name="f'You Won' if unref(store.user.is_player(unref(store.game.result).win)) else 'You Lost'">
            <Column t-style="g[4]">
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
                    text="f'New rating: {unref(store.game.result).new_stat.rating} ({unref(store.game.result).rating_change:+})'" 
                    text_color="colors['black']" 
                />
                <Label 
                    text="f'{unref(win_player).name} won'" 
                    text_color="colors['black']" 
                />
            </Column>
        </Modal>
        """,
        **kwargs,
    )
