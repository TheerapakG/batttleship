import asyncio

from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.reactivity import Ref, computed, unref
from tgraphics.style import *

from .. import store
from ...shared import models, emote_type


@Component.register("Gacha")
def gacha(**kwargs):
    window = store.ctx.use_window()

    pull_disabled = computed(lambda: unref(store.user.player).coins < 100)
    last_pull = Ref(None)

    async def return_button(_e):
        from .main_menu import main_menu

        await store.ctx.set_scene(main_menu())

    async def pull_button(_e):
        if (client := unref(store.ctx.client)) is not None and (
            user := unref(store.user.player)
        ) is not None:
            result = await client.gacha(models.BearingPlayerAuth.from_player(user))
            store.user.save(result.player)
            last_pull.value = emote_type.EMOTE_VARIANTS[result.emote.id].name

    return Component.render_xml(
        """
        <Layer>
            <Absolute t-style="w['full'](window) | h['full'](window)" stick_bottom="False">
                <Pad t-style="p_l[4] | p_t[4]">
                    <RoundedRectLabelButton 
                        text="'Return'"
                        font_size="20"
                        t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[24] | h[10]"
                        handle-ClickEvent="return_button"
                    />
                </Pad>
            </Absolute>
            <Column t-style="w['full'](window) | h['full'](window) | g[4]">
                <RoundedRectLabelButton 
                    text="'Pull 1: 100 coins'"
                    t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[96] | h[10]"
                    disabled="unref(pull_disabled)"
                    handle-ClickEvent="pull_button"
                />
                <Image t-if="unref(last_pull) is not None" texture="unref(last_pull)" />
                <Label 
                    text="f'coins: {unref(store.user.player).coins}'"
                    t-style="text_c['white']"
                />
            </Column>
        </Layer>
        """,
        **kwargs,
    )
