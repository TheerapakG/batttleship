from copy import deepcopy
from dataclasses import replace
from functools import partial

from pyglet.window import key

from tgraphics.color import colors
from tgraphics.event import ComponentMountedEvent
from tgraphics.component import Component, ClickEvent, use_key_pressed
from tgraphics.reactivity import computed, unref, Ref, Watcher
from tgraphics.style import *

from .. import store
from ..component import game_end_overlay
from ...shared import models, ship_type
from ...shared.utils import add, mat_mul_vec


@Component.register("ShipSetup")
def ship_setup(**kwargs):
    window = store.ctx.use_window()

    player_board = store.game.player_board

    player_grid = computed(
        lambda: (
            _player_board.grid
            if (_player_board := unref(player_board)) is not None
            else []
        )
    )
    player_grid_col = computed(
        lambda: len(_player_grid)
        if (_player_grid := unref(player_grid)) is not None
        else 0
    )
    player_grid_rows = computed(
        lambda: (
            [len(col) for col in _player_grid]
            if (_player_grid := unref(player_grid)) is not None
            else []
        )
    )

    player_ship = computed(
        lambda: (
            _player_board.ship
            if (_player_board := unref(player_board)) is not None
            else []
        )
    )
    player_ship_indices = computed(
        lambda: (
            {models.ShipId.from_ship(ship): i for i, ship in enumerate(_player_ship)}
            if (_player_ship := unref(player_ship)) is not None
            else {}
        )
    )

    current_ship_index = Ref[int | None](None)
    current_ship = computed(
        lambda: (
            _player_ship[_current_ship_index]
            if (_player_ship := unref(player_ship)) is not None
            and (_current_ship_index := unref(current_ship_index)) is not None
            else None
        )
    )

    hover_index = Ref[tuple[int, int]]((0, 0))
    submit = Ref(False)
    not_submitable = computed(
        lambda: (
            unref(submit) or not all(ship.tile_position for ship in unref(player_ship))
        )
    )
    player_submits = computed(lambda: [*unref(store.game.board_lookup).keys()])

    def check_submit(player: models.PlayerId):
        if not unref(store.user.is_player(player)):
            return computed(lambda: player in unref(player_submits))
        else:
            return submit

    current_placement = computed(
        lambda: (
            {
                add(
                    unref(hover_index),
                    mat_mul_vec(
                        ship_type.ORIENTATIONS[_current_ship.orientation],
                        offset,
                    ),
                ): sprite
                for offset, sprite in ship_type.SHIP_VARIANTS[
                    _current_ship.ship_variant.id
                ].placement_offsets.items()
            }
            if (_current_ship := unref(current_ship)) is not None
            else {}
        )
    )

    def check_placement():
        if (_player_grid := unref(player_grid)) is None:
            return False
        for col, row in unref(current_placement):
            if col < 0 or col >= len(_player_grid):
                return False
            if row < 0 or row >= len(_player_grid[col]):
                return False
            if not isinstance(unref(_player_grid[col][row]), models.EmptyTile):
                return False
        return True

    current_placement_legal = computed(check_placement)

    def get_tile_color(
        col: int,
        row: int,
    ):
        def _get_tile_color():
            if (_player_grid := unref(player_grid)) is None:
                return colors["red"][300]
            if (col, row) in unref(current_placement):
                if unref(current_placement_legal):
                    return colors["emerald"][300]
                else:
                    return colors["red"][300]
            else:
                match unref(_player_grid[col][row]):
                    case models.EmptyTile():
                        return colors["white"]
                    case models.ShipTile():
                        return colors["emerald"][500]

        return computed(_get_tile_color)

    def get_ship_color(index: int):
        def _get_ship_color():
            if unref(player_ship)[index].tile_position:
                return colors["red"][300]
            else:
                return colors["emerald"][300]

        return computed(_get_ship_color)

    def on_key_r_change(state: bool):
        if state and ((ship_index := unref(current_ship_index)) is not None):
            _current_ship = unref(current_ship)
            unref(player_board).ship[ship_index] = replace(
                _current_ship,
                orientation=(_current_ship.orientation + 1) % 4,
            )
            current_ship.trigger()

    def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_tasks.update(store.game.get_tasks())
        event.instance.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(use_key_pressed(key.R), on_key_r_change),
                ]
                if w is not None
            ]
        )

    def on_tile_click(col: int, row: int, event: ClickEvent):
        if (
            not unref(submit)
            and (_player_board := store.game.get_player_board_ref()) is not None
        ):
            if (
                (ship_index := unref(current_ship_index)) is not None
                and (placement := unref(current_placement)) is not None
                and unref(current_placement_legal)
            ):
                grid = deepcopy(unref(_player_board).grid)
                ship = deepcopy(unref(_player_board).ship)
                for col, row in placement.keys():
                    grid[col][row] = models.ShipTile(
                        models.ShipId.from_ship(unref(player_board).ship[ship_index])
                    )
                ship[ship_index] = replace(
                    ship[ship_index],
                    tile_position=[position for position in placement.keys()],
                )
                _player_board.value = replace(_player_board.value, grid=grid, ship=ship)
                current_ship_index.value = None
            elif isinstance(
                (ship_tile := unref(_player_board).grid[col][row]), models.ShipTile
            ):
                grid = deepcopy(unref(_player_board).grid)
                ship = deepcopy(unref(_player_board).ship)
                for i, s in enumerate(ship):
                    if models.ShipId.from_ship(s) == ship_tile.ship:
                        for col, row in s.tile_position:
                            grid[col][row] = models.EmptyTile()
                        ship[i] = replace(
                            ship[i],
                            tile_position=[],
                        )
                        current_ship_index.value = i
                _player_board.value = replace(_player_board.value, grid=grid, ship=ship)

    def on_tile_mounted(col: int, row: int, event: ComponentMountedEvent):
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

    def on_ship_click(ship_index: int, _event: ClickEvent):
        if (
            not unref(submit)
            and (_player_board := store.game.get_player_board_ref()) is not None
        ):
            grid = deepcopy(unref(_player_board).grid)
            ship = deepcopy(unref(_player_board).ship)
            for col, row in ship[ship_index].tile_position:
                grid[col][row] = models.EmptyTile()
            ship[ship_index] = replace(ship[ship_index], tile_position=[])
            _player_board.value = replace(_player_board.value, grid=grid, ship=ship)
            current_ship_index.value = ship_index

    async def on_submit_button(_e):
        submit.value = True
        await store.game.board_submit()

    return Component.render_xml(
        """
        <Layer>
            <Column t-style="w['full'](window) | h['full'](window) | g[4]" handle-ComponentMountedEvent="on_mounted">
                <EmotePicker />
                <Row t-style="g[1]">
                    <RoundedRectLabelButton 
                        t-for="ship_index in range(len(unref(player_ship)))"
                        text="''" 
                        text_color="colors['white']"
                        color="get_ship_color(ship_index)"
                        hover_color="colors['white']"
                        disabled_color="colors['white']"
                        width="32"
                        height="32"
                        handle-ClickEvent="partial(on_ship_click, ship_index)"
                    />
                </Row>
                <Column t-style="g[1]">
                    <Row t-for="col in range(unref(player_grid_col))" t-style="g[1]">
                        <RoundedRectLabelButton 
                            t-for="row in range(unref(player_grid_rows)[col])"
                            text="''" 
                            text_color="colors['white']"
                            color="get_tile_color(col, row)"
                            hover_color="get_tile_color(col, row)"
                            disabled_color="colors['white']"
                            width="32"
                            height="32"
                            handle-ClickEvent="partial(on_tile_click, col, row)"
                            handle-ComponentMountedEvent="partial(on_tile_mounted, col, row)"
                        />
                    </Row>
                </Column>
                <Row t-style="g[4]">
                    <Layer t-for="player_id, player_info in unref(store.game.players).items()">
                        <Column>
                            <Label
                                text="'Submitted' if unref(check_submit(player_id)) else 'Not Submitted'"
                                text_color="colors['white']" 
                            />
                            <Label
                                text="f'{player_info.name}: {unref(store.game.get_player_point(player_id))} ({unref(store.game.get_player_score(player_id))})'" 
                                text_color="colors['white']" 
                            />
                        </Column>
                        <Image 
                            t-if="unref(store.game.get_player_emote(models.PlayerId.from_player_info(player_info))) is not None" 
                            t-style="w[12] | h[12]"
                            name="unref(store.game.get_player_emote(models.PlayerId.from_player_info(player_info)))"
                        />
                    </Layer>
                    <RoundedRectLabelButton
                        text="'Submit'"
                        disabled="not_submitable"
                        t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                        handle-ClickEvent="on_submit_button"
                    />
                </Row>
            </Column>
            <GameEndOverlay t-if="unref(store.game.result) is not None" />
        </Layer>
        """,
        **kwargs,
    )
