from tgraphics.component import Window, Component
from tgraphics.reactivity import Ref, computed, unref

from ..client import BattleshipClient

window: Ref[Window | None] = Ref(None)
client: Ref[BattleshipClient | None] = Ref(None)


def use_window():
    return computed(lambda: unref(window))


def use_client():
    return computed(lambda: unref(client))


async def set_scene(component: Component | None):
    if (win := unref(window)) is not None:
        await win.set_scene(component)
