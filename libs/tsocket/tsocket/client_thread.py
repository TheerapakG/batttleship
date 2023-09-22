import asyncio
from collections.abc import Awaitable, AsyncIterator, Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import partial, wraps
import inspect
import logging
import queue
import ssl
from threading import Thread
from typing import Any, Generic, Protocol, TypeVar, get_args, runtime_checkable

from uuid import UUID

from cattrs.preconf.cbor2 import Cbor2Converter

from .client import Client, simple_writer, stream_writer, simple_reader, stream_reader
from .shared import ConnectedError, DisconnectedError, ResponseError

log = logging.getLogger(__name__)

converter = Cbor2Converter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)

T = TypeVar("T")
U = TypeVar("U")


@runtime_checkable  # yikes?
class _Route(Protocol):
    def get_fake_route(self, name: str) -> Callable[["Client", Any], Any]:
        ...


class WorkItem(Protocol):
    async def run(self, client: Client):
        ...


@dataclass
class DisconnectItem:
    async def run(self, client: Client):
        await client.disconnect()


async def queue_to_asynciterator(content_queue: queue.SimpleQueue[Future[T]]):
    while True:
        while True:
            try:
                content = content_queue.get_nowait()
                break
            except queue.Empty:
                await asyncio.sleep(0)
                continue

        while True:
            try:
                yield content.result(0)
            except TimeoutError:
                await asyncio.sleep(0)
                continue


async def awaitable_to_future(content_aw: Awaitable[T], future: Future[T]):
    try:
        content = await content_aw
    except ResponseError as err:
        future.set_exception(ResponseError(err.method, err.content))
    except Exception as err:  # pylint: disable=W0718
        future.set_exception(err)
    else:
        future.set_result(content)


async def asynciterator_to_queue(
    content_it: AsyncIterator[T], content_queue: queue.SimpleQueue[Future[T]]
):
    try:
        async for content in content_it:
            future = Future()
            future.set_result(content)
            content_queue.put(future)
    except ResponseError as err:
        future = Future()
        future.set_exception(ResponseError(err.method, err.content))
        content_queue.put(future)
    except Exception as err:  # pylint: disable=W0718
        future = Future()
        future.set_exception(err)
        content_queue.put(future)
    else:
        future = Future()
        future.set_exception(StopIteration())
        content_queue.put(future)


@dataclass
class SimpleWorkItem(Generic[T, U]):
    name: str
    content: T
    cls: type[U]
    future: Future[U] = field(default_factory=Future)

    async def run(self, client: Client):
        if self.future.set_running_or_notify_cancel():
            with client.session.create_channel() as channel:
                write_task = asyncio.create_task(
                    simple_writer(channel, self.name, self.content)
                )
                await awaitable_to_future(simple_reader(channel, self.cls), self.future)
                await write_task


@dataclass
class _SimpleRoute(Generic[T, U]):
    func: Callable[["ClientThread", T], Future[U]]

    def __call__(self, data: T) -> Future[U]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_route(self, name: str) -> Callable[["ClientThread", T], Future[U]]:
        func = self.func

        @wraps(func)
        def fake_route(self: "ClientThread", data: T) -> Future[U]:
            work = SimpleWorkItem(
                name, data, get_args(inspect.signature(func).return_annotation)[0]
            )
            self.work_queue.put(work)
            return work.future

        return fake_route


@dataclass
class StreamInWorkItem(Generic[T, U]):
    name: str
    content: queue.SimpleQueue[Future[T]]
    cls: type[U]
    future: Future[U] = field(default_factory=Future)

    async def run(self, client: Client):
        if self.future.set_running_or_notify_cancel():
            with client.session.create_channel() as channel:
                write_task = asyncio.create_task(
                    stream_writer(
                        channel, self.name, queue_to_asynciterator(self.content)
                    )
                )
                await awaitable_to_future(simple_reader(channel, self.cls), self.future)
                await write_task


@dataclass
class _StreamInRoute(Generic[T, U]):
    func: Callable[["ClientThread", queue.SimpleQueue[Future[T]]], Future[U]]

    def __call__(self, data: T) -> Future[U]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_route(
        self, name: str
    ) -> Callable[["ClientThread", queue.SimpleQueue[Future[T]]], Future[U]]:
        func = self.func

        @wraps(func)
        def fake_route(
            self: "ClientThread", data: queue.SimpleQueue[Future[T]]
        ) -> Future[U]:
            work = StreamInWorkItem(
                name, data, get_args(inspect.signature(func).return_annotation)[0]
            )
            self.work_queue.put(work)
            return work.future

        return fake_route


@dataclass
class StreamOutWorkItem(Generic[T, U]):
    name: str
    content: T
    cls: type[U]
    future: Future[queue.SimpleQueue[Future[U]]] = field(default_factory=Future)

    async def run(self, client: Client):
        if self.future.set_running_or_notify_cancel():
            out_queue = queue.SimpleQueue()
            self.future.set_result(out_queue)
            with client.session.create_channel() as channel:
                write_task = asyncio.create_task(
                    simple_writer(channel, self.name, self.content)
                )
                await asynciterator_to_queue(
                    stream_reader(channel, self.cls), out_queue
                )
                await write_task


@dataclass
class _StreamOutRoute(Generic[T, U]):
    func: Callable[["ClientThread", T], Future[queue.SimpleQueue[Future[U]]]]

    def __call__(self, data: T) -> Future[queue.SimpleQueue[Future[U]]]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_route(
        self, name: str
    ) -> Callable[["ClientThread", T], Future[queue.SimpleQueue[Future[U]]]]:
        func = self.func

        @wraps(func)
        def fake_route(
            self: "ClientThread", data: T
        ) -> Future[queue.SimpleQueue[Future[U]]]:
            work = StreamOutWorkItem(
                name,
                data,
                get_args(
                    get_args(get_args(inspect.signature(func).return_annotation)[0])[0]
                )[0],
            )
            self.work_queue.put(work)
            return work.future

        return fake_route


@dataclass
class StreamInOutWorkItem(Generic[T, U]):
    name: str
    content: queue.SimpleQueue[Future[T]]
    cls: type[U]
    future: Future[queue.SimpleQueue[Future[U]]] = field(default_factory=Future)

    async def run(self, client: Client):
        if self.future.set_running_or_notify_cancel():
            out_queue = queue.SimpleQueue()
            self.future.set_result(out_queue)
            with client.session.create_channel() as channel:
                write_task = asyncio.create_task(
                    stream_writer(
                        channel, self.name, queue_to_asynciterator(self.content)
                    )
                )
                await asynciterator_to_queue(
                    stream_reader(channel, self.cls), out_queue
                )
                await write_task


@dataclass
class _StreamInOutRoute(Generic[T, U]):
    func: Callable[
        ["ClientThread", queue.SimpleQueue[Future[T]]],
        Future[queue.SimpleQueue[Future[U]]],
    ]

    def __call__(
        self, data: queue.SimpleQueue[Future[T]]
    ) -> Future[queue.SimpleQueue[Future[U]]]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_route(
        self, name: str
    ) -> Callable[
        ["ClientThread", queue.SimpleQueue[Future[T]]],
        Future[queue.SimpleQueue[Future[U]]],
    ]:
        func = self.func

        @wraps(func)
        def fake_route(
            self: "ClientThread", data: queue.SimpleQueue[Future[T]]
        ) -> Future[queue.SimpleQueue[Future[U]]]:
            work = StreamInOutWorkItem(
                name,
                data,
                get_args(
                    get_args(get_args(inspect.signature(func).return_annotation)[0])[0]
                )[0],
            )
            self.work_queue.put(work)
            return work.future

        return fake_route


class Route:
    @classmethod
    def simple(
        cls, func: Callable[["ClientThread", T], Future[U]]
    ) -> _SimpleRoute[T, U]:
        return _SimpleRoute[T, U](func)

    @classmethod
    def stream_in(
        cls, func: Callable[["ClientThread", queue.SimpleQueue[Future[T]]], Future[U]]
    ) -> _StreamInRoute[T, U]:
        return _StreamInRoute[T, U](func)

    @classmethod
    def stream_out(
        cls, func: Callable[["ClientThread", T], Future[queue.SimpleQueue[Future[U]]]]
    ) -> _StreamOutRoute[T, U]:
        return _StreamOutRoute[T, U](func)

    @classmethod
    def stream_in_out(
        cls,
        func: Callable[
            ["ClientThread", queue.SimpleQueue[Future[T]]],
            Future[queue.SimpleQueue[Future[U]]],
        ],
    ) -> _StreamInOutRoute[T, U]:
        return _StreamInOutRoute[T, U](func)


class ClientThreadMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        routes = {
            name: route for name, route in attrs.items() if isinstance(route, _Route)
        }
        attrs["routes"] = routes
        attrs.update(
            {name: route.get_fake_route(name) for name, route in routes.items()}
        )
        return super().__new__(mcs, name, bases, attrs)


@dataclass
class ClientThread(metaclass=ClientThreadMeta):
    work_queue: queue.SimpleQueue[WorkItem] = field(default_factory=queue.SimpleQueue)
    thread: Thread | None = field(default=None)

    async def _runner(
        self,
        host: str | None,
        port: int | str | None,
        ssl: ssl.SSLContext | bool | None = None,  # pylint: disable=W0621
    ):
        client = Client()
        await client.connect(host, port, ssl=ssl)
        is_exit = False
        running_tasks = set[asyncio.Task]()
        while True:
            running_tasks = {task for task in running_tasks if not task.done()}
            try:
                work = self.work_queue.get_nowait()
            except queue.Empty:
                if is_exit:
                    await asyncio.gather(*running_tasks, return_exceptions=True)
                    break
                await asyncio.sleep(0)
                continue

            if isinstance(work, DisconnectItem):
                is_exit = True

            running_tasks.add(asyncio.create_task(work.run(client)))

    def connect(
        self,
        host: str | None,
        port: int | str | None,
        ssl: ssl.SSLContext | bool | None = None,  # pylint: disable=W0621
    ):
        if self.thread is not None:
            raise ConnectedError()
        self.thread = Thread(
            target=partial(asyncio.run, self._runner(host, port, ssl=ssl)), daemon=True
        )
        self.thread.start()

    def disconnect(self):
        if self.thread is None:
            raise DisconnectedError()
        thread = self.thread
        self.thread = None
        self.work_queue.put(DisconnectItem())
        thread.join()
