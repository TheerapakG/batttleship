import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window, use_height
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref
from tsocket.shared import Empty
from tgraphics.size import widths, heights
from tgraphics.style import (
    c,
    text_c,
    hover_c,
    disabled_c,
    w,
    h,
    p_l,
    r_b,
    r_t,
    r_l,
    r_r,
    g,
)

from .. import store
from ..client import BattleshipClient
from ...shared import models, emote_type


@Component.register("Gacha")
def gacha(window: Window, client: BattleshipClient, **kwargs):
    pull_disabled = computed(lambda: unref(store.user.player).coins < 100)
    last_pull = Ref(None)

    async def return_button(_e):
        from .main_menu import main_menu

        await window.set_scene(main_menu(window, client))

    async def pull_button(_e):
        if (user := unref(store.user.player)) is not None:
            result = await client.gacha(models.BearingPlayerAuth.from_player(user))
            store.user.save(result.player)
            last_pull.value = emote_type.EMOTE_VARIANTS[result.emote.id].name

    return Component.render_xml(
        """
        <Layer center_x="False" center_y="False">
            <Pad pad_left="widths[4]" pad_bottom="unref(use_height(window)) - heights[10] - heights[4]">
                <RoundedRectLabelButton 
                    text="'Return'"
                    font_size="20"
                    t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[24] | h[10]"
                    handle-ClickEvent="return_button"
                />
            </Pad>
            <Column t-style="w['full'](window) | h['full'](window) | g[4]">
                <RoundedRectLabelButton 
                    text="'Pull 1: 100 coins'"
                    t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[96] | h[10]"
                    disabled="unref(pull_disabled)"
                    handle-ClickEvent="pull_button"
                />
                <Image t-if="unref(last_pull) is not None" name="unref(last_pull)" />
                <Label 
                    text="f'coins: {unref(store.user.player).coins}'"
                    t-style="text_c['white']"
                />
            </Column>
        </Layer>
        """,
        **kwargs,
    )
