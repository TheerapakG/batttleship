from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.style import *

from . import lobby
from .. import store
from ...shared import models


@Component.register("PrivateLobby")
def private_lobby(join_code: str, room: models.RoomInfo, **kwargs):
    window = store.ctx.use_window()
    return Component.render_xml(
        """
        <Layer>
            <Column t-style="w['full'](window) | h['full'](window)" >
                <Pad pad_top="300">
                    <Label text="join_code" text_color="colors['white']" />
                </Pad>
            </Column>
            <Lobby room="room" />
        </Layer>
        """,
        **kwargs,
    )
