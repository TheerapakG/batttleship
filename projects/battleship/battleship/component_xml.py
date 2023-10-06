from random import randrange

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import Ref, computed, unref

import pyglet

window = Window(resizable=True)


def try_parse_int(string: str, default: int):
    try:
        return int(string)
    except (TypeError, ValueError):
        return default


grid_size_input = Ref("1")
grid_size = computed(lambda: try_parse_int(unref(grid_size_input), 1))
gap_size_input = Ref("2")
gap_size = computed(lambda: try_parse_int(unref(gap_size_input), 2))
color = Ref((255, 255, 255, 255))
text = computed(lambda: f"{unref(grid_size)} {unref(gap_size)} {unref(color)}")


def rand_grid(_):
    color.value = (randrange(127, 256), randrange(127, 255), randrange(127, 255), 255)


@Component.register("InputComponent")
def input_component(text_ref: Ref[str], **kwargs):
    return Component.render_xml(
        """
        <Layer>
            <Rect color="colors['white']" width="50" height="30" />
            <Input
                text="text_ref"
                color="colors['black']"
                caret_color="colors['black']"
                selection_background_color="colors['cyan'][300]"
                selection_color="colors['black']"
                width="50"
                height="20"
            />
        </Layer>
        """,
        **kwargs,
    )


window.scene = Component.render_xml(
    """
    <Column gap="16" width="window.width" height="window.height">
        <Column gap="gap_size">
            <Row t-for="_ in range(unref(grid_size))" gap="gap_size">
                <Rect t-for="_ in range(unref(grid_size))" color="color" width="16" height="16" />
            </Row>
        </Column>
        <Label text="text" color="colors['white']" />
        <Row gap="16">
            <InputComponent text_ref="grid_size_input" />
            <Label t-if="unref(grid_size) % 2 == 0" text="'!'" color="colors['white']" />
            <InputComponent text_ref="gap_size_input" />
            <Label t-if="unref(gap_size) % 2 == 0" text="'!'" color="colors['white']" />
        </Row>
    </Column>
    """
)

pyglet.clock.schedule_interval(rand_grid, 1.0)
pyglet.app.run()
