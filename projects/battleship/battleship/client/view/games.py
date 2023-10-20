import asyncio
from dataclasses import replace
from functools import partial
from uuid import UUID, uuid4

from pyglet.window import key

from tgraphics.color import colors
from tgraphics.event import ComponentMountedEvent
from tgraphics.component import Component, Window, use_key_pressed
from tgraphics.reactivity import computed, unref, Ref, Watcher
from tgraphics.style import c, text_c, hover_c, disable_c, w, h

from .. import store
from ..client import BattleshipClient
from ..component.button import ClickEvent
from ...shared import models, shot_type
from ...shared.utils import add, mat_mul_vec


@Component.register("games")
def games(
    window: Window, client: BattleshipClient, **kwargs
):
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
    shots = {
            shot_type.NORMAL_SHOT_VARIANT.id :Ref(models.ShotType(shot_type.NORMAL_SHOT_VARIANT, [], 0)),
            shot_type.TWOBYTWO_SHOT_VARIANT.id :Ref(models.ShotType(shot_type.TWOBYTWO_SHOT_VARIANT, [], 0)),
            shot_type.THREEROW_SHOT_VARIANT.id :Ref(models.ShotType(shot_type.THREEROW_SHOT_VARIANT, [], 0)),
        }
    # Assume we pull normal shot type
    current_shot_id = Ref[UUID| None](shot_type.NORMAL_SHOT_VARIANT.id)
    hover_index = Ref[tuple[int, int]]((0, 0))
    submit = Ref(False)
    not_submitable = computed(
        lambda: unref(submit)
        or not all(unref(shot).tile_position for shot in shots.values())
    )
    # player_submits = Ref(set())

    current_placement = computed(
        lambda: (
            {
                add(
                    unref(hover_index),
                    mat_mul_vec(
                        shot_type.ORINTATIONS[unref(shots[shot_id]).orientation],
                        offset,
                    ),
                ): sprite
                for offset, sprite in shot_type.SHOT_VARIANTS[
                    unref(shots[shot_id]).shot_variant.id
                ].placement_offsets.items()
            }
            if (shot_id := unref(current_shot_id)) is not None
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
    # Tile models is subject to change 
    def get_tile_color(
        col: int,
        row: int,
        tile: Ref[
            models.EmptyTile | models.ShipTile | models.ObstacleTile | models.MineTile | models.ChoosenTile | models.MissTile | models.HitTile
        ],
    ):
        def _get_tile_color(
            inner_tile: models.EmptyTile
            | models.ShipTile
            | models.ObstacleTile
            | models.MineTile
            | models.ChoosenTile
            | models.MissTile
            | models.HitTile,
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

    async def subscribe_player_leave():
        async for _ in client.on_room_leave():
            from .main_menu import main_menu

            await window.set_scene(main_menu(window=window, client=client))

    # async def subscribe_room_player_submit():
    #     async for player_id in client.on_room_player_submit():
    #         player_submits.value.add(player_id)
    #         player_submits.trigger()

    # async def subscribe_room_submit():
    #     async for _ in client.on_room_submit():
    #         from .games import games

    #         await window.set_scene(games(window, client))

    def on_key_r_change(state: bool):
        if state and ((shot_id := unref(current_shot_id)) is not None):
            current_shot_ref = shots[shot_id]
            current_shot_ref.value = replace(
                unref(current_shot_ref),
                orientation=(unref(current_shot_ref).orientation + 1) % 4,
            )
            current_shot_ref.trigger()

    async def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_leave()),
                # asyncio.create_task(subscribe_room_player_submit()),
                # asyncio.create_task(subscribe_room_submit()),
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
        if not unref(submit):
            if (placement := unref(current_placement)) is not None and (
                (shot_id := unref(current_shot_id)) is not None
                and unref(current_placement_legal)
            ):
                for col, row in placement.keys():
                    board[col][row].value = models.ChoosenTile
                current_shot_ref = shots[shot_id]
                current_shot_ref.value = replace(
                    unref(current_shot_ref),
                    tile_position=[position for position in placement.keys()],
                )
                current_shot_ref.trigger()
            elif isinstance((shot_tile := unref(board[col][row])), models.ChoosenTile):
                current_shot_ref = shots[shot_tile.ship]
                for col, row in unref(current_shot_ref).tile_position:
                    board[col][row].value = models.EmptyTile()
                current_shot_ref.value = replace(
                    unref(current_shot_ref), tile_position=[]
                )
                current_shot_ref.trigger()
                current_shot_id.value = models.ShipId.from_ship(unref(current_shot_ref))

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

    async def on_submit_button(_e):
        pass

    return Component.render_xml(
        """
        <Column gap="16" width="window.width" height="window.height" handle-ComponentMountedEvent="on_mounted">
            <RoundedRectLabelButton
                text="'Submit'"
                disable="not_submitable"
                t-style="c['teal'][400] | hover_c['teal'][500] | disable_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                handle-ClickEvent="on_submit_button"
            />
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
