import asyncio
from contextlib import suppress
from copy import deepcopy
from dataclasses import replace
from functools import partial
from uuid import UUID, uuid4

from pyglet.media import Player

from tgraphics.component import loader
from tgraphics.reactivity import Ref, computed, unref

from . import ctx, user
from .. import store
from ...shared import models, ship_type, shot_type, emote_type

media_player = Player()

hit_sound = loader.media("sfx/hit.wav", False)
miss_sound = loader.media("sfx/miss.wav", False)
found_sound = loader.media("sfx/found.wav", False)
sfx_volume = Ref(1.0)

room: Ref[models.RoomId | None] = Ref(None)

skin: Ref[str] = Ref("")

players = Ref(dict[models.PlayerId, models.PlayerInfo]())
alive_players = Ref(list[models.PlayerInfo]())
dead_players = Ref(list[models.PlayerInfo]())

player_scores = Ref(dict[models.PlayerId, Ref[int]]())
player_points = Ref(dict[models.PlayerId, Ref[int]]())

emotes = Ref(dict[models.PlayerId, tuple[models.EmoteVariantId, UUID]]())


def get_player_emote(player_id: models.PlayerId):
    return computed(
        lambda: emote_type.EMOTE_VARIANTS[tup[0].id].name
        if (tup := unref(emotes).get(player_id)) is not None
        else None
    )


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
    room_delete.value = False
    result.value = None
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
    await generate_board(unref(skin))


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

room_delete = Ref(False)


async def set_board_id(board_id: models.BoardId):
    current_board_id.value = board_id
    if (
        unref(turn)
        and (client := unref(ctx.client)) is not None
        and (_room := unref(room)) is not None
    ):
        await client.display_board(models.DisplayBoardArgs(_room, board_id))


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


async def generate_board(skin: str):
    if (user_player := unref(user.player)) is not None:
        board = models.Board(
            uuid4(),
            models.PlayerId.from_player(user_player),
            unref(room),
            [[models.EmptyTile() for _ in range(8)] for _ in range(8)],
            [models.Ship(uuid4(), s, [], 0) for s in ship_type.SHIP_SKIN_LOOKUP[skin]],
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
        if shot_result.hit:
            if any(isinstance(r.tile, models.ShipTile) for r in shot_result.reveal):
                media_player.queue(hit_sound)
            else:
                media_player.queue(miss_sound)
        else:
            if any(isinstance(r.tile, models.ShipTile) for r in shot_result.reveal):
                media_player.queue(found_sound)

        media_player.play()


async def board_submit():
    if (client := unref(ctx.client)) is not None:
        await client.board_submit(unref(player_board))


async def shot_submit(
    shot_variant: models.ShotVariantId, position: tuple[int, int], orientation: int
):
    if (
        (client := unref(ctx.client)) is not None
        and (_room := unref(room)) is not None
        and (_current_board_id := unref(current_board_id)) is not None
    ):
        shot_result = await client.shot_submit(
            models.ShotSubmitArgs(
                _room,
                models.Shot(shot_variant, position, orientation, _current_board_id),
            ),
        )

        process_shot_result(shot_result)
        shots.value[shot_variant].value = unref(shots.value[shot_variant]) - 1


async def subscribe_player_leave():
    if (client := unref(ctx.client)) is not None:
        async for player in client.on_room_leave():
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
    if (client := unref(ctx.client)) is not None:
        async for data in client.on_room_player_submit():
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
    if (client := unref(ctx.client)) is not None:
        async for _ in client.on_room_submit():
            await set_board_id(models.BoardId.from_board(unref(player_board)))
            from ..view.game import game

            asyncio.create_task(store.ctx.set_scene(game()))


async def subscribe_room_delete():
    if (client := unref(ctx.client)) is not None:
        async for _ in client.on_room_delete():
            room_delete.value = True


async def subscribe_turn_start():
    if (client := unref(ctx.client)) is not None:
        async for player in client.on_game_turn_start():
            turn.value = unref(user.is_player(models.PlayerId.from_player_info(player)))
            if unref(turn):
                await set_board_id(
                    unref(board_lookup)[
                        models.PlayerId.from_player_info(
                            unref(alive_players_not_user)[0]
                        )
                    ]
                )


async def subscribe_turn_end():
    if (client := unref(ctx.client)) is not None:
        async for player in client.on_game_turn_end():
            if unref(user.is_player(models.PlayerId.from_player_info(player))):
                turn.value = False


async def subscribe_display_board():
    if (client := unref(ctx.client)) is not None:
        async for board_id in client.on_game_board_display():
            if not unref(turn):
                current_board_id.value = board_id


async def subscribe_shot_board():
    if (client := unref(ctx.client)) is not None:
        async for shot_result in client.on_game_board_shot():
            if not unref(user.is_player(shot_result.player)):
                process_shot_result(shot_result)


async def do_game_reset():
    from ..view.ship_setup import ship_setup

    await store.ctx.set_scene(ship_setup())
    await room_reset()


async def subscribe_game_reset():
    if (client := unref(ctx.client)) is not None:
        async for _ in client.on_game_reset():
            asyncio.create_task(do_game_reset())


async def do_emote_reset(player: models.PlayerId, u: UUID):
    await asyncio.sleep(3)
    if emotes.value[player][1] == u:
        del emotes.value[player]
        emotes.update()


async def subscribe_emote_display():
    if (client := unref(ctx.client)) is not None:
        async for emote_display in client.on_emote_display():
            u = uuid4()
            emotes.value[emote_display.player] = (emote_display.emote, u)
            emotes.update()
            asyncio.create_task(do_emote_reset(emote_display.player, u))


result: Ref[models.GameEndData | None] = Ref(None)


async def subscribe_game_end():
    if (client := unref(ctx.client)) is not None:
        async for game_result in client.on_game_end():
            player_points.value[game_result.win].value += 1
            user.save_info(game_result.new_stat)
            result.value = game_result


def get_tasks():
    return [
        asyncio.create_task(subscribe_player_leave()),
        asyncio.create_task(subscribe_room_player_submit()),
        asyncio.create_task(subscribe_room_submit()),
        asyncio.create_task(subscribe_room_delete()),
        asyncio.create_task(subscribe_turn_start()),
        asyncio.create_task(subscribe_turn_end()),
        asyncio.create_task(subscribe_display_board()),
        asyncio.create_task(subscribe_shot_board()),
        asyncio.create_task(subscribe_game_reset()),
        asyncio.create_task(subscribe_game_end()),
        asyncio.create_task(subscribe_emote_display()),
    ]
