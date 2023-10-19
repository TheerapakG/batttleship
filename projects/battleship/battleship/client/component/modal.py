from tgraphics.color import colors, with_alpha
from tgraphics.event import Event
from tgraphics.style import c, w, h, r_b, r_t
from tgraphics.component import Component, Window
from tgraphics.reactivity import ReadRef


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
                <Layer>
                    <RoundedRect t-style="c['white'] | w[128] | h[64] | r_b[4] | r_t[0]" />
                    <Slot component="inner_component" />
                </Layer>
                <Layer>
                    <RoundedRect t-style="c['teal'][400] | w[128] | h[12] | r_b[0] | r_t[4]" />
                    <Label
                        text="name"
                        t-style="c['white']"
                    />
                </Layer>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
