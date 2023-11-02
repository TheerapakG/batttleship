import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tsocket.shared import Empty
from tgraphics.style import c, text_c, hover_c, disabled_c, w, h, r_b, r_t, r_l, r_r, g

from .. import store
from ..client import BattleshipClient
from ..component import create_player_modal
from ...shared import models


@Component.register("profile")
def profile(window: Window, client: BattleshipClient, **kwargs):
    online = Ref(None)

    async def return_button(_e):
        from .main_menu import main_menu

        await window.set_scene(main_menu(window, client))

    # async def set_online_status():
    #    unref(online.replace(None,"Online")) if client.online(Empty()) else unref(online.replace(None,"Offline"))

    return Component.render_xml(
        """
        <Layer>
            <Pad pad_right="800">
                <Pad pad_bottom="440">
                    <RoundedRectLabelButton 
                        text="'Return'"
                        font_size="20"
                        t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[24] | h[10]"
                        handle-ClickEvent="return_button"
                    />
                </Pad>
            </Pad>
            <Pad pad_bottom="440">
                <Label text="f'{unref(store.user.name)}'" font_size="36"/>
            </Pad>
            <Column t-style="w['full'](window) | h['full'](window) | g[5]">
                <Row t-style="g[10]">
                    <Label text="f'Wins: '" text_color="colors['white']" />
                    <Label text="f'Total Scores: '" text_color="colors['white']" />

                </Row>
                <Row t-style="g[10]">
                    <Label text="f'Status: {unref(online)}'" text_color="colors['white']" />
                    <Label text="f'Ratings: {unref(store.user.rating)}'" text_color="colors['white']" />

                </Row>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
