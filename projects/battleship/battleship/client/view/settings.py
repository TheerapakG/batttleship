import asyncio
from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.style import *
from tgraphics.reactivity import Ref, computed, unref

from .. import store
from ...shared import models


@Component.register("Settings")
def settings(**kwargs):
    window = store.ctx.use_window()
    default_volume = Ref(unref(store.bgm.bgm_volume) * 10)
    display_sfx = computed(
        lambda: "Enable" if unref(store.game.sfx_volume) == 1.0 else "Disable"
    )

    def change_color():
        if unref(display_sfx) == "Enable":
            return colors["emerald"][500]
        else:
            return colors["red"][500]

    async def increase_volume(_e):
        default_volume.value = unref(default_volume) + 1
        store.bgm.bgm_volume.value = unref(default_volume) / 10
        store.bgm.set_volume(unref(default_volume) / 10)

    async def decrease_volume(_e):
        default_volume.value = unref(default_volume) - 1
        store.bgm.bgm_volume.value = unref(default_volume) / 10
        store.bgm.set_volume(unref(default_volume) / 10)

    async def page_return(_e):
        from .main_menu import main_menu

        asyncio.create_task(store.ctx.set_scene(main_menu()))

    async def disable_sfx(_e):
        if store.game.sfx_volume.value == 1.0:
            store.game.sfx_volume.value = 0.0
        elif store.game.sfx_volume.value == 0.0:
            store.game.sfx_volume.value = 1.0

    return Component.render_xml(
        """
        <Layer>
            <Column t-style="w['full'](window) | h['full'](window) | g[4]">
                <RoundedRectLabelButton 
                    text="f'SFX is currently {unref(display_sfx.value)}'" 
                    text_color="colors['white']"
                    color="change_color()"
                    hover_color="change_color()"
                    disabled_color="colors['slate'][300]"
                    width="200"
                    height="48"
                    handle-ClickEvent="disable_sfx"
                />
                <Row gap="30">
                    <RoundedRectLabelButton
                        text="'-'"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[12] | h[12]"
                        disabled="computed(lambda: unref(unref(default_volume))==0)"
                        handle-ClickEvent="decrease_volume"
                    />
                    <Label text="f'{unref(unref(default_volume))}'" text_color="colors['white']"/>
                    <RoundedRectLabelButton
                        text="'+'"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[12] | h[12]"
                        disabled="computed(lambda: unref(unref(default_volume))==10)"
                        handle-ClickEvent="increase_volume"
                    />
                </Row>
            </Column>
            <Absolute t-style="w['full'](window) | h['full'](window)" stick_bottom="False">
                <Pad t-style="p_l[4] | p_t[4]">
                    <RoundedRectLabelButton 
                        text="'Return'"
                        font_size="20"
                        t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[24] | h[10]"
                        handle-ClickEvent="page_return"
                    />
                </Pad>
            </Absolute>
        </Layer>
        """,
        **kwargs,
    )
