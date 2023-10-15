from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import ComputedFuture, computed, unref, Ref
from tsocket.shared import Empty

from .. import store
from ..client import BattleshipClient


@Component.register("Games")
def games_ui(window: Window, client: BattleshipClient, **kwargs):
    gap_size = 1
    grid_row = [str(i) for i in range(1, 9)[::-1]]
    # [8,7,6,5,4,3,2,1]
    grid_column = [chr(i + 97) for i in range(8)]
    # [a,b,c,d,e,f,g,h]

    battleship_state = {}
    for the_row in grid_row:
        for the_column in grid_column:
            battleship_state[the_column + the_row] = Ref("white")
    # Starting board

    def select_shooting_spot(position):
        if unref(battleship_state[position]) == "white":
            battleship_state[position] = "green"

    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Column gap="gap_size">
                <Row t-for="row in grid_row" gap="gap_size">
                    <LabelButton 
                        t-for="column in grid_column"
                        text="column+row" 
                        text_color="colors[unref(battleship_state[column+row])]"
                        color="colors['white']"
                        hover_color="colors['green']"
                        width="1"
                        height="1"
                        handle-ClickEvent="select_shooting_spot(column+row)"
                    />
                </Row>
            </Column>
        </Column>
        """,
        **kwargs,
    )
