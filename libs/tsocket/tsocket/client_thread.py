import asyncio
from collections.abc import Awaitable, AsyncIterator, Callable
from concurrent.futures import Future
import contextlib
from contextlib import AbstractContextManager, contextmanager
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

ClientThreadT_contra = TypeVar(
    "ClientThreadT_contra", bound="ClientThread", contravariant=True
)
T = TypeVar("T")
U = TypeVar("U")


@runtime_checkable  # yikes?
class _Route(Protocol[ClientThreadT_contra]):
    def get_fake_route(self, name: str) -> Callable[[ClientThreadT_contra, Any], Any]:
        ...


class WorkItem(Protocol):
    async def run(self, client: Client):
        ...


@dataclass
class DisconnectItem:
    async def run(self, client: Client):
        pass


async def queue_to_asynciterator(content_queue: queue.SimpleQueue[Future[T]]):
    while True:
        content = await asyncio.to_thread(content_queue.get)
        yield await asyncio.to_thread(content.result)


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
            future = Future[T]()
            future.set_result(content)
            content_queue.put(future)
    except ResponseError as err:
        future = Future[T]()
        future.set_exception(ResponseError(err.method, err.content))
        content_queue.put(future)
    except Exception as err:  # pylint: disable=W0718
        future = Future[T]()
        future.set_exception(err)
        content_queue.put(future)
    else:
        future = Future[T]()
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
class _SimpleRoute(Generic[ClientThreadT_contra, T, U]):
    func: Callable[[ClientThreadT_contra, T], Future[U]]

    def __call__(self, data: T) -> Future[U]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_route(
        self, name: str
    ) -> Callable[[ClientThreadT_contra, T], Future[U]]:
        func = self.func

        @wraps(func)
        def fake_route(self: ClientThreadT_contra, data: T) -> Future[U]:
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
class _StreamInRoute(Generic[ClientThreadT_contra, T, U]):
    func: Callable[[ClientThreadT_contra, queue.SimpleQueue[Future[T]]], Future[U]]

    def __call__(self, data: T) -> Future[U]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_route(
        self, name: str
    ) -> Callable[[ClientThreadT_contra, queue.SimpleQueue[Future[T]]], Future[U]]:
        func = self.func

        @wraps(func)
        def fake_route(
            self: ClientThreadT_contra, data: queue.SimpleQueue[Future[T]]
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
            out_queue = queue.SimpleQueue[Future[U]]()
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
class _StreamOutRoute(Generic[ClientThreadT_contra, T, U]):
    func: Callable[[ClientThreadT_contra, T], Future[queue.SimpleQueue[Future[U]]]]

    def __call__(self, data: T) -> Future[queue.SimpleQueue[Future[U]]]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_route(
        self, name: str
    ) -> Callable[[ClientThreadT_contra, T], Future[queue.SimpleQueue[Future[U]]]]:
        func = self.func

        @wraps(func)
        def fake_route(
            self: ClientThreadT_contra, data: T
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
            out_queue = queue.SimpleQueue[Future[U]]()
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
class _StreamInOutRoute(Generic[ClientThreadT_contra, T, U]):
    func: Callable[
        [ClientThreadT_contra, queue.SimpleQueue[Future[T]]],
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
        [ClientThreadT_contra, queue.SimpleQueue[Future[T]]],
        Future[queue.SimpleQueue[Future[U]]],
    ]:
        func = self.func

        @wraps(func)
        def fake_route(
            self: ClientThreadT_contra, data: queue.SimpleQueue[Future[T]]
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
    def simple(cls, func: Callable[[ClientThreadT_contra, T], Future[U]]):
        return _SimpleRoute(func)

    @classmethod
    def stream_in(
        cls,
        func: Callable[[ClientThreadT_contra, queue.SimpleQueue[Future[T]]], Future[U]],
    ):
        return _StreamInRoute(func)

    @classmethod
    def stream_out(
        cls,
        func: Callable[[ClientThreadT_contra, T], Future[queue.SimpleQueue[Future[U]]]],
    ):
        return _StreamOutRoute(func)

    @classmethod
    def stream_in_out(
        cls,
        func: Callable[
            [ClientThreadT_contra, queue.SimpleQueue[Future[T]]],
            Future[queue.SimpleQueue[Future[U]]],
        ],
    ):
        return _StreamInOutRoute(func)


@dataclass
class UnsubscribeWorkItem:
    name: str
    task: asyncio.Task[None]
    future: Future[None] = field(default_factory=Future)

    async def run(self, _client: Client):
        if self.future.set_running_or_notify_cancel():
            self.task.cancel()
            self.future.set_result(None)


@dataclass
class SubscribeWorkItem(Generic[ClientThreadT_contra, T]):
    name: str
    cls: type[T]
    client_thread: ClientThreadT_contra
    future: Future[AbstractContextManager[queue.SimpleQueue[Future[T]]]] = field(
        default_factory=Future
    )

    async def run(self, client: Client):
        if self.future.set_running_or_notify_cancel():
            out_queue = queue.SimpleQueue[Future[T]]()
            client_queue = asyncio.Queue[bytes]()
            queue_set = client.cbs.get(self.name, set())
            queue_set.add(client_queue)
            client.cbs[self.name] = queue_set

            async def async_subscriber():
                while True:
                    yield converter.loads(
                        await client_queue.get(),
                        self.cls,
                    )

            async def async_subscriber_to_queue():
                with contextlib.suppress(asyncio.CancelledError):
                    try:
                        await asynciterator_to_queue(async_subscriber(), out_queue)
                    finally:
                        client.cbs[self.name].remove(client_queue)
                        if not client.cbs[self.name]:
                            del client.cbs[self.name]

            subscribe_task = asyncio.create_task(async_subscriber_to_queue())

            @contextmanager
            def getter_manager():
                try:
                    yield out_queue
                finally:
                    work = UnsubscribeWorkItem(self.name, subscribe_task)
                    self.client_thread.work_queue.put(work)
                    work.future.result()

            self.future.set_result(getter_manager())


@dataclass
class _Subscribe(Generic[ClientThreadT_contra, T]):
    func: Callable[
        [ClientThreadT_contra],
        Future[AbstractContextManager[queue.SimpleQueue[Future[T]]]],
    ]

    def __call__(self) -> Future[AbstractContextManager[queue.SimpleQueue[Future[T]]]]:
        # For tricking LSP / type checker
        raise NotImplementedError()

    def get_fake_subscribe(
        self, name: str
    ) -> Callable[
        [ClientThreadT_contra],
        Future[AbstractContextManager[queue.SimpleQueue[Future[T]]]],
    ]:
        func = self.func

        @wraps(func)
        def fake_subscribe(
            self: ClientThreadT_contra,
        ) -> Future[AbstractContextManager[queue.SimpleQueue[Future[T]]]]:
            work = SubscribeWorkItem(
                name,
                get_args(
                    get_args(
                        get_args(
                            get_args(inspect.signature(func).return_annotation)[0]
                        )[0]
                    )[0]
                )[0],
                self,
            )
            self.work_queue.put(work)
            return work.future

        return fake_subscribe


def subscribe(
    func: Callable[
        [ClientThreadT_contra],
        Future[AbstractContextManager[queue.SimpleQueue[Future[T]]]],
    ],
):
    return _Subscribe(func)


class ClientThreadMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        routes = {
            name: route for name, route in attrs.items() if isinstance(route, _Route)
        }
        attrs["routes"] = routes
        attrs.update(
            {name: route.get_fake_route(name) for name, route in routes.items()}
        )
        subscribes = {
            name: subscribe
            for name, subscribe in attrs.items()
            if isinstance(subscribe, _Subscribe)
        }
        attrs["subscribes"] = subscribes
        attrs.update(
            {name: route.get_fake_subscribe(name) for name, route in subscribes.items()}
        )
        return super().__new__(mcs, name, bases, attrs)


@dataclass
class ClientThread(metaclass=ClientThreadMeta):
    work_queue: queue.SimpleQueue[WorkItem] = field(
        init=False, default_factory=queue.SimpleQueue
    )
    thread: Thread | None = field(init=False, default=None)

    async def _runner(
        self,
        host: str | None,
        port: int | str | None,
        ssl: ssl.SSLContext | bool | None = None,  # pylint: disable=W0621
    ):
        client = Client()
        await client.connect(host, port, ssl=ssl)
        running_tasks = set[asyncio.Task]()
        while True:
            running_tasks = {task for task in running_tasks if not task.done()}
            work = await asyncio.to_thread(self.work_queue.get)

            if isinstance(work, DisconnectItem):
                await asyncio.gather(*running_tasks, return_exceptions=True)
                await client.disconnect()
                break

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
