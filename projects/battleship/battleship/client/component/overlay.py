from tgraphics.color import colors, with_alpha
from tgraphics.style import *
from tgraphics.component import Component
from tgraphics.reactivity import ReadRef

from .. import store


@Component.register("Overlay")
def overlay(children: list[Component] | ReadRef[list[Component]], **kwargs):
    window = store.ctx.use_window()

    return Component.render_xml(
        """
        <Layer>
            <Rect t-style="w['full'](window) | h['full'](window)" color="with_alpha(colors['black'],63)" />
            <Column>
                <Slot components="children" />
            </Column>
        </Layer>
        """,
        **kwargs,
    )
