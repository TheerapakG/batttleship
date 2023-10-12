from pathlib import Path

from tgraphics.reactivity import Ref, computed, unref

from ..utils import platform_app_directory, converter
from ...shared import models

store = Ref[models.Player | None](None)

name = computed(lambda: player.name if (player := unref(store)) is not None else None)
rating = computed(
    lambda: player.rating if (player := unref(store)) is not None else None
)


def load():
    Path("./.data").mkdir(parents=True, exist_ok=True)
    with open("./.data/user.json", encoding="utf-8") as f:
        store.value = converter.loads(f.read(), models.Player)


def save(player: models.Player):
    Path("./.data").mkdir(parents=True, exist_ok=True)
    with open("./.data/user.json", "w+", encoding="utf-8") as f:
        f.write(converter.dumps(player))
    store.value = player
