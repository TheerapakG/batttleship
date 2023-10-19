import asyncio
from dataclasses import replace
from functools import partial
from uuid import UUID, uuid4

from pyglet.window import key

from tgraphics.color import colors
from tgraphics.event import ComponentMountedEvent
from tgraphics.component import Component, Window, use_key_pressed
from tgraphics.reactivity import computed, unref, Ref, Watcher

from .. import store
from ..client import BattleshipClient
from ...shared import models, ship
from ..component.button import ClickEvent


def add(vec1: tuple[int, ...], vec2: tuple[int, ...]):
    return tuple(i + j for i, j in zip(vec1, vec2))


def dot(vec1: tuple[int, ...], vec2: tuple[int, ...]):
    return tuple(i * j for i, j in zip(vec1, vec2))


def mat_mul_vec(mat: tuple[tuple[int, ...], ...], vec: tuple[int, ...]):
    return tuple(sum(dot(i, vec)) for i in mat)


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
    ships = {
        models.ShipId.from_ship(ship): Ref(ship)
        for ship in [
            models.Ship(uuid4(), ship.NORMAL_SHIP_VARIANT, [], 0) for _ in range(4)
        ]
    }
    current_ship_id = Ref[models.ShipId | None](None)
    hover_index = Ref[tuple[int, int]]((0, 0))

    current_placement = computed(
        lambda: (
            {
                add(
                    unref(hover_index),
                    mat_mul_vec(
                        ship.ORINTATIONS[unref(ships[ship_id]).orientation],
                        offset,
                    ),
                ): sprite
                for offset, sprite in ship.SHIP_VARIANTS[
                    unref(ships[ship_id]).ship_variant.id
                ].placement_offsets.items()
            }
            if (ship_id := unref(current_ship_id)) is not None
            else {}
        )
    )

    def check_placement():
        for col, row in unref(current_placement).keys():
            if col < 0 or col >= len(board):
                return False
            if row < 0 or row >= len(board[col]):
                return False
            if not isinstance(unref(board[col][row]), models.EmptyTile):
                return False
        return True

    current_placement_legal = computed(check_placement)

    def get_tile_color(
        col: int,
        row: int,
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
            if (col, row) in unref(current_placement):
                if unref(current_placement_legal):
                    return colors["emerald"][300]
                else:
                    return colors["red"][300]
            else:
                match inner_tile:
                    case models.EmptyTile():
                        return colors["white"]
                    case models.ShipTile():
                        return colors["cyan"][300]

        return computed(lambda: _get_tile_color(unref(tile)))

    def get_ship_color(ship: Ref[models.Ship]):
        def _get_ship_color(
            inner_ship: models.Ship,
        ):
            if inner_ship.tile_position:
                return colors["red"][300]
            else:
                return colors["emerald"][300]

        return computed(lambda: _get_ship_color(unref(ship)))

    async def subscribe_player_leave():
        async for _ in client.on_room_leave():
            from .main_menu import main_menu

            await window.set_scene(main_menu(window=window, client=client))

    def on_key_r_change(state: bool):
        if state and ((ship_id := unref(current_ship_id)) is not None):
            current_ship_ref = ships[ship_id]
            current_ship_ref.value = replace(
                unref(current_ship_ref),
                orientation=(unref(current_ship_ref).orientation + 1) % 4,
            )
            current_ship_ref.trigger()

    async def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_leave()),
            ]
        )
        event.instance.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(use_key_pressed(key.R), on_key_r_change),
                ]
                if w is not None
            ]
        )

    async def on_tile_click(col: int, row: int, event: ClickEvent):
        if (placement := unref(current_placement)) is not None and (
            (ship_id := unref(current_ship_id)) is not None
            and unref(current_placement_legal)
        ):
            for col, row in placement.keys():
                board[col][row].value = models.ShipTile(ship_id)
            current_ship_ref = ships[ship_id]
            current_ship_ref.value = replace(
                unref(current_ship_ref),
                tile_position=[position for position in placement.keys()],
            )
            current_ship_ref.trigger()
            current_ship_id.value = None
        elif isinstance((ship_tile := unref(board[col][row])), models.ShipTile):
            current_ship_ref = ships[ship_tile.ship]
            for col, row in unref(current_ship_ref).tile_position:
                board[col][row].value = models.EmptyTile()
            current_ship_ref.value = replace(unref(current_ship_ref), tile_position=[])
            current_ship_ref.trigger()
            current_ship_id.value = models.ShipId.from_ship(unref(current_ship_ref))

    async def on_tile_mounted(col: int, row: int, event: ComponentMountedEvent):
        event.instance.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        event.instance.hover,
                        lambda _: hover_index.set_value((col, row)),
                    )
                ]
                if w is not None
            ]
        )

    async def on_ship_click(ship_id: int, _event: ClickEvent):
        current_ship_id.value = ship_id

    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height" handle-ComponentMountedEvent="on_mounted">
            <Row gap="4">
                <RoundedRectLabelButton 
                    t-for="ship_id, ship in ships.items()"
                    text="''" 
                    text_color="colors['white']"
                    color="get_ship_color(ship)"
                    hover_color="colors['white']"
                    disable_color="colors['white']"
                    width="32"
                    height="32"
                    handle-ClickEvent="partial(on_ship_click, ship_id)"
                />
            </Row>
            <Column gap="4">
                <Row t-for="col, board_col in enumerate(board)" gap="4">
                    <RoundedRectLabelButton 
                        t-for="row, tile in enumerate(board_col)"
                        text="''" 
                        text_color="colors['white']"
                        color="get_tile_color(col, row, tile)"
                        hover_color="get_tile_color(col, row, tile)"
                        disable_color="colors['white']"
                        width="32"
                        height="32"
                        handle-ClickEvent="partial(on_tile_click, col, row)"
                        handle-ComponentMountedEvent="partial(on_tile_mounted, col, row)"
                    />
                </Row>
            </Column>
        </Column>
        """,
        **kwargs,
    )
