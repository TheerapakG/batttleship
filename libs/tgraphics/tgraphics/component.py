import asyncio
from collections.abc import Callable, Iterator
import contextlib
from dataclasses import dataclass, field, replace, InitVar
from functools import partial
import inspect
import re
import time
from typing import Any, Awaitable, ClassVar, Generic, ParamSpec, TypeVar
from xml.etree import ElementTree

import pyglet
from pyglet import gl
from pyglet.graphics import Batch, ShaderGroup
from pyglet.graphics.shader import Shader, ShaderProgram
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
    ModelEvent,
    InputEvent,
)
from .reactivity import ReadRef, Ref, Watcher, computed, unref, isref

loader = Loader(["./resources"])
loader.reindex()

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
    def make_capturer(func: Callable[["ComponentInstance", Event], Awaitable[Any]]):
        return _EventCapturer(cls, func)

    return make_capturer


def event_handler(cls: type[Event]):
    def make_handler(func: Callable[["ComponentInstance", Event], Awaitable[Any]]):
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
            k: computed(lambda v=v: eval(v, frame.frame.f_globals | init_locals, {}))
            for k, v in self.props.items()
        } | override_vars

        event_capturers = {
            Event.from_name(k): eval(v, frame.frame.f_globals | init_locals, {})
            for k, v in self.capturers.items()
        }

        if (capturers := init_vars.get("event_capturers", None)) is not None:
            for event, capturer in event_capturers.items():
                if (existed_capturer := capturers.get(event, None)) is not None:

                    async def merged_capturer(
                        event,
                        existed_capturer=existed_capturer,
                        capturer=capturer,
                    ):
                        if await existed_capturer(event) is StopPropagate:
                            return StopPropagate
                        return await capturer(event)

                    capturers[event] = merged_capturer
                else:
                    capturers[event] = capturer
        else:
            init_vars["event_capturers"] = event_capturers

        event_handlers = {
            Event.from_name(k): eval(v, frame.frame.f_globals | init_locals, {})
            for k, v in self.handlers.items()
        }

        if (handlers := init_vars.get("event_handlers", None)) is not None:
            for event, handler in event_handlers.items():
                if (existed_handler := handlers.get(event, None)) is not None:

                    async def merged_handler(
                        event,
                        existed_handler=existed_handler,
                        handler=handler,
                    ):
                        if await existed_handler(event) is StopPropagate:
                            return StopPropagate
                        return await handler(event)

                    handlers[event] = merged_handler
                else:
                    handlers[event] = handler
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
    _cls_event_capturers: dict[
        type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]
    ]
    _cls_event_handlers: dict[
        type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]
    ]
    _flat_event_capturers: dict[
        type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]
    ]
    _flat_event_handlers: dict[
        type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]
    ]
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

    async def set_focus(cls, instance: "ComponentInstance"):
        focus = unref(ComponentInstance._focus)
        if focus is instance:
            return StopPropagate

        if await instance.capture(ComponentFocusEvent(instance)) is StopPropagate:
            return StopPropagate

        if await cls.blur() is StopPropagate:  # pylint: disable=E1120
            return StopPropagate

        cls._focus.value = instance

    async def blur(cls):
        if (focus := unref(cls._focus)) is not None:
            focus: ComponentInstance  # type: ignore[no-redef]
            if await focus.capture(ComponentBlurEvent(focus)) is StopPropagate:
                return StopPropagate
            cls._focus.value = None


@dataclass(kw_only=True)
class ComponentInstance(Generic[C], metaclass=ComponentInstanceMeta):
    _cls_event_capturers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]]
    ]
    _cls_event_handlers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]]
    ]
    _flat_event_capturers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]]
    ]
    _flat_event_handlers: ClassVar[
        dict[type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]]
    ]
    _focus: ClassVar[Ref["ComponentInstance | None"]] = Ref(None)
    component: C
    event_capturers: dict[
        type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]
    ] = field(init=False)
    event_handlers: dict[
        type[Event], Callable[["ComponentInstance", Event], Awaitable[Any]]
    ] = field(init=False)
    before_mounted_data: Ref[BeforeMountedComponentInstanceData | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    after_mounted_data: Ref[AfterMountedComponentInstanceData | None] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    mount_duration: Ref[float] = field(init=False, default_factory=lambda: Ref(0))
    hover: Ref[bool] = field(init=False, default_factory=lambda: Ref(False))
    _hover: Ref["ComponentInstance | None"] = field(
        init=False, default_factory=lambda: Ref(None)
    )
    bound_tasks: set[asyncio.Task] = field(init=False, default_factory=set)
    bound_watchers: set[Watcher] = field(init=False, default_factory=set)

    def __post_init__(self):
        capturers = self._flat_event_capturers.copy()
        handlers = self._flat_event_handlers.copy()
        for event, capturer in self.component.event_capturers.items():
            if (existed_capturer := capturers.get(event, None)) is not None:

                async def merged_capturer(
                    instance,
                    event,
                    existed_capturer=existed_capturer,
                    capturer=capturer,
                ):
                    if await existed_capturer(instance, event) is StopPropagate:
                        return StopPropagate
                    return await capturer(event)

                capturers[event] = merged_capturer
            else:

                async def transform_capturer(_, event, capturer=capturer):
                    return await capturer(event)

                capturers[event] = transform_capturer
        for event, handler in self.component.event_handlers.items():
            if (existed_handler := handlers.get(event, None)) is not None:

                async def merged_handler(
                    instance, event, existed_handler=existed_handler, handler=handler
                ):
                    if await existed_handler(instance, event) is StopPropagate:
                        return StopPropagate
                    return await handler(event)

                handlers[event] = merged_handler
            else:

                async def transform_handler(_, event, handler=handler):
                    return await handler(event)

                handlers[event] = transform_handler
        self.event_capturers = capturers
        self.event_handlers = handlers

    def __hash__(self) -> int:
        return id(self)

    def _before_draw(self, _dt: float):
        self.mount_duration.value = self.mount_duration.value + _dt

    def _draw(self, _dt: float):
        pass

    def before_draw(self, dt: float):
        if unref(is_mounted(self)):
            self._before_draw(dt)
            for children in unref(use_children(self)):
                unref(children).before_draw(dt)

    def draw(self, dt: float):
        if unref(is_mounted(self)):
            self._draw(dt)
            for children in unref(use_children(self)):
                unref(children).draw(dt)

    async def capture(self, event: Event):
        if not unref(self.component.disabled):
            for event_type in type(event).mro():
                if (capturer := self.event_capturers.get(event_type)) is not None:
                    return await capturer(self, event)

    async def dispatch(self, event: Event):
        if not unref(self.component.disabled):
            for event_type in type(event).mro():
                if (handler := self.event_handlers.get(event_type)) is not None:
                    return await handler(self, event)

    def get_child_at(self, p: Positional) -> Iterator["ComponentInstance"]:
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
                yield unref_child

    @event_capturer(FocusEvent)
    async def focus_capturer(self, event: FocusEvent):
        if (focus := unref(ComponentInstance.focus)) is not None:
            focus: ComponentInstance  # type: ignore[no-redef]
            return await focus.dispatch(event)

    @event_capturer(BubblingEvent)
    async def bubbling_capturer(self, event: BubblingEvent):
        for child in self.get_child_at(event):
            if (
                await child.capture(
                    replace(
                        event,
                        instance=child,
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
            return await self.dispatch(event)

    @event_capturer(Event)
    async def generic_capturer(self, event: Event):
        return await self.dispatch(event)

    async def _set_hover(self, child: "ComponentInstance| None", p: Positional):
        if (hover := unref(self._hover)) is not None:
            await hover.capture(
                MouseLeaveEvent(
                    hover,
                    x=(p.x - unref(use_offset_x(hover))) / unref(use_scale_x(self)),
                    y=(p.y - unref(use_offset_y(hover))) / unref(use_scale_y(self)),
                )
            )
        self._hover.value = child

    @event_capturer(MouseEnterEvent)
    async def mouse_enter_capturer(self, event: MouseEnterEvent):
        self.hover.value = True
        for child in self.get_child_at(event):
            if (
                await child.capture(
                    replace(
                        event,
                        instance=child,
                        x=(event.x - unref(use_offset_x(child)))
                        / unref(use_scale_x(self)),
                        y=(event.y - unref(use_offset_y(child)))
                        / unref(use_scale_y(self)),
                    )
                )
                is StopPropagate
            ):
                await self._set_hover(child, event)
                return StopPropagate
        return await self.dispatch(event)

    @event_handler(MouseEnterEvent)
    async def mouse_enter_handler(self, event: MouseEnterEvent):
        return StopPropagate

    @event_capturer(MouseMotionEvent)
    async def mouse_motion_capturer(self, event: MouseMotionEvent):
        for child in self.get_child_at(event):
            if child is unref(self._hover):
                if (
                    await child.capture(
                        replace(
                            event,
                            instance=child,
                            x=(event.x - unref(use_offset_x(child)))
                            / unref(use_scale_x(self)),
                            y=(event.y - unref(use_offset_y(child)))
                            / unref(use_scale_y(self)),
                        )
                    )
                    is StopPropagate
                ):
                    return StopPropagate
            elif (
                await child.capture(
                    MouseEnterEvent(
                        child,
                        (event.x - unref(use_offset_x(child)))
                        / unref(use_scale_x(self)),
                        (event.y - unref(use_offset_y(child)))
                        / unref(use_scale_y(self)),
                    )
                )
                is StopPropagate
            ):
                await self._set_hover(child, event)
                return StopPropagate
        await self._set_hover(None, event)
        return await self.dispatch(event)

    @event_handler(MouseMotionEvent)
    async def mouse_motion_handler(self, event: MouseMotionEvent):
        return StopPropagate

    @event_capturer(MouseLeaveEvent)
    async def mouse_leave_capturer(self, event: MouseLeaveEvent):
        self.hover.value = False
        await self._set_hover(None, event)
        return await self.dispatch(event)

    @event_handler(MousePressEvent)
    async def mouse_press_handler(self, _event: MousePressEvent):
        if unref(ComponentInstance.focus) is not self:
            await ComponentInstance.blur()

    @event_handler(ComponentUnmountedEvent)
    async def component_unmounted_handler(self, _: ComponentUnmountedEvent):
        for task in self.bound_tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.bound_tasks.clear()
        for watcher in self.bound_watchers:
            watcher.unwatch()
        for child in unref(use_children(self)):
            await unref(child).capture(ComponentUnmountedEvent(unref(child)))
        self.bound_watchers.clear()
        self.before_mounted_data.value = None
        self.after_mounted_data.value = None
        self.mount_duration.value = 0

    @event_handler(ModelEvent)
    async def component_model_handler(self, event: ModelEvent):
        if event.field in self.component.models:
            model_ref = getattr(self.component, event.field)
            model_ref.value = event.value


def use_offset_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get x offset of component instance relative to the parent"
    return computed(
        lambda: unref(data.offset_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_offset_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get y offset of component instance relative to the parent"
    return computed(
        lambda: unref(data.offset_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_acc_offset_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get x offset of component instance relative to the window"
    return computed(
        lambda: unref(data.acc_offset_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_acc_offset_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get y offset of component instance relative to the window"
    return computed(
        lambda: unref(data.acc_offset_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 0
    )


def use_scale_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get x scaling of component instance relative to the parent"
    return computed(
        lambda: unref(data.scale_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_scale_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get y scaling of component instance relative to the parent"
    return computed(
        lambda: unref(data.scale_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_acc_scale_x(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get x scaling of component instance relative to the window"
    return computed(
        lambda: unref(data.acc_scale_x)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_acc_scale_y(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get y scaling of component instance relative to the window"
    return computed(
        lambda: unref(data.acc_scale_y)
        if (data := unref(unref(instance).before_mounted_data)) is not None
        else 1
    )


def use_width(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get width of component instance unscaled"
    return computed(
        lambda: unref(data.width)
        if (data := unref(unref(instance).after_mounted_data)) is not None
        else 0
    )


def use_height(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> float | ReadRef[float]:
    "get height of component instance unscaled"
    return computed(
        lambda: unref(data.height)
        if (data := unref(unref(instance).after_mounted_data)) is not None
        else 0
    )


def use_hover(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> bool | ReadRef[bool]:
    "get hover status of component instance"
    return computed(lambda: unref(unref(instance).hover))


def use_children(
    instance: ComponentInstance | ReadRef[ComponentInstance],
) -> (
    list[ComponentInstance | ReadRef[ComponentInstance]]
    | ReadRef[list[ComponentInstance | ReadRef[ComponentInstance]]]
):
    "get children instances of component instance"
    return computed(
        lambda: unref(data.children)
        if (data := unref(unref(instance).after_mounted_data)) is not None
        else []
    )


def is_mounted(instance: ComponentInstance):
    "get mounted status of the component instance"
    return computed(
        lambda: unref(instance.before_mounted_data) is not None
        and unref(instance.after_mounted_data) is not None
    )


@dataclass
class ElementRenderError(Exception):
    exc: Exception
    element: ElementTree.Element


class RenderError(Exception):
    pass


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
        "register component for rendering with XML"

        def wrapper(func: Callable[..., "Component"]):
            mcs._components[name] = func
            return func

        return wrapper

    @classmethod
    def from_name(mcs, name: str):
        "get registered component with the name"
        return mcs._components[name]

    @classmethod
    def render_element(
        mcs,
        element: ElementTree.Element,
        frame: inspect.FrameInfo,
        scope_values: dict | None = None,
    ) -> "list[Component] | ReadRef[list[Component]]":
        "render child components from XML string"

        try:
            if scope_values is None:
                scope_values = {}

            frame_locals = _get_merged_locals(frame, **scope_values)

            data = ElementComponentData(element)

            def render_fn(
                additional_scope_values, override_values
            ) -> list["Component"]:
                return [
                    data.cls(
                        **data.get_init_vars(
                            frame,
                            (scope_values | additional_scope_values),
                            override_values,
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
                                s.strip() for s in directive_value.split(" in ")
                            ]
                            eval_for_values = computed(
                                lambda: eval(
                                    for_values, frame.frame.f_globals, frame_locals
                                )
                            )

                            def render_fn(
                                for_var,
                                eval_for_values,
                                additional_scope_values,
                                override_values,
                            ):
                                if isref(eval_for_values):
                                    _ref_list = override_values.get("_ref_list", [])
                                    _ref_list.append(eval_for_values)
                                    override_values["_ref_list"] = _ref_list

                                def assign_var(for_var, v):
                                    for_vars = [
                                        f_v.strip() for f_v in for_var.split(",")
                                    ]
                                    return (
                                        {f_v: val for f_v, val in zip(for_vars, v)}
                                        if len(for_vars) > 1
                                        else {for_vars[0]: v}
                                    )

                                return [
                                    component
                                    for components in [
                                        unref(
                                            old_render_fn(
                                                additional_scope_values
                                                | assign_var(for_var, v),
                                                override_values,
                                            )
                                        )
                                        for v in unref(eval_for_values)
                                    ]
                                    for component in components
                                ]

                            return partial(render_fn, for_var, eval_for_values)

                        render_fn = for_render_fn_wrapper(render_fn, directive_value)
                    case "if":

                        def if_render_fn_wrapper(
                            old_render_fn: Callable[..., list["Component"]],
                            directive_value: str,
                        ):
                            eval_val = computed(
                                lambda: eval(
                                    directive_value, frame.frame.f_globals, frame_locals
                                )
                            )

                            def render_fn(
                                eval_val, additional_scope_values, override_values
                            ):
                                if isref(eval_val):
                                    _ref_list = override_values.get("_ref_list", [])
                                    _ref_list.append(eval_val)
                                    override_values["_ref_list"] = _ref_list

                                return (
                                    old_render_fn(
                                        additional_scope_values, override_values
                                    )
                                    if unref(eval_val)
                                    else []
                                )

                            return partial(render_fn, eval_val)

                        render_fn = if_render_fn_wrapper(render_fn, directive_value)
                    case "style":

                        def style_render_fn_wrapper(
                            old_render_fn: Callable[..., list["Component"]],
                            directive_value: str,
                        ):
                            eval_val = computed(
                                lambda: eval(
                                    directive_value, frame.frame.f_globals, frame_locals
                                )
                            )

                            def render_fn(
                                eval_val, additional_scope_values, override_values
                            ):
                                if isref(eval_val):
                                    _ref_list = override_values.get("_ref_list", [])
                                    _ref_list.append(eval_val)
                                    override_values["_ref_list"] = _ref_list

                                return old_render_fn(
                                    additional_scope_values,
                                    override_values | unref(eval_val),
                                )

                            return partial(render_fn, eval_val)

                        render_fn = style_render_fn_wrapper(render_fn, directive_value)

                    case _ if directive_key.startswith("model-"):

                        def model_render_fn_wrapper(
                            old_render_fn: Callable[..., list["Component"]],
                            directive_key: str,
                            directive_value: str,
                        ):
                            def render_fn(additional_scope_values, override_values):
                                model = directive_key.removeprefix("model-")

                                models = override_values.get("models", [])
                                models.append(model)
                                override_values["models"] = models

                                model_ref = eval(
                                    directive_value, frame.frame.f_globals, frame_locals
                                )
                                override_values[model] = model_ref

                                _ref_list = override_values.get("_ref_list", [])
                                _ref_list.append(model_ref)
                                override_values["_ref_list"] = _ref_list

                                return old_render_fn(
                                    additional_scope_values, override_values
                                )

                            return render_fn

                        render_fn = model_render_fn_wrapper(
                            render_fn, directive_key, directive_value
                        )

            return computed(lambda: render_fn({}, {}))
        except ElementRenderError:
            raise
        except Exception as exc:
            raise ElementRenderError(exc, element) from exc

    @classmethod
    def render_root_element(
        mcs, element: ElementTree.Element, frame: inspect.FrameInfo, **kwargs
    ) -> "Component":
        "render root component from XML string"
        try:
            data = ElementComponentData(element)

            for directive_key, directive_value in data.directives.items():
                match directive_key:
                    case _ if directive_key.startswith("model-"):
                        model = directive_key.removeprefix("model-")
                        models = kwargs.get("models", [])
                        models.append(model)
                        kwargs["models"] = models

                        model_ref = eval(
                            directive_value, frame.frame.f_globals, frame.frame.f_locals
                        )
                        kwargs[model] = model_ref
        except ElementRenderError:
            raise
        except Exception as exc:
            raise ElementRenderError(exc, element) from exc

        return data.cls(**data.get_init_vars(frame, {}, kwargs))

    @classmethod
    def render_xml(mcs, xml: str, **kwargs) -> "Component":
        "render component from XML string"
        try:
            return mcs.render_root_element(
                ElementTree.fromstring(xml), inspect.stack()[1], **kwargs
            )
        except ElementTree.ParseError as exc:
            raise RenderError(str(exc)) from exc
        except ElementRenderError as exc:
            raise RenderError(f"{exc.exc} in element {exc.element.tag}") from exc


@dataclass(kw_only=True)
class Component(metaclass=ComponentMeta):
    disabled: bool | ReadRef[bool] = field(default=False)
    event_capturers: dict[type[Event], Callable[[Event], Awaitable[Any]]] = field(
        default_factory=dict, repr=False
    )
    event_handlers: dict[type[Event], Callable[[Event], Awaitable[Any]]] = field(
        default_factory=dict, repr=False
    )
    models: list[str] = field(default_factory=list, repr=False)
    children: list["Component" | ReadRef["Component"]] | ReadRef[
        list["Component" | ReadRef["Component"]]
    ] = field(default_factory=list["Component" | ReadRef["Component"]])
    _ref_list: list[ReadRef] = field(default_factory=list)

    def get_instance(self):
        return ComponentInstance(component=self)


@dataclass
class PadInstance(ComponentInstance["Pad"]):
    def __hash__(self) -> int:
        return id(self)

    @event_handler(ComponentMountedEvent)
    async def component_mounted_handler(self, _: ComponentMountedEvent):
        child = computed(
            lambda: unref(unref(self.component.children)[0]).get_instance()
            if unref(self.component.children)
            else None
        )
        previous_child: ComponentInstance | None = None

        async def mount_child(child: ComponentInstance):
            nonlocal previous_child
            if previous_child is not None:
                previous_child.capture(ComponentUnmountedEvent(previous_child))
            previous_child = child
            if child is not None:
                off_x = computed(
                    lambda: unref(self.component.pad_left)
                    * unref(use_acc_scale_x(self))
                )
                off_y = computed(
                    lambda: unref(self.component.pad_bottom)
                    * unref(use_acc_scale_y(self))
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
                await child.capture(ComponentMountedEvent(child))

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        child,
                        lambda c: asyncio.create_task(mount_child(c)),
                        trigger_init=True,
                    ),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            computed(
                lambda: (
                    unref(use_width(unref(child))) if unref(child) is not None else 0
                )
                + unref(self.component.pad_left)
                + unref(self.component.pad_right)
            ),
            computed(
                lambda: (
                    unref(use_height(unref(child))) if unref(child) is not None else 0
                )
                + unref(self.component.pad_bottom)
                + unref(self.component.pad_top)
            ),
            computed(lambda: [unref(child)] if unref(child) is not None else []),
        )

    @event_handler(MouseEnterEvent)
    async def mouse_enter_handler(self, _e: MouseEnterEvent):
        return None

    @event_handler(MouseMotionEvent)
    async def mouse_motion_handler(self, _e: MouseMotionEvent):
        return None


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
    async def component_mounted_handler(self, _: ComponentMountedEvent):
        children = computed(
            lambda: [
                computed(lambda c=c: unref(c).get_instance())
                for c in unref(self.component.children)
            ]
        )
        collapsed_children = computed(lambda: [unref(c) for c in unref(children)])
        previous_collapsed_children: list[ComponentInstance] = []

        async def mount_child(index: int):
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
            await child.capture(ComponentMountedEvent(child))

        async def mount_children(current_collapsed_children: list[ComponentInstance]):
            nonlocal previous_collapsed_children
            child_lookup = {
                child: i for i, child in enumerate(unref(current_collapsed_children))
            }
            current = set(current_collapsed_children)
            previous = set(previous_collapsed_children)
            for child in previous - current:
                await child.capture(ComponentUnmountedEvent(child))
            for child in current - previous:
                await mount_child(child_lookup[child])

            previous_collapsed_children = current_collapsed_children

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        children,
                        lambda cs: asyncio.create_task(mount_children(cs)),
                        trigger_init=True,
                    ),
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

    @event_handler(MouseEnterEvent)
    async def mouse_enter_handler(self, _e: MouseEnterEvent):
        return None

    @event_handler(MouseMotionEvent)
    async def mouse_motion_handler(self, _e: MouseMotionEvent):
        return None


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
    async def component_mounted_handler(self, _: ComponentMountedEvent):
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

        async def mount_child(index: int):
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
            await child.capture(ComponentMountedEvent(child))

        async def mount_children(current_collapsed_children: list[ComponentInstance]):
            nonlocal previous_collapsed_children
            child_lookup = {
                child: i for i, child in enumerate(unref(current_collapsed_children))
            }
            current = set(current_collapsed_children)
            previous = set(previous_collapsed_children)
            for child in previous - current:
                await child.capture(ComponentUnmountedEvent(child))
            for child in current - previous:
                await mount_child(child_lookup[child])

            previous_collapsed_children = current_collapsed_children

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        collapsed_children,
                        lambda cs: asyncio.create_task(mount_children(cs)),
                        trigger_init=True,
                    ),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width, height, children
        )

    @event_handler(MouseEnterEvent)
    async def mouse_enter_handler(self, _e: MouseEnterEvent):
        return None

    @event_handler(MouseMotionEvent)
    async def mouse_motion_handler(self, _e: MouseMotionEvent):
        return None


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
    async def component_mounted_handler(self, _: ComponentMountedEvent):
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
            lambda: sum(unref(c_h) for c_h in unref(children_height))
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

        async def mount_child(index: int):
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
            await child.capture(ComponentMountedEvent(child))

        async def mount_children(current_collapsed_children: list[ComponentInstance]):
            nonlocal previous_collapsed_children
            child_lookup = {
                child: i for i, child in enumerate(unref(current_collapsed_children))
            }
            current = set(current_collapsed_children)
            previous = set(previous_collapsed_children)
            for child in previous - current:
                await child.capture(ComponentUnmountedEvent(child))
            for child in current - previous:
                await mount_child(child_lookup[child])

            previous_collapsed_children = current_collapsed_children

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        collapsed_children,
                        lambda cs: asyncio.create_task(mount_children(cs)),
                        trigger_init=True,
                    ),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width, height, children
        )

    @event_handler(MouseEnterEvent)
    async def mouse_enter_handler(self, _e: MouseEnterEvent):
        return None

    @event_handler(MouseMotionEvent)
    async def mouse_motion_handler(self, _e: MouseMotionEvent):
        return None


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
class SlotInstance(ComponentInstance["Slot"]):
    _instance: Ref[ComponentInstance | None] = field(init=False)

    def __hash__(self) -> int:
        return id(self)

    def _draw(self, dt: float):
        if (instance := self._instance.value) is not None:
            instance.draw(dt)

    @event_handler(ComponentMountedEvent)
    async def component_mounted_handler(self, _: ComponentMountedEvent):
        self._instance = Ref(None)

        width = computed(
            lambda: unref(use_width(instance)) * unref(use_acc_scale_x(self))
            if (instance := unref(self._instance)) is not None
            else 0
        )
        height = computed(
            lambda: unref(use_height(instance)) * unref(use_acc_scale_y(self))
            if (instance := unref(self._instance)) is not None
            else 0
        )

        async def mount_slot():
            if (instance := unref(self._instance)) is not None:
                await instance.capture(ComponentUnmountedEvent(instance))
            instance = self.component.component.get_instance()
            self._instance.value = instance

            instance.before_mounted_data.value = BeforeMountedComponentInstanceData(
                0,
                0,
                use_acc_offset_x(self),
                use_acc_offset_y(self),
                1,
                1,
                use_acc_scale_x(self),
                use_acc_scale_y(self),
            )
            await instance.capture(ComponentMountedEvent(instance))

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(
                        self.component.component,
                        lambda cs: asyncio.create_task(mount_slot()),
                        trigger_init=True,
                    ),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            width,
            height,
            computed(
                lambda: [instance]
                if (instance := unref(self._instance)) is not None
                else []
            ),
        )


@dataclass
class Slot(Component):
    component: Component | ReadRef[Component]

    def get_instance(self):
        return SlotInstance(component=self)


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
    async def component_mounted_handler(self, _: ComponentMountedEvent):
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


class _BlendShaderGroup(ShaderGroup):
    def set_state(self):
        super().set_state()
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    def unset_state(self):
        gl.glDisable(gl.GL_BLEND)
        super().unset_state()


@dataclass
class RoundedRectInstance(ComponentInstance["RoundedRect"]):
    vert: ClassVar[Shader] = Shader(
        """
        #version 330 core
        in vec2 translation;
        in vec2 size;
        in float radius;
        in vec2 tex_coord;
        in vec2 tex_off;
        in float round;
        in vec4 color;

        out vec2 vertex_size;
        out float vertex_radius;
        out vec2 vertex_tex_coord;
        out float vertex_round;
        out vec2 vertex_radius_direction;
        out vec4 vertex_color;

        uniform WindowBlock
        {
            mat4 projection;
            mat4 view;
        } window;

        void main()
        {
            vec2 pos = size * tex_coord + radius * tex_off;
            gl_Position = window.projection * window.view * vec4(translation + pos, 0.0, 1.0);
            vertex_size = size;
            vertex_radius = radius;
            vertex_tex_coord = pos / size;
            vertex_round = round;
            vertex_radius_direction = tex_coord;
            vertex_color = color;
        }
        """,
        "vertex",
    )
    frag: ClassVar[Shader] = Shader(
        """
        #version 330 core
        in vec2 vertex_size;
        in float vertex_radius;
        in vec2 vertex_tex_coord;
        in float vertex_round;
        in vec2 vertex_radius_direction;
        in vec4 vertex_color;

        out vec4 fragColor;

        void main() 
        {
            vec2 off = (vertex_tex_coord * 2 - vec2(1.0)) * vertex_radius_direction - vertex_tex_coord;
            vec2 pos = vec2(vertex_radius) + off * vertex_size;

            fragColor = length(pos) > vertex_radius && vertex_round > 0.0 ? vec4(0.0): vertex_color;
        }
        """,
        "fragment",
    )
    program: ClassVar[ShaderProgram] = ShaderProgram(vert, frag)
    _batch: Batch = field(init=False)
    _group: _BlendShaderGroup = field(init=False)
    _vertex_list: VertexList = field(init=False)

    def __hash__(self) -> int:
        return id(self)

    def _draw(self, _dt: float):
        self._batch.draw()

    def _update_x(self, x: float):
        self._vertex_list.translation[::2] = (x,) * 16

    def _update_y(self, y: float):
        self._vertex_list.translation[1::2] = (y,) * 16

    def _update_width(self, width: float):
        self._vertex_list.size[::2] = (width,) * 16

    def _update_height(self, height: float):
        self._vertex_list.size[1::2] = (height,) * 16

    def _update_radius_bottom_left(self, radius: float):
        self._vertex_list.radius[0:4] = (radius,) * 4

    def _update_radius_bottom_right(self, radius: float):
        self._vertex_list.radius[4:8] = (radius,) * 4

    def _update_radius_top_left(self, radius: float):
        self._vertex_list.radius[12:16] = (radius,) * 4

    def _update_radius_top_right(self, radius: float):
        self._vertex_list.radius[8:12] = (radius,) * 4

    def _update_color(self, color: tuple[int, int, int, int]):
        self._vertex_list.color[:] = color * 16

    @event_handler(ComponentMountedEvent)
    async def component_mounted_handler(self, _: ComponentMountedEvent):
        x = use_acc_offset_x(self)
        y = use_acc_offset_y(self)
        width = computed(
            lambda: unref(self.component.width) * unref(use_acc_scale_x(self))
        )
        height = computed(
            lambda: unref(self.component.height) * unref(use_acc_scale_y(self))
        )
        radius_bottom_left = computed(
            lambda: r
            if (r := unref(self.component.radius_bottom_left)) is not None
            else min(unref(width), unref(height)) / 2
        )
        radius_bottom_right = computed(
            lambda: r
            if (r := unref(self.component.radius_bottom_right)) is not None
            else min(unref(width), unref(height)) / 2
        )
        radius_top_left = computed(
            lambda: r
            if (r := unref(self.component.radius_top_left)) is not None
            else min(unref(width), unref(height)) / 2
        )
        radius_top_right = computed(
            lambda: r
            if (r := unref(self.component.radius_top_right)) is not None
            else min(unref(width), unref(height)) / 2
        )
        self._batch = Batch()
        self._group = _BlendShaderGroup(self.program)
        self._vertex_list = self.program.vertex_list_indexed(
            16,
            gl.GL_TRIANGLES,
            [
                *[*[0, 1, 2, 0, 2, 3], *[1, 4, 7, 1, 7, 2], *[4, 5, 6, 4, 6, 7]],
                *[*[3, 2, 13, 3, 13, 12], *[2, 7, 8, 2, 8, 13], *[7, 6, 9, 7, 9, 8]],
                *[
                    *[12, 13, 14, 12, 14, 15],
                    *[13, 8, 11, 13, 11, 14],
                    *[8, 9, 10, 8, 10, 11],
                ],
            ],
            self._batch,
            self._group,
            translation=("f", (unref(x), unref(y)) * 16),
            size=("f", (unref(width), unref(height)) * 16),
            radius=(
                "f",
                (unref(radius_bottom_left),) * 4
                + (unref(radius_bottom_right),) * 4
                + (unref(radius_top_right),) * 4
                + (unref(radius_top_left),) * 4,
            ),
            tex_coord=(
                "f",
                (
                    *(0, 0, 0, 0, 0, 0, 0, 0),
                    *(1, 0, 1, 0, 1, 0, 1, 0),
                    *(1, 1, 1, 1, 1, 1, 1, 1),
                    *(0, 1, 0, 1, 0, 1, 0, 1),
                ),
            ),
            tex_off=(
                "f",
                (
                    *(0, 0, 1, 0, 1, 1, 0, 1),
                    *(-1, 0, 0, 0, 0, 1, -1, 1),
                    *(-1, -1, 0, -1, 0, 0, -1, 0),
                    *(0, -1, 1, -1, 1, 0, 0, 0),
                ),
            ),
            round=(
                "f",
                (
                    *(1, 0, 0, 0),
                    *(0, 1, 0, 0),
                    *(0, 0, 1, 0),
                    *(0, 0, 0, 1),
                ),
            ),
            color=("Bn", unref(self.component.color) * 16),
        )

        self.bound_watchers.update(
            [
                w
                for w in [
                    Watcher.ifref(x, self._update_x),
                    Watcher.ifref(y, self._update_y),
                    Watcher.ifref(width, self._update_width),
                    Watcher.ifref(height, self._update_height),
                    Watcher.ifref(radius_bottom_left, self._update_radius_bottom_left),
                    Watcher.ifref(
                        radius_bottom_right, self._update_radius_bottom_right
                    ),
                    Watcher.ifref(radius_top_left, self._update_radius_top_left),
                    Watcher.ifref(radius_top_right, self._update_radius_top_right),
                    Watcher.ifref(self.component.color, self._update_color),
                ]
                if w is not None
            ]
        )

        self.after_mounted_data.value = AfterMountedComponentInstanceData(
            self.component.width, self.component.height
        )


@dataclass
class RoundedRect(Component):
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]]
    width: int | float | ReadRef[int | float]
    height: int | float | ReadRef[int | float]
    radius_bottom_left: int | float | None | ReadRef[int | float | None] = field(
        default=None
    )
    radius_bottom_right: int | float | None | ReadRef[int | float | None] = field(
        default=None
    )
    radius_top_left: int | float | None | ReadRef[int | float | None] = field(
        default=None
    )
    radius_top_right: int | float | None | ReadRef[int | float | None] = field(
        default=None
    )

    def get_instance(self):
        return RoundedRectInstance(component=self)


@dataclass
class ImageInstance(ComponentInstance["Image"]):
    _sprite: Sprite = field(init=False)

    def __hash__(self) -> int:
        return id(self)

    def _draw(self, _dt: float):
        gl.glEnable(gl.GL_BLEND)
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
    async def component_mounted_handler(self, _: ComponentMountedEvent):
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
            unref(image),
            unref(x),
            unref(y),
        )
        self._sprite.width = unref(draw_width)
        self._sprite.height = unref(draw_height)

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
    async def component_unmounted_handler(self, event: ComponentUnmountedEvent):
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
    async def component_mounted_handler(self, _: ComponentMountedEvent):
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
                    Watcher.ifref(self.component.color, self._update_color),
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
    async def component_mounted_handler(self, _: ComponentMountedEvent):
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
            if (mark := unref(self._mark)) is None
            else min(len(unref(self.component.text)), mark)
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
    async def component_focus_handler(self, _: ComponentFocusEvent):
        self._visible.value = True
        self._caret_visible.value = True
        pyglet.clock.schedule_interval(self._blink, 0.5)

    @event_handler(ComponentBlurEvent)
    async def component_blur_handler(self, _: ComponentBlurEvent):
        self._position.value = 0
        self._mark.value = None
        pyglet.clock.unschedule(self._blink)
        self._visible.value = False
        self._caret_visible.value = False

    @event_handler(TextEvent)
    async def text_handler(self, event: TextEvent):
        position = unref(self._position_clamped)
        new_text = event.text.replace("\r", "\n")
        text = unref(self.component.text)
        self._position.value = position + len(new_text)
        await self.capture(
            InputEvent(self, "".join((text[:position], new_text, text[position:])))
        )

    async def _text_motion_handler(
        self, event: TextMotionEvent | TextMotionSelectEvent
    ):
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
                    await self.capture(InputEvent(self, self.delete_selection()))
                    return
                elif position > 0:
                    self._position.value = position - 1
                    await self.capture(
                        InputEvent(self, text[: position - 1] + text[position:])
                    )
                    return
            case key.MOTION_DELETE:
                if mark is not None:
                    await self.capture(InputEvent(self, self.delete_selection()))
                    return
                elif position < len(text):
                    await self.capture(
                        InputEvent(self, text[:position] + text[position + 1 :])
                    )
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
    async def text_motion_handler(self, event: TextMotionEvent):
        await self._text_motion_handler(event)

    @event_handler(TextMotionSelectEvent)
    async def text_motion_select_handler(self, event: TextMotionSelectEvent):
        await self._text_motion_handler(event)

    @event_handler(MousePressEvent)
    async def mouse_press_handler(self, event: MousePressEvent):
        await ComponentInstance.set_focus(self)
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
    async def mouse_drag_handler(self, event: MouseDragEvent):
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


loop = asyncio.get_event_loop()
pyglet.clock.schedule(lambda dt: loop.run_until_complete(asyncio.sleep(0)))

_current_keys = Ref(dict())


def use_key_pressed(key):
    return computed(lambda: unref(_current_keys).get(key, False))


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
    _last_draw_time: float | None = field(init=False, default=None)

    def __post_init__(self, _width, _height, resizable):
        self._window = _Window(
            unref(_width),
            unref(_height),
            resizable=resizable,
            config=gl.Config(sample_buffers=1, samples=4, double_buffer=True),
        )

        self.width = Ref(self._window.width)
        self.height = Ref(self._window.height)

        @self._window.event
        def on_draw():
            _t = time.time()
            self._window.clear()
            if (scene_instance := self.scene_instance) is not None:
                scene_instance.before_draw(
                    (_t - _lt) if (_lt := self._last_draw_time) is not None else 0
                )
                scene_instance.draw(
                    (_t - _lt) if (_lt := self._last_draw_time) is not None else 0
                )
            self._last_draw_time = _t

        @self._window.event
        def on_key_press(symbol, modifiers):
            _current_keys.value[symbol] = True
            _current_keys.trigger()
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        KeyPressEvent(scene_instance, symbol, modifiers)
                    )
                )

        @self._window.event
        def on_close():
            loop.create_task(self.set_scene(None))

        @self._window.event
        def on_key_release(symbol, modifiers):
            _current_keys.value[symbol] = False
            _current_keys.trigger()
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        KeyReleaseEvent(scene_instance, symbol, modifiers)
                    )
                )

        @self._window.event
        def on_mouse_drag(x, y, dx, dy, buttons, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        MouseDragEvent(scene_instance, x, y, dx, dy, buttons, modifiers)
                    )
                )

        @self._window.event
        def on_mouse_enter(x, y):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(MouseEnterEvent(scene_instance, x, y))
                )

        @self._window.event
        def on_mouse_leave(x, y):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(MouseLeaveEvent(scene_instance, x, y))
                )

        @self._window.event
        def on_mouse_motion(x, y, dx, dy):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        MouseMotionEvent(scene_instance, x, y, dx, dy)
                    )
                )

        @self._window.event
        def on_mouse_press(x, y, button, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        MousePressEvent(scene_instance, x, y, button, modifiers)
                    )
                )

        @self._window.event
        def on_mouse_release(x, y, button, modifiers):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        MouseReleaseEvent(scene_instance, x, y, button, modifiers)
                    )
                )

        @self._window.event
        def on_mouse_scroll(x, y, scroll_x, scroll_y):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        MouseScrollEvent(scene_instance, x, y, scroll_x, scroll_y)
                    )
                )

        @self._window.event
        def on_resize(width, height):
            self.width.value = width
            self.height.value = height

        @self._window.event
        def on_text(text):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(TextEvent(scene_instance, text))
                )

        @self._window.event
        def on_text_motion(motion):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(TextMotionEvent(scene_instance, motion))
                )

        @self._window.event
        def on_text_motion_select(motion):
            if (scene_instance := self.scene_instance) is not None:
                loop.create_task(
                    scene_instance.capture(
                        TextMotionSelectEvent(scene_instance, motion)
                    )
                )

    @property
    def scene(self):
        return self._scene

    async def set_scene(self, new_scene: Component | None):
        new_scene_instance = new_scene.get_instance() if new_scene is not None else None
        if (scene_instance := self._scene_instance) is not None:
            self._scene = new_scene
            self._scene_instance = new_scene_instance
            await scene_instance.capture(ComponentUnmountedEvent(scene_instance))
        else:
            self._scene = new_scene
            self._scene_instance = new_scene_instance
        if new_scene_instance is not None:
            new_scene_instance.before_mounted_data.value = (
                BeforeMountedComponentInstanceData(0, 0, 0, 0, 1, 1, 1, 1)
            )
            await new_scene_instance.capture(ComponentMountedEvent(new_scene_instance))

    @property
    def scene_instance(self):
        return self._scene_instance
