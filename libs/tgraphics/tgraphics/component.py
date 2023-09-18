from collections.abc import Callable
from dataclasses import dataclass, field, InitVar

from pyglet.shapes import Rectangle
from pyglet.text import Label as _Label

from .reactivity import Computed, ReadRef, Watcher, isref, unref


@dataclass(kw_only=True)
class Component:
    width: float | ReadRef[float] = field(default=0)
    height: float | ReadRef[float] = field(default=0)
    disabled: bool | ReadRef[bool] = field(default=False)

    def draw(self, x: float, y: float):
        pass

    def hit_test(self, x: float, y: float):
        if (
            not unref(self.disabled)
            and 0 < x < unref(self.width)
            and 0 < y < unref(self.height)
        ):
            yield self


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

    def __post_init__(self, children):
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

    def hit_test(self, x: float, y: float):
        if (
            not unref(self.disabled)
            and 0 < x < unref(self.width)
            and 0 < y < unref(self.height)
        ):
            yield from unref(self._children).hit_test(
                x - unref(self.pad_left), y - unref(self.pad_bottom)
            )
            yield self


@dataclass
class Center(Component):
    children: InitVar[Callable[[], Component]]
    _width: InitVar[float | ReadRef[float] | None] = field(default=None)
    _height: InitVar[float | ReadRef[float] | None] = field(default=None)
    width: float | ReadRef[float] = field(init=False)
    height: float | ReadRef[float] = field(init=False)
    _children: ReadRef[Component] = field(init=False)

    def __post_init__(self, children, _width, _height):
        self._children = Computed(children)

        self.width = (
            _width
            if _width is not None
            else Computed(lambda: unref(self._children).width)
        )
        self.height = (
            _height
            if _height is not None
            else Computed(lambda: unref(self._children).height)
        )

    def draw(self, x: float, y: float):
        unref(self._children).draw(
            x + (unref(self.width) - unref(unref(self._children).width)) / 2,
            y + (unref(self.height) - unref(unref(self._children).height)) / 2,
        )

    def hit_test(self, x: float, y: float):
        if (
            not unref(self.disabled)
            and 0 < x < unref(self.width)
            and 0 < y < unref(self.height)
        ):
            yield from unref(self._children).hit_test(
                x - (unref(self.width) - unref(unref(self._children).width)) / 2,
                y - (unref(self.height) - unref(unref(self._children).height)) / 2,
            )
            yield self


@dataclass
class Layer(Component):
    children: InitVar[Callable[[], list[Component]]]
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _children: ReadRef[list[Component]] = field(init=False)

    def __post_init__(self, children):
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
                x + ((unref(self.width) - unref(c.height)) / 2),
                y + ((unref(self.height) - unref(c.height)) / 2),
            )

    def hit_test(self, x: float, y: float):
        if (
            not unref(self.disabled)
            and 0 < x < unref(self.width)
            and 0 < y < unref(self.height)
        ):
            for c in reversed(unref(self._children)):
                gen = c.hit_test(
                    x - ((unref(self.width) - unref(c.height)) / 2),
                    y - ((unref(self.height) - unref(c.height)) / 2),
                )

                if (yielded := next(gen, None)) is None:
                    continue

                yield yielded
                yield from gen
                break
            yield self


@dataclass
class Row(Component):
    children: InitVar[Callable[[], list[Component]]]
    gap: float | ReadRef[float] = field(default=0, kw_only=True)
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _children: ReadRef[list[Component]] = field(init=False)

    def __post_init__(self, children):
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
        c_x = 0
        for c in unref(self._children):
            c.draw(
                x + c_x,
                y + ((unref(self.height) - unref(c.height)) / 2),
            )
            c_x += unref(c.width) + unref(self.gap)

    def hit_test(self, x: float, y: float):
        if (
            not unref(self.disabled)
            and 0 < x < unref(self.width)
            and 0 < y < unref(self.height)
        ):
            c_x = 0
            for c in unref(self._children):
                if c_x >= x:
                    break
                if c_x < x < c_x + unref(c.width):
                    yield from c.hit_test(
                        x - c_x, y - ((unref(self.height) - unref(c.height)) / 2)
                    )
                    break
                c_x += unref(c.width) + unref(self.gap)
            yield self


@dataclass
class Column(Component):
    children: InitVar[Callable[[], list[Component]]]
    gap: float | ReadRef[float] = field(default=0, kw_only=True)
    width: ReadRef[float] = field(init=False)
    height: ReadRef[float] = field(init=False)
    _children: ReadRef[list[Component]] = field(init=False)

    def __post_init__(self, children):
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
        c_y = 0
        for c in unref(self._children):
            c.draw(
                x + ((unref(self.width) - unref(c.width)) / 2),
                y + c_y,
            )
            c_y += unref(c.height) + unref(self.gap)

    def hit_test(self, x: float, y: float):
        if (
            not unref(self.disabled)
            and 0 < x < unref(self.width)
            and 0 < y < unref(self.height)
        ):
            c_y = 0
            for c in unref(self._children):
                if c_y >= y:
                    break
                if c_y < y < c_y + unref(c.height):
                    yield from c.hit_test(
                        x - ((unref(self.width) - unref(c.width)) / 2), y - c_y
                    )
                    break
                c_y += unref(c.height) + unref(self.gap)
            yield self


@dataclass
class Rect(Component):
    color: tuple[int, int, int, int] | ReadRef[tuple[int, int, int, int]]

    def draw(self, x: float, y: float):
        Rectangle(x, y, unref(self.width), unref(self.height), unref(self.color)).draw()


@dataclass
class Label(Component):
    text: str | ReadRef[str]
    color: tuple[int, int, int, int]
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

    def __post_init__(self, _width, _height):
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
