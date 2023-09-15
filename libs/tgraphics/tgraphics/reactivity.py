from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Generic, TypeVar

T = TypeVar("T")


@dataclass
class Effect:
    tracking: ClassVar["Effect | None"]
    watchers: set["Watcher"] = field(default_factory=set)
    dependents: set["Effect"] = field(default_factory=set)

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
        for watcher in self.watchers:
            watcher.trigger()
        dependents = self.dependents
        self.dependents = set()
        for dependent in dependents:
            dependent.trigger()

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
        self._value = new_value
        self.update()


class Computed(ReadRef[T]):
    _func: Callable[[], T]

    def __init__(self, func: Callable[[], T]):
        self._func = func
        self.track()
        super().__init__(self._func())
        self.untrack()

    def trigger(self):
        self.track()
        self._value = self._func()
        self.untrack()
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
