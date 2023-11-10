import asyncio
from functools import partial

from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.reactivity import unref
from tgraphics.style import *

from .. import store
from ...shared import models, avatar_type


@Component.register("profile")
def profile(**kwargs):
    window = store.ctx.use_window()

    async def return_button(_e):
        from .main_menu import main_menu

        asyncio.create_task(store.ctx.set_scene(main_menu()))

    async def on_avatar_button(avatar_variant: avatar_type.AvatarVariant, _e):
        if (client := unref(store.ctx.client)) is not None and (
            user := unref(store.user.player)
        ) is not None:
            result = await client.player_avatar_set(
                models.PlayerAvatarSetArgs(
                    models.BearingPlayerAuth.from_player(user).auth_token,
                    models.AvatarVariantId.from_avatar_variant(avatar_variant),
                )
            )
            store.user.save(result)

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
                    <Label text="f'Ratings: {unref(store.user.rating)}'" text_color="colors['white']" />
                    <Label text="f'Coins: {unref(store.user.coins)}'" text_color="colors['white']" />
                </Row>
                <Row t-style="g[10]">
                    <RoundedRectImageButton 
                        t-for="avatar_variant in avatar_type.AVATAR_VARIANTS.values()"
                        texture="avatar_variant.name"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | w[16] | h[16] | r_t[4] | r_b[4] | r_l[4] | r_r[4]"
                        handle-ClickEvent="partial(on_avatar_button, avatar_variant)"
                    />
                </Row>
                <Image texture="unref(store.user.avatar).name" />
            </Column>
        </Layer>
        """,
        **kwargs,
    )
