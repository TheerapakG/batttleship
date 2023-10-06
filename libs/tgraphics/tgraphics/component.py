from collections.abc import Callable
from dataclasses import dataclass, field, replace, InitVar
from functools import partial
import inspect
from typing import Any, ClassVar, ParamSpec
from xml.etree import ElementTree

from pyglet.graphics import Batch
from pyglet.image import TextureRegion
from pyglet.resource import Loader
from pyglet.shapes import Rectangle
from pyglet.sprite import Sprite
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
    ComponentMountedEvent,
    ComponentUnmountedEvent,
    ComponentFocusEvent,
    ComponentBlurEvent,
)
from .reactivity import ReadRef, Ref, Watcher, computed, isref, unref

loader = Loader(["resources"])

P = ParamSpec("P")


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


def _get_merged_locals(frame: inspect.FrameInfo, **additional_locals):
    new_locals = frame.frame.f_locals.copy()
    new_locals.update(additional_locals)
    return new_locals


@dataclass
class ElementComponentData:
    element: ElementTree.Element

    @property
    def cls(self):
        return Component.from_name(self.element.tag)

    @property
    def directives(self):
        return {
            attr_key.removeprefix("t-"): attr_val
            for attr_key, attr_val in self.element.attrib.items()
            if attr_key.startswith("t-")
        }

    @property
    def capturers(self):
        return {
            attr_key.removeprefix("capture-"): attr_val
            for attr_key, attr_val in self.element.attrib.items()
            if attr_key.startswith("capture-")
        }

    @property
    def handlers(self):
        return {
            attr_key.removeprefix("handle-"): attr_val
            for attr_key, attr_val in self.element.attrib.items()
            if attr_key.startswith("handle-")
        }

    @property
    def props(self):
        return {
            attr_key.removeprefix("handle-"): attr_val
            for attr_key, attr_val in self.element.attrib.items()
            if not any(
                attr_key.startswith(prefix) for prefix in ["t-", "capture-", "handle-"]
            )
        }

    def get_init_vars(self, frame: inspect.FrameInfo, additional_locals, override_vars):
        init_locals = _get_merged_locals(frame, **additional_locals)

        init_vars = {
            k: eval(v, frame.frame.f_globals, init_locals)
            for k, v in self.props.items()
        } | override_vars

        event_capturers = {
            Event.from_name(k): eval(v, frame.frame.f_globals, init_locals)
            for k, v in self.capturers.items()
        }
        if (capturers := init_vars.get("event_capturers", None)) is not None:
            capturers.update()
        else:
            init_vars["event_capturers"] = event_capturers

        event_handlers = {
            Event.from_name(k): eval(v, frame.frame.f_globals, init_locals)
            for k, v in self.handlers.items()
        }

        if (handlers := init_vars.get("event_handlers", None)) is not None:
            handlers.update(event_handlers)
        else:
            init_vars["event_handlers"] = event_handlers

        if len(self.element) > 0:
            init_vars["children"] = computed(
                lambda: [
                    component
                    for children in self.element
                    for component in unref(
                        Component.render_element(children, frame, init_locals)
                    )
                ]
            )

        return init_vars


class ComponentMeta(type):
    _components: ClassVar[dict[str, Callable[..., "Component"]]] = dict()
    _cls_event_capturers: dict[type[Event], Callable[["Component", Event], Any]]
    _cls_event_handlers: dict[type[Event], Callable[["Component", Event], Any]]
    _flat_event_capturers: dict[type[Event], Callable[["Component", Event], Any]]
    _flat_event_handlers: dict[type[Event], Callable[["Component", Event], Any]]

    def __new__(
        mcs: type["ComponentMeta"],
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
    ):
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
        cls = super().__new__(mcs, name, bases, attrs)
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
        mcs._components[name] = cls
        return cls

    @classmethod
    def register(mcs, name: str):
        def wrapper(func: Callable[..., "Component"]):
            mcs._components[name] = func
            return func

        return wrapper

    @classmethod
    def from_name(mcs, name: str):
        return mcs._components[name]

    @classmethod
    def render_element(
        mcs,
        element: ElementTree.Element,
        frame: inspect.FrameInfo,
        scope_values: dict | None = None,
    ) -> "list[Component] | ReadRef[list[Component]]":
        """MAKE SURE THAT INPUTTED XML IS SAFE"""

        if scope_values is None:
            scope_values = dict()

        frame_locals = _get_merged_locals(frame, **scope_values)

        data = ElementComponentData(element)

        def render_fn(**additional_scope_values):
            return [
                data.cls(
                    **data.get_init_vars(
                        frame, (scope_values | additional_scope_values), {}
                    )
                )
            ]

        for directive_key, directive_value in data.directives.items():
            match directive_key:
                case "for":

                    def for_render_fn_wrapper(old_render_fn, directive_value):
                        for_var, for_values = [
                            s.strip() for s in directive_value.split("in")
                        ]
                        eval_for_values = computed(
                            lambda: unref(
                                eval(for_values, frame.frame.f_globals, frame_locals)
                            )
                        )

                        def render_fn(**additional_scope_values):
                            return computed(
                                lambda: [
                                    component
                                    for components in [
                                        unref(
                                            old_render_fn(
                                                **(
                                                    {for_var: v}
                                                    | additional_scope_values
                                                ),
                                            )
                                        )
                                        for v in unref(eval_for_values)
                                    ]
                                    for component in components
                                ]
                            )

                        return render_fn

                    render_fn = for_render_fn_wrapper(render_fn, directive_value)
                case "if":

                    def if_render_fn_wrapper(old_render_fn, directive_value):
                        eval_val = computed(
                            lambda: unref(
                                eval(
                                    directive_value, frame.frame.f_globals, frame_locals
                                )
                            )
                        )

                        def render_fn(**additional_scope_values):
                            return computed(
                                lambda: unref(old_render_fn(**additional_scope_values))
                                if unref(eval_val)
                                else []
                            )

                        return render_fn

                    render_fn = if_render_fn_wrapper(render_fn, directive_value)

        x = computed(render_fn)
        return x

    @classmethod
    def render_root_element(
        mcs, element: ElementTree.Element, frame: inspect.FrameInfo, **kwargs
    ) -> "Component":
        """MAKE SURE THAT INPUTTED XML IS SAFE"""

        data = ElementComponentData(element)

        return data.cls(**data.get_init_vars(frame, {}, kwargs))

    @classmethod
    def render_xml(mcs, xml: str, **kwargs) -> "Component | ReadRef['Component']":
        """MAKE SURE THAT THE INPUTTED XML IS SAFE"""
        return mcs.render_root_element(
            ElementTree.fromstring(xml), inspect.stack()[1], **kwargs
        )


@dataclass
class BeforeMountedComponentData:
    offset_x: float | ReadRef[float]  # actual x offset of child relative to parent
    offset_y: float | ReadRef[float]  # actual y offset of child relative to parent
    acc_offset_x: float | ReadRef[float]  # actual x offset of child relative to window
    acc_offset_y: float | ReadRef[float]  # actual y offset of child relative to window
    scale_x: float | ReadRef[float]  # x scaling relative to normal
    scale_y: float | ReadRef[float]  # y scaling relative to normal


@dataclass
class AfterMountedComponentData:
    width: float | ReadRef[float]  # what component think its width is without scaling
    height: float | ReadRef[float]  # what component think its height is without scaling


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
    disabled: bool | ReadRef[bool] = field(default=False)
    event_capturers: dict[type[Event], Callable[[Event], Any]] = field(
        default_factory=dict
    )
    event_handlers: dict[type[Event], Callable[[Event], Any]] = field(
        default_factory=dict
    )
    children: list["Component"] | ReadRef[list["Component"]] = field(
        default_factory=list["Component"]
    )
    before_mounted_component_data: BeforeMountedComponentData = field(init=False)
    after_mounted_component_data: AfterMountedComponentData = field(init=False)
    children_hover: Ref["Component | None"] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    bound_watchers: set[Watcher] = field(init=False, default_factory=set)

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
            focus: Component  # type: ignore[no-redef]
            if focus.capture(ComponentBlurEvent()) is StopPropagate:
                return StopPropagate
            Component._focus.value = None

    def _draw(self, _dt: float):
        pass

    def draw(self, dt: float):
        self._draw(dt)
        for children in unref(self.children):
            children.draw(dt)

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

    def get_relative_x_multiplier(self, comp: "Component"):
        return unref(comp.before_mounted_component_data.scale_x) / unref(
            self.before_mounted_component_data.scale_x
        )

    def get_relative_y_multiplier(self, comp: "Component"):
        return unref(comp.before_mounted_component_data.scale_y) / unref(
            self.before_mounted_component_data.scale_y
        )

    def get_children_at(self, p: Positional) -> "Component | None":
        for children in reversed(unref(self.children)):
            if (
                not unref(children.disabled)
                and unref(children.before_mounted_component_data.offset_x)
                < p.x
                < (
                    unref(children.before_mounted_component_data.offset_x)
                    + unref(children.after_mounted_component_data.width)
                    * self.get_relative_x_multiplier(children)
                )
                and unref(children.before_mounted_component_data.offset_y)
                < p.y
                < (
                    unref(children.before_mounted_component_data.offset_y)
                    + unref(children.after_mounted_component_data.height)
                    * self.get_relative_y_multiplier(children)
                )
            ):
                return children
        return None

    @event_capturer(FocusEvent)
    def focus_capturer(self, event: FocusEvent):
        if (focus := unref(Component._focus)) is not None:
            focus: Component  # type: ignore[no-redef]
            return focus.dispatch(event)

    @event_capturer(BubblingEvent)
    def bubbling_capturer(self, event: BubblingEvent):
        if (children := self.get_children_at(event)) is not None:
            if (
                children.capture(
                    replace(
                        event,
                        x=(
                            event.x
                            - unref(children.before_mounted_component_data.offset_x)
                        )
                        * self.get_relative_x_multiplier(children),
                        y=(
                            event.y
                            - unref(children.before_mounted_component_data.offset_y)
                        )
                        * self.get_relative_y_multiplier(children),
                    )
                )
                is StopPropagate
            ):
                return StopPropagate
        if 0 < event.x < unref(
            self.after_mounted_component_data.width
        ) and 0 < event.y < unref(self.after_mounted_component_data.height):
            return self.dispatch(event)

    @event_capturer(Event)
    def generic_capturer(self, event: Event):
        return self.dispatch(event)

    def _process_children_leave(
        self, p: Positional, new_children: "Component | None" = None
    ):
        if children := unref(self.children_hover):
            children: "Component"  # type: ignore[no-redef]
            children.capture(
                MouseLeaveEvent(
                    (p.x - unref(children.before_mounted_component_data.offset_x))
                    * self.get_relative_x_multiplier(children),
                    (p.y - unref(children.before_mounted_component_data.offset_y))
                    * self.get_relative_y_multiplier(children),
                )
            )
        self.children_hover.value = new_children

    def _process_children_position(self, p: Positional) -> "Component | None":
        if (new_children := self.get_children_at(p)) is not None:
            if self.children_hover.value is not new_children:
                self._process_children_leave(p, new_children)
                new_children.capture(
                    MouseEnterEvent(
                        (
                            p.x
                            - unref(new_children.before_mounted_component_data.offset_x)
                        )
                        * self.get_relative_x_multiplier(new_children),
                        (
                            p.y
                            - unref(new_children.before_mounted_component_data.offset_y)
                        )
                        * self.get_relative_y_multiplier(new_children),
                    )
                )
                self.children_hover.value = new_children
            return new_children
        else:
            self._process_children_leave(p, None)
            return None

    @event_capturer(MouseEnterEvent)
    def mouse_enter_capturer(self, event: MouseEnterEvent):
        self.children_hover.value = None
        self._process_children_position(event)
        return self.dispatch(event)

    @event_capturer(MouseMotionEvent)
    def mouse_motion_capturer(self, event: MouseMotionEvent):
        if (children := self._process_children_position(event)) is not None:
            if (
                children.capture(
                    replace(
                        event,
                        x=(
                            event.x
                            - unref(children.before_mounted_component_data.offset_x)
                        )
                        * self.get_relative_x_multiplier(children),
                        y=(
                            event.y
                            - unref(children.before_mounted_component_data.offset_y)
                        )
                        * self.get_relative_y_multiplier(children),
                    )
                )
                is StopPropagate
            ):
                return StopPropagate
        return self.dispatch(event)

    @event_capturer(MouseLeaveEvent)
    def mouse_leave_capturer(self, event: MouseLeaveEvent):
        self._process_children_leave(event, None)
        return self.dispatch(event)

    @event_handler(MousePressEvent)
    def mouse_press_handler(self, _event: MousePressEvent):
        if unref(Component._focus) is not self:
            Component.blur()

    @event_handler(ComponentUnmountedEvent)
    def component_unmounted_handler(self, _: ComponentUnmountedEvent):
        for watcher in self.bound_watchers:
            watcher.unwatch()
        for children in unref(self.children):
            children.capture(ComponentUnmountedEvent())
        self.bound_watchers.clear()


@dataclass
class Pad(Component):
    children: list["Component"] | ReadRef[list["Component"]] = field(
        default_factory=list["Component"]
    )
    pad_bottom: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    pad_top: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    pad_left: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    pad_right: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    _children_width: Ref[float | ReadRef[float]] = field(
        init=False, default_factory=lambda: Ref(0)
    )
    _children_height: Ref[float | ReadRef[float]] = field(
        init=False, default_factory=lambda: Ref(0)
    )

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        self.after_mounted_component_data = AfterMountedComponentData(
            computed(
                lambda: unref(unref(self._children_width))
                + unref(self.pad_left)
                + unref(self.pad_right)
            ),
            computed(
                lambda: unref(unref(self._children_height))
                + unref(self.pad_bottom)
                + unref(self.pad_top)
            ),
        )

        def mount_children():
            children = unref(self.children)[0]
            before_mounted_component_data = self.before_mounted_component_data
            acc_offset_x = before_mounted_component_data.acc_offset_x
            acc_offset_y = before_mounted_component_data.acc_offset_y
            off_x = computed(
                lambda: unref(self.pad_left)
                * unref(before_mounted_component_data.scale_x)
            )
            off_y = computed(
                lambda: unref(self.pad_bottom)
                * unref(before_mounted_component_data.scale_y)
            )
            children.before_mounted_component_data = BeforeMountedComponentData(
                off_x,
                off_y,
                computed(lambda: unref(acc_offset_x) + unref(off_x)),
                computed(lambda: unref(acc_offset_y) + unref(off_y)),
                before_mounted_component_data.scale_x,
                before_mounted_component_data.scale_y,
            )
            children.capture(ComponentMountedEvent())
            self._children_width.value = children.after_mounted_component_data.width
            self._children_height.value = children.after_mounted_component_data.height

        if isref(self.children):
            self.bound_watchers.add(
                Watcher([self.children], mount_children, trigger_init=True)
            )
        else:
            mount_children()


@dataclass
class Layer(Component):
    children: list["Component"] | ReadRef[list["Component"]] = field(
        default_factory=list["Component"]
    )
    _width: Ref[ReadRef[float] | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    _height: Ref[ReadRef[float] | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        def do_mount_children(children: Component):
            before_mounted_component_data = self.before_mounted_component_data
            acc_offset_x = before_mounted_component_data.acc_offset_x
            acc_offset_y = before_mounted_component_data.acc_offset_y
            pad_x_ref = Ref(0)
            pad_y_ref = Ref(0)
            off_x = computed(
                lambda: unref(unref(pad_x_ref))
                * unref(before_mounted_component_data.scale_x)
            )
            off_y = computed(
                lambda: unref(unref(pad_y_ref))
                * unref(before_mounted_component_data.scale_y)
            )
            children.before_mounted_component_data = BeforeMountedComponentData(
                off_x,
                off_y,
                computed(lambda: unref(acc_offset_x) + unref(off_x)),
                computed(lambda: unref(acc_offset_y) + unref(off_y)),
                before_mounted_component_data.scale_x,
                before_mounted_component_data.scale_y,
            )
            children.capture(ComponentMountedEvent())
            pad_x_ref.value = computed(
                lambda: (
                    unref(width) - unref(children.after_mounted_component_data.width)
                )
                / 2
                if ((width := unref(self._width)) is not None)
                else 0
            )
            pad_y_ref.value = computed(
                lambda: (
                    unref(height) - unref(children.after_mounted_component_data.height)
                )
                / 2
                if ((height := unref(self._height)) is not None)
                else 0
            )

        def mount_children():
            for children in unref(self.children):
                do_mount_children(children)

        if isref(self.children):
            self.bound_watchers.add(
                Watcher([self.children], mount_children, trigger_init=True)
            )
        else:
            mount_children()

        _width = computed(
            lambda: max(
                unref(children.after_mounted_component_data.width)
                for children in unref(self.children)
            )
        )
        self._width.value = _width
        _height = computed(
            lambda: max(
                unref(children.after_mounted_component_data.height)
                for children in unref(self.children)
            )
        )
        self._height.value = _height

        self.after_mounted_component_data = AfterMountedComponentData(_width, _height)


@dataclass
class Row(Component):
    children: list["Component"] | ReadRef[list["Component"]] = field(
        default_factory=list["Component"]
    )
    gap: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    width: int | float | None | ReadRef[int | float | None] = field(default=None)
    height: int | float | None | ReadRef[int | float | None] = field(default=None)
    _children_width: Ref[ReadRef[float] | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    _height: Ref[ReadRef[float] | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        def do_mount_children(children: Component, pad_x: float | ReadRef[float]):
            before_mounted_component_data = self.before_mounted_component_data
            acc_offset_x = before_mounted_component_data.acc_offset_x
            acc_offset_y = before_mounted_component_data.acc_offset_y
            pad_y_ref = Ref(0)
            off_x = computed(
                lambda: unref(pad_x) * unref(before_mounted_component_data.scale_x)
            )
            off_y = computed(
                lambda: unref(unref(pad_y_ref))
                * unref(before_mounted_component_data.scale_y)
            )
            children.before_mounted_component_data = BeforeMountedComponentData(
                off_x,
                off_y,
                computed(lambda: unref(acc_offset_x) + unref(off_x)),
                computed(lambda: unref(acc_offset_y) + unref(off_y)),
                before_mounted_component_data.scale_x,
                before_mounted_component_data.scale_y,
            )
            children.capture(ComponentMountedEvent())
            pad_y_ref.value = computed(
                lambda: (
                    unref(height) - unref(children.after_mounted_component_data.height)
                )
                / 2
                if ((height := unref(self._height)) is not None)
                else 0
            )

            return computed(
                lambda: unref(pad_x)
                + unref(children.after_mounted_component_data.width)
                + unref(self.gap)
            )

        def mount_children():
            pad_x = computed(
                lambda: 0
                if unref(self.width) is None
                or unref(unref(self._children_width)) is None
                else (unref(self.width) - unref(unref(self._children_width))) / 2
            )
            for children in unref(self.children):
                pad_x = do_mount_children(children, pad_x)

        if isref(self.children):
            self.bound_watchers.add(
                Watcher([self.children], mount_children, trigger_init=True)
            )
        else:
            mount_children()

        _children_width = computed(
            lambda: sum(
                unref(children.after_mounted_component_data.width)
                for children in unref(self.children)
            )
            + unref(self.gap) * max(len(unref(self.children)) - 1, 0)
        )
        self._children_width.value = _children_width
        _height = computed(
            lambda: unref(self.height)
            if unref(self.height) is not None
            else max(
                unref(children.after_mounted_component_data.height)
                for children in unref(self.children)
            )
        )
        self._height.value = _height

        self.after_mounted_component_data = AfterMountedComponentData(
            unref(self.width) if unref(self.width) is not None else _children_width,
            _height,
        )


@dataclass
class Column(Component):
    children: list["Component"] | ReadRef[list["Component"]] = field(
        default_factory=list["Component"]
    )
    gap: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    width: int | float | None | ReadRef[int | float | None] = field(default=None)
    height: int | float | None | ReadRef[int | float | None] = field(default=None)
    _width: Ref[ReadRef[float] | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    _children_height: Ref[ReadRef[float] | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        def do_mount_children(children: Component, pad_y: float | ReadRef[float]):
            before_mounted_component_data = self.before_mounted_component_data
            acc_offset_x = before_mounted_component_data.acc_offset_x
            acc_offset_y = before_mounted_component_data.acc_offset_y
            pad_x_ref = Ref(0)
            off_x = computed(
                lambda: unref(unref(pad_x_ref))
                * unref(before_mounted_component_data.scale_x)
            )
            off_y = computed(
                lambda: unref(pad_y) * unref(before_mounted_component_data.scale_y)
            )
            children.before_mounted_component_data = BeforeMountedComponentData(
                off_x,
                off_y,
                computed(lambda: unref(acc_offset_x) + unref(off_x)),
                computed(lambda: unref(acc_offset_y) + unref(off_y)),
                before_mounted_component_data.scale_x,
                before_mounted_component_data.scale_y,
            )
            children.capture(ComponentMountedEvent())
            pad_x_ref.value = computed(
                lambda: (
                    unref(width) - unref(children.after_mounted_component_data.width)
                )
                / 2
                if ((width := unref(self._width)) is not None)
                else 0
            )

            return computed(
                lambda: unref(pad_y)
                + unref(children.after_mounted_component_data.height)
                + unref(self.gap)
            )

        def mount_children():
            pad_y = computed(
                lambda: 0
                if unref(self.height) is None
                or unref(unref(self._children_height)) is None
                else (unref(self.height) - unref(unref(self._children_height))) / 2
            )
            for children in unref(self.children):
                pad_y = do_mount_children(children, pad_y)

        if isref(self.children):
            self.bound_watchers.add(
                Watcher([self.children], mount_children, trigger_init=True)
            )
        else:
            mount_children()

        _width = computed(
            lambda: unref(self.width)
            if unref(self.width) is not None
            else max(
                unref(children.after_mounted_component_data.width)
                for children in unref(self.children)
            )
        )
        self._width.value = _width
        _children_height = computed(
            lambda: sum(
                unref(children.after_mounted_component_data.height)
                for children in unref(self.children)
            )
            + unref(self.gap) * max(len(unref(self.children)) - 1, 0)
        )
        self._children_height.value = _children_height

        self.after_mounted_component_data = AfterMountedComponentData(
            _width,
            unref(self.height) if unref(self.height) is not None else _children_height,
        )


@dataclass
class Rect(Component):
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]]
    width: int | float | ReadRef[int | float]
    height: int | float | ReadRef[int | float]
    _rect: Rectangle = field(init=False)

    def _draw(self, _dt: float):
        self._rect.draw()

    def _update_x(self, x: float):
        self._rect.x = x

    def _update_y(self, y: float):
        self._rect.y = y

    def _update_width(self, width: float):
        self._rect.width = width

    def _update_height(self, height: float):
        self._rect.height = height

    def _update_color(self, color: tuple[int, int, int, int]):
        self._rect.color = color

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        before_mounted_component_data = self.before_mounted_component_data
        x = before_mounted_component_data.acc_offset_x
        y = before_mounted_component_data.acc_offset_y
        width = computed(
            lambda: unref(self.width) * unref(before_mounted_component_data.scale_x)
        )
        height = computed(
            lambda: unref(self.height) * unref(before_mounted_component_data.scale_y)
        )
        self._rect = Rectangle(
            unref(x), unref(y), unref(width), unref(height), unref(self.color)
        )

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(width, self._update_width),
                    Watcher.ifref(height, self._update_height),
                    Watcher.ifref(self.color, self._update_color),
                ]
                if w is not None
            ]
        )

        self.after_mounted_component_data = AfterMountedComponentData(
            self.width, self.height
        )


@dataclass
class Image(Component):
    name: str | ReadRef[str]
    width: int | float | ReadRef[int | float] | None = field(default=None)
    height: int | float | ReadRef[int | float] | None = field(default=None)
    _sprite: Sprite = field(init=False)

    def _draw(self, _dt: float):
        self._sprite.draw()

    def _update_x(self, x: float):
        self._sprite.x = x

    def _update_y(self, y: float):
        self._sprite.y = y

    def _update_width(self, width: float):
        self._sprite.width = width

    def _update_height(self, height: float):
        self._sprite.height = height

    def _update_image(self, image: TextureRegion):
        self._sprite.image = image

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        before_mounted_component_data = self.before_mounted_component_data
        x = before_mounted_component_data.acc_offset_x
        y = before_mounted_component_data.acc_offset_y
        image = computed(lambda: loader.image(unref(self.name)))
        width = computed(
            lambda: unref(self.width) * unref(before_mounted_component_data.scale_x)
            if self.width is not None
            else unref(image).width * unref(before_mounted_component_data.scale_x)
        )
        height = computed(
            lambda: unref(self.height) * unref(before_mounted_component_data.scale_y)
            if self.height is not None
            else unref(image).height * unref(before_mounted_component_data.scale_y)
        )
        self._sprite = Sprite(
            unref(x), unref(y), unref(width), unref(height), unref(image)
        )

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(width, self._update_width),
                    Watcher.ifref(height, self._update_height),
                    Watcher.ifref(image, self._update_image),
                ]
                if w is not None
            ]
        )

        self.after_mounted_component_data = AfterMountedComponentData(width, height)

    @event_handler(ComponentUnmountedEvent)
    def component_unmounted_handler(self, event: ComponentUnmountedEvent):
        super().component_unmounted_handler(event)
        self._sprite.delete()
        del self._sprite


@dataclass
class Label(Component):
    text: str | ReadRef[str]
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]] = field(
        default=(255, 255, 255, 255)
    )
    font_name: str | None | ReadRef[str | None] = field(default=None)
    font_size: int | float | None | ReadRef[int | float | None] = field(default=None)
    bold: bool | ReadRef[bool] = field(default=False)
    italic: bool | ReadRef[bool] = field(default=False)
    width: int | float | ReadRef[int | float] | None = field(default=None)
    height: int | float | ReadRef[int | float] | None = field(default=None)
    _label: Ref[_Label] = field(init=False)

    def _draw(self, _dt: float):
        self._label.value.draw()

    def _update_x(self, x: float):
        self._label.value.x = x

    def _update_y(self, y: float):
        self._label.value.y = y

    def _update_text(self, text: str):
        self._label.value.text = text
        self._label.trigger()

    def _update_color(self, color: tuple[int, int, int, int]):
        self._label.value.color = color

    def _update_font_name(self, font_name: str | None):
        self._label.value.font_name = font_name
        self._label.trigger()

    def _update_font_size(self, font_size: int | float | None):
        self._label.value.font_size = font_size
        self._label.trigger()

    def _update_bold(self, bold: bool):
        self._label.value.bold = bold
        self._label.trigger()

    def _update_italic(self, italic: bool):
        self._label.value.italic = italic
        self._label.trigger()

    def _update_width(self, width: int | float):
        self._label.value.width = width
        self._label.trigger()

    def _update_height(self, height: int | float):
        self._label.value.height = height
        self._label.trigger()

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        before_mounted_component_data = self.before_mounted_component_data
        x = before_mounted_component_data.acc_offset_x
        y = before_mounted_component_data.acc_offset_y
        scale_x = before_mounted_component_data.scale_x
        scale_y = before_mounted_component_data.scale_y
        _width = computed(
            lambda: unref(self.width) * unref(scale_x)
            if self.width is not None
            else None
        )
        _height = computed(
            lambda: unref(self.height) * unref(scale_y)
            if self.height is not None
            else None
        )
        self._label = Ref(
            _Label(
                unref(self.text),
                font_name=unref(self.font_name),
                font_size=unref(self.font_size),
                bold=unref(self.bold),
                italic=unref(self.italic),
                color=unref(self.color),
                width=unref(_width),
                height=unref(_height),
            )
        )
        self._label.value.x = unref(x)
        self._label.value.y = unref(y)

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(self.text, self._update_text),
                    Watcher.ifref(self.font_name, self._update_font_name),
                    Watcher.ifref(self.font_size, self._update_font_size),
                    Watcher.ifref(self.bold, self._update_bold),
                    Watcher.ifref(self.italic, self._update_italic),
                    Watcher.ifref(_width, self._update_width),
                    Watcher.ifref(_height, self._update_height),
                ]
                if w is not None
            ]
        )

        width = (
            self.width
            if self.width is not None
            else computed(lambda: unref(self._label).content_width / unref(scale_x))
        )
        height = (
            self.height
            if self.height is not None
            else computed(lambda: unref(self._label).content_height / unref(scale_y))
        )

        self.after_mounted_component_data = AfterMountedComponentData(width, height)


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
    font_name: str | None | ReadRef[str | None] = field(default=None)
    font_size: int | float | None | ReadRef[int | float | None] = field(default=None)
    bold: bool | ReadRef[bool] = field(default=False)
    italic: bool | ReadRef[bool] = field(default=False)
    width: int | float | ReadRef[int | float] | None = field(default=None)
    height: int | float | ReadRef[int | float] | None = field(default=None)
    _batch: Batch = field(init=False)
    _document: UnformattedDocument = field(init=False)
    _layout: Ref[IncrementalTextLayout] = field(init=False)
    _caret: Caret = field(init=False)

    def _draw(self, _dt: float):
        self._batch.draw()

    def _update_x(self, x: float):
        self._layout.value.x = x

    def _update_y(self, y: float):
        self._layout.value.y = y

    def _update_text(self, text: str):
        self._document.text = text
        self._layout.trigger()

    def _update_color(self, color: tuple[int, int, int, int]):
        self._document.set_style(0, 0, {"color": color})

    def _update_caret_color(self, caret_color: tuple[int, int, int, int]):
        self._caret.color = caret_color

    def _update_selection_background_color(
        self, selection_background_color: tuple[int, int, int, int]
    ):
        self._layout.value.selection_background_color = selection_background_color

    def _update_selection_color(self, selection_color: tuple[int, int, int, int]):
        self._layout.value.selection_color = selection_color

    def _update_font_name(self, font_name: str | None):
        self._document.set_style(0, 0, {"font_name": font_name})
        self._layout.trigger()

    def _update_font_size(self, font_size: int | float | None):
        self._document.set_style(0, 0, {"font_size": font_size})
        self._layout.trigger()

    def _update_bold(self, bold: bool):
        self._document.set_style(0, 0, {"bold": bold})
        self._layout.trigger()

    def _update_italic(self, italic: bool):
        self._document.set_style(0, 0, {"italic": italic})
        self._layout.trigger()

    def _update_width(self, width: int | float):
        self._layout.value.width = width
        self._layout.trigger()

    def _update_height(self, height: int | float):
        self._layout.value.height = height
        self._layout.trigger()

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        before_mounted_component_data = self.before_mounted_component_data
        x = before_mounted_component_data.acc_offset_x
        y = before_mounted_component_data.acc_offset_y
        scale_x = before_mounted_component_data.scale_x
        scale_y = before_mounted_component_data.scale_y
        _width = computed(
            lambda: unref(self.width) * unref(scale_x)
            if self.width is not None
            else None
        )
        _height = computed(
            lambda: unref(self.height) * unref(scale_y)
            if self.height is not None
            else None
        )

        self._batch = Batch()

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

        self._layout = Ref(
            IncrementalTextLayout(
                self._document,
                width=unref(_width),
                height=unref(_height),
                batch=self._batch,
            )
        )
        self._layout.value.selection_background_color = unref(
            self.selection_background_color
        )
        self._layout.value.selection_color = unref(self.selection_color)
        self._layout.value.x = unref(x)
        self._layout.value.y = unref(y)

        self._caret = Caret(
            unref(self._layout), color=unref(self.caret_color), batch=self._batch
        )
        self._caret.visible = False

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(self.text, self._update_text),
                    Watcher.ifref(self.color, self._update_color),
                    Watcher.ifref(self.caret_color, self._update_caret_color),
                    Watcher.ifref(
                        self.selection_background_color,
                        self._update_selection_background_color,
                    ),
                    Watcher.ifref(self.selection_color, self._update_selection_color),
                    Watcher.ifref(self.font_name, self._update_font_name),
                    Watcher.ifref(self.font_size, self._update_font_size),
                    Watcher.ifref(self.bold, self._update_bold),
                    Watcher.ifref(self.italic, self._update_italic),
                    Watcher.ifref(_width, self._update_width),
                    Watcher.ifref(_height, self._update_height),
                ]
                if w is not None
            ]
        )

        width = (
            self.width
            if self.width is not None
            else computed(lambda: unref(self._layout).content_width / unref(scale_x))
        )
        height = (
            self.height
            if self.height is not None
            else computed(lambda: unref(self._layout).content_height / unref(scale_y))
        )

        self.after_mounted_component_data = AfterMountedComponentData(width, height)

    @event_handler(ComponentBlurEvent)
    def component_blur_handler(self, _: ComponentBlurEvent):
        self._layout.value.set_selection(0, 0)
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
            self._layout.value.x + event.x,
            self._layout.value.y + event.y,
            event.button,
            event.modifiers,
        )
        return StopPropagate

    @event_handler(MouseDragEvent)
    def mouse_drag_handler(self, event: MouseDragEvent):
        self._caret.on_mouse_drag(
            self._layout.value.x + event.x,
            self._layout.value.y + event.y,
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
    _scene: Component | None = field(default=None)
    resizable: InitVar[bool] = field(default=False, kw_only=True)
    width: ReadRef[int] = field(init=False)
    height: ReadRef[int] = field(init=False)
    _window: _Window = field(init=False)

    def __post_init__(self, _width, _height, resizable):
        self._window = _Window(unref(_width), unref(_height), resizable=resizable)

        self.width = Ref(self._window.width)
        self.height = Ref(self._window.height)

        @self._window.event
        def on_refresh(dt: float):
            self._window.clear()
            if (scene := self.scene) is not None:
                scene.draw(dt)

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
        def on_resize(width, height):
            self.width.value = width
            self.height.value = height

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

    @property
    def scene(self):
        return self._scene

    @scene.setter
    def scene(self, new_scene: Component):
        if (scene := self.scene) is not None:
            self._scene = new_scene
            scene.capture(ComponentUnmountedEvent())
        else:
            self._scene = new_scene
        new_scene.before_mounted_component_data = BeforeMountedComponentData(
            0, 0, 0, 0, 1, 1
        )
        new_scene.capture(ComponentMountedEvent())
