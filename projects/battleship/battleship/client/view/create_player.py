from tgraphics.color import colors
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
                color="colors['cyan'][400]"
                hover_color="colors['cyan'][500]"
                width="128"
                height="32 + 4"
                handle-ClickEvent="on_create_player_button"
            />
            <Layer>
                <RoundedRect color="colors['white']" width="260" height="36" radius="18" />
                <Input
                    t-model-text="name"
                    color="colors['black']"
                    caret_color="colors['black']"
                    selection_background_color="colors['cyan'][300]"
                    selection_color="colors['black']"
                    width="224"
                    height="20"
                />
            </Layer>
        </Column>
        """,
        **kwargs,
    )
