from tgraphics.color import colors, with_alpha
from tgraphics.component import Component, ClickEvent
from tgraphics.event import Event
from tgraphics.style import *
from tgraphics.reactivity import Ref, unref

from . import modal
from .. import store
from ...shared import models


class PlayerCreatedEvent(Event):
    pass


@Component.register("CreatePlayerModal")
def create_player_modal(**kwargs):
    name = Ref("")

    async def on_create_player_button(event: ClickEvent):
        player = await unref(store.ctx.use_client()).player_create(
            models.PlayerCreateArgs(unref(name))
        )
        store.user.save(player)

        await event.instance.capture(PlayerCreatedEvent(event.instance))

    return Component.render_xml(
        """
        <Modal name="'registration'">
            <Column t-style="g[4]">
                <RoundedRectLabelButton 
                    text="'Create User'"
                    t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                    handle-ClickEvent="on_create_player_button"
                />
                <Layer>
                    <RoundedRect t-style="c['teal'][100] | w[64] | h[9]" />
                    <Input
                        t-model-text="name"
                        caret_color="colors['black']"
                        selection_background_color="colors['teal'][300]"
                        t-style="text_c['black'] | w[56] | h[5]"
                    />
                </Layer>
            </Column>
        </Modal>
        """,
        **kwargs
    )
