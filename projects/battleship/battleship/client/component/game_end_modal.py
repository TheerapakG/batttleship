from tgraphics.color import colors, with_alpha
from tgraphics.event import Event
from tgraphics.style import c, text_c, hover_c, disabled_c, w, h, r_b, r_t, g
from tgraphics.component import Component, Window, ClickEvent
from tgraphics.reactivity import Ref, unref

from tsocket.shared import ResponseError

from . import modal
from .. import store
from ..client import BattleshipClient
from ...shared import models


class PlayerCreatedEvent(Event):
    pass


@Component.register("GameEndModal")
def game_end_modal(window: Window, client: BattleshipClient, **kwargs):
    async def on_rematch_button(event: ClickEvent):
        from ..view.ship_setup import ship_setup

        await unref(window).set_scene(ship_setup(window, client))
        await store.game.room_reset()

    async def on_return_button(event: ClickEvent):
        if not unref(store.game.room_delete):
            try:
                await client.room_leave(unref(store.game.room))
            except ResponseError:
                pass  # happens if room closes server side while we were sending

        from ..view.main_menu import main_menu

        await window.set_scene(main_menu(window, client))

    return Component.render_xml(
        """
        <Modal window="window" name="f'You Won' if unref(store.user.is_player(unref(store.game.result).win)) else 'You Lost'">
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
            </Column>
        </Modal>
        """,
        **kwargs
    )
