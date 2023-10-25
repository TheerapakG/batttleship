import asyncio
from dataclasses import replace
from functools import partial
from uuid import UUID, uuid4

from pyglet.window import key

from tgraphics.color import colors
from tgraphics.event import ComponentMountedEvent
from tgraphics.component import Component, Window, use_key_pressed
from tgraphics.reactivity import computed, unref, Ref, Watcher
from tgraphics.style import c, text_c, hover_c, disabled_c, w, h

from .. import store
from ..client import BattleshipClient
from ..component.button import ClickEvent
from ...shared import models, shot_type
from ...shared.utils import add, mat_mul_vec


@Component.register("games")
def games(window: Window, client: BattleshipClient, **kwargs):
    board = [
        [
            Ref[
                models.EmptyTile
                | models.ShipTile
                | models.ObstacleTile
                | models.MineTile
                | models.ChosenTile
                | models.MissTile
                | models.HitTile,
            ](models.EmptyTile())
            for _ in range(8)
        ]
        for _ in range(8)
    ]
    shots = {
        shot_type.NORMAL_SHOT_VARIANT.id: Ref(
            models.ShotType(shot_type.NORMAL_SHOT_VARIANT, [], 0)
        ),
        shot_type.TWOBYTWO_SHOT_VARIANT.id: Ref(
            models.ShotType(shot_type.TWOBYTWO_SHOT_VARIANT, [], 0)
        ),
        shot_type.THREEROW_SHOT_VARIANT.id: Ref(
            models.ShotType(shot_type.THREEROW_SHOT_VARIANT, [], 0)
        ),
        shot_type.MINE.id: Ref(models.ShotType(shot_type.MINE, [], 0)),
        shot_type.SCAN.id: Ref(models.ShotType(shot_type.SCAN, [], 0)),
    }
    skills = {
        shot_type.MINE.id: Ref(models.ShotType(shot_type.MINE, [], 0)),
        shot_type.SCAN.id: Ref(models.ShotType(shot_type.SCAN, [], 0)),
    }
    # Assume we pull normal shot type
    receive_shot_id = Ref[UUID | None](shot_type.THREEROW_SHOT_VARIANT.id)
    # Introduce receive_shot_id to restore id from skill
    current_shot_id = Ref[UUID | None](unref(receive_shot_id))
    hover_index = Ref[tuple[int, int]]((0, 0))
    submit = Ref(False)
    skill_chosen = Ref(False)
    chosen = Ref(False)
    not_submitable = computed(
        lambda: unref(submit) or not unref(shots[unref(current_shot_id)]).tile_position
    )
    # player_submits = Ref(set())

    current_placement = computed(
        lambda: (
            {
                add(
                    unref(hover_index),
                    mat_mul_vec(
                        shot_type.ORIENTATIONS[unref(shots[shot_id]).orientation],
                        offset,
                    ),
                ): sprite
                for offset, sprite in shot_type.SHOT_VARIANTS[
                    shot_id
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

    def get_tile_color(
        col: int,
        row: int,
        tile: Ref[
            models.EmptyTile
            | models.ShipTile
            | models.ObstacleTile
            | models.MineTile
            | models.ChosenTile
            | models.MissTile
            | models.HitTile
        ],
    ):
        def _get_tile_color(
            inner_tile: models.EmptyTile
            | models.ShipTile
            | models.ObstacleTile
            | models.MineTile
            | models.ChosenTile
            | models.MissTile
            | models.HitTile,
        ):
            if (col, row) in unref(current_placement):
                if unref(current_placement_legal) and unref(skill_chosen):
                    return colors["violet"][300]
                elif unref(current_placement_legal):
                    return colors["emerald"][300]
                else:
                    return colors["red"][300]
            else:
                match inner_tile:
                    case models.EmptyTile():
                        return colors["white"]
                    case models.ChosenTile():
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
                and not unref(chosen)
            ):
                for col, row in placement.keys():
                    board[col][row].value = models.ChosenTile()
                current_shot_ref = shots[shot_id]
                current_shot_ref.value = replace(
                    unref(current_shot_ref),
                    tile_position=[position for position in placement.keys()],
                )
                current_shot_ref.trigger()
                chosen.value = True
            elif isinstance((shots_tile := unref(board[col][row])), models.ChosenTile):
                current_shot_ref = shots[unref(current_shot_id)]
                for col, row in unref(current_shot_ref).tile_position:
                    board[col][row].value = models.EmptyTile()
                current_shot_ref.value = replace(
                    unref(current_shot_ref), tile_position=[]
                )
                current_shot_ref.trigger()
                chosen.value = False

    async def skill_select(skill_id: UUID, event: ClickEvent):
        if not unref(submit):
            if not unref(skill_chosen):
                skill_chosen.value = True
                current_shot_id.value = skill_id
            elif unref(skill_chosen):
                skill_chosen.value = False
                current_shot_id.value = unref(receive_shot_id)

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
        submit.value = True

        async def submit_data():
            pass

        async def update(data_received):
            pass

        data_received = await submit_data()
        update(data_received)
        if unref(skill_chosen):
            skill_chosen.value = False
            current_shot_id.value = unref(receive_shot_id)

    return Component.render_xml(
        """
        <Row gap="16" width="window.width" height="window.height" handle-ComponentMountedEvent="on_mounted">
            <Column gap="16">
                <Row gap="16">
                    <RoundedRectLabelButton 
                        t-for="skill_id, skill in skills.items()"
                        text="unref(skill).shot_variant.text"
                        disabled="unref(chosen)"
                        t-style="c['teal'][300] | hover_c['teal'][400] | disabled_c['slate'][500] | text_c['white'] | w[12] | h[12]"
                        handle-ClickEvent="partial(skill_select, skill_id)"
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
                            disabled_color="colors['white']"
                            width="32"
                            height="32"
                            handle-ClickEvent="partial(on_tile_click, col, row)"
                            handle-ComponentMountedEvent="partial(on_tile_mounted, col, row)"
                        />
                    </Row>
                </Column>
            </Column>
            <RoundedRectLabelButton
                text="'Submit'"
                disabled="not_submitable"
                t-style="c['teal'][400] | hover_c['teal'][500] | disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                handle-ClickEvent="on_submit_button"
            />
        </Row>
        """,
        **kwargs,
    )
