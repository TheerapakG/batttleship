from tgraphics.color import colors, with_alpha
from tgraphics.style import *
from tgraphics.component import Component
from tgraphics.reactivity import ReadRef

from . import overlay
from .. import store


@Component.register("Modal")
def modal(
    name: str | ReadRef[str],
    children: list[Component] | ReadRef[list[Component]],
    **kwargs
):
    window = store.ctx.use_window()

    return Component.render_xml(
        """
        <Overlay>
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
        </Overlay>
        """,
        **kwargs,
    )
