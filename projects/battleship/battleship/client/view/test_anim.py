from tgraphics.animation import ease_out
from tgraphics.color import colors, use_interpolate, with_alpha
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, computed, unref, Watcher
from tgraphics.style import w, h, g

from ..client import BattleshipClient


@Component.register("MainMenu")
def main_menu(
    window: Window, client: BattleshipClient, name: str | None = None, **kwargs
):
    duration = Ref(0)
    duration_clamped_ratio = computed(lambda: min(unref(duration), 3) / 3)
    duration_ratio = computed(lambda: (max(unref(duration) - 3, 0) % 1) / 1)

    async def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_watchers.update(
            [
                Watcher.ifref(event.instance.mount_duration, duration.set_value),
            ]
        )

    return Component.render_xml(
        """
        <Layer handle-ComponentMountedEvent="on_mounted">
            <Column t-style="w['full'](window) | h['full'](window) | g[0]">
                <Offset offset_y="-360 + 360 * unref(ease_out(duration_clamped_ratio))">
                    <Scale scale_x="ease_out(duration_clamped_ratio)" scale_y="ease_out(duration_clamped_ratio)">
                            <Label 
                                text="'test'" 
                                text_color="use_interpolate(with_alpha(colors['cyan'][300], 127), with_alpha(colors['cyan'][300], 255), duration_ratio)"
                                font_size="50"
                                bold="True"
                            />
                    </Scale>
                </Offset>
            </Column>
        </Layer>
        """,
        **kwargs,
    )
