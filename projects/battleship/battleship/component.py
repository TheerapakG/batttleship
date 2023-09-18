from random import randrange

from tgraphics.component import Center, Column, Label, Rect, Row
from tgraphics.reactivity import Computed, Ref, unref

import pyglet

window = pyglet.window.Window()

window_width = Ref(window.width)
window_height = Ref(window.height)
grid_size = Ref(1)
gap_size = Ref(2)
color = Ref((255, 255, 255, 255))
text = Computed(lambda: f"{unref(grid_size)} {unref(gap_size)} {unref(color)}")


def rand_grid(_):
    grid_size.value = randrange(1, 17)
    gap_size.value = randrange(4, 17, 4)
    color.value = (randrange(127, 256), randrange(127, 255), randrange(127, 255), 255)


grid = Center(
    lambda: Column(
        lambda: [
            Column(
                lambda: [
                    Row(
                        lambda: [
                            Rect(color, width=16, height=16)
                            for _ in range(unref(grid_size))
                        ],
                        gap=gap_size,
                    )
                    for _ in range(unref(grid_size))
                ],
                gap=gap_size,
            ),
            Label(text, (255, 255, 255, 255)),
        ],
        gap=16,
    ),
    _width=window_width,
    _height=window_height,
)


@window.event
def on_draw():
    window.clear()
    grid.draw(0, 0)


@window.event
def on_resize(width, height):
    window_width.value = width
    window_height.value = height


pyglet.clock.schedule_interval(rand_grid, 1.0)
pyglet.app.run()
