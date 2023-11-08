import asyncio
from collections import deque
from collections.abc import (
    Awaitable,
    Callable,
    Iterable,
    Sequence,
    KeysView,
    ValuesView,
    ItemsView,
)
from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import sys
from typing import Any, ClassVar, Generic, Protocol, TypeGuard, TypeVar, overload
import weakref

log = logging.getLogger(__name__)

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


class SupportsIndex(Protocol):
    def __index__(self) -> int:
        ...


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
                    if (update in Effect.update_set) and ((u := update()) is not None):
                        u.trigger()
                    try:
                        Effect.update_set.remove(update)
                    except KeyError:
                        pass
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

    def __repr__(self):
        return f"{type(self).__name__}({repr(self._value)})"


class Ref(ReadRef[T]):
    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value: T):
        self.set_value(new_value)

    def set_value(self, new_value: T):
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()

    def trigger(self):
        self.update()


class RefList(Ref[list[T]], Generic[T]):
    _proxies: weakref.WeakSet["Effect"]

    def __init__(self, value: list[T] | None = None):
        super().__init__(value if value is not None else [])
        self._proxies = weakref.WeakSet()

    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value: list[T]):
        self.set_value(new_value)

    def set_value(self, new_value: list[T]):
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.trigger()

    def trigger(self):
        self.update()
        for proxy in self._proxies:
            proxy.trigger()

    def __getitem__(self, key: SupportsIndex):
        # TODO: more robust typing
        match key:
            case int():
                proxy = RefListItemProxy(self, key)
            case slice():
                proxy = RefListViewProxy(self, key)
        self._proxies.add(proxy)
        return proxy

    def __setitem__(self, key: SupportsIndex, value: T | Sequence[T]):
        # TODO: more robust typing
        new_value = self._value.copy()
        new_value[key] = value
        self.set_value(new_value)

    def __delitem__(self, key: SupportsIndex):
        new_value = self._value.copy()
        del new_value[key]
        self.set_value(new_value)

    def __len__(self):
        proxy = RefListLenProxy(self)
        self._proxies.add(proxy)
        return proxy

    def insert(self, index: SupportsIndex, value: T):
        new_value = self._value.copy()
        new_value.insert(index, value)
        self.set_value(new_value)

    def __contains__(self, value: T):
        proxy = RefListContainsProxy(self, value)
        self._proxies.add(proxy)
        return proxy

    def __iter__(self):
        index = 0
        while index < len(self.value):
            yield RefListItemProxy(self, index)
            index += 1

    def __reversed__(self):
        index = len(self.value)
        while index > 0:
            index -= 1
            yield RefListItemProxy(self, index)

    def index(
        self, value: T, start: SupportsIndex = 0, stop: SupportsIndex = sys.maxsize
    ):
        proxy = RefListIndexProxy(self, value, start, stop)
        self._proxies.add(proxy)
        return proxy

    def count(self, value: T):
        proxy = RefListCountProxy(self, value)
        self._proxies.add(proxy)
        return proxy

    def append(self, value: T):
        new_value = self._value.copy()
        new_value.append(value)
        self.set_value(new_value)

    def reverse(self):
        new_value = self._value.copy()
        new_value.reverse()
        self.set_value(new_value)

    def extend(self, it: Iterable[T]):
        new_value = self._value.copy()
        new_value.extend(it)
        self.set_value(new_value)

    def pop(self, index: SupportsIndex = -1):
        new_value = self._value.copy()
        new_value.pop(index)
        self.set_value(new_value)

    def remove(self, value: T):
        new_value = self._value.copy()
        new_value.remove(value)
        self.set_value(new_value)

    def __iadd__(self, value: Iterable[T]):
        new_value = self._value.copy()
        new_value += value
        self.set_value(new_value)


class RefListCountProxy(ReadRef[int], Generic[T]):
    ref_list: RefList[T]
    count_value: T

    def __init__(self, ref_list: RefList[T], value: T):
        self.ref_list = ref_list
        self.count_value = value
        super().__init__(value in ref_list.value)

    def trigger(self):
        new_value = self.ref_list.value.count(self.count_value)
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefListIndexProxy(ReadRef[int | None], Generic[T]):
    ref_list: RefList[T]
    index_value: T
    start: SupportsIndex
    stop: SupportsIndex

    def __init__(
        self,
        ref_list: RefList[T],
        value: T,
        start: SupportsIndex = 0,
        stop: SupportsIndex = sys.maxsize,
    ):
        self.ref_list = ref_list
        self.index_value = value
        self.start = start
        self.stop = stop
        super().__init__(ref_list.value.index(value, start, stop))

    def trigger(self):
        try:
            new_value = self.ref_list.value.index(
                self.index_value, self.start, self.stop
            )
        except ValueError:
            new_value = None
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefListContainsProxy(ReadRef[bool], Generic[T]):
    ref_list: RefList[T]
    contains_value: T

    def __init__(self, ref_list: RefList[T], value: T):
        self.ref_list = ref_list
        self.contains_value = value
        super().__init__(value in ref_list.value)

    def trigger(self):
        new_value = len(self.contains_value in self.ref_list.value)
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefListLenProxy(ReadRef[int], Generic[T]):
    ref_list: RefList[T]

    def __init__(self, ref_list: RefList[T]):
        self.ref_list = ref_list
        super().__init__(len(ref_list.value))

    def trigger(self):
        new_value = len(self.ref_list.value)
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefListViewProxy(ReadRef[list[T]]):
    ref_list: RefList[T]
    index: slice

    def __init__(self, ref_list: RefList[T], index: slice):
        self.ref_list = ref_list
        self.index = index
        super().__init__(ref_list.value[index])

    def trigger(self):
        new_value = self.ref_list.value[self.index]
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefListItemProxy(ReadRef[T]):
    ref_list: RefList[T]
    index: int

    def __init__(self, ref_list: RefList[T], index: int):
        self.ref_list = ref_list
        self.index = index
        super().__init__(ref_list.value[index])

    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value: T):
        self.set_value(new_value)

    def set_value(self, new_value: T):
        self.ref_list[self.index] = new_value

    def trigger(self):
        new_value = self.ref_list.value[self.index]
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefDict(Ref[dict[K, V]]):
    _keys_proxies: weakref.WeakSet["Effect"]
    _values_proxies: weakref.WeakSet["Effect"]
    _items_proxies: weakref.WeakSet["Effect"]

    def __hash__(self) -> int:
        return id(self)

    def __init__(self, value: dict[K, V] | None = None):
        super().__init__(value if value is not None else {})
        self._keys_proxies = weakref.WeakSet()
        self._values_proxies = weakref.WeakSet()
        self._items_proxies = weakref.WeakSet()

    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value: dict[K, V]):
        self.set_value(new_value)

    def set_value(self, new_value: dict[K, V]):
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.trigger()

    def trigger(self):
        self.update()
        for proxy in self._keys_proxies:
            proxy.trigger()
        for proxy in self._values_proxies:
            proxy.trigger()
        for proxy in self._items_proxies:
            proxy.trigger()

    def __getitem__(self, key: K):
        proxy = RefDictGetProxy(self, key, None)
        self._items_proxies.add(proxy)
        return proxy

    def __setitem__(self, key: K, value: V):
        if key not in self._value:
            self._value[key] = value
            for proxy in self._keys_proxies:
                proxy.trigger()
            for proxy in self._values_proxies:
                proxy.trigger()
            for proxy in self._items_proxies:
                proxy.trigger()
        else:
            old_value, self._value[key] = self._value[key], value
            if old_value != value:
                for proxy in self._values_proxies:
                    proxy.trigger()
                for proxy in self._items_proxies:
                    proxy.trigger()

    def __delitem__(self, key: K):
        new_value = self._value.copy()
        del new_value[key]
        self.set_value(new_value)

    def __iter__(self):
        raise NotImplementedError()

    def __len__(self):
        proxy = RefDictLenProxy(self)
        self._keys_proxies.add(proxy)
        return proxy

    def __contains__(self, key: K):
        proxy = RefDictContainsProxy(self, key)
        self._keys_proxies.add(proxy)
        return proxy

    def keys(self):
        proxy = RefDictKeysProxy(self)
        self._keys_proxies.add(proxy)
        return proxy

    def items(self):
        proxy = RefDictItemsProxy(self)
        self._items_proxies.add(proxy)
        return proxy

    def values(self):
        proxy = RefDictValuesProxy(self)
        self._values_proxies.add(proxy)
        return proxy

    def get(self, key: K, default: T = None):
        proxy = RefDictGetProxy(self, key, default)
        self._items_proxies.add(proxy)
        return proxy

    def __eq__(self, other):
        raise NotImplementedError()

    def __ne__(self, other):
        raise NotImplementedError()

    def pop(self, key: K, default: T):
        value = self._value.pop(key, default)
        for proxy in self._keys_proxies:
            proxy.trigger()
        for proxy in self._values_proxies:
            proxy.trigger()
        for proxy in self._items_proxies:
            proxy.trigger()
        return value

    def popitem(self):
        value = self._value.popitem()
        for proxy in self._keys_proxies:
            proxy.trigger()
        for proxy in self._values_proxies:
            proxy.trigger()
        for proxy in self._items_proxies:
            proxy.trigger()
        return value

    def clear(self):
        self._value.clear()
        for proxy in self._keys_proxies:
            proxy.trigger()
        for proxy in self._values_proxies:
            proxy.trigger()
        for proxy in self._items_proxies:
            proxy.trigger()

    def dict_update(self, other, **kwargs):
        self._value.update(other, **kwargs)
        for proxy in self._keys_proxies:
            proxy.trigger()
        for proxy in self._values_proxies:
            proxy.trigger()
        for proxy in self._items_proxies:
            proxy.trigger()

    def setdefault(self, key: K, default: V):
        if key not in self._value:
            self._value[key] = default
            for proxy in self._keys_proxies:
                proxy.trigger()
            for proxy in self._values_proxies:
                proxy.trigger()
            for proxy in self._items_proxies:
                proxy.trigger()
        return self[key]


class RefDictGetProxy(ReadRef[V | T], Generic[K, V, T]):
    ref_dict: RefDict[K, V]
    key: K
    default: T

    def __init__(self, ref_dict: RefDict[K, V], key: K, default: T):
        self.ref_dict = ref_dict
        self.key = key
        self.default = default
        super().__init__(ref_dict.value.get(key, default))

    @property
    def value(self):
        return super().value

    @value.setter
    def value(self, new_value: V):
        self.set_value(new_value)

    def set_value(self, new_value: V):
        self.ref_dict[self.key] = new_value

    def trigger(self):
        new_value = self.ref_dict.value.get(self.key, self.default)
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefDictValuesProxy(ReadRef[ValuesView[V]], Generic[K, V]):
    def __init__(self, ref_dict: RefDict[K, V]):
        super().__init__(ref_dict.value.values())

    def trigger(self):
        self.update()


class RefDictItemsProxy(ReadRef[ItemsView[K, V]]):
    def __init__(self, ref_dict: RefDict[K, V]):
        super().__init__(ref_dict.value.items())

    def trigger(self):
        self.update()


class RefDictKeysProxy(ReadRef[KeysView[K]], Generic[K, V]):
    def __init__(self, ref_dict: RefDict[K, V]):
        super().__init__(ref_dict.value.keys())

    def trigger(self):
        self.update()


class RefDictContainsProxy(ReadRef[bool], Generic[K, V]):
    ref_dict: RefDict[K, V]
    contains_value: K

    def __init__(self, ref_dict: RefDict[K, V], value: K):
        self.ref_dict = ref_dict
        self.contains_value = value
        super().__init__(value in ref_dict.value)

    def trigger(self):
        new_value = len(self.contains_value in self.ref_dict.value)
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class RefDictLenProxy(ReadRef[int], Generic[K, V]):
    ref_dict: RefDict[K, V]

    def __init__(self, ref_dict: RefDict[K, V]):
        self.ref_dict = ref_dict
        super().__init__(len(ref_dict.value))

    def trigger(self):
        new_value = len(self.ref_dict.value)
        old_value, self._value = self._value, new_value
        if old_value != new_value:
            self.update()


class Computed(ReadRef[T_co]):
    _func: Callable[[], T_co]

    def __init__(self, func: Callable[[], T_co]):
        self._func = func
        super().__init__(None)  # type: ignore
        with self.track():
            try:
                self._value = self._func()
            except Exception:
                log.exception("exception in computed")
                raise

    def trigger(self):
        with self.track():
            try:
                new_value = self._func()
                old_value, self._value = self._value, new_value
                if old_value != new_value:
                    self.update()
            except Exception:
                log.exception("exception in computed")


def computed(func: Callable[[], T]):
    computed_instance = Computed(func)
    if len(computed_instance.depends) == 0:
        with Effect.track_barrier():
            return computed_instance.value
    return computed_instance


class ComputedAsync(Generic[T_contra], ReadRef[T_contra | None]):
    _coro: Awaitable[T_contra]

    def __init__(self, coro: Awaitable[T_contra]):
        super().__init__(None)
        self._value = None
        self.set_awaitable(coro)

    def set_awaitable(self, coro: Awaitable[T_contra]):
        self._coro = coro
        asyncio.create_task(coro).add_done_callback(
            lambda task: self._set_value(task.result())
        )

    def _set_value(self, new_value: T_contra):
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

    def __eq__(self, other):
        return hash(self) != hash(other)

    def __del__(self):
        for source in self._sources:
            try:
                source.watchers.remove(self)
            except KeyError:
                pass
        try:
            Effect.update_set.remove(weakref.ref(self))
        except KeyError:
            pass

    def unwatch(self):
        self.__del__()

    def trigger(self):
        with Effect.track_barrier():
            self._func()

    @classmethod
    def ifref(
        cls,
        maybe_ref: ReadRef[T] | T,
        func: Callable[[T], Any],
        *,
        trigger_init: bool = False,
    ):
        if isref(maybe_ref):
            return cls(
                [maybe_ref], lambda: func(unref(maybe_ref)), trigger_init=trigger_init
            )
        if trigger_init:
            func(maybe_ref)  # type: ignore
        return None


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


def unref(maybe_ref: Callable[[], T] | ReadRef[T] | T) -> T:
    if callable(maybe_ref):
        return maybe_ref()
    if isref(maybe_ref):
        return maybe_ref.value
    return maybe_ref  # type: ignore
