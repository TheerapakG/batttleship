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
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


class Triggerable(Protocol):
    def trigger(self):
        ...


@dataclass
class Effect:
    tracking: ClassVar[list["Effect | None"]] = []
    update_queue: ClassVar[deque[weakref.ref[Triggerable]]] = deque()
    update_set: ClassVar[set[weakref.ref[Triggerable]]] = set()
    watchers: weakref.WeakSet["Watcher"] = field(default_factory=weakref.WeakSet)
    depends: set["Effect"] = field(default_factory=set)
    dependents: weakref.WeakSet["Effect"] = field(default_factory=weakref.WeakSet)
    _old_depends: set["Effect"] = field(default_factory=set)  # for maintaining refcount

    def __hash__(self) -> int:
        return id(self)

    @contextmanager
    def track(self):
        self._old_depends = self.depends
        self.depends = set()
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
            tracking.depends.add(self)
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


class ReadRef(Effect, Generic[T_co]):
    _value: T_co

    def __init__(self, value: T_co):
        super().__init__()
        self._value = value

    @property
    def value(self):
        self.add_tracking_dependent()
        return self._value


class Ref(ReadRef[T_contra]):
    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value: T_contra):
        if self._value != new_value:
            self._value = new_value
            self.update()

    def trigger(self):
        self.update()


class Computed(ReadRef[T_co]):
    _func: Callable[[], T_co]

    def __init__(self, func: Callable[[], T_co]):
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


def computed(func: Callable[[], T]):
    computed_instance = Computed(func)
    if len(computed_instance.depends) == 0:
        return computed_instance.value
    return computed_instance


_future_update_queue = SimpleQueue[tuple[weakref.ref["ComputedFuture"], Any]]()


def update_computed_future(_dt):
    try:
        while True:
            computed_fut_weak, value = _future_update_queue.get_nowait()
            if (computed_fut := computed_fut_weak()) is not None:
                computed_fut._set_value(value)  # pylint: disable=W0212
    except Empty:
        return


pyglet.clock.schedule(update_computed_future)


class ComputedFuture(ReadRef[T_contra]):
    _fut: Future[T_contra]
    _cbs: list[Callable[[T_contra], Any]]

    def __init__(self, fut: Future[T_contra]):
        super().__init__(None)
        self._cbs = []
        self.set_future(fut)

    def set_future(self, fut: Future[T_contra]):
        self._fut = fut
        self._fut.add_done_callback(
            lambda fut: _future_update_queue.put((weakref.ref(self), fut.result()))
        )

    def add_done_callback(self, fun: Callable[[T_contra], Any]):
        self._cbs.append(fun)

    def _set_value(self, new_value: T_contra):
        for cb in self._cbs:
            cb(new_value)
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

    @classmethod
    def ifref(
        cls,
        maybe_ref: ReadRef[T] | T,
        func: Callable[[T], Any],
        *,
        trigger_init: bool = False,
    ):
        return (
            cls([maybe_ref], lambda: func(unref(maybe_ref)), trigger_init=trigger_init)
            if isref(maybe_ref)
            else None
        )


def isref(maybe_ref: ReadRef[T] | T) -> TypeGuard[ReadRef[T]]:
    return isinstance(maybe_ref, ReadRef)


@overload
def unref(maybe_ref: Callable[[], T]) -> T:
    ...


@overload
def unref(maybe_ref: ReadRef[T]) -> T:
    ...


@overload
def unref(maybe_ref: T) -> T:
    ...


def unref(maybe_ref: Callable[[], T] | ReadRef[T] | T):
    if callable(maybe_ref):
        return maybe_ref()
    if isref(maybe_ref):
        return maybe_ref.value
    return maybe_ref
