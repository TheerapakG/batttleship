from random import randrange

from tgraphics.component import Column, Input, Label, Layer, Rect, Row, Window
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


window.scene = Column(
    computed(
        lambda: [
            Column(
                computed(
                    lambda: [
                        Row(
                            [
                                Rect(color, width=16, height=16)
                                for _ in range(unref(grid_size))
                            ],
                            gap=gap_size,
                        )
                        for _ in range(unref(grid_size))
                    ]
                ),
                gap=gap_size,
            ),
            Label(text, (255, 255, 255, 255)),
            Row(
                [
                    Layer(
                        [
                            Rect((255, 255, 255, 255), width=50, height=30),
                            Input(
                                grid_size_input,
                                (0, 0, 0, 255),
                                (0, 0, 0, 255),
                                (127, 127, 127, 255),
                                (0, 0, 0, 255),
                                width=50,
                                height=20,
                            ),
                        ]
                    ),
                    Layer(
                        [
                            Rect((255, 255, 255, 255), width=50, height=30),
                            Input(
                                gap_size_input,
                                (0, 0, 0, 255),
                                (0, 0, 0, 255),
                                (127, 127, 127, 255),
                                (0, 0, 0, 255),
                                width=50,
                                height=20,
                            ),
                        ]
                    ),
                ],
                gap=16,
            ),
        ]
    ),
    gap=16,
    width=window.width,
    height=window.height,
)


pyglet.clock.schedule_interval(rand_grid, 1.0)
pyglet.app.run()
