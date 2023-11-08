from functools import partial

from tgraphics.color import colors, with_alpha
from tgraphics.event import Event
from tgraphics.style import *
from tgraphics.component import Component, ClickEvent
from tgraphics.reactivity import unref

from . import modal
from .. import store
from ...shared import models, emote_type


class PlayerCreatedEvent(Event):
    pass


@Component.register("EmotePicker")
def emote_picker(**kwargs):
    async def on_emote_button(emote: emote_type.EmoteVariant, event: ClickEvent):
        if (client := unref(store.ctx.client)) is not None and (
            room := unref(store.game.room)
        ) is not None:
            await client.emote_display(
                models.EmoteDisplayArgs(
                    room,
                    models.EmoteVariantId.from_emote_variant(emote),
                )
            )

    return Component.render_xml(
        """
        <Row t-style="g[4]">
            <RoundedRectImageButton 
                t-for="emote_id, emote_variant in emote_type.EMOTE_VARIANTS.items()"
                texture="emote_variant.name"
                t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | w[16] | h[16]"
                disabled="emote_id not in unref(store.user.player).emotes"
                handle-ClickEvent="partial(on_emote_button, emote_variant)"
            />
        </Row>
        """,
        **kwargs,
    )
