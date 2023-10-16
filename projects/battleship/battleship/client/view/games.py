from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import computed, unref, Ref
from tsocket.shared import Empty

from .. import store
from ..client import BattleshipClient


@Component.register("Games")
def games_ui(window: Window, client: BattleshipClient, **kwargs):
    gap_size = 10
    grid_row = [chr(i + 97) for i in range(8)[::-1]]
    grid_column = [str(i) for i in range(1, 9)]
    skill_activated = Ref("False")
    battleship_state = {}
    for row in grid_row:
        for column in grid_column:
            battleship_state[(column,row)] = Ref("white")
    # Starting board

    async def select_shooting_spot(e_):
        async def check_position(column, row):
            if unref(skill_activated) == "False":
                if unref(battleship_state[(column, row)]) == "white":
                    battleship_state[(column, row)].value = "green"
            elif unref(skill_activated) == "True":
                # A skill that bomb a row
                for each_column in range(1,9):
                    if battleship_state[(column, each_column)] != "brown":
                        battleship_state[(column, each_column)].value = "green"
    async def select_skill(e_):
        skill_activated.value = "True"
    async def confirm_shoot(e_):
        async def check_hit():
            pass
        for position, color in battleship_state.items():
            if unref(color) == "green":
                pass
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
