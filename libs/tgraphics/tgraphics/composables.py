from typing import TypeVar

from .reactivity import ReadRef, computed, unref

T = TypeVar("T")


def use_window(source: ReadRef[T], size: int):
    window = (None,) * size

    def _update_window():
        nonlocal window
        window = window[1:] + (unref(source),)
        return window

    return computed(_update_window)
