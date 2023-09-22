from collections.abc import Callable
from dataclasses import dataclass, field, replace, InitVar
from functools import partial
from typing import Any, ClassVar

from pyglet.graphics import Batch
from pyglet.shapes import Rectangle
from pyglet.text import Label as _Label
from pyglet.text.document import UnformattedDocument
from pyglet.text.layout import IncrementalTextLayout
from pyglet.text.caret import Caret
from pyglet.window import Window as _Window

from .event import (
    Event,
    Positional,
    FocusEvent,
    BubblingEvent,
    StopPropagate,
    KeyPressEvent,
    KeyReleaseEvent,
    MouseDragEvent,
    MouseEnterEvent,
    MouseLeaveEvent,
    MouseMotionEvent,
    MousePressEvent,
    MouseReleaseEvent,
    MouseScrollEvent,
    TextEvent,
    TextMotionEvent,
    TextMotionSelectEvent,
    ComponentFocusEvent,
    ComponentBlurEvent,
)
from .reactivity import Effect, Computed, ReadRef, Ref, Watcher, isref, unref


@dataclass
class _EventCapturer:
    event: type[Event]
    func: Callable[["Component", Event], Any]

    def __call__(self, event: Event):
        # For tricking LSP / type checker
        raise NotImplementedError()


@dataclass
class _EventHandler:
    event: type[Event]
    func: Callable[["Component", Event], Any]

    def __call__(self, event: Event):
        # For tricking LSP / type checker
        raise NotImplementedError()


def event_capturer(cls: type[Event]):
    def make_capturer(func: Callable[["Component", Event], Any]):
        return _EventCapturer(cls, func)

    return make_capturer


def event_handler(cls: type[Event]):
    def make_handler(func: Callable[["Component", Event], Any]):
        return _EventHandler(cls, func)

    return make_handler


class ComponentMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        capturers = {
            name: handler
            for name, handler in attrs.items()
            if isinstance(handler, _EventCapturer)
        }
        handlers = {
            name: handler
            for name, handler in attrs.items()
            if isinstance(handler, _EventHandler)
        }
        attrs.update({name: capturer.func for name, capturer in capturers.items()})
        attrs.update({name: handler.func for name, handler in handlers.items()})
        cls: type[Component] = super().__new__(mcs, name, bases, attrs)
        cls._cls_event_capturers = {
            capturer.event: capturer.func for capturer in capturers.values()
        }
        cls._cls_event_handlers = {
            handler.event: handler.func for handler in handlers.values()
        }
        cls._flat_event_capturers = {}
        cls._flat_event_handlers = {}
        for base in reversed(cls.mro()):
            cls._flat_event_capturers.update(getattr(base, "_cls_event_capturers", {}))
            cls._flat_event_handlers.update(getattr(base, "_cls_event_handlers", {}))
        return cls


@dataclass(kw_only=True)
class Component(metaclass=ComponentMeta):
    _focus: ClassVar[Ref["Component | None"]] = Ref(None)
    _cls_event_capturers: ClassVar[
        dict[type[Event], Callable[["Component", Event], Any]]
    ]
    _cls_event_handlers: ClassVar[
        dict[type[Event], Callable[["Component", Event], Any]]
    ]
    _flat_event_capturers: ClassVar[
        dict[type[Event], Callable[["Component", Event], Any]]
    ]
    _flat_event_handlers: ClassVar[
        dict[type[Event], Callable[["Component", Event], Any]]
    ]
    width: float | ReadRef[float] = field(default=0)
    height: float | ReadRef[float] = field(default=0)
    disabled: bool | ReadRef[bool] = field(default=False)
    event_capturers: dict[type[Event], Callable[[Event], Any]] = field(
        default_factory=dict
    )
    event_handlers: dict[type[Event], Callable[[Event], Any]] = field(
        default_factory=dict
    )
    children_hover: ReadRef["Component | None"] = field(
        init=False, default_factory=lambda: Ref(None)
    )

    def __post_init__(self):
        capturers = {
            event: partial(capturers, self)
            for event, capturers in self._flat_event_capturers.items()
        }
        handlers = {
            event: partial(handler, self)
            for event, handler in self._flat_event_handlers.items()
        }
        capturers.update(self.event_capturers)
        handlers.update(self.event_handlers)
        self.event_capturers = capturers
        self.event_handlers = handlers

    def focus(self):
        focus = unref(Component._focus)
        if focus is self:
            return StopPropagate

        if self.capture(ComponentFocusEvent()) is StopPropagate:
            return StopPropagate

        if Component.blur() is StopPropagate:
            return StopPropagate
        Component._focus.value = self

    @classmethod
    def blur(cls):
        if (focus := unref(Component._focus)) is not None:
            focus: Component
            if focus.capture(ComponentBlurEvent()) is StopPropagate:
                return StopPropagate
            Component._focus.value = None

    def draw(self, _x: float, _y: float):
        pass

    def capture(self, event: Event):
        if not unref(self.disabled):
            for event_type in type(event).mro():
                if (capturer := self.event_capturers.get(event_type)) is not None:
                    return capturer(event)

    def dispatch(self, event: Event):
        if not unref(self.disabled):
            for event_type in type(event).mro():
                if (handler := self.event_handlers.get(event_type)) is not None:
                    return handler(event)

    def get_child_at(self, _p: Positional) -> tuple["Component", float, float] | None:
        return None

    def get_child_rel(self, _c: "Component") -> tuple[float, float] | None:
        return None

    @event_capturer(FocusEvent)
    def focus_capturer(self, event: FocusEvent):
        if (focus := unref(Component._focus)) is not None:
            focus: Component
            return focus.dispatch(event)

    @event_capturer(BubblingEvent)
    def bubbling_capturer(self, event: BubblingEvent):
        if (children_tup := self.get_child_at(event)) is not None:
            c, dx, dy = children_tup
            if (
                c.capture(
                    replace(
                        event,
                        x=event.x - dx,
                        y=event.y - dy,
                    )
                )
                is StopPropagate
            ):
                return StopPropagate
        if 0 < event.x < unref(self.width) and 0 < event.y < unref(self.height):
            return self.dispatch(event)

    @event_capturer(Event)
    def generic_capturer(self, event: Event):
        return self.dispatch(event)

    def _process_child_leave(self, p: Positional, new_c: "Component | None" = None):
        if (c := self.children_hover.value) is not None and (
            rel := self.get_child_rel(c)
        ) is not None:
            dx, dy = rel
            c.capture(
                MouseLeaveEvent(
                    p.x - dx,
                    p.y - dy,
                )
            )
        self.children_hover.value = new_c

    def _process_child_position(
        self, p: Positional
    ) -> tuple["Component", float, float] | None:
        if (new_c_tup := self.get_child_at(p)) is not None:
            new_c, new_dx, new_dy = new_c_tup
            if self.children_hover.value is not new_c:
                self._process_child_leave(p, new_c)
                new_c.capture(
                    MouseEnterEvent(
                        p.x - new_dx,
                        p.y - new_dy,
                    )
                )
                self.children_hover.value = new_c
            return new_c_tup
        else:
            self._process_child_leave(p, None)

    @event_capturer(MouseEnterEvent)
    def mouse_enter_capturer(self, event: MouseEnterEvent):
        self.children_hover.value = None
        self._process_child_position(event)
        return self.dispatch(event)

    @event_capturer(MouseMotionEvent)
    def mouse_motion_capturer(self, event: MouseMotionEvent):
        if (c_tup := self._process_child_position(event)) is not None:
            c, dx, dy = c_tup
            if (
                c.capture(
                    replace(
                        event,
                        x=event.x - dx,
                        y=event.y - dy,
                    )
                )
                is StopPropagate
            ):
                return StopPropagate
        return self.dispatch(event)

    @event_capturer(MouseLeaveEvent)
    def mouse_leave_capturer(self, event: MouseLeaveEvent):
        self._process_child_leave(event, None)
        return self.dispatch(event)

    @event_handler(MousePressEvent)
    def mouse_press_handler(self, _event: MousePressEvent):
        if unref(Component._focus) is not self:
            Component.blur()


@dataclass
class Pad(Component):
    children: InitVar[Callable[[], Component]]
    pad_bottom: float | ReadRef[float] = field(default=0, kw_only=True)
    pad_top: float | ReadRef[float] = field(default=0, kw_only=True)
    pad_left: float | ReadRef[float] = field(default=0, kw_only=True)
    pad_right: float | ReadRef[float] = field(default=0, kw_only=True)
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _children: ReadRef[Component] = field(init=False)
    _children_hover: bool = field(init=False, default=False)

    def __post_init__(self, children):  # pylint: disable=W0221
        super().__post_init__()
        self._children = Computed(children)

        self.width = Computed(
            lambda: unref(unref(self._children).width)
            + unref(self.pad_left)
            + unref(self.pad_right)
        )
        self.height = Computed(
            lambda: unref(unref(self._children).height)
            + unref(self.pad_top)
            + unref(self.pad_bottom)
        )

    def draw(self, x: float, y: float):
        unref(self._children).draw(x + unref(self.pad_left), y + unref(self.pad_bottom))

    def get_child_at(self, p: Positional) -> tuple["Component", float, float] | None:
        return (
            (unref(self._children), unref(self.pad_left), unref(self.pad_bottom))
            if not unref(unref(self._children).disabled)
            and unref(self.pad_left) < p.x < unref(self.width) - unref(self.pad_right)
            and unref(self.pad_bottom) < p.y < unref(self.height) - unref(self.pad_top)
            else None
        )

    def get_child_rel(self, _c: "Component") -> tuple[float, float] | None:
        return unref(self.pad_left), unref(self.pad_bottom)


@dataclass
class Center(Component):
    children: InitVar[Callable[[], Component]]
    _width: InitVar[float | ReadRef[float] | None] = field(default=None)
    _height: InitVar[float | ReadRef[float] | None] = field(default=None)
    width: float | ReadRef[float] = field(init=False)
    height: float | ReadRef[float] = field(init=False)
    _children: ReadRef[Component] = field(init=False)
    _pad_x: ReadRef[float] = field(init=False)
    _pad_y: ReadRef[float] = field(init=False)

    def __post_init__(self, children, _width, _height):  # pylint: disable=W0221
        super().__post_init__()
        self._children = Computed(children)

        self.width = (
            _width if _width else Computed(lambda: unref(unref(self._children).width))
        )
        self.height = (
            _height
            if _height
            else Computed(lambda: unref(unref(self._children).height))
        )

        self._pad_x = Computed(
            lambda: (unref(self.width) - unref(unref(self._children).width)) / 2
        )
        self._pad_y = Computed(
            lambda: (unref(self.height) - unref(unref(self._children).height)) / 2
        )

    def draw(self, x: float, y: float):
        unref(self._children).draw(
            x + unref(self._pad_x),
            y + unref(self._pad_y),
        )

    def get_child_at(self, p: Positional) -> tuple["Component", float, float] | None:
        return (
            (unref(self._children), unref(self._pad_x), unref(self._pad_y))
            if not unref(unref(self._children).disabled)
            and unref(self._pad_x) < p.x < unref(self.width) - unref(self._pad_x)
            and unref(self._pad_y) < p.y < unref(self.height) - unref(self._pad_y)
            else None
        )

    def get_child_rel(self, _c: "Component") -> tuple[float, float] | None:
        return unref(self._pad_x), unref(self._pad_y)


@dataclass
class Layer(Component):
    children: InitVar[Callable[[], list[Component]]]
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _children: ReadRef[list[Component]] = field(init=False)
    _children_hover: Component | None = field(init=False, default=None)

    def __post_init__(self, children):  # pylint: disable=W0221
        super().__post_init__()
        self._children = Computed(children)

        def _width():
            return max(unref(c.width) for c in unref(self._children))

        self.width = Computed(_width)

        def _height():
            return max(unref(c.height) for c in unref(self._children))

        self.height = Computed(_height)

    def draw(self, x: float, y: float):
        for c in unref(self._children):
            c.draw(
                x + ((unref(self.width) - unref(c.width)) / 2),
                y + ((unref(self.height) - unref(c.height)) / 2),
            )

    def get_child_at(self, p: Positional) -> tuple["Component", float, float] | None:
        for c in reversed(unref(self._children)):
            if (
                not unref(c.disabled)
                and ((unref(self.width) - unref(c.width)) / 2)
                < p.x
                < ((unref(self.width) + unref(c.width)) / 2)
                and ((unref(self.height) - unref(c.height)) / 2)
                < p.y
                < ((unref(self.height) + unref(c.height)) / 2)
            ):
                return (
                    c,
                    ((unref(self.width) - unref(c.width)) / 2),
                    ((unref(self.height) - unref(c.height)) / 2),
                )

    def get_child_rel(self, c: "Component") -> tuple[float, float] | None:
        return (unref(self.width) - unref(c.width)) / 2, (
            unref(self.height) - unref(c.height)
        ) / 2


@dataclass
class Row(Component):
    children: InitVar[Callable[[], list[Component]]]
    gap: float | ReadRef[float] = field(default=0, kw_only=True)
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _children: ReadRef[list[Component]] = field(init=False)

    def __post_init__(self, children):  # pylint: disable=W0221
        super().__post_init__()
        self._children = Computed(children)

        def _width():
            _children = unref(self._children)

            return sum(unref(c.width) for c in _children) + unref(self.gap) * (
                len(_children) - 1
            )

        self.width = Computed(_width)

        def _height():
            return max(unref(c.height) for c in unref(self._children))

        self.height = Computed(_height)

    def draw(self, x: float, y: float):
        c_x = 0.0
        for c in unref(self._children):
            c.draw(
                x + c_x,
                y + ((unref(self.height) - unref(c.height)) / 2),
            )
            c_x += unref(c.width) + unref(self.gap)

    def get_child_at(self, p: Positional) -> tuple["Component", float, float] | None:
        c_x = 0.0
        for c in unref(self._children):
            if c_x >= p.x:
                break
            elif c_x < p.x < c_x + unref(c.width):
                if (not c.disabled) and (
                    unref(self.height) - unref(c.height)
                ) / 2 < p.y < (unref(self.height) + unref(c.height)) / 2:
                    return c, c_x, (unref(self.height) - unref(c.height)) / 2
                break
            else:
                c_x += unref(c.width) + unref(self.gap)

    def get_child_rel(self, c: "Component") -> tuple[float, float] | None:
        c_x = 0.0
        for _c in unref(self._children):
            if c is _c:
                return c_x, (unref(self.height) - unref(c.height)) / 2
            else:
                c_x += unref(c.width) + unref(self.gap)


@dataclass
class Column(Component):
    children: InitVar[Callable[[], list[Component]]]
    gap: float | ReadRef[float] = field(default=0, kw_only=True)
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _children: ReadRef[list[Component]] = field(init=False)

    def __post_init__(self, children):  # pylint: disable=W0221
        super().__post_init__()
        self._children = Computed(children)

        def _width():
            return max(unref(c.width) for c in unref(self._children))

        self.width = Computed(_width)

        def _height():
            _children = unref(self._children)
            return sum(unref(c.height) for c in _children) + unref(self.gap) * (
                len(_children) - 1
            )

        self.height = Computed(_height)

    def draw(self, x: float, y: float):
        c_y = 0.0
        for c in unref(self._children):
            c.draw(
                x + ((unref(self.width) - unref(c.width)) / 2),
                y + c_y,
            )
            c_y += unref(c.height) + unref(self.gap)

    def get_child_at(self, p: Positional) -> tuple["Component", float, float] | None:
        c_y = 0.0
        for c in unref(self._children):
            if c_y >= p.y:
                break
            elif c_y < p.y < c_y + unref(c.height):
                if (not c.disabled) and (
                    unref(self.width) - unref(c.width)
                ) / 2 < p.x < (unref(self.width) + unref(c.width)) / 2:
                    return c, (unref(self.width) - unref(c.width)) / 2, c_y
                break
            else:
                c_y += unref(c.height) + unref(self.gap)

    def get_child_rel(self, c: "Component") -> tuple[float, float] | None:
        c_y = 0.0
        for _c in unref(self._children):
            if c is _c:
                return (unref(self.width) - unref(c.width)) / 2, c_y
            else:
                c_y += unref(c.height) + unref(self.gap)


@dataclass
class Rect(Component):
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]]

    def draw(self, x: float, y: float):
        Rectangle(x, y, unref(self.width), unref(self.height), unref(self.color)).draw()


@dataclass
class Label(Component):
    text: str | ReadRef[str]
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]] = field(
        default=(255, 255, 255, 255)
    )
    font_name: str | ReadRef[str] | None = field(default=None)
    font_size: float | ReadRef[float] | None = field(default=None)
    bold: bool | ReadRef[bool] = field(default=False)
    italic: bool | ReadRef[bool] = field(default=False)
    _width: InitVar[float | ReadRef[float] | None] = field(default=None)
    _height: InitVar[float | ReadRef[float] | None] = field(default=None)
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _label: _Label = field(init=False)
    _watchers: list[Watcher | None] = field(init=False)

    def __post_init__(self, _width, _height):  # pylint: disable=W0221
        super().__post_init__()
        with Effect.track_barrier():
            self._label = _Label(
                unref(self.text),
                font_name=unref(self.font_name),
                font_size=unref(self.font_size),
                bold=unref(self.bold),
                italic=unref(self.italic),
                color=unref(self.color),
                width=unref(_width),
                height=unref(_height),
            )
        self.width = Computed(lambda: self._label.content_width)
        self.height = Computed(lambda: self._label.content_height)

        def _trigger_dims():
            self.width.trigger()
            self.height.trigger()

        def _on_text():
            self._label.text = unref(self.text)
            _trigger_dims()

        def _on_color():
            self._label.color = unref(self.color)
            _trigger_dims()

        def _on_font_name():
            self._label.font_name = unref(self.font_name)
            _trigger_dims()

        def _on_font_size():
            self._label.font_size = unref(self.font_size)
            _trigger_dims()

        def _on_bold():
            self._label.bold = unref(self.bold)
            _trigger_dims()

        def _on_italic():
            self._label.italic = unref(self.italic)
            _trigger_dims()

        def _on_width():
            self._label.width = unref(_width)
            _trigger_dims()

        def _on_height():
            self._label.height = unref(_height)
            _trigger_dims()

        self._watchers = [
            Watcher([self.text], _on_text) if isref(self.text) else None,
            Watcher([self.color], _on_color) if isref(self.color) else None,
            Watcher([self.font_name], _on_font_name) if isref(self.font_name) else None,
            Watcher([self.font_size], _on_font_size) if isref(self.font_size) else None,
            Watcher([self.bold], _on_bold) if isref(self.bold) else None,
            Watcher([self.italic], _on_italic) if isref(self.italic) else None,
            Watcher([_width], _on_width) if isref(_width) else None,
            Watcher([_height], _on_height) if isref(_height) else None,
        ]

    def draw(self, x: float, y: float):
        self._label.x = x
        self._label.y = y
        self._label.draw()


@dataclass
class Input(Component):
    text: Ref[str]
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]] = field(
        default=(255, 255, 255, 255)
    )
    caret_color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]] = field(
        default=(255, 255, 255, 255)
    )
    selection_background_color: tuple[int, int, int, int] | ReadRef[
        tuple[int, int, int, int]
    ] = field(default=(127, 127, 127, 255))
    selection_color: tuple[int, int, int, int] | ReadRef[
        tuple[int, int, int, int]
    ] = field(default=(255, 255, 255, 255))
    font_name: str | ReadRef[str] | None = field(default=None)
    font_size: float | ReadRef[float] | None = field(default=None)
    bold: bool | ReadRef[bool] = field(default=False)
    italic: bool | ReadRef[bool] = field(default=False)
    _width: InitVar[float | ReadRef[float] | None] = field(default=None)
    _height: InitVar[float | ReadRef[float] | None] = field(default=None)
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _batch: Batch = field(init=False)
    _document: UnformattedDocument = field(init=False)
    _layout: IncrementalTextLayout = field(init=False)
    _caret: Caret = field(init=False)
    _watchers: list[Watcher | None] = field(init=False)

    def __post_init__(self, _width, _height):  # pylint: disable=W0221
        super().__post_init__()

        self._batch = Batch()
        with Effect.track_barrier():
            self._document = UnformattedDocument(unref(self.text))
            self._document.set_style(
                0,
                0,
                {
                    "color": unref(self.color),
                    "font_name": unref(self.font_name),
                    "font_size": unref(self.font_size),
                    "bold": unref(self.bold),
                    "italic": unref(self.italic),
                },
            )
            self._layout = IncrementalTextLayout(
                self._document,
                width=unref(_width),
                height=unref(_height),
                batch=self._batch,
            )
            self._layout.selection_background_color = unref(
                self.selection_background_color
            )
            self._layout.selection_color = unref(self.selection_color)
            self._caret = Caret(
                self._layout, color=unref(self.caret_color), batch=self._batch
            )
            self._caret.visible = False

        self.width = Computed(lambda: self._layout.width)
        self.height = Computed(lambda: self._layout.height)

        def _trigger_dims():
            self.width.trigger()
            self.height.trigger()

        def _on_text():
            self._document.text = unref(self.text)
            _trigger_dims()

        def _on_color():
            self._document.set_style(0, 0, {"color": unref(self.color)})
            _trigger_dims()

        def _on_caret_color():
            self._caret.color = unref(self.caret_color)
            _trigger_dims()

        def _on_selection_background_color():
            self._layout.selection_background_color = unref(
                self.selection_background_color
            )
            _trigger_dims()

        def _on_selection_color():
            self._layout.selection_color = unref(self.selection_color)
            _trigger_dims()

        def _on_font_name():
            self._layout.document.set_style(0, 0, {"font_name": unref(self.font_name)})
            _trigger_dims()

        def _on_font_size():
            self._layout.document.set_style(0, 0, {"font_size": unref(self.font_size)})
            _trigger_dims()

        def _on_bold():
            self._document.set_style(0, 0, {"bold": unref(self.bold)})
            _trigger_dims()

        def _on_italic():
            self._document.set_style(0, 0, {"italic": unref(self.italic)})
            _trigger_dims()

        def _on_width():
            self._layout.width = unref(_width)
            _trigger_dims()

        def _on_height():
            self._layout.height = unref(_height)
            _trigger_dims()

        self._watchers = [
            Watcher([self.text], _on_text) if isref(self.text) else None,
            Watcher([self.color], _on_color) if isref(self.color) else None,
            Watcher([self.caret_color], _on_caret_color)
            if isref(self.caret_color)
            else None,
            Watcher([self.selection_background_color], _on_selection_background_color)
            if isref(self.selection_background_color)
            else None,
            Watcher([self.selection_color], _on_selection_color)
            if isref(self.selection_color)
            else None,
            Watcher([self.font_name], _on_font_name) if isref(self.font_name) else None,
            Watcher([self.font_size], _on_font_size) if isref(self.font_size) else None,
            Watcher([self.bold], _on_bold) if isref(self.bold) else None,
            Watcher([self.italic], _on_italic) if isref(self.italic) else None,
            Watcher([_width], _on_width) if isref(_width) else None,
            Watcher([_height], _on_height) if isref(_height) else None,
        ]

    def draw(self, x: float, y: float):
        self._layout.x = x
        self._layout.y = y
        self._batch.draw()

    @event_handler(ComponentBlurEvent)
    def component_blur_handler(self, _: ComponentBlurEvent):
        self._layout.set_selection(0, 0)
        self._caret.visible = False

    @event_handler(TextEvent)
    def text_handler(self, event: TextEvent):
        self._caret.on_text(event.text)
        self.text.value = self._document.text

    @event_handler(TextMotionEvent)
    def text_motion_handler(self, event: TextMotionEvent):
        self._caret.on_text_motion(event.motion)
        self.text.value = self._document.text

    @event_handler(TextMotionSelectEvent)
    def text_motion_select_handler(self, event: TextMotionSelectEvent):
        self._caret.on_text_motion_select(event.motion)
        self.text.value = self._document.text

    @event_handler(MousePressEvent)
    def mouse_press_handler(self, event: MousePressEvent):
        self.focus()
        self._caret.visible = True
        self._caret.on_mouse_press(
            self._layout.x + event.x,
            self._layout.y + event.y,
            event.button,
            event.modifiers,
        )
        return StopPropagate

    @event_handler(MouseDragEvent)
    def mouse_drag_handler(self, event: MouseDragEvent):
        self._caret.on_mouse_drag(
            self._layout.x + event.x,
            self._layout.y + event.y,
            event.dx,
            event.dy,
            event.buttons,
            event.modifiers,
        )
        return StopPropagate


@dataclass
class Window:
    _width: InitVar[int | ReadRef[int] | None] = field(default=None)
    _height: InitVar[int | ReadRef[int] | None] = field(default=None)
    scene: Component | None = field(default=None)
    resizable: InitVar[bool] = field(default=False, kw_only=True)
    width: ReadRef[int] = field(init=False)
    height: ReadRef[int] = field(init=False)
    _window: _Window = field(init=False)

    def __post_init__(self, _width, _height, resizable):
        self._window = _Window(unref(_width), unref(_height), resizable=resizable)

        self.width = Computed(lambda: self._window.width)
        self.height = Computed(lambda: self._window.height)

        @self._window.event
        def on_draw():
            self._window.clear()
            if (scene := self.scene) is not None:
                scene.draw(0, 0)

        @self._window.event
        def on_key_press(symbol, modifiers):
            if (scene := self.scene) is not None:
                scene.capture(KeyPressEvent(symbol, modifiers))

        @self._window.event
        def on_key_release(symbol, modifiers):
            if (scene := self.scene) is not None:
                scene.capture(KeyReleaseEvent(symbol, modifiers))

        @self._window.event
        def on_mouse_drag(x, y, dx, dy, buttons, modifiers):
            if (scene := self.scene) is not None:
                scene.capture(MouseDragEvent(x, y, dx, dy, buttons, modifiers))

        @self._window.event
        def on_mouse_enter(x, y):
            if (scene := self.scene) is not None:
                scene.capture(MouseEnterEvent(x, y))

        @self._window.event
        def on_mouse_leave(x, y):
            if (scene := self.scene) is not None:
                scene.capture(MouseLeaveEvent(x, y))

        @self._window.event
        def on_mouse_motion(x, y, dx, dy):
            if (scene := self.scene) is not None:
                scene.capture(MouseMotionEvent(x, y, dx, dy))

        @self._window.event
        def on_mouse_press(x, y, button, modifiers):
            if (scene := self.scene) is not None:
                scene.capture(MousePressEvent(x, y, button, modifiers))

        @self._window.event
        def on_mouse_release(x, y, button, modifiers):
            if (scene := self.scene) is not None:
                scene.capture(MouseReleaseEvent(x, y, button, modifiers))

        @self._window.event
        def on_mouse_scroll(x, y, scroll_x, scroll_y):
            if (scene := self.scene) is not None:
                scene.capture(MouseScrollEvent(x, y, scroll_x, scroll_y))

        @self._window.event
        def on_resize(_width, _height):
            self.width.trigger()
            self.height.trigger()

        @self._window.event
        def on_text(text):
            if (scene := self.scene) is not None:
                scene.capture(TextEvent(text))

        @self._window.event
        def on_text_motion(motion):
            if (scene := self.scene) is not None:
                scene.capture(TextMotionEvent(motion))

        @self._window.event
        def on_text_motion_select(motion):
            if (scene := self.scene) is not None:
                scene.capture(TextMotionSelectEvent(motion))
