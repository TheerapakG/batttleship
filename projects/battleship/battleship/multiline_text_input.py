from tgraphics.color import colors
from tgraphics.event import InputEvent
from tgraphics.component import Column, Input, Window
from tgraphics.reactivity import Ref, computed

import pyglet

window = Window(resizable=True)


text_input = Ref("1\n12\n12\n1")


def set_input_ref(ref: Ref[str]):
    def _handler(event: InputEvent):
        ref.value = event.text

    return _handler


window.scene = Column(
    computed(
        lambda: [
            Input(
                text_input,
                color=colors["white"],
                caret_color=colors["white"],
                selection_background_color=colors["gray"][500],
                selection_color=colors["white"],
                width=100,
                height=100,
                event_handlers={InputEvent: set_input_ref(text_input)},
            ),
        ]
    ),
    gap=16,
    width=window.width,
    height=window.height,
)


pyglet.app.run()
