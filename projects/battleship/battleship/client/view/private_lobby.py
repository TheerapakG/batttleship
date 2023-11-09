from tgraphics.color import colors
from tgraphics.component import Component
from tgraphics.style import *

from . import lobby
from .. import store
from ...shared import models


@Component.register("PrivateLobby")
def private_lobby(join_code: str, **kwargs):
    window = store.ctx.use_window()
    return Component.render_xml(
        """
        <Layer>
            <Absolute t-style="w['full'](window) | h['full'](window)" >
                <Column t-style="w['full'](window)">
                    <Pad t-style="p_b[16]">
                        <Label text="f'code: {join_code}'" text_color="colors['white']" />
                    </Pad>
                </Column>
            </Absolute>
            <Lobby />
        </Layer>
        """,
        **kwargs,
    )
