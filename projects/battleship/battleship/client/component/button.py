from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.event import Event, ComponentMountedEvent, MousePressEvent
from tgraphics.reactivity import Ref, ReadRef, Watcher, computed, unref


class ClickEvent(Event):
    pass


@Component.register("LabelButton")
def label_button(
    text: str | ReadRef[str],
    text_color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]],
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]],
    hover_color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]],
    width: float | ReadRef[float],
    height: float | ReadRef[float],
    **kwargs
):
    radius = computed(lambda: unref(height) / 2)

    hover = Ref(False)
    bg_color = computed(lambda: unref(hover_color) if unref(hover) else unref(color))

    def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_watchers.update(
            [
                w
                for w in [Watcher.ifref(event.instance.hover, hover.set_value)]
                if w is not None
            ]
        )

    def on_click(event: MousePressEvent):
        event.instance.capture(ClickEvent(event.instance))

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted" handle-MousePressEvent="on_click">
            <RoundedRect width="width" height="height" radius="radius" color="bg_color" />
            <Label text="text" color="text_color" />
        </Layer>
        """,
        **kwargs,
    )
