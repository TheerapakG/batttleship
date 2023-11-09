from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.reactivity import unref
from tgraphics.style import *

from .. import store


@Component.register("profile")
def profile(**kwargs):
    window = store.ctx.use_window()

    async def return_button(_e):
        from .main_menu import main_menu

        asyncio.create_task(store.ctx.set_scene(main_menu()))

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
            <Pad pad_bottom="440">
                <Label text="f'{unref(store.user.name)}'" font_size="36"/>
            </Pad>
            <Column t-style="w['full'](window) | h['full'](window) | g[5]">
                <Row t-style="g[10]">
                    <Label text="f'Wins: '" text_color="colors['white']" />
                    <Label text="f'Total Scores: '" text_color="colors['white']" />

                </Row>
                <Row t-style="g[10]">
                    <Label text="f'Ratings: {unref(store.user.rating)}'" text_color="colors['white']" />
                    <Label text="f'Coins: {unref(store.user.coins)}'" text_color="colors['white']" />
                </Row>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
