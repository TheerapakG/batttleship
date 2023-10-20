from tgraphics.color import colors, use_interpolate, with_alpha
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref, Watcher

from ..client import BattleshipClient


@Component.register("MainMenu")
def main_menu(
    window: Window, client: BattleshipClient, name: str | None = None, **kwargs
):
    duration = Ref(0)

    duration_ratio = computed(lambda: (unref(duration) % 3) / 3)

    async def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_watchers.update(
            [
                Watcher.ifref(event.instance.mount_duration, duration.set_value),
            ]
        )

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted">
            <Column 
                gap="0"
                t-style="w['full'](window) | h['full'](window)"
            >
                <Label 
                    text="'test'" 
                    color="use_interpolate(with_alpha(colors['cyan'][300], 0), with_alpha(colors['cyan'][300], 255), duration_ratio)"
                    font_size="50"
                    bold="True"
                />
            </Column>
        </Layer>
        """,
        **kwargs,
    )
