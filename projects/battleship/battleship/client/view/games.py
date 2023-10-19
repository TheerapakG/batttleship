from tgraphics.color import colors
from tgraphics.component import Component, Window
from tgraphics.reactivity import computed, unref, Ref
from tgraphics.style import c, text_c, hover_c, disable_c, w, h


from .. import store
from ..client import BattleshipClient


@Component.register("Games")
def games(window: Window, client: BattleshipClient, **kwargs):
    skill_activated = Ref("False")
    target_choosen = Ref("False")
    board = []
    # Starting board
    for row in range(8):
        board.append([])
        for column in range(8):
            board[row].append(Ref("Normal Space"))

    def select_grid(column: int, row: int, event):
        if unref(target_choosen) == "True":
            pass
        if unref(skill_activated) == "False":
            if unref(board[row][column]) == "Normal Space":
                board[row][column].value = "Choosen Space"
        elif unref(skill_activated) == "True":
            for each_column in range(8):
                if unref(board[row][each_column]) != "Environment Space":
                    board[row][each_column].value = "Choosen Space"

    async def select_skill(e_):
        skill_activated.value = "True"

    async def confirm_shoot(e_):
        for state in board:
            for grid in state:
                if unref(grid) == "Choosen Space":
                    pass

    return Component.render_xml(
        """
        <Column gap="4" width="window.width" height="window.height">
            <Row t-for="col in range(8)" gap="4">
                <RoundedRectLabelButton 
                    t-for="row in range(8)"
                    text="''" 
                    text_color="colors['white']"
                    color="colors['white']"
                    hover_color="colors['white']"
                    disable_color="colors['white']"
                    width="32"
                    height="32"
                    handle-ClickEvent="select_grid(col, row)"
                />
            </Row>
        </Column>
        """,
        **kwargs,
    )
