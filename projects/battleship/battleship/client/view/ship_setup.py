from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import computed, unref, Ref
from tsocket.shared import Empty

from .. import store
from ..client import BattleshipClient


@Component.register("shipsetup")
def ship_setup(window: Window, client: BattleshipClient, **kwargs):
    gap_size = 16
    skill_activated = Ref("False")
    target_choosen = Ref("False")
    battleship_state = [[Ref("Normal Space") for _ in range(8)] for i in range(8)]
    color_state = []
    # Starting board
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
