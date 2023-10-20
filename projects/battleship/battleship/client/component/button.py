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
    font_size: int | float | None | ReadRef[int | float | None] = None,
    bold: bool | ReadRef[bool] = False,
    italic: bool | ReadRef[bool] = False,
    disable: bool | ReadRef[bool] = False,
    **kwargs
):
    hover = Ref(False)
    bg_color = computed(
        lambda: unref(disable_color)
        if unref(disable)
        else (unref(hover_color) if unref(hover) else unref(color))
    )

    async def on_mounted(event: ComponentMountedEvent):
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
            <Label text="text" color="text_color" font_name="font_name" font_size="font_size" bold="bold" italic="italic" />
        </Layer>
        """,
        **kwargs,
    )
