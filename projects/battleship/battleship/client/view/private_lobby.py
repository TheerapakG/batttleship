from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.style import w, h

from .lobby import lobby
from ..client import BattleshipClient
from ...shared import models


@Component.register("PrivateLobby")
def private_lobby(
    window: Window,
    client: BattleshipClient,
    join_code: str,
    room: models.RoomInfo,
    **kwargs
):
    lobby_component = lobby(window, client, room)

    return Component.render_xml(
        """
        <Layer>
            <Column t-style="w['full'](window) | h['full'](window)" >
                <Pad pad_top="300">
                    <Label text="join_code" text_color="colors['white']" />
                </Pad>
            </Column>
            <Slot component="lobby_component" />
        </Layer>
        """,
        **kwargs,
    )
