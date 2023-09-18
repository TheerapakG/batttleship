from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Generic, Protocol, TypeGuard, TypeVar
import weakref

T = TypeVar("T")


class Triggerable(Protocol):
    def trigger(self):
        ...


@dataclass
class Effect:
    tracking: ClassVar["Effect | None"]
    update_queue: ClassVar[deque[weakref.ref[Triggerable]]] = deque()
    update_set: ClassVar[set[weakref.ref[Triggerable]]] = set()
    watchers: weakref.WeakSet["Watcher"] = field(default_factory=weakref.WeakSet)
    dependents: weakref.WeakSet["Effect"] = field(default_factory=weakref.WeakSet)

    def __hash__(self) -> int:
        return id(self)

    def track(self):
        Effect.tracking = self

    def untrack(self):
        Effect.tracking = None

    def add_tracking_dependent(self):
        if (tracking := Effect.tracking) is not None:
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
        self.track()
        self._value = self._func()
        self.untrack()

    def trigger(self):
        self.track()
        new_value = self._func()
        self.untrack()
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


def unref(maybe_ref: ReadRef[T] | T) -> T:
    if isref(maybe_ref):
        return maybe_ref.value
    else:
        return maybe_ref
