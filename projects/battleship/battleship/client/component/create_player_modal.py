from tgraphics.color import colors, with_alpha
from tgraphics.event import Event
from tgraphics.template import c, text_c, hover_c, disable_c, w, h, r_b, r_t
from tgraphics.component import Component, Window
from tgraphics.reactivity import Ref, unref

from .. import store
from .button import ClickEvent
from ..client import BattleshipClient
from ...shared import models


class PlayerCreatedEvent(Event):
    pass


@Component.register("CreatePlayerModal")
def create_player_modal(window: Window, client: BattleshipClient, **kwargs):
    name = Ref("")

    async def on_create_player_button(event: ClickEvent):
        player = await client.player_create(models.PlayerCreateArgs(unref(name)))
        store.user.save(player)

        await event.instance.capture(PlayerCreatedEvent(event.instance))

    return Component.render_xml(
        """
        <Layer>
            <Rect width="window.width" height="window.height" color="with_alpha(colors['black'],127)" />
            <Column>
                <Layer>
                    <RoundedRect t-template="c['white'] | w[128] | h[64] | r_b[4] | r_t[0]" />
                    <Column gap="16">
                        <LabelButton 
                            text="'Create User'"
                            t-template="c['teal'][400] | hover_c['teal'][500] | disable_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                            handle-ClickEvent="on_create_player_button"
                        />
                        <Layer>
                            <RoundedRect t-template="c['teal'][100] | w[64] | h[9]" />
                            <Input
                                t-model-text="name"
                                color="colors['black']"
                                caret_color="colors['black']"
                                selection_background_color="colors['teal'][300]"
                                t-template="w[56] | h[5]"
                            />
                        </Layer>
                    </Column>
                </Layer>
                <Layer>
                    <RoundedRect t-template="c['teal'][400] | w[128] | h[12] | r_b[0] | r_t[4]" />
                    <Label
                        text="'Registration'"
                        t-template="c['white']"
                    />
                </Layer>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
