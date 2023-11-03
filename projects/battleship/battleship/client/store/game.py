import asyncio
from contextlib import suppress
from copy import deepcopy
from dataclasses import replace
from functools import partial
from uuid import uuid4

from pyglet.media import Player

from tgraphics.component import Window, loader
from tgraphics.reactivity import Ref, computed, unref

from . import user
from ..client import BattleshipClient
from ...shared import models, ship_type, shot_type

media_player = Player()

hit_sound = loader.media("hit.wav", False)
miss_sound = loader.media("miss.wav", False)

window: Ref[Window | None] = Ref(None)
client: Ref[BattleshipClient | None] = Ref(None)

room: Ref[models.RoomId | None] = Ref(None)

players = Ref(dict[models.PlayerId, models.PlayerInfo]())
alive_players = Ref(list[models.PlayerInfo]())
dead_players = Ref(list[models.PlayerInfo]())

player_scores = Ref(dict[models.PlayerId, Ref[int]]())
player_points = Ref(dict[models.PlayerId, Ref[int]]())


def _get_player_score(player: models.PlayerId):
    if (player_ref := unref(player_scores).get(player)) is None:
        return 0
    return unref(player_ref)


def get_player_score(player: models.PlayerId):
    return computed(partial(_get_player_score, player))


def _get_player_point(player: models.PlayerId):
    if (player_ref := unref(player_points).get(player)) is None:
        return 0
    return unref(player_ref)


def get_player_point(player: models.PlayerId):
    return computed(partial(_get_player_point, player))


async def room_reset():
    alive_players.value = [*unref(players).values()]
    dead_players.value = []
    player_scores.value = {
        models.PlayerId.from_player_info(player): Ref(0)
        for player in unref(alive_players)
    }
    current_board_id.value = None
    board_lookup.value = {}
    board_lookup.trigger()
    boards.value = {}
    boards.trigger()
    shots.value = {
        models.ShotVariantId.from_shot_variant(shot_type.NORMAL_SHOT_VARIANT): Ref(-1),
        models.ShotVariantId.from_shot_variant(shot_type.TWOBYTWO_SHOT_VARIANT): Ref(2),
        models.ShotVariantId.from_shot_variant(shot_type.SCAN): Ref(2),
    }
    shots.trigger()
    turn.value = False
    await generate_board()


alive_players_not_user = computed(
    lambda: [
        p
        for p in unref(alive_players)
        if not unref(user.is_player(models.PlayerId.from_player_info(p)))
    ]
)

user_alive = computed(
    lambda: any(
        user.is_player(models.PlayerId.from_player_info(player))
        for player in unref(alive_players)
    )
)

boards: Ref[dict[models.BoardId, Ref[models.Board]]] = Ref({})
board_lookup: Ref[dict[models.PlayerId, models.BoardId]] = Ref({})

current_board_id: Ref[models.BoardId | None] = Ref(None)
turn = Ref(False)


async def set_board_id(board_id: models.BoardId):
    current_board_id.value = board_id
    if (
        unref(turn)
        and (_client := unref(client)) is not None
        and (_room := unref(room)) is not None
    ):
        await _client.display_board(models.DisplayBoardArgs(_room, board_id))


shots = Ref(
    {
        models.ShotVariantId.from_shot_variant(shot_type.NORMAL_SHOT_VARIANT): Ref(-1),
        models.ShotVariantId.from_shot_variant(shot_type.TWOBYTWO_SHOT_VARIANT): Ref(2),
        models.ShotVariantId.from_shot_variant(shot_type.SCAN): Ref(2),
    }
)


def get_player_board_ref():
    if (user_player := unref(user.player)) is None:
        return None
    if (
        board_id := unref(board_lookup).get(models.PlayerId.from_player(user_player))
    ) is None:
        return None
    if (board := unref(boards).get(board_id)) is None:
        return None
    return board


def _get_player_board():
    if (user_player := unref(user.player)) is None:
        return None
    if (
        board_id := unref(board_lookup).get(models.PlayerId.from_player(user_player))
    ) is None:
        return None
    if (board := unref(boards).get(board_id)) is None:
        return None
    return unref(board)


player_board = computed(_get_player_board)


def _get_current_board():
    if (board := unref(boards).get(unref(current_board_id))) is None:
        return None
    return unref(board)


current_board = computed(_get_current_board)


def is_current_board_player(player: models.PlayerId):
    return computed(
        lambda: player == _current_board.player
        if (_current_board := unref(current_board)) is not None
        else False
    )


async def generate_board():
    if (user_player := unref(user.player)) is not None:
        board = models.Board(
            uuid4(),
            models.PlayerId.from_player(user_player),
            unref(room),
            [[models.EmptyTile() for _ in range(8)] for _ in range(8)],
            [
                models.Ship(uuid4(), ship_type.NORMAL_SHIP_VARIANT, [], 0),
                models.Ship(uuid4(), ship_type.NORMAL_SHIP_VARIANT, [], 0),
                models.Ship(uuid4(), ship_type.T_SHIP_VARIANT, [], 0),
                models.Ship(uuid4(), ship_type.T_SHIP_VARIANT, [], 0),
            ],
        )
        board_id = models.BoardId.from_board(board)
        boards.value[board_id] = Ref(board)
        board_lookup.value[board.player] = board_id
        boards.trigger()
        board_lookup.trigger()
        return board
    else:
        raise Exception()


def process_shot_result(shot_result: models.ShotResult, play_audio: bool = True):
    board = unref(boards)[shot_result.board]
    new_grid = deepcopy(board.value.grid)
    player_scores.value[shot_result.player].value += sum(
        1
        for r in shot_result.reveal
        if isinstance(r.tile, models.ShipTile) and r.tile.hit
    )
    for r in shot_result.reveal:
        new_grid[r.loc[0]][r.loc[1]] = r.tile
    board.value = replace(
        board.value,
        grid=new_grid,
        ship=[*set([*board.value.ship, *shot_result.reveal_ship])],
    )
    if play_audio:
        if any(isinstance(r.tile, models.ShipTile) for r in shot_result.reveal):
            media_player.queue(hit_sound)
        else:
            media_player.queue(miss_sound)
        media_player.play()


async def board_submit():
    await unref(client).board_submit(unref(player_board))


async def shot_submit(
    shot_variant: models.ShotVariantId, position: tuple[int, int], orientation: int
):
    if (_room := unref(room)) is not None and (
        _current_board_id := unref(current_board_id)
    ) is not None:
        shot_result = await unref(client).shot_submit(
            models.ShotSubmitArgs(
                _room,
                models.Shot(shot_variant, position, orientation, _current_board_id),
            ),
        )

        process_shot_result(shot_result, False)


async def subscribe_player_leave():
    async for player in unref(client).on_room_leave():
        alive_players.value.remove(player)
        dead_players.value.append(player)
        alive_players.trigger()
        dead_players.trigger()

        with suppress(KeyError, IndexError):
            player_id = models.PlayerId.from_player_info(player)
            del board_lookup.value[player_id]
            board_id = unref(board_lookup)[player_id]
            del boards.value[board_id]

            if unref(current_board_id) == board_id:
                await set_board_id(
                    unref(board_lookup)[
                        models.PlayerId.from_player_info(
                            unref(alive_players_not_user)[0]
                        )
                    ]
                )


async def subscribe_room_player_submit():
    async for data in unref(client).on_room_player_submit():
        if data.board not in unref(boards):
            boards.value[data.board] = Ref(
                models.Board(
                    data.board.id,
                    data.player,
                    unref(room),
                    [[models.EmptyTile() for _ in range(8)] for _ in range(8)],
                    [],
                )
            )
        boards.trigger()
        board_lookup.value[data.player] = data.board
        board_lookup.trigger()


async def subscribe_room_submit():
    async for _ in unref(client).on_room_submit():
        await set_board_id(models.BoardId.from_board(unref(player_board)))
        from ..view.game import game

        asyncio.create_task(unref(window).set_scene(game(unref(window))))


async def subscribe_turn_start():
    async for player in unref(client).on_game_turn_start():
        turn.value = unref(user.is_player(models.PlayerId.from_player_info(player)))
        if unref(turn):
            await set_board_id(
                unref(board_lookup)[
                    models.PlayerId.from_player_info(unref(alive_players_not_user)[0])
                ]
            )


async def subscribe_turn_end():
    async for player in unref(client).on_game_turn_end():
        if unref(user.is_player(models.PlayerId.from_player_info(player))):
            turn.value = False


async def subscribe_display_board():
    async for board_id in unref(client).on_game_board_display():
        if not unref(turn):
            current_board_id.value = board_id


async def subscribe_shot_board():
    async for shot_result in unref(client).on_game_board_shot():
        if not unref(user.is_player(shot_result.player)):
            process_shot_result(shot_result)


async def do_game_reset():
    await room_reset()

    from ..view.ship_setup import ship_setup

    await unref(window).set_scene(ship_setup(unref(window), unref(client)))


async def subscribe_game_reset():
    async for _ in unref(client).on_game_reset():
        asyncio.create_task(do_game_reset())


async def subscribe_game_end():
    async for game_result in unref(client).on_game_end():
        player_points.value[
            models.PlayerId.from_player_info(game_result[-1])
        ].value += 1
        # TODO:
        pass


def get_tasks():
    return [
        asyncio.create_task(subscribe_player_leave()),
        asyncio.create_task(subscribe_room_player_submit()),
        asyncio.create_task(subscribe_room_submit()),
        asyncio.create_task(subscribe_turn_start()),
        asyncio.create_task(subscribe_turn_end()),
        asyncio.create_task(subscribe_display_board()),
        asyncio.create_task(subscribe_shot_board()),
        asyncio.create_task(subscribe_game_reset()),
        asyncio.create_task(subscribe_game_end()),
    ]
