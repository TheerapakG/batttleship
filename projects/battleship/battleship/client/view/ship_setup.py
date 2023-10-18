import asyncio
from functools import partial
from uuid import uuid4

from tgraphics.color import colors
from tgraphics.event import ComponentMountedEvent
from tgraphics.component import Component, Window
from tgraphics.reactivity import computed, unref, Ref

from .. import store
from ..client import BattleshipClient
from ...shared import models, ship


@Component.register("ShipSetup")
def ship_setup(window: Window, client: BattleshipClient, **kwargs):
    board = [
        [
            Ref[
                models.EmptyTile
                | models.ShipTile
                | models.ObstacleTile
                | models.MineTile
            ](models.EmptyTile())
            for _ in range(8)
        ]
        for _ in range(8)
    ]
    available_ship = [
        Ref(models.Ship(uuid4(), ship.NORMAL_SHIP_VARIANT, [], 0)) for _ in range(4)
    ]

    def get_tile_color(
        tile: Ref[
            models.EmptyTile | models.ShipTile | models.ObstacleTile | models.MineTile
        ],
    ):
        def _get_tile_color(
            inner_tile: models.EmptyTile
            | models.ShipTile
            | models.ObstacleTile
            | models.MineTile,
        ):
            match inner_tile:
                case models.EmptyTile():
                    return colors["white"]
                case models.ShipTile():
                    return colors["emerald"][300]

        return computed(lambda: _get_tile_color(unref(tile)))

    async def on_tile_click(col: int, row: int, event):
        pass

    async def subscribe_player_leave():
        async for _ in client.on_room_leave():
            from .main_menu import main_menu

            await window.set_scene(main_menu(window=window, client=client))

    async def on_mounted(event: ComponentMountedEvent):
        # TODO: async component
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_leave()),
            ]
        )

    # Starting board
    return Component.render_xml(
        """
        <Column gap="4" width="window.width" height="window.height" handle-ComponentMountedEvent="on_mounted">
            <Row t-for="col, board_col in enumerate(board)" gap="4">
                <LabelButton 
                    t-for="row, tile in enumerate(board_col)"
                    text="''" 
                    text_color="colors['white']"
                    color="get_tile_color(tile)"
                    hover_color="colors['white']"
                    disable_color="colors['white']"
                    width="32"
                    height="32"
                    handle-ClickEvent="partial(on_tile_click, col, row)"
                />
            </Row>
        </Column>
        """,
        **kwargs,
    )
