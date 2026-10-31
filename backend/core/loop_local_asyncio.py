"""Lazy asyncio primitives scoped to their running event loop.

A module-level asyncio.Lock/Semaphore may attach to a loop that is later closed
(for example during lifespan restarts or multiple test event loops). Each active
loop must have its own live admission primitive.

Weak keys AND weak values are intentional: asyncio waiters can retain their
event loop, so a strong value in a WeakKeyDictionary can accidentally keep a
closed loop alive. Call sites must retain the returned primitive for the entire
acquire/release lifecycle, including cancellation cleanup callbacks.
"""

from __future__ import annotations

import asyncio
from threading import Lock
from typing import Callable, Generic, TypeVar
from weakref import ReferenceType, WeakKeyDictionary, ref


_T = TypeVar("_T")


class LoopLocalAsyncPrimitive(Generic[_T]):
    """Construct a lock/semaphore on first use within each running event loop."""

    def __init__(self, factory: Callable[[], _T]) -> None:
        self._factory = factory
        self._guard = Lock()
        self._primitives: WeakKeyDictionary[
            asyncio.AbstractEventLoop, ReferenceType[_T]
        ] = WeakKeyDictionary()

    def get(self) -> _T:
        loop = asyncio.get_running_loop()  # Fail rather than bind to a guessed loop.
        with self._guard:
            handle = self._primitives.get(loop)
            primitive = handle() if handle is not None else None
            if primitive is None:
                primitive = self._factory()
                self._primitives[loop] = ref(primitive)
            return primitive
