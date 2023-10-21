from collections.abc import Awaitable
import inspect
from typing import TypeVar

T = TypeVar("T")


async def maybe_await(maybe_awaitable: T | Awaitable[T]) -> T:
    if inspect.isawaitable(maybe_awaitable):
        return await maybe_awaitable
    else:
        return maybe_awaitable  # type: ignore
