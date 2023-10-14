from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import ComputedFuture, computed, unref
from tsocket.shared import Empty

from .. import store
from ..client import BattleshipClient


@Component.register("Games")
def games_ui(window: Window, client: BattleshipClient, **kwargs):
    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
        </Column>
        """,
        **kwargs,
    )
