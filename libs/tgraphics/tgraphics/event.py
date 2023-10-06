from dataclasses import dataclass
from typing import Any, ClassVar, Protocol


class EventMeta(type):
    _events: ClassVar[dict[str, type["Event"]]] = dict()

    def __new__(
        mcs: type["Event"],
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
    ):
        cls = super().__new__(mcs, name, bases, attrs)
        mcs._events[name] = cls
        return cls

    @classmethod
    def from_name(mcs, name: str):
        return mcs._events[name]


@dataclass
class Event(metaclass=EventMeta):
    pass


@dataclass
class FocusEvent(Event):
    pass


class Positional(Protocol):
    __dataclass_fields__: ClassVar[dict]
    x: float
    y: float


@dataclass
class BubblingEvent(Event):
    x: float
    y: float


@dataclass
class MouseEnterEvent(Event):
    x: float
    y: float


@dataclass
class MouseLeaveEvent(Event):
    x: float
    y: float


class ComponentMountedEvent(Event):
    pass


class ComponentUnmountedEvent(Event):
    pass


class ComponentFocusEvent(Event):
    pass


class ComponentBlurEvent(Event):
    pass


@dataclass
class KeyPressEvent(FocusEvent):
    symbol: int
    modifiers: int


@dataclass
class KeyReleaseEvent(FocusEvent):
    symbol: int
    modifiers: int


@dataclass
class TextEvent(FocusEvent):
    text: str


@dataclass
class TextMotionEvent(FocusEvent):
    motion: int


@dataclass
class TextMotionSelectEvent(FocusEvent):
    motion: int


@dataclass
class MouseDragEvent(FocusEvent):
    x: float
    y: float
    dx: int
    dy: int
    buttons: int
    modifiers: int


@dataclass
class MousePressEvent(BubblingEvent):
    button: int
    modifiers: int


@dataclass
class MouseReleaseEvent(BubblingEvent):
    button: int
    modifiers: int


@dataclass
class MouseMotionEvent(BubblingEvent):
    dx: int
    dy: int


@dataclass
class MouseScrollEvent(BubblingEvent):
    scroll_x: int
    scroll_y: int


StopPropagate = object()
