import asyncio
from dataclasses import replace
from functools import partial
from uuid import UUID, uuid4

from pyglet.window import key

from tgraphics.color import colors
from tgraphics.event import ComponentMountedEvent
from tgraphics.component import Component, Window, use_key_pressed
from tgraphics.reactivity import computed, unref, Ref, Watcher
from tgraphics.composables import use_window
from tgraphics.style import c, text_c, hover_c, disabled_c, w, h, g

from .. import store
from ..client import BattleshipClient
from ..component.button import ClickEvent
from ...shared import models, shot_type
from ...shared.utils import add, mat_mul_vec


@Component.register("Game")
def game(
    window: Window,
    client: BattleshipClient,
    room: models.RoomInfo,
    user_board: list[
        list[
            Ref[
                models.EmptyTile
                | models.ShipTile
                | models.ObstacleTile
                | models.MineTile
            ]
        ]
    ],
    **kwargs,
):
    alive_players = Ref(list(room.players))
    dead_players = Ref(list[models.PlayerId]())

    alive_players_not_user = computed(
        lambda: [
            p
            for p in unref(alive_players)
            if not unref(store.user.is_player(models.PlayerId.from_player_info(p)))
        ]
    )

    rev_board_lookup = {
        board_id: player_id for player_id, board_id in room.boards.items()
    }

    board_ids = Ref(set(rev_board_lookup.keys()))
    current_board_id = Ref(
        room.boards[models.PlayerId.from_player_info(unref(alive_players_not_user)[0])]
    )

    async def set_board_id(board_id: models.BoardId):
        current_board_id.value = board_id
        await client.display_board(
            models.DisplayBoardArgs(models.RoomId.from_room_info(room), board_id)
        )

    current_board_player_id = computed(
        lambda: rev_board_lookup[unref(current_board_id)]
    )

    boards = {
        board_id: [
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
        for board_id in unref(board_ids)
    }
    boards_ships = {board_id: set() for board_id in unref(board_ids)}
    boards[
        room.boards[models.PlayerId.from_player(unref(store.user.store))]
    ] = user_board
    current_board = computed(lambda: boards[unref(current_board_id)])

    shots = {
        shot_type.NORMAL_SHOT_VARIANT.id: Ref(-1),
        shot_type.TWOBYTWO_SHOT_VARIANT.id: Ref(2),
        shot_type.SCAN.id: Ref(2),
    }
    current_shot_type_id = Ref[UUID | None](None)
    hover_index = Ref[tuple[int, int]]((0, 0))
    orientation = Ref(0)

    is_turn = Ref(False)
    is_shot_submitable = computed(
        lambda: unref(is_turn)
        and unref(current_board_player_id) != unref(store.user.store)
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
                    unref(c_shot_type_id)
                ].placement_offsets.items()
            }
            if (
                unref(is_shot_submitable)
                and ((c_shot_type_id := unref(current_shot_type_id)) is not None)
            )
            else {}
        )
    )

    def check_shot_placement():
        c_shot_placement = unref(current_shot_placement)
        if not c_shot_placement:
            return False
        for col, row in c_shot_placement.keys():
            c_board = unref(current_board)
            if col < 0 or col >= len(c_board):
                return False
            if row < 0 or row >= len(c_board[col]):
                return False
        return True

    current_shot_placement_legal = computed(check_shot_placement)

    def get_user_tile_color(col: int, row: int):
        def _get_tile_color():
            match unref(user_board[col][row]):
                case models.EmptyTile(hit=False):
                    return colors["slate"][300]
                case models.EmptyTile(hit=True):
                    return colors["cyan"][300]
                case models.ShipTile(hit=False):
                    return colors["emerald"][500]
                case models.ShipTile(hit=True):
                    return colors["red"][500]

        return computed(_get_tile_color)

    def get_current_tile_color(col: int, row: int):
        def _get_tile_color():
            if (col, row) in unref(current_shot_placement):
                if unref(current_shot_placement_legal):
                    return colors["emerald"][300]
                else:
                    return colors["red"][300]
            else:
                match unref(unref(current_board)[col][row]):
                    case models.EmptyTile(hit=False):
                        return (
                            colors["white"]
                            if unref(is_shot_submitable)
                            else colors["slate"][300]
                        )
                    case models.EmptyTile(hit=True):
                        return colors["cyan"][300]
                    case models.ShipTile(hit=False):
                        return colors["emerald"][500]
                    case models.ShipTile(hit=True):
                        return colors["red"][500]

        return computed(_get_tile_color)

    def get_shot_color(
        shot_id: UUID,
    ):
        def _get_shot_color():
            if unref(shots[shot_id]) == 0:
                return colors["red"][400]
            else:
                return colors["emerald"][400]

        return computed(_get_shot_color)

    def get_shot_hover_color(
        shot_id: UUID,
    ):
        def _get_shot_color():
            if unref(shots[shot_id]) == 0:
                return colors["red"][500]
            else:
                return colors["emerald"][500]

        return computed(_get_shot_color)

    async def subscribe_player_leave():
        async for player in client.on_room_leave():
            alive_players.value.remove(player)
            dead_players.value.append(player)
            alive_players.trigger()
            dead_players.trigger()

            player_id = models.PlayerId.from_player_info(player)
            board_id = room.boards[player_id]
            board_ids.value.remove(board_id)
            board_ids.trigger()

            if unref(current_board_id) == board_id and unref(is_turn):
                await set_board_id(
                    room.boards[
                        models.PlayerId.from_player_info(
                            unref(alive_players_not_user)[0]
                        )
                    ]
                )

    async def subscribe_turn_start():
        async for player in client.on_game_turn_start():
            is_turn.value = unref(
                store.user.is_player(models.PlayerId.from_player_info(player))
            )
            if unref(is_turn):
                turn_timer.value = 10
                await set_board_id(
                    room.boards[
                        models.PlayerId.from_player_info(
                            unref(alive_players_not_user)[0]
                        )
                    ]
                )

    async def subscribe_turn_end():
        async for player in client.on_game_turn_end():
            if unref(store.user.is_player(models.PlayerId.from_player_info(player))):
                is_turn.value = False

    async def subscribe_display_board():
        async for board_id in client.on_game_board_display():
            if not unref(is_turn):
                current_board_id.value = board_id

    async def subscribe_shot_board():
        async for shot_result in client.on_game_board_shot():
            boards_ships[shot_result.board].update(shot_result.reveal_ship)
            for r in shot_result.reveal:
                boards[shot_result.board][r.loc[0]][r.loc[1]].value = r.tile

    def on_key_r_change(state: bool):
        if unref(is_turn) and state:
            orientation.value = (unref(orientation) + 1) % 4

    def set_timer(durations: tuple[float | None, ...]):
        if unref(is_turn):
            match durations:
                case (float(begin), float(end)):
                    turn_timer.value = unref(turn_timer) - end + begin

    def on_mounted(event: ComponentMountedEvent):
        event.instance.bound_tasks.update(
            [
                asyncio.create_task(subscribe_player_leave()),
                asyncio.create_task(subscribe_turn_start()),
                asyncio.create_task(subscribe_turn_end()),
                asyncio.create_task(subscribe_display_board()),
                asyncio.create_task(subscribe_shot_board()),
            ]
        )
        event.instance.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(use_key_pressed(key.R), on_key_r_change),
                    Watcher.ifref(
                        use_window(event.instance.mount_duration, 2), set_timer
                    ),
                ]
                if w is not None
            ]
        )

    async def on_tile_click(event: ClickEvent):
        if unref(current_shot_placement_legal) and (
            c_shot_type_id := unref(current_shot_type_id)
        ):
            shot_result = await client.shot_submit(
                models.ShotSubmitArgs(
                    models.RoomId.from_room_info(room),
                    models.Shot(
                        models.ShotTypeVariantId(c_shot_type_id),
                        unref(hover_index),
                        unref(orientation),
                        unref(current_board_id),
                    ),
                )
            )
            boards_ships[shot_result.board].update(shot_result.reveal_ship)
            for r in shot_result.reveal:
                boards[shot_result.board][r.loc[0]][r.loc[1]].value = r.tile

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

    def on_shot_click(shot_id: UUID, _event: ClickEvent):
        if unref(is_turn):
            current_shot_type_id.value = shot_id

    async def on_player_click(player_info: models.PlayerInfo, _event: ClickEvent):
        if unref(is_turn):
            await set_board_id(
                room.boards[models.PlayerId.from_player_info(player_info)]
            )

    return Component.render_xml(
        """
        <Column t-style="w['full'](window) | h['full'](window) | g[4]" handle-ComponentMountedEvent="on_mounted">
            <Row t-style="g[1]">
                <RoundedRectLabelButton 
                    t-for="shot_id, count in shots.items()"
                    text="shot_type.SHOT_VARIANTS[shot_id].text" 
                    text_color="colors['white']"
                    color="get_shot_color(shot_id)"
                    hover_color="get_shot_hover_color(shot_id)"
                    disabled_color="colors['slate'][300]"
                    width="128"
                    height="32"
                    disabled="not unref(is_turn)"
                    handle-ClickEvent="partial(on_shot_click, shot_id)"
                />
            </Row>
            <Row t-style="g[4]">
                <Column t-if="models.PlayerInfo.from_player(unref(store.user.store)) in unref(alive_players)" t-style="g[1]">
                    <Row t-for="col, board_col in enumerate(unref(user_board))" t-style="g[1]">
                        <RoundedRect
                            t-for="row, tile in enumerate(board_col)"
                            color="get_user_tile_color(col, row)"
                            width="32"
                            height="32"
                        />
                    </Row>
                </Column>
                <Column t-style="g[1]">
                    <Row t-for="col, board_col in enumerate(unref(current_board))" t-style="g[1]">
                        <RoundedRectLabelButton 
                            t-for="row, tile in enumerate(board_col)"
                            text="''" 
                            text_color="colors['white']"
                            color="get_current_tile_color(col, row)"
                            hover_color="get_current_tile_color(col, row)"
                            disabled_color="get_current_tile_color(col, row)"
                            width="32"
                            height="32"
                            handle-ClickEvent="on_tile_click"
                            handle-ComponentMountedEvent="partial(on_tile_mounted, col, row)"
                        />
                    </Row>
                </Column>
            </Row>
            <Row t-style="g[4]">
                <RoundedRectLabelButton 
                    t-for="player_info in alive_players_not_user"
                    t-style="disabled_c['slate'][500] | text_c['white'] | w[48] | h[12]"
                    color="colors['teal'][400] if models.PlayerId.from_player_info(player_info) != unref(current_board_player_id) else colors['teal'][600]"
                    hover_color="colors['teal'][500] if models.PlayerId.from_player_info(player_info) != unref(current_board_player_id) else colors['teal'][600]"
                    text="player_info.name"
                    handle-ClickEvent="partial(on_player_click, player_info)"
                />
            </Row>
            <Row>
                <Label t-if="is_turn" text="str(round(unref(turn_timer)))" text_color="colors['white']"/>
            </Row>
        </Column>
        """,
        **kwargs,
    )
