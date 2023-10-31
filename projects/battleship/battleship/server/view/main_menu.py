import asyncio

from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, unref
from tgraphics.style import w, h

from ..server import BattleshipServer


@Component.register("MainMenu")
def main_menu(window: Window, server: BattleshipServer, **kwargs):
    online_count = Ref(None)

    async def set_online_count():
        while True:
            online_count.value = len(server.sessions)
            await asyncio.sleep(1.0)

    async def on_mounted(event: ComponentMountedEvent):
        # TODO: async component
        event.instance.bound_tasks.update([asyncio.create_task(set_online_count())])

    return Component.render_xml(
        """
        <Column t-style="w['full'](window) | h['full'](window)" handle-ComponentMountedEvent="on_mounted">
            <Label text="f'There are currently {unref(online_count)} player(s) online.'" text_color="colors['white']" />
        </Column>
        """,
        **kwargs,
    )
