import asyncio
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import partial, wraps
import inspect
import logging
from queue import Queue
import ssl
from threading import Thread
from typing import Any, Callable, Generic, TypeVar, get_args
from uuid import UUID

from cattrs.preconf.cbor2 import Cbor2Converter

from .client import Client
from .shared import ConnectedError, DisconnectedError, Message

log = logging.getLogger(__name__)

converter = Cbor2Converter()

converter.register_structure_hook(UUID, lambda d, t: UUID(bytes=d))
converter.register_unstructure_hook(UUID, lambda u: u.bytes)

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class Route(Generic[T, U]):
    func: Callable[["Client", T], Future[U]]

    def __call__(self, data: T) -> Future[U]:
        # For tricking LSP / type checker
        raise NotImplementedError()


def route(func: Callable[["Client", T], Future[U]]):
    return Route(func)


def get_fake_route(name: str, rte: Route[T, U]):
    @wraps(rte.func)
    def fake_route(self: "ClientThread", data: T) -> Future[U]:
        return self.request(
            name,
            converter.dumps(data),
            get_args(inspect.signature(rte.func).return_annotation)[0],
        )

    return fake_route


class ClientThreadMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        routes = {
            name: route for name, route in attrs.items() if isinstance(route, Route)
        }
        attrs["routes"] = routes
        attrs.update(
            {name: get_fake_route(name, route) for name, route in routes.items()}
        )
        return super().__new__(mcs, name, bases, attrs)


@dataclass
class DisconnectItem:
    pass


@dataclass
class WorkItem(Generic[T]):
    msg: Message
    wait: bool
    cls: type[T] | None = field(default=None)
    future: Future[T | None] = field(default_factory=Future)


@dataclass
class ClientThread(metaclass=ClientThreadMeta):
    work_queue: Queue[DisconnectItem | WorkItem] = field(default=Queue())
    thread: Thread | None = field(default=None)

    async def _runner(
        self,
        host: str | None,
        port: int | str | None,
        ssl: ssl.SSLContext | bool | None = None,  # pylint: disable=W0621
    ):
        client = Client()
        await client.connect(host, port, ssl=ssl)
        while True:
            work = self.work_queue.get()
            if isinstance(work, DisconnectItem):
                await client.disconnect()
                self.work_queue.task_done()
            else:
                if work.future.set_running_or_notify_cancel():
                    try:
                        data = await client.write(work.msg, wait=work.wait)
                        if work.cls:
                            work.future.set_result(converter.loads(data, work.cls))
                        else:
                            work.future.set_result(data)
                    except Exception as err:  # pylint: disable=W0718
                        work.future.set_exception(err)
                self.work_queue.task_done()

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
        self.thread = None
        self.work_queue.put(DisconnectItem())
        self.work_queue.join()

    def write(
        self,
        msg: Message,
        *,
        wait: bool = True,
    ):
        work = WorkItem(msg, wait=wait)
        self.work_queue.put(work)
        return work.future

    def request(self, msg_method: str, data: bytes, cls: type[T]) -> Future[T]:
        work = WorkItem(Message(msg_method, data), wait=True, cls=cls)
        self.work_queue.put(work)
        return work.future
