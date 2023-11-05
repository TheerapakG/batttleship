from contextlib import suppress
from functools import partial

from pyglet.window import key

from tgraphics.color import colors
from tgraphics.event import ComponentMountedEvent
from tgraphics.component import Component, Window, ClickEvent, use_key_pressed
from tgraphics.reactivity import computed, unref, Ref, Watcher
from tgraphics.composables import use_window
from tgraphics.style import c, text_c, hover_c, disabled_c, w, h, g

from .. import store
from ..component import game_end_modal
from ...shared import models, shot_type
from ...shared.utils import add, mat_mul_vec


def _expect_index_error(func, default):
    with suppress(IndexError):
        return func()
    return default


@Component.register("Game")
def game(window: Window, **kwargs):
    player_grid = computed(
        lambda: (
            _player_board.grid
            if (_player_board := unref(store.game.player_board)) is not None
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
            if (_player_board := unref(store.game.player_board)) is not None
            else []
        )
    )

    current_grid = computed(
        lambda: (
            _current_board.grid
            if (_current_board := unref(store.game.current_board)) is not None
            else []
        )
    )

    current_grid_col = computed(
        lambda: len(_current_grid)
        if (_current_grid := unref(current_grid)) is not None
        else 0
    )
    current_grid_rows = computed(
        lambda: (
            [len(col) for col in _current_grid]
            if (_current_grid := unref(current_grid)) is not None
            else []
        )
    )

    current_ship = computed(
        lambda: (
            _current_board.ship
            if (_current_board := unref(store.game.current_board)) is not None
            else []
        )
    )

    current_shot_type_id = Ref[models.ShotVariantId | None](None)
    hover_index = Ref[tuple[int, int]]((0, 0))
    orientation = Ref(0)

    is_current_board_player = (
        store.game.is_current_board_player(models.PlayerId.from_player(player))
        if (player := unref(store.user.player))
        else False
    )

    not_submitable = computed(
        lambda: not unref(store.game.turn) or unref(is_current_board_player)
    )
    turn_timer = Ref(0)

    current_shot_placement = computed(
        lambda: (
            {
                add(
                    unref(hover_index),
                    mat_mul_vec(
                        shot_type.ORIENTATIONS[unref(orientation)],
                        offset,
                    ),
                ): sprite
                for offset, sprite in shot_type.SHOT_VARIANTS[
                    _current_shot_type_id.id
                ].placement_offsets.items()
            }
            if (
                not unref(not_submitable)
                and ((_current_shot_type_id := unref(current_shot_type_id)) is not None)
            )
            else {}
        )
    )

    def check_shot_placement():
        _current_shot_placement = unref(current_shot_placement)
        if not _current_shot_placement:
            return False
        for col, row in _current_shot_placement.keys():
            _current_grid = unref(current_grid)
            if col < 0 or col >= len(_current_grid):
                return False
            if row < 0 or row >= len(_current_grid[col]):
                return False
        return True

    current_shot_placement_legal = computed(check_shot_placement)

    def get_player_tile_color(col: int, row: int):
        def _get_tile_color():
            try:
                match unref(player_grid)[col][row]:
                    case models.EmptyTile(hit=False):
                        return colors["slate"][300]
                    case models.EmptyTile(hit=True):
                        return colors["cyan"][300]
                    case models.ShipTile(hit=False):
                        return colors["emerald"][500]
                    case models.ShipTile(hit=True):
                        return colors["red"][500]
            except IndexError:
                return colors["slate"][300]

        return computed(_get_tile_color)

    def get_current_tile_color(col: int, row: int):
        def _get_tile_color():
            if (col, row) in unref(current_shot_placement):
                if unref(current_shot_placement_legal):
                    return colors["emerald"][300]
                else:
                    return colors["red"][300]
            else:
                try:
                    match unref(current_grid)[col][row]:
                        case models.EmptyTile(hit=False):
                            return (
                                colors["slate"][300]
                                if unref(not_submitable)
                                else colors["white"]
                            )
                        case models.EmptyTile(hit=True):
                            return colors["cyan"][300]
                        case models.ShipTile(hit=False):
                            return colors["emerald"][500]
                        case models.ShipTile(hit=True):
                            return colors["red"][500]
                except IndexError:
                    return colors["slate"][300]

        return computed(_get_tile_color)

    def get_shot_color(
        shot_id: models.ShotVariantId,
    ):
        def _get_shot_color():
            if unref(unref(store.game.shots)[shot_id]) == 0:
                return colors["red"][400]
            else:
                return colors["emerald"][400]

        return computed(_get_shot_color)

    def get_shot_hover_color(
        shot_id: models.ShotVariantId,
    ):
        def _get_shot_color():
            if unref(unref(store.game.shots)[shot_id]) == 0:
                return colors["red"][500]
            else:
                return colors["emerald"][500]

        return computed(_get_shot_color)

    def on_key_r_change(state: bool):
        if unref(store.game.turn) and state:
            orientation.value = (unref(orientation) + 1) % 4

    def on_turn(state: bool):
        if state:
            turn_timer.value = 10

    def set_timer(durations: tuple[float | None, ...]):
        if unref(store.game.turn):
            match durations:
                case (float(begin), float(end)):
                    turn_timer.value = unref(turn_timer) - end + begin

    def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(use_key_pressed(key.R), on_key_r_change),
                    Watcher.ifref(store.game.turn, on_turn),
                    Watcher.ifref(
                        use_window(event.instance.mount_duration, 2), set_timer
                    ),
                ]
                if w is not None
            ]
        )
        event.instance.bound_tasks.update(store.game.get_tasks())

    async def on_tile_click(col: int, row: int, event: ClickEvent):
        if (
            unref(current_shot_placement_legal)
            and (_current_shot_type_id := unref(current_shot_type_id)) is not None
        ):
            await store.game.shot_submit(
                _current_shot_type_id, (col, row), unref(orientation)
            )

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

    def on_shot_click(shot_id: models.ShotVariantId, _event: ClickEvent):
        if unref(store.game.turn):
            current_shot_type_id.value = shot_id

    async def on_player_click(player_info: models.PlayerInfo, _event: ClickEvent):
        if unref(store.game.turn):
            await store.game.set_board_id(
                unref(store.game.board_lookup)[
                    models.PlayerId.from_player_info(player_info)
                ]
            )

    return Component.render_xml(
        """
        <Layer>
            <Column t-style="w['full'](window) | h['full'](window) | g[4]" handle-ComponentMountedEvent="on_mounted">
                <Row t-style="g[1]">
                    <RoundedRectLabelButton 
                        t-for="shot_id, count in unref(store.game.shots).items()"
                        text="shot_type.SHOT_VARIANTS[shot_id.id].text" 
                        text_color="colors['white']"
                        color="get_shot_color(shot_id)"
                        hover_color="get_shot_hover_color(shot_id)"
                        disabled_color="colors['slate'][300]"
                        width="128"
                        height="32"
                        disabled="not unref(store.game.turn)"
                        handle-ClickEvent="partial(on_shot_click, shot_id)"
                    />
                </Row>
                <Row t-style="g[4]">
                    <Column t-if="store.game.user_alive" t-style="g[1]">
                        <Row t-for="col in range(unref(player_grid_col))" t-style="g[1]">
                            <RoundedRect
                                t-for="row in range(_expect_index_error(lambda: unref(player_grid_rows)[col], 0))"
                                color="get_player_tile_color(col, row)"
                                width="32"
                                height="32"
                            />
                        </Row>
                    </Column>
                    <Column t-style="g[1]">
                        <Row t-for="col in range(unref(current_grid_col))" t-style="g[1]">
                            <RoundedRectLabelButton 
                                t-for="row in range(_expect_index_error(lambda: unref(current_grid_rows)[col], 0))"
                                text="''" 
                                text_color="colors['white']"
                                color="get_current_tile_color(col, row)"
                                hover_color="get_current_tile_color(col, row)"
                                disabled_color="get_current_tile_color(col, row)"
                                width="32"
                                height="32"
                                handle-ClickEvent="partial(on_tile_click, col, row)"
                                handle-ComponentMountedEvent="partial(on_tile_mounted, col, row)"
                            />
                        </Row>
                    </Column>
                </Row>
                <Row t-style="g[4]">
                    <RoundedRectLabelButton 
                        t-for="player_info in unref(store.game.alive_players_not_user)"
                        t-style="disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                        color="colors['teal'][600] if unref(store.game.is_current_board_player(models.PlayerId.from_player_info(player_info))) else colors['teal'][400]"
                        hover_color="colors['teal'][600] if unref(store.game.is_current_board_player(models.PlayerId.from_player_info(player_info))) else colors['teal'][500]"
                        text="player_info.name"
                        handle-ClickEvent="partial(on_player_click, player_info)"
                    />
                </Row>
                <Row>
                    <Label t-if="unref(store.game.turn)" text="str(round(unref(turn_timer)))" text_color="colors['white']"/>
                </Row>
                <Row t-style="g[4]">
                    <Label
                        t-for="player_id, player_info in unref(store.game.players).items()"
                        t-style="text_c['white']"
                        text="f'{player_info.name}: {unref(store.game.get_player_point(player_id))} ({unref(store.game.get_player_score(player_id))})'"
                    />
                </Row>
            </Column>
            <GameEndModal t-if="unref(store.game.result) is not None" window="window" client="client" />
        </Layer>
        """,
        **kwargs,
    )
