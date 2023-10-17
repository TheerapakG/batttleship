
from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import computed, unref, Ref
from tsocket.shared import Empty


from .. import store
from ..client import BattleshipClient
from ..component.button import ClickEvent

@Component.register("Games")
def games_ui(window: Window, client: BattleshipClient, **kwargs):
    gap_size = 16
    grid_row = [i for i in range(8)]
    grid_column = [i for i in range(8)]
    skill_activated = Ref("False")
    target_choosen = Ref("False")
    battleship_state = []
    color_state = []
    # Starting board
    for row in range(8):
        battleship_state.append([])
        for column in range(8):
            battleship_state[row].append(Ref("Normal Space"))
    for row in range(8):
        battleship_state.append([])

    def select_shooting_spot(position: (int, int)):
        def shooting(event: ClickEvent):
            (column, row) = position
            if unref(target_choosen) == "True":
                pass
            if unref(skill_activated) == "False":
                if unref(battleship_state[row][column]) == "Normal Space":
                    battleship_state[row][column].value = "Choosen Space"
                print(battleship_state)
            elif unref(skill_activated) == "True":
                # A skill that bomb a row
                for each_column in range(8):
                    if unref(battleship_state[row][each_column]) != "Environment Space":
                        battleship_state[row][each_column].value = "Choosen Space"
    def select_skill(e_):
        skill_activated.value = "True"
    async def confirm_shoot(e_):
        async def check_hit():
            pass
        for state in battleship_state:
            for values in state:
                if unref(values) == "Choosen Space":
                    pass
    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <Column gap="gap_size">
                <Row t-for="row in grid_row" gap="gap_size">
                    <LabelButton 
                        t-for="column in grid_column"
                        text="str(row)+str(column)" 
                        text_color="colors['white']"
                        color="colors['white']"
                        hover_color="colors['white']"
                        width="4"
                        height="4"
                        handle-ClickEvent="select_shooting_spot((column, row))"
                    />
                </Row>
            </Column>
        </Column>
        """,
        **kwargs,
    )
