from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import computed, unref, Ref
from tsocket.shared import Empty

from .. import store
from ..client import BattleshipClient


@Component.register("shipsetup")
def ship_setup(window: Window, client: BattleshipClient, **kwargs):
    grid_row = [chr(i + 97) for i in range(8)[::-1]]
    grid_column = [str(i) for i in range(1, 9)]
    battleship_state = {}
    battleship_type = []
    for row in grid_row:
        for column in grid_column:
            battleship_state[(column, row)] = Ref("white")
    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Column gap="gap_size">
                <Row t-for="row in grid_row" gap="gap_size">
                    <LabelButton 
                        t-for="column in grid_column"
                        text="row+column" 
                        text_color="colors[unref(battleship_state[(column,row)])]"
                        color="colors['white']"
                        hover_color="colors['white']"
                        width="1"
                        height="1"
                        handle-ClickEvent="select_shooting_spot"
                    />
                </Row>
            </Column>
        </Column>
        """,
        **kwargs,
    )
