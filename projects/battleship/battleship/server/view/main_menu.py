import asyncio
from functools import partial

from tgraphics.color import colors
from tgraphics.component import Component, Window, ClickEvent
from tgraphics.event import ComponentMountedEvent
from tgraphics.reactivity import Ref, unref
from tgraphics.style import c, text_c, hover_c, disabled_c, w, h, r_b, r_t, g

from ..server import BattleshipServer
from ..models import Room


@Component.register("MainMenu")
def main_menu(window: Window, server: BattleshipServer, **kwargs):
    online_count = Ref(None)
    rooms = Ref[list[Room]]([])

    async def update():
        while True:
            online_count.value = len(server.sessions)
            rooms.value = [*server.rooms.values()]
            rooms.trigger()
            await asyncio.sleep(1.0)

    async def on_mounted(event: ComponentMountedEvent):
        # TODO: async component
        event.instance.bound_tasks.update([asyncio.create_task(update())])

    async def on_reset_button(room: Room, event: ClickEvent):
        await room.do_room_reset(hard=True)

    return Component.render_xml(
        """
        <Column t-style="w['full'](window) | h['full'](window)" handle-ComponentMountedEvent="on_mounted">
            <Column t-for="room in unref(rooms)">
                <Row t-style="g[4]">
                    <Label text="f', '.join([p.name for p in room.players.values()])" text_color="colors['white']" />
                    <RoundedRectLabelButton 
                        text="'Reset'"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                        handle-ClickEvent="partial(on_reset_button, room)"
                    />
                </Row>
            </Column>
            <Label text="'Active Rooms:'" text_color="colors['white']" />
            <Label text="f'There are currently {unref(online_count)} player(s) online.'" text_color="colors['white']" />
        </Column>
        """,
        **kwargs,
    )
