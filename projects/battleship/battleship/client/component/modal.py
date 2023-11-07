from tgraphics.color import colors, with_alpha
from tgraphics.event import Event
from tgraphics.style import *
from tgraphics.component import Component
from tgraphics.reactivity import ReadRef

from .. import store


class PlayerCreatedEvent(Event):
    pass


@Component.register("Modal")
def modal(
    name: str | ReadRef[str],
    children: list[Component] | ReadRef[list[Component]],
    **kwargs
):
    window = store.ctx.use_window()

    return Component.render_xml(
        """
        <Layer>
            <Rect t-style="w['full'](window) | h['full'](window)" color="with_alpha(colors['black'],127)" />
            <Column>
                <Layer>
                    <RoundedRect t-style="c['white'] | w[128] | h[64] | r_b[4] | r_t[0]" />
                    <Slot components="children" />
                </Layer>
                <Layer>
                    <RoundedRect t-style="c['teal'][400] | w[128] | h[12] | r_b[0] | r_t[4]" />
                    <Label
                        text="name"
                        t-style="text_c['white']"
                    />
                </Layer>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
