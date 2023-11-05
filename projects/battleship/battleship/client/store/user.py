from dataclasses import replace, asdict
from pathlib import Path

from tgraphics.reactivity import Ref, computed, unref

from ..utils import platform_app_directory, converter
from ...shared import models

player = Ref[models.Player | None](None)

name = computed(lambda: user.name if (user := unref(player)) is not None else None)
rating = computed(lambda: user.rating if (user := unref(player)) is not None else None)


def is_player(_player: models.PlayerId):
    return computed(
        lambda: _player == models.PlayerId.from_player(user)
        if (user := unref(player)) is not None
        else False
    )


def load():
    Path("./.data").mkdir(parents=True, exist_ok=True)
    with open("./.data/user.json", encoding="utf-8") as f:
        player.value = converter.loads(f.read(), models.Player)


def save(_player: models.Player):
    Path("./.data").mkdir(parents=True, exist_ok=True)
    with open("./.data/user.json", "w+", encoding="utf-8") as f:
        f.write(converter.dumps(_player))
    player.value = _player


def save_info(_player: models.PlayerInfo):
    Path("./.data").mkdir(parents=True, exist_ok=True)
    if (user := unref(player)) is not None:
        new_user = replace(user, **asdict(_player))
        with open("./.data/user.json", "w+", encoding="utf-8") as f:
            f.write(converter.dumps(new_user))
        player.value = new_user
