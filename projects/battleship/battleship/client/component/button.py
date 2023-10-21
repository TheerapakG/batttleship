import math
from typing import Literal

from tgraphics.color import colors
from tgraphics.component import Component, use_hover
from tgraphics.event import Event, ComponentMountedEvent, MousePressEvent, StopPropagate
from tgraphics.reactivity import Ref, ReadRef, Watcher, computed, unref


class ClickEvent(Event):
    pass


@Component.register("RoundedRectLabelButton")
def rounded_rect_label_button(
    text: str | ReadRef[str],
    text_color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]],
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]],
    hover_color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]],
    disable_color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]],
    width: float | ReadRef[float],
    height: float | ReadRef[float],
    radius_bottom_left: int | float | None | ReadRef[int | float | None] = None,
    radius_bottom_right: int | float | None | ReadRef[int | float | None] = None,
    radius_top_left: int | float | None | ReadRef[int | float | None] = None,
    radius_top_right: int | float | None | ReadRef[int | float | None] = None,
    font_name: str | None | ReadRef[str | None] = None,
    font_size: int
    | float
    | Literal["full"]
    | None
    | ReadRef[int | float | Literal["full"] | None] = None,
    bold: bool | ReadRef[bool] = False,
    italic: bool | ReadRef[bool] = False,
    disable: bool | ReadRef[bool] = False,
    **kwargs,
):
    hover = Ref(False)
    bg_color = computed(
        lambda: unref(disable_color)
        if unref(disable)
        else (unref(hover_color) if unref(hover) else unref(color))
    )

    label_multiline = computed(lambda: any(c in unref(text) for c in "\n\u2028\u2029"))

    label_diff = computed(
        lambda: min(unref(width), unref(height)) * (1 - math.sqrt(1 / 2))
    )

    label_width = computed(lambda: unref(width) - unref(label_diff))
    calc_label_height = computed(lambda: unref(height) - unref(label_diff))
    label_height = computed(
        lambda: unref(calc_label_height) if unref(label_multiline) else None
    )
    label_font_size = computed(
        lambda: f_s if (f_s := unref(font_size)) != "full" else unref(calc_label_height)
    )

    def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_watchers.update(
            [
                w
                for w in [Watcher.ifref(use_hover(event.instance), hover.set_value)]
                if w is not None
            ]
        )

    async def on_click(event: MousePressEvent):
        await event.instance.capture(ClickEvent(event.instance))
        return StopPropagate

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted" handle-MousePressEvent="on_click">
            <RoundedRect 
                width="width" 
                height="height" 
                color="bg_color" 
                radius_bottom_left="radius_bottom_left" 
                radius_bottom_right="radius_bottom_right"
                radius_top_left="radius_top_left"
                radius_top_right="radius_top_right"
            />
            <Label 
                text="text" 
                text_color="text_color" 
                font_name="font_name" 
                font_size="label_font_size" 
                bold="bold" 
                italic="italic" 
                width="label_width" 
                height="label_height" 
            />
        </Layer>
        """,
        **kwargs,
    )
