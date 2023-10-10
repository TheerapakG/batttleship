from collections.abc import Callable
from dataclasses import dataclass, field, replace, InitVar
import inspect
import re
import time
from typing import Any, ClassVar, Generic, ParamSpec, TypeVar
from xml.etree import ElementTree

import pyglet
from pyglet import gl
from pyglet.graphics import Batch
from pyglet.graphics.vertexdomain import VertexList
from pyglet.image import TextureRegion
from pyglet.resource import Loader
from pyglet.shapes import Rectangle
from pyglet.sprite import Sprite
from pyglet.text import Label as _Label
from pyglet.text.document import UnformattedDocument
from pyglet.text.layout import IncrementalTextLayout
from pyglet.window import Window as _Window, key

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
    InputEvent,
)
from .reactivity import ReadRef, Ref, Watcher, computed, unref

loader = Loader(["resources"])

P = ParamSpec("P")


@dataclass
class _EventCapturer:
    event: type[Event]
    func: Callable[["ComponentInstance", Event], Any]

    def __call__(self, event: Event):
        # For tricking LSP / type checker
        raise NotImplementedError()


@dataclass
class _EventHandler:
    event: type[Event]
    func: Callable[["ComponentInstance", Event], Any]

    def __call__(self, event: Event):
        # For tricking LSP / type checker
        raise NotImplementedError()


def event_capturer(cls: type[Event]):
    def make_capturer(func: Callable[["ComponentInstance", Event], Any]):
        return _EventCapturer(cls, func)

    return make_capturer


def event_handler(cls: type[Event]):
    def make_handler(func: Callable[["ComponentInstance", Event], Any]):
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
            capturers.update(event_capturers)
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
            render_results = [
                Component.render_element(children, frame, init_locals)
                for children in self.element
            ]
            init_vars["children"] = computed(
                lambda: [
                    component
                    for render_result in render_results
                    for component in unref(render_result)
                ]
            )

        return init_vars


@dataclass
class BeforeMountedComponentInstanceData:
    offset_x: float | ReadRef[float]  # actual x offset of child relative to parent
    offset_y: float | ReadRef[float]  # actual y offset of child relative to parent
    acc_offset_x: float | ReadRef[float]  # actual x offset of child relative to window
    acc_offset_y: float | ReadRef[float]  # actual y offset of child relative to window
    scale_x: float | ReadRef[float]  # x scaling relative to parent
    scale_y: float | ReadRef[float]  # y scaling relative to parent
    acc_scale_x: float | ReadRef[float]  # x scaling relative to window
    acc_scale_y: float | ReadRef[float]  # y scaling relative to window


@dataclass
class AfterMountedComponentInstanceData:
    width: float | ReadRef[float]  # what component think its width is without scaling
    height: float | ReadRef[float]  # what component think its height is without scaling
    children: list["ComponentInstance" | ReadRef["ComponentInstance"]] | ReadRef[
        list["ComponentInstance" | ReadRef["ComponentInstance"]]
    ] = field(default_factory=list["ComponentInstance" | ReadRef["ComponentInstance"]])


C = TypeVar("C", bound="Component")


class ComponentInstanceMeta(type):
    _cls_event_capturers: dict[type[Event], Callable[["ComponentInstance", Event], Any]]
    _cls_event_handlers: dict[type[Event], Callable[["ComponentInstance", Event], Any]]
    _flat_event_capturers: dict[
        type[Event], Callable[["ComponentInstance", Event], Any]
    ]
    _flat_event_handlers: dict[type[Event], Callable[["ComponentInstance", Event], Any]]
    _focus: Ref["ComponentInstance | None"]

    def __new__(
        mcs: type["ComponentInstanceMeta"],
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
        return cls

    @property
    def focus(cls):
        return cls._focus

    @focus.setter
    def focus(cls, instance: "ComponentInstance"):
        focus = unref(ComponentInstance._focus)
        if focus is instance:
            return StopPropagate

        if instance.capture(ComponentFocusEvent()) is StopPropagate:
            return StopPropagate

        if cls.blur() is StopPropagate:  # pylint: disable=E1120
            return StopPropagate

        cls._focus.value = instance

    def blur(cls):
        if (focus := unref(cls._focus)) is not None:
            focus: ComponentInstance  # type: ignore[no-redef]
            if focus.capture(ComponentBlurEvent()) is StopPropagate:
                return StopPropagate
            cls._focus.value = None


@dataclass(kw_only=True)
class ComponentInstance(Generic[C], metaclass=ComponentInstanceMeta):
    _cls_event_capturers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Any]]
    ]
    _cls_event_handlers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Any]]
    ]
    _flat_event_capturers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Any]]
    ]
    _flat_event_handlers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Any]]
    ]
    _focus: ClassVar[Ref["ComponentInstance | None"]] = Ref(None)
    component: C
    event_capturers: dict[
        type[Event], Callable[["ComponentInstance", Event], Any]
    ] = field(init=False)
    event_handlers: dict[
        type[Event], Callable[["ComponentInstance", Event], Any]
    ] = field(init=False)
    before_mounted_data: Ref[BeforeMountedComponentInstanceData | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    after_mounted_data: Ref["AfterMountedComponentInstanceData | None"] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    child_hover: Ref["ComponentInstance | None"] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    bound_watchers: set[Watcher] = field(init=False, default_factory=set)

    def __post_init__(self):
        # TODO: merge capturer / handler
        capturers = self._flat_event_capturers.copy()
        handlers = self._flat_event_handlers.copy()
        capturers.update(
            {
                event: lambda _, e: capturer(e)
                for event, capturer in self.component.event_capturers.items()
            }
        )
        handlers.update(
            {
                event: lambda _, e: handler(e)
                for event, handler in self.component.event_handlers.items()
            }
        )
        self.event_capturers = capturers
        self.event_handlers = handlers

    def __hash__(self) -> int:
        return id(self)

    def _draw(self, _dt: float):
        pass

    def draw(self, dt: float):
        self._draw(dt)
        for children in unref(use_children(self)):
            unref(children).draw(dt)

    def capture(self, event: Event):
        if not unref(self.component.disabled):
            for event_type in type(event).mro():
                if (capturer := self.event_capturers.get(event_type)) is not None:
                    return capturer(self, event)

    def dispatch(self, event: Event):
        if not unref(self.component.disabled):
            for event_type in type(event).mro():
                if (handler := self.event_handlers.get(event_type)) is not None:
                    return handler(self, event)

    def get_child_at(self, p: Positional) -> "ComponentInstance | None":
        for child in reversed(unref(use_children(self))):
            unref_child = unref(child)
            if (
                not unref(unref_child.component.disabled)
                and unref(use_offset_x(unref_child))
                < p.x
                < (
                    unref(use_offset_x(unref_child))
                    + unref(use_width(unref_child)) * unref(use_scale_x(self))
                )
                and unref(use_offset_y(unref_child))
                < p.y
                < (
                    unref(use_offset_y(unref_child))
                    + unref(use_height(unref_child)) * unref(use_scale_y(self))
                )
            ):
                return unref_child
        return None

    @event_capturer(FocusEvent)
    def focus_capturer(self, event: FocusEvent):
        if (focus := unref(ComponentInstance.focus)) is not None:
            focus: ComponentInstance  # type: ignore[no-redef]
            return focus.dispatch(event)

    @event_capturer(BubblingEvent)
    def bubbling_capturer(self, event: BubblingEvent):
        if (child := self.get_child_at(event)) is not None:
            if (
                child.capture(
                    replace(
                        event,
                        x=(event.x - unref(use_offset_x(child)))
                        / unref(use_scale_x(self)),
                        y=(event.y - unref(use_offset_y(child)))
                        / unref(use_scale_y(self)),
                    )
                )
                is StopPropagate
            ):
                return StopPropagate
        if 0 < event.x < unref(use_width(self)) and 0 < event.y < unref(
            use_height(self)
        ):
            return self.dispatch(event)

    @event_capturer(Event)
    def generic_capturer(self, event: Event):
        return self.dispatch(event)

    def _process_child_leave(
        self, p: Positional, new_child: "ComponentInstance | None" = None
    ):
        if child := unref(self.child_hover):
            child: "ComponentInstance"  # type: ignore[no-redef]
            child.capture(
                MouseLeaveEvent(
                    (p.x - unref(use_offset_x(child))) / unref(use_scale_x(self)),
                    (p.y - unref(use_offset_y(child))) / unref(use_scale_y(self)),
                )
            )
        self.child_hover.value = new_child

    def _process_child_position(self, p: Positional) -> "ComponentInstance | None":
        if (new_child := self.get_child_at(p)) is not None:
            if self.child_hover.value is not new_child:
                self._process_child_leave(p, new_child)
                new_child.capture(
                    MouseEnterEvent(
                        (p.x - unref(use_offset_x(new_child)))
                        / unref(use_scale_x(self)),
                        (p.y - unref(use_offset_y(new_child)))
                        / unref(use_scale_y(self)),
                    )
                )
                self.child_hover.value = new_child
            return new_child
        else:
            self._process_child_leave(p, None)
            return None

    @event_capturer(MouseEnterEvent)
    def mouse_enter_capturer(self, event: MouseEnterEvent):
        self.child_hover.value = None
        self._process_child_position(event)
        return self.dispatch(event)

    @event_capturer(MouseMotionEvent)
    def mouse_motion_capturer(self, event: MouseMotionEvent):
        if (child := self._process_child_position(event)) is not None:
            if (
                child.capture(
                    replace(
                        event,
                        x=(event.x - unref(use_offset_x(child)))
                        / unref(use_scale_x(self)),
                        y=(event.y - unref(use_offset_y(child)))
                        / unref(use_scale_y(self)),
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
        if unref(ComponentInstance.focus) is not self:
            ComponentInstance.blur()

    @event_handler(ComponentUnmountedEvent)
    def component_unmounted_handler(self, _: ComponentUnmountedEvent):
        for watcher in self.bound_watchers:
            watcher.unwatch()
        for child in unref(use_children(self)):
            unref(child).capture(ComponentUnmountedEvent())
        self.bound_watchers.clear()
        self.before_mounted_data.value = None
        self.after_mounted_data.value = None


def use_offset_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.offset_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_offset_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.offset_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_acc_offset_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.acc_offset_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_acc_offset_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.acc_offset_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_scale_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.scale_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_scale_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.scale_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_acc_scale_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.acc_scale_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_acc_scale_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.acc_scale_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_width(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.width)
        if (data := unref(unref(instance).after_mounted_data)) is not None
        else 0
    )


def use_height(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    return computed(
        lambda: unref(data.height)
        if (data := unref(unref(instance).after_mounted_data)) is not None
        else 0
    )


def use_children(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> (
    list[ComponentInstance | ReadRef[ComponentInstance]]
    | ReadRef[list[ComponentInstance | ReadRef[ComponentInstance]]]
):
    return computed(
        lambda: unref(data.children)
        if (data := unref(unref(instance).after_mounted_data)) is not None
        else []
    )


def is_mounted(instance: ComponentInstance):
    return computed(
        lambda: unref(instance.before_mounted_data) is not None
        and unref(instance.after_mounted_data) is not None
    )


class ComponentMeta(type):
    _components: ClassVar[dict[str, Callable[..., "Component"]]] = dict()

    def __new__(
        mcs: type["ComponentMeta"],
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
    ):
        cls = super().__new__(mcs, name, bases, attrs)
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
            scope_values = {}

        frame_locals = _get_merged_locals(frame, **scope_values)

        data = ElementComponentData(element)

        def render_fn(
            **additional_scope_values,
        ) -> list["Component"]:
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

                    def for_render_fn_wrapper(
                        old_render_fn: Callable[..., list["Component"]],
                        directive_value: str,
                    ):
                        for_var, for_values = [
                            s.strip() for s in directive_value.split("in")
                        ]
                        eval_for_values = computed(
                            lambda: unref(
                                eval(for_values, frame.frame.f_globals, frame_locals)
                            )
                        )

                        def render_fn(**additional_scope_values):
                            return [
                                component
                                for components in [
                                    unref(
                                        old_render_fn(
                                            **({for_var: v} | additional_scope_values),
                                        )
                                    )
                                    for v in unref(eval_for_values)
                                ]
                                for component in components
                            ]

                        return render_fn

                    render_fn = for_render_fn_wrapper(render_fn, directive_value)
                case "if":

                    def if_render_fn_wrapper(
                        old_render_fn: Callable[..., list["Component"]],
                        directive_value: str,
                    ):
                        eval_val = computed(
                            lambda: unref(
                                eval(
                                    directive_value, frame.frame.f_globals, frame_locals
                                )
                            )
                        )

                        def render_fn(**additional_scope_values):
                            return (
                                unref(old_render_fn(**additional_scope_values))
                                if unref(eval_val)
                                else []
                            )

                        return render_fn

                    render_fn = if_render_fn_wrapper(render_fn, directive_value)

        return computed(render_fn)

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


@dataclass(kw_only=True)
class Component(metaclass=ComponentMeta):
    disabled: bool | ReadRef[bool] = field(default=False)
    event_capturers: dict[type[Event], Callable[[Event], Any]] = field(
        default_factory=dict, repr=False
    )
    event_handlers: dict[type[Event], Callable[[Event], Any]] = field(
        default_factory=dict, repr=False
    )
    children: list["Component" | ReadRef["Component"]] | ReadRef[
        list["Component" | ReadRef["Component"]]
    ] = field(default_factory=list["Component" | ReadRef["Component"]])

    def get_instance(self):
        return ComponentInstance(component=self)


@dataclass
class PadInstance(ComponentInstance["Pad"]):
    def __hash__(self) -> int:
        return id(self)

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        child = computed(
            lambda: unref(unref(self.component.children)[0]).get_instance()
        )

        def mount_child(child: ComponentInstance):
            off_x = computed(
                lambda: unref(self.component.pad_left) * unref(use_acc_scale_x(self))
            )
            off_y = computed(
                lambda: unref(self.component.pad_bottom) * unref(use_acc_scale_y(self))
            )
            child.before_mounted_data.value = BeforeMountedComponentInstanceData(
                off_x,
                off_y,
                computed(lambda: unref(use_acc_offset_x(self)) + unref(off_x)),
                computed(lambda: unref(use_acc_offset_y(self)) + unref(off_y)),
                1,
                1,
                use_acc_scale_x(self),
                use_acc_scale_y(self),
            )
            child.capture(ComponentMountedEvent())

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(child, mount_child, trigger_init=True),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            computed(
                lambda: unref(use_width(unref(child)[0]))
                + unref(self.component.pad_left)
                + unref(self.component.pad_right)
            ),
            computed(
                lambda: unref(use_height(unref(child)[0]))
                + unref(self.component.pad_bottom)
                + unref(self.component.pad_top)
            ),
            computed(lambda: [unref(child)]),
        )


@dataclass
class Pad(Component):
    children: list["Component" | ReadRef["Component"]] | ReadRef[
        list["Component" | ReadRef["Component"]]
    ] = field(default_factory=list["Component" | ReadRef["Component"]])
    pad_bottom: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    pad_top: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    pad_left: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    pad_right: int | float | ReadRef[int | float] = field(default=0, kw_only=True)

    def get_instance(self):
        return PadInstance(component=self)


@dataclass
class LayerInstance(ComponentInstance["Layer"]):
    def __hash__(self) -> int:
        return id(self)

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        children = computed(
            lambda: [
                computed(lambda c=c: unref(c).get_instance())
                for c in unref(self.component.children)
            ]
        )
        collapsed_children = computed(lambda: [unref(c) for c in unref(children)])
        previous_collapsed_children: list[ComponentInstance] = []

        def mount_child(index: int):
            child = unref(collapsed_children)[index]

            pad_x = computed(
                lambda: (unref(use_width(self)) - unref(use_width(child))) / 2
            )
            pad_y = computed(
                lambda: (unref(use_height(self)) - unref(use_height(child))) / 2
            )

            off_x = computed(lambda: unref(pad_x) * unref(use_acc_scale_x(self)))
            off_y = computed(lambda: unref(pad_y) * unref(use_acc_scale_y(self)))
            child.before_mounted_data.value = BeforeMountedComponentInstanceData(
                off_x,
                off_y,
                computed(lambda: unref(use_acc_offset_x(self)) + unref(off_x)),
                computed(lambda: unref(use_acc_offset_y(self)) + unref(off_y)),
                1,
                1,
                use_acc_scale_x(self),
                use_acc_scale_y(self),
            )
            child.capture(ComponentMountedEvent())

        def mount_children(current_collapsed_children: list[ComponentInstance]):
            nonlocal previous_collapsed_children
            child_lookup = {
                child: i for i, child in enumerate(unref(current_collapsed_children))
            }
            current = set(current_collapsed_children)
            previous = set(previous_collapsed_children)
            for child in previous - current:
                child.capture(ComponentUnmountedEvent())
            for child in current - previous:
                mount_child(child_lookup[child])

            previous_collapsed_children = current_collapsed_children

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(children, mount_children, trigger_init=True),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            computed(lambda: max(unref(use_width(child)) for child in unref(children))),
            computed(
                lambda: max(unref(use_height(child)) for child in unref(children))
            ),
            children,
        )


@dataclass
class Layer(Component):
    children: list["Component" | ReadRef["Component"]] | ReadRef[
        list["Component" | ReadRef["Component"]]
    ] = field(default_factory=list["Component" | ReadRef["Component"]])

    def get_instance(self):
        return LayerInstance(component=self)


@dataclass
class RowInstance(ComponentInstance["Row"]):
    def __hash__(self) -> int:
        return id(self)

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        children = computed(
            lambda: [
                computed(lambda c=c: unref(c).get_instance())
                for c in unref(self.component.children)
            ]
        )
        children_width = computed(lambda: [use_width(c) for c in unref(children)])
        collapsed_children = computed(lambda: [unref(c) for c in unref(children)])
        previous_collapsed_children: list[ComponentInstance] = []

        sum_width = computed(
            lambda: sum(unref(c_w) for c_w in unref(children_width))
            + (len(unref(children_width)) - 1) * unref(self.component.gap)
        )

        width = computed(
            lambda: unref(self.component.width)
            if unref(self.component.width) is not None
            else unref(sum_width)
        )

        height = computed(
            lambda: unref(self.component.height)
            if unref(self.component.height) is not None
            else max(unref(use_height(child)) for child in unref(children))
        )

        def mount_child(index: int):
            child = unref(collapsed_children)[index]

            pad_x = computed(
                lambda: ((unref(width) - unref(sum_width)) / 2)
                + sum(unref(c_w) for c_w in unref(children_width)[:index])
                + index * unref(self.component.gap)
            )
            pad_y = computed(lambda: (unref(height) - unref(use_height(child))) / 2)

            off_x = computed(lambda: unref(pad_x) * unref(use_acc_scale_x(self)))
            off_y = computed(lambda: unref(pad_y) * unref(use_acc_scale_y(self)))
            child.before_mounted_data.value = BeforeMountedComponentInstanceData(
                off_x,
                off_y,
                computed(lambda: unref(use_acc_offset_x(self)) + unref(off_x)),
                computed(lambda: unref(use_acc_offset_y(self)) + unref(off_y)),
                1,
                1,
                use_acc_scale_x(self),
                use_acc_scale_y(self),
            )
            child.capture(ComponentMountedEvent())

        def mount_children(current_collapsed_children: list[ComponentInstance]):
            nonlocal previous_collapsed_children
            child_lookup = {
                child: i for i, child in enumerate(unref(current_collapsed_children))
            }
            current = set(current_collapsed_children)
            previous = set(previous_collapsed_children)
            for child in previous - current:
                child.capture(ComponentUnmountedEvent())
            for child in current - previous:
                mount_child(child_lookup[child])

            previous_collapsed_children = current_collapsed_children

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        collapsed_children, mount_children, trigger_init=True
                    ),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width, height, children
        )


@dataclass
class Row(Component):
    children: list["Component" | ReadRef["Component"]] | ReadRef[
        list["Component" | ReadRef["Component"]]
    ] = field(default_factory=list["Component" | ReadRef["Component"]])
    gap: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    width: int | float | None | ReadRef[int | float | None] = field(default=None)
    height: int | float | None | ReadRef[int | float | None] = field(default=None)

    def get_instance(self):
        return RowInstance(component=self)


@dataclass
class ColumnInstance(ComponentInstance["Column"]):
    def __hash__(self) -> int:
        return id(self)

    @event_handler(ComponentMountedEvent)
    def component_mounted_handler(self, _: ComponentMountedEvent):
        children = computed(
            lambda: [
                computed(lambda c=c: unref(c).get_instance())
                for c in unref(self.component.children)
            ]
        )
        children_height = computed(lambda: [use_height(c) for c in unref(children)])
        collapsed_children = computed(lambda: [unref(c) for c in unref(children)])
        previous_collapsed_children: list[ComponentInstance] = []

        sum_height = computed(
            lambda: sum(unref(c_w) for c_w in unref(children_height))
            + (len(unref(children_height)) - 1) * unref(self.component.gap)
        )

        width = computed(
            lambda: unref(self.component.width)
            if unref(self.component.width) is not None
            else max(unref(use_width(child)) for child in unref(children))
        )

        height = computed(
            lambda: unref(self.component.height)
            if unref(self.component.height) is not None
            else unref(sum_height)
        )

        def mount_child(index: int):
            child = unref(collapsed_children)[index]

            pad_x = computed(lambda: (unref(width) - unref(use_width(child))) / 2)
            pad_y = computed(
                lambda: ((unref(height) - unref(sum_height)) / 2)
                + sum(unref(c_h) for c_h in unref(children_height)[:index])
                + index * unref(self.component.gap)
            )

            off_x = computed(lambda: unref(pad_x) * unref(use_acc_scale_x(self)))
            off_y = computed(lambda: unref(pad_y) * unref(use_acc_scale_y(self)))
            child.before_mounted_data.value = BeforeMountedComponentInstanceData(
                off_x,
                off_y,
                computed(lambda: unref(use_acc_offset_x(self)) + unref(off_x)),
                computed(lambda: unref(use_acc_offset_y(self)) + unref(off_y)),
                1,
                1,
                use_acc_scale_x(self),
                use_acc_scale_y(self),
            )
            child.capture(ComponentMountedEvent())

        def mount_children(current_collapsed_children: list[ComponentInstance]):
            nonlocal previous_collapsed_children
            child_lookup = {
                child: i for i, child in enumerate(unref(current_collapsed_children))
            }
            current = set(current_collapsed_children)
            previous = set(previous_collapsed_children)
            for child in previous - current:
                child.capture(ComponentUnmountedEvent())
            for child in current - previous:
                mount_child(child_lookup[child])

            previous_collapsed_children = current_collapsed_children

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        collapsed_children, mount_children, trigger_init=True
                    ),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width, height, children
        )


@dataclass
class Column(Component):
    children: list["Component" | ReadRef["Component"]] | ReadRef[
        list["Component" | ReadRef["Component"]]
    ] = field(default_factory=list["Component" | ReadRef["Component"]])
    gap: int | float | ReadRef[int | float] = field(default=0, kw_only=True)
    width: int | float | None | ReadRef[int | float | None] = field(default=None)
    height: int | float | None | ReadRef[int | float | None] = field(default=None)

    def get_instance(self):
        return ColumnInstance(component=self)


@dataclass
class RectInstance(ComponentInstance["Rect"]):
    _rect: Rectangle = field(init=False)

    def __hash__(self) -> int:
        return id(self)

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
        x = use_acc_offset_x(self)
        y = use_acc_offset_y(self)
        width = computed(
            lambda: unref(self.component.width) * unref(use_acc_scale_x(self))
        )
        height = computed(
            lambda: unref(self.component.height) * unref(use_acc_scale_y(self))
        )
        self._rect = Rectangle(
            unref(x), unref(y), unref(width), unref(height), unref(self.component.color)
        )

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(width, self._update_width),
                    Watcher.ifref(height, self._update_height),
                    Watcher.ifref(self.component.color, self._update_color),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            self.component.width, self.component.height
        )


@dataclass
class Rect(Component):
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]]
    width: int | float | ReadRef[int | float]
    height: int | float | ReadRef[int | float]

    def get_instance(self):
        return RectInstance(component=self)


@dataclass
class ImageInstance(ComponentInstance["Image"]):
    _sprite: Sprite = field(init=False)

    def __hash__(self) -> int:
        return id(self)

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
        x = use_acc_offset_x(self)
        y = use_acc_offset_y(self)
        image = computed(lambda: loader.image(unref(self.component.name)))
        width = computed(
            lambda: unref(self.component.width)
            if unref(self.component.width) is not None
            else unref(image).width
        )
        height = computed(
            lambda: unref(self.component.height)
            if unref(self.component.height) is not None
            else unref(image).height
        )
        draw_width = computed(lambda: unref(width) * unref(use_acc_scale_x(self)))
        draw_height = computed(lambda: unref(height) * unref(use_acc_scale_y(self)))
        self._sprite = Sprite(
            unref(x), unref(y), unref(draw_width), unref(draw_height), unref(image)
        )

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(draw_width, self._update_width),
                    Watcher.ifref(draw_height, self._update_height),
                    Watcher.ifref(image, self._update_image),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width, height, []
        )

    @event_handler(ComponentUnmountedEvent)
    def component_unmounted_handler(self, event: ComponentUnmountedEvent):
        super().component_unmounted_handler(event)
        self._sprite.delete()
        del self._sprite


@dataclass
class Image(Component):
    name: str | ReadRef[str]
    width: int | float | None | ReadRef[int | float | None] = field(default=None)
    height: int | float | None | ReadRef[int | float | None] = field(default=None)

    def get_instance(self):
        return ImageInstance(component=self)


@dataclass
class LabelInstance(ComponentInstance["Label"]):
    _label: Ref[_Label] = field(init=False)

    def __hash__(self) -> int:
        return id(self)

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
        x = use_acc_offset_x(self)
        y = use_acc_offset_y(self)
        draw_width = computed(
            lambda: width * unref(use_acc_scale_x(self))
            if (width := unref(self.component.width)) is not None
            else None
        )
        draw_height = computed(
            lambda: height * unref(use_acc_scale_y(self))
            if (height := unref(self.component.height)) is not None
            else None
        )
        self._label = Ref(
            _Label(
                unref(self.component.text),
                font_name=unref(self.component.font_name),
                font_size=unref(self.component.font_size),
                bold=unref(self.component.bold),
                italic=unref(self.component.italic),
                color=unref(self.component.color),
                width=unref(draw_width),
                height=unref(draw_height),
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
                    Watcher.ifref(self.component.text, self._update_text),
                    Watcher.ifref(self.component.font_name, self._update_font_name),
                    Watcher.ifref(self.component.font_size, self._update_font_size),
                    Watcher.ifref(self.component.bold, self._update_bold),
                    Watcher.ifref(self.component.italic, self._update_italic),
                    Watcher.ifref(draw_width, self._update_width),
                    Watcher.ifref(draw_height, self._update_height),
                ]
                if w is not None
            ]
        )

        width = computed(
            lambda: unref(self.component.width)
            if unref(self.component.width) is not None
            else unref(self._label).content_width / unref(use_acc_scale_x(self))
        )
        height = computed(
            lambda: unref(self.component.height)
            if unref(self.component.height) is not None
            else unref(self._label).content_height / unref(use_acc_scale_y(self))
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width, height, []
        )


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

    def get_instance(self):
        return LabelInstance(component=self)


@dataclass
class InputInstance(ComponentInstance["Input"]):
    _next_word_re: ClassVar[re.Pattern[str]] = re.compile(r"(?<=\W)\w")
    _previous_word_re: ClassVar[re.Pattern[str]] = re.compile(r"(?<=\W)\w+\W*$")
    _batch: Batch = field(init=False)
    _document: UnformattedDocument = field(init=False)
    _layout: Ref[IncrementalTextLayout] = field(init=False)
    _caret: VertexList = field(init=False)
    _position: Ref[int] = field(init=False, default_factory=lambda: Ref(0))
    _mark: Ref[int | None] = field(init=False, default_factory=lambda: Ref(None))
    _position_clamped: ReadRef[int] = field(init=False)
    _mark_clamped: ReadRef[int | None] = field(init=False)
    _visible: Ref[bool] = field(init=False, default_factory=lambda: Ref(False))
    _caret_visible: Ref[bool] = field(init=False, default_factory=lambda: Ref(False))
    _click_time: float = field(init=False, default=0)
    _click_count: int = field(init=False, default=0)

    def __hash__(self) -> int:
        return id(self)

    def _blink(self, _dt):
        self._caret_visible.value = (
            not unref(self._caret_visible) if unref(self._visible) else False
        )

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
        x = use_acc_offset_x(self)
        y = use_acc_offset_y(self)
        draw_width = computed(
            lambda: width * unref(use_acc_scale_x(self))
            if (width := unref(self.component.width)) is not None
            else None
        )
        draw_height = computed(
            lambda: height * unref(use_acc_scale_y(self))
            if (height := unref(self.component.height)) is not None
            else None
        )

        self._batch = Batch()

        self._document = UnformattedDocument(unref(self.component.text))
        self._document.set_style(
            0,
            0,
            {
                "color": unref(self.component.color),
                "font_name": unref(self.component.font_name),
                "font_size": unref(self.component.font_size),
                "bold": unref(self.component.bold),
                "italic": unref(self.component.italic),
            },
        )

        self._layout = Ref(
            IncrementalTextLayout(
                self._document,
                width=unref(draw_width),
                height=unref(draw_height),
                multiline=True,
                batch=self._batch,
            )
        )
        self._layout.value.selection_background_color = unref(
            self.component.selection_background_color
        )
        self._layout.value.selection_color = unref(self.component.selection_color)
        self._layout.value.x = unref(x)
        self._layout.value.y = unref(y)

        def _caret_color():
            r, g, b, a = unref(self.component.caret_color)
            visible = unref(self._caret_visible)
            return (r, g, b, a if visible else 0, r, g, b, a if visible else 0)

        self._position_clamped = computed(
            lambda: min(len(unref(self.component.text)), unref(self._position))
        )
        self._mark_clamped = computed(
            lambda: None
            if unref(self._mark) is None
            else min(len(unref(self.component.text)), unref(self._mark))
        )

        def _caret_position():
            layout = unref(self._layout)
            position = unref(self._position_clamped)
            mark = unref(self._mark_clamped)
            line = layout.get_line_from_position(position)
            _x, _y = layout.get_point_from_position(position, line)
            _z = layout.z
            _x += unref(x)
            _y += unref(y) + layout.height

            if mark is not None:
                layout.set_selection(min(position, mark), max(position, mark))

            layout.ensure_line_visible(line)
            layout.ensure_x_visible(_x)

            font = self._document.get_font(max(0, position - 1))
            return (_x, _y + font.descent, _z, _x, _y + font.ascent, _z)

        caret_color = computed(_caret_color)
        caret_position = computed(_caret_position)
        caret_group = self._layout.value.foreground_decoration_group
        self._caret = caret_group.program.vertex_list(
            2, gl.GL_LINES, self._batch, caret_group, colors=("Bn", unref(caret_color))
        )
        self._caret.position[:] = unref(caret_position)

        def _update_caret_color(
            new_caret_color: tuple[int, int, int, int, int, int, int, int]
        ):
            self._caret.colors[:] = new_caret_color

        def _update_caret_position(
            new_caret_position: tuple[int, int, int, int, int, int]
        ):
            self._caret.position[:] = new_caret_position

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(self.component.text, self._update_text),
                    Watcher.ifref(self.component.color, self._update_color),
                    Watcher.ifref(
                        self.component.selection_background_color,
                        self._update_selection_background_color,
                    ),
                    Watcher.ifref(
                        self.component.selection_color, self._update_selection_color
                    ),
                    Watcher.ifref(self.component.font_name, self._update_font_name),
                    Watcher.ifref(self.component.font_size, self._update_font_size),
                    Watcher.ifref(self.component.bold, self._update_bold),
                    Watcher.ifref(self.component.italic, self._update_italic),
                    Watcher.ifref(draw_width, self._update_width),
                    Watcher.ifref(draw_height, self._update_height),
                    Watcher.ifref(caret_color, _update_caret_color),
                    Watcher.ifref(caret_position, _update_caret_position),
                ]
                if w is not None
            ]
        )

        width = computed(
            lambda: unref(self.component.width)
            if unref(self.component.width) is not None
            else unref(self._layout).content_width / unref(use_acc_scale_x(self))
        )
        height = computed(
            lambda: unref(self.component.height)
            if unref(self.component.height) is not None
            else unref(self._layout).content_height / unref(use_acc_scale_y(self))
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width, height, []
        )

    def delete_selection(self):
        position = unref(self._position_clamped)
        mark = unref(self._mark_clamped)
        start = min(mark, position)
        end = max(mark, position)
        self._position.value = start
        self._mark.value = None
        text = unref(self.component.text)
        return text[:start] + text[end:]

    def move_to_point(self, p: Positional):
        self.select_to_point(p)
        self._mark.value = None

    def select_to_point(self, p: Positional):
        self._position.value = unref(self._layout).get_position_from_point(
            unref(use_acc_offset_x(self)) + p.x, unref(use_acc_offset_y(self)) + p.y
        )

    def select_word(self, p: Positional):
        text = unref(self.component.text)
        point_position = unref(self._layout).get_position_from_point(
            unref(use_acc_offset_x(self)) + p.x, unref(use_acc_offset_y(self)) + p.y
        )
        self._position.value = (
            m1.start()
            if (m1 := InputInstance._next_word_re.search(text, 0, point_position))
            else len(text)
        )
        self._mark.value = (
            m2.start()
            if (
                m2 := InputInstance._previous_word_re.search(
                    text, endpos=point_position + 1
                )
            )
            else 0
        )

    def select_paragraph(self, p: Positional):
        point_position = unref(self._layout).get_position_from_point(
            unref(use_acc_offset_x(self)) + p.x, unref(use_acc_offset_y(self)) + p.y
        )
        self._position.value = self._document.get_paragraph_end(point_position)
        self._mark.value = self._document.get_paragraph_start(point_position)

    @event_handler(ComponentFocusEvent)
    def component_focus_handler(self, _: ComponentFocusEvent):
        self._visible.value = True
        self._caret_visible.value = True
        pyglet.clock.schedule_interval(self._blink, 0.5)

    @event_handler(ComponentBlurEvent)
    def component_blur_handler(self, _: ComponentBlurEvent):
        self._position.value = 0
        self._mark.value = None
        pyglet.clock.unschedule(self._blink)
        self._visible.value = False
        self._caret_visible.value = False

    @event_handler(TextEvent)
    def text_handler(self, event: TextEvent):
        position = unref(self._position_clamped)
        new_text = event.text.replace("\r", "\n")
        text = unref(self.component.text)
        self._position.value = position + len(new_text)
        self.capture(InputEvent("".join((text[:position], new_text, text[position:]))))

    def _text_motion_handler(self, event: TextMotionEvent | TextMotionSelectEvent):
        select = isinstance(event, TextMotionSelectEvent)
        position = unref(self._position_clamped)
        mark = unref(self._mark_clamped)
        text = unref(self.component.text)
        layout = unref(self._layout)

        if select and mark is None:
            self._mark.value = position

        match event.motion:
            case key.MOTION_BACKSPACE:
                if mark is not None:
                    self.capture(InputEvent(self.delete_selection()))
                    return
                elif position > 0:
                    self._position.value = position - 1
                    self.capture(InputEvent(text[: position - 1] + text[position:]))
                    return
            case key.MOTION_DELETE:
                if mark is not None:
                    self.capture(InputEvent(self.delete_selection()))
                    return
                elif position < len(text):
                    self.capture(InputEvent(text[:position] + text[position + 1 :]))
                    return

        if mark is not None and not select:
            self._mark.value = None

        match event.motion:
            case key.MOTION_LEFT:
                self._position.value = max(0, position - 1)
            case key.MOTION_RIGHT:
                self._position.value = min(len(text), position + 1)
            case key.MOTION_UP:
                line = layout.get_line_from_position(position)
                if line > 0:
                    line_position = layout.get_position_on_line(
                        line, unref(use_acc_offset_x(self))
                    )
                    line_diff = position - line_position
                    last_line_position = layout.get_position_on_line(
                        line - 1, unref(use_acc_offset_x(self))
                    )
                    self._position.value = min(
                        line_position - 1, last_line_position + line_diff
                    )
                else:
                    self._position.value = 0
            case key.MOTION_DOWN:
                line = layout.get_line_from_position(position)
                if line + 1 < layout.get_line_count():
                    line_position = layout.get_position_on_line(
                        line, unref(use_acc_offset_x(self))
                    )
                    line_diff = position - line_position
                    next_line_position = layout.get_position_on_line(
                        line + 1, unref(use_acc_offset_x(self))
                    )
                    end_next_line_position = (
                        layout.get_position_on_line(
                            line + 2, unref(use_acc_offset_x(self))
                        )
                        - 1
                        if line + 2 < layout.get_line_count()
                        else len(text)
                    )
                    self._position.value = min(
                        end_next_line_position, next_line_position + line_diff
                    )
                else:
                    self._position.value = len(text)
            case key.MOTION_BEGINNING_OF_LINE:
                self._position.value = layout.get_position_on_line(
                    layout.get_line_from_position(position),
                    unref(use_acc_offset_x(self)),
                )
            case key.MOTION_END_OF_LINE:
                line = layout.get_line_from_position(position)
                if line < layout.get_line_count() - 1:
                    self._position.value = (
                        layout.get_position_on_line(
                            line + 1, unref(use_acc_offset_x(self))
                        )
                        - 1
                    )
                else:
                    self._position.value = len(text)
            case key.MOTION_BEGINNING_OF_FILE:
                self._position.value = 0
            case key.MOTION_END_OF_FILE:
                self._position.value = len(text)
            case key.MOTION_NEXT_WORD:
                if m := InputInstance._next_word_re.search(text, position + 1):
                    self._position.value = m.start()
                else:
                    self._position.value = len(text)
            case key.MOTION_PREVIOUS_WORD:
                if m := InputInstance._previous_word_re.search(text, endpos=position):
                    self._position.value = m.start()
                else:
                    self._position.value = 0

    @event_handler(TextMotionEvent)
    def text_motion_handler(self, event: TextMotionEvent):
        self._text_motion_handler(event)

    @event_handler(TextMotionSelectEvent)
    def text_motion_select_handler(self, event: TextMotionSelectEvent):
        self._text_motion_handler(event)

    @event_handler(MousePressEvent)
    def mouse_press_handler(self, event: MousePressEvent):
        ComponentInstance.focus = self
        t = time.time()
        if t - self._click_time > 0.25:
            self._click_count = 0
        self._click_count += 1
        self._click_time = t

        match self._click_count % 3:
            case 1:
                self.move_to_point(event)
            case 2:
                self.select_word(event)
            case 0:
                self.select_paragraph(event)
        return StopPropagate

    @event_handler(MouseDragEvent)
    def mouse_drag_handler(self, event: MouseDragEvent):
        if unref(self._mark_clamped) is None:
            self._mark.value = unref(self._position_clamped)
        self.select_to_point(event)
        return StopPropagate


@dataclass
class Input(Component):
    text: ReadRef[str]
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

    def get_instance(self):
        return InputInstance(component=self)


@dataclass
class Window:
    _width: InitVar[int | ReadRef[int] | None] = field(default=None)
    _height: InitVar[int | ReadRef[int] | None] = field(default=None)
    _scene: Component | None = field(default=None)
    _scene_instance: ComponentInstance | None = field(default=None)
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
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.draw(dt)

        @self._window.event
        def on_key_press(symbol, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(KeyPressEvent(symbol, modifiers))

        @self._window.event
        def on_key_release(symbol, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(KeyReleaseEvent(symbol, modifiers))

        @self._window.event
        def on_mouse_drag(x, y, dx, dy, buttons, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(MouseDragEvent(x, y, dx, dy, buttons, modifiers))

        @self._window.event
        def on_mouse_enter(x, y):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(MouseEnterEvent(x, y))

        @self._window.event
        def on_mouse_leave(x, y):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(MouseLeaveEvent(x, y))

        @self._window.event
        def on_mouse_motion(x, y, dx, dy):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(MouseMotionEvent(x, y, dx, dy))

        @self._window.event
        def on_mouse_press(x, y, button, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(MousePressEvent(x, y, button, modifiers))

        @self._window.event
        def on_mouse_release(x, y, button, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(MouseReleaseEvent(x, y, button, modifiers))

        @self._window.event
        def on_mouse_scroll(x, y, scroll_x, scroll_y):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(MouseScrollEvent(x, y, scroll_x, scroll_y))

        @self._window.event
        def on_resize(width, height):
            self.width.value = width
            self.height.value = height

        @self._window.event
        def on_text(text):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(TextEvent(text))

        @self._window.event
        def on_text_motion(motion):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(TextMotionEvent(motion))

        @self._window.event
        def on_text_motion_select(motion):
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.capture(TextMotionSelectEvent(motion))

    @property
    def scene(self):
        return self._scene

    @property
    def scene_instance(self):
        return self._scene_instance

    @scene.setter
    def scene(self, new_scene: Component):
        new_scene_instance = new_scene.get_instance()
        if (scene_instance := self._scene_instance) is not None:
            self._scene = new_scene
            self._scene_instance = new_scene_instance
            scene_instance.capture(ComponentUnmountedEvent())
        else:
            self._scene = new_scene
            self._scene_instance = new_scene_instance
        new_scene_instance.before_mounted_data.value = (
            BeforeMountedComponentInstanceData(0, 0, 0, 0, 1, 1, 1, 1)
        )
        new_scene_instance.capture(ComponentMountedEvent())
