from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass, field
from queue import Empty, SimpleQueue
from typing import Any, ClassVar, Generic, Protocol, TypeGuard, TypeVar, overload
import weakref

import pyglet

T = TypeVar("T")


class Triggerable(Protocol):
    def trigger(self):
        ...


@dataclass
class Effect:
    tracking: ClassVar[list["Effect | None"]] = []
    update_queue: ClassVar[deque[weakref.ref[Triggerable]]] = deque()
    update_set: ClassVar[set[weakref.ref[Triggerable]]] = set()
    watchers: weakref.WeakSet["Watcher"] = field(default_factory=weakref.WeakSet)
    dependents: weakref.WeakSet["Effect"] = field(default_factory=weakref.WeakSet)

    def __hash__(self) -> int:
        return id(self)

    @contextmanager
    def track(self):
        Effect.tracking.append(self)
        try:
            yield
        finally:
            Effect.tracking.pop()

    @classmethod
    @contextmanager
    def track_barrier(cls):
        Effect.tracking.append(None)
        try:
            yield
        finally:
            Effect.tracking.pop()

    def add_tracking_dependent(self):
        if Effect.tracking and (tracking := Effect.tracking[-1]) is not None:
            self.dependents.add(tracking)

    def update(self):
        this_update_set = (
            {weakref.ref[Triggerable](w) for w in self.watchers}
            | {weakref.ref[Triggerable](d) for d in self.dependents}
        ) - Effect.update_set
        self.dependents = weakref.WeakSet()
        is_runner = len(Effect.update_set) == 0
        Effect.update_queue.extend(this_update_set)
        Effect.update_set.update(this_update_set)
        if is_runner:
            try:
                while True:
                    update = Effect.update_queue.popleft()
                    if (u := update()) is not None:
                        u.trigger()
                    Effect.update_set.remove(update)
            except IndexError:
                pass

    def trigger(self):
        pass


class ReadRef(Effect, Generic[T]):
    _value: T

    def __init__(self, value: T):
        super().__init__()
        self._value = value

    @property
    def value(self):
        self.add_tracking_dependent()
        return self._value


class Ref(ReadRef[T]):
    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value: T):
        if self._value != new_value:
            self._value = new_value
            self.update()


class Computed(ReadRef[T]):
    _func: Callable[[], T]

    def __init__(self, func: Callable[[], T]):
        self._func = func
        super().__init__(None)
        with self.track():
            self._value = self._func()

    def trigger(self):
        with self.track():
            new_value = self._func()
        if self._value != new_value:
            self._value = new_value
            self.update()


_future_update_queue = SimpleQueue[tuple["ComputedFuture", Any]]()


def update_computed_future(_dt):
    try:
        while True:
            computed_fut, value = _future_update_queue.get_nowait()
            computed_fut._set_value(value)  # pylint: disable=W0212
    except Empty:
        return


pyglet.clock.schedule(update_computed_future)


class ComputedFuture(ReadRef[T]):
    _fut: Future[T]

    def __init__(self, fut: Future[T]):
        super().__init__(None)
        self.set_future(fut)

    def set_future(self, fut: Future[T]):
        self._fut = fut
        self._fut.add_done_callback(
            lambda fut: _future_update_queue.put(self, fut.result())
        )

    def _set_value(self, new_value: T):
        if self._value != new_value:
            self._value = new_value
            self.update()


class Watcher:
    _sources: list[Effect]
    _func: Callable[[], None]

    def __init__(
        self,
        sources: list[Effect],
        func: Callable[[], None],
        *,
        trigger_init: bool = False,
    ):
        self._sources = sources
        self._func = func
        for source in self._sources:
            source.watchers.add(self)
        if trigger_init:
            self.trigger()

    def __hash__(self) -> int:
        return id(self)

    def unwatch(self):
        for source in self._sources:
            try:
                source.watchers.remove(self)
            except KeyError:
                pass

    def trigger(self):
        self._func()


def isref(maybe_ref: ReadRef[T] | T) -> TypeGuard[ReadRef[T]]:
    return isinstance(maybe_ref, ReadRef)


@overload
def unref(maybe_ref: ReadRef[T]) -> T:
    ...


@overload
def unref(maybe_ref: T) -> T:
    ...


def unref(maybe_ref):
    if isref(maybe_ref):
        return maybe_ref.value
    else:
        return maybe_ref
