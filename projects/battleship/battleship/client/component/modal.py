from tgraphics.color import colors, with_alpha
from tgraphics.event import Event
from tgraphics.template import c, text_c, hover_c, disable_c, w, h, r_b, r_t
from tgraphics.component import Component, Window
from tgraphics.reactivity import Ref, ReadRef, unref

from .. import store
from .button import ClickEvent
from ..client import BattleshipClient
from ...shared import models


class PlayerCreatedEvent(Event):
    pass


@Component.register("Modal")
def modal(
    window: Window,
    name: str | ReadRef[str],
    inner_component: Component | ReadRef[Component],
    **kwargs
):
    return Component.render_xml(
        """
        <Layer>
            <Rect width="window.width" height="window.height" color="with_alpha(colors['black'],127)" />
            <Column>
                <Slot component="inner_component" />
                <Layer>
                    <RoundedRect t-template="c['teal'][400] | w[128] | h[12] | r_b[0] | r_t[4]" />
                    <Label
                        text="name"
                        t-template="c['white']"
                    />
                </Layer>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
