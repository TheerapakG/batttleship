from tgraphics.color import colors
from tgraphics.template import color, width, height
from tgraphics.component import Component, Window
from tgraphics.reactivity import ComputedFuture, Ref, unref

from .. import store
from ..component.button import label_button
from ..client_thread import BattleshipClientThread
from ...shared import models


@Component.register("CreatePlayer")
def create_player(window: Window, client: BattleshipClientThread, **kwargs):
    name = Ref("")

    def on_create_player_button(_e):
        def on_player_created(player: models.Player):
            nonlocal window
            nonlocal client

            store.user.save(player)

            from .main_menu import main_menu

            window.scene = main_menu(window=window, client=client)

        ComputedFuture(
            client.player_create(models.PlayerCreateArgs(unref(name)))
        ).add_done_callback(on_player_created)

    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height">
            <LabelButton 
                text="'Create User'" 
                text_color="colors['white']"
                color="colors['cyan'][500]"
                hover_color="colors['cyan'][600]"
                t-template="width[48] | height[9]"
                handle-ClickEvent="on_create_player_button"
            />
            <Layer>
                <RoundedRect t-template="color['white'] | width[64] | height[9]" />
                <Input
                    t-model-text="name"
                    color="colors['black']"
                    caret_color="colors['black']"
                    selection_background_color="colors['cyan'][300]"
                    t-template="width[56] | height[5]"
                />
            </Layer>
        </Column>
        """,
        **kwargs,
    )
