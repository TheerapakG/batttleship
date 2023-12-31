from cattrs import ClassValidationError
from dataclasses import replace, asdict
from pathlib import Path

from tgraphics.reactivity import Ref, computed, unref

from ..utils import platform_app_directory, converter
from ...shared import models, avatar_type

player = Ref[models.Player | None](None)

name = computed(lambda: user.name if (user := unref(player)) is not None else None)
avatar = computed(
    lambda: avatar_type.AVATAR_VARIANTS[user.avatar.id]
    if (user := unref(player)) is not None
    else None
)
rating = computed(lambda: user.rating if (user := unref(player)) is not None else None)
coins = computed(lambda: user.coins if (user := unref(player)) is not None else None)


def is_player(_player: models.PlayerId):
    return computed(
        lambda: _player == models.PlayerId.from_player(user)
        if (user := unref(player)) is not None
        else False
    )


def load():
    Path("./.data").mkdir(parents=True, exist_ok=True)
    try:
        with open("./.data/user.json", encoding="utf-8") as f:
            player.value = converter.loads(f.read(), models.Player)
    except ClassValidationError:
        pass


def save(_player: models.Player):
    Path("./.data").mkdir(parents=True, exist_ok=True)
    with open("./.data/user.json", "w+", encoding="utf-8") as f:
        f.write(converter.dumps(_player))
    player.value = _player
    player.update()


def save_info(_player: models.PlayerInfo):
    Path("./.data").mkdir(parents=True, exist_ok=True)
    if (user := unref(player)) is not None:
        new_user = replace(user, **asdict(_player))
        with open("./.data/user.json", "w+", encoding="utf-8") as f:
            f.write(converter.dumps(new_user))
        player.value = new_user
        player.update()
