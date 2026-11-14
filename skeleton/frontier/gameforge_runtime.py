"""Provider-neutral runtime contracts distilled from gameforge-rs gf-services.

Source revision: 8f0a107e5cac31fbfe39fee07daad415fd453aca.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


class BufferClass(Enum):
    SMALL = 4096
    MEDIUM = 65536
    LARGE = 1 << 20


@dataclass(frozen=True)
class BufferLease:
    data: bytearray
    buffer_class: BufferClass


class BufferPool:
    """Hard-capped reusable buffer classes; no unbounded retention."""

    def __init__(self, class_cap: int = 64, *, active_cap: int = 256) -> None:
        if not isinstance(class_cap, int) or isinstance(class_cap, bool) or class_cap < 1:
            raise ValueError("class_cap must be >= 1")
        if not isinstance(active_cap, int) or isinstance(active_cap, bool) or not 1 <= active_cap <= 4096:
            raise ValueError("active_cap must be in [1, 4096]")
        if class_cap > 256:
            raise ValueError("class_cap must not exceed 256")
        self._lock = RLock()
        self._active_cap = active_cap
        self._cap = class_cap
        self._free: dict[BufferClass, list[bytearray]] = {c: [] for c in BufferClass}
        self._leases: dict[int, BufferLease] = {}
        self.leased = 0

    @staticmethod
    def classify(min_size: int) -> BufferClass:
        if not isinstance(min_size, int) or isinstance(min_size, bool) or min_size < 0:
            raise ValueError("min_size must be a non-negative integer")
        if min_size <= 4096:
            return BufferClass.SMALL
        if min_size <= 65536:
            return BufferClass.MEDIUM
        if min_size <= BufferClass.LARGE.value:
            return BufferClass.LARGE
        raise ValueError("requested size exceeds largest buffer class")

    def lease(self, min_size: int) -> BufferLease:
        cls = self.classify(min_size)
        with self._lock:
            if len(self._leases) >= self._active_cap:
                raise RuntimeError("active buffer lease capacity reached")
            buf = self._free[cls].pop() if self._free[cls] else bytearray(cls.value)
            lease = BufferLease(buf, cls)
            self._leases[id(lease)] = lease
            self.leased += 1
            return lease

    def reclaim(self, lease: BufferLease) -> bool:
        if not isinstance(lease, BufferLease):
            raise TypeError("lease must be BufferLease")
        with self._lock:
            owned = self._leases.pop(id(lease), None)
            if owned is not lease:
                return False
            self.leased -= 1
            # A caller may still hold an alias or memoryview of the old bytearray.
            # Never expose that storage to a subsequent owner.
            if len(self._free[lease.buffer_class]) < self._cap:
                self._free[lease.buffer_class].append(bytearray(lease.buffer_class.value))
            return True

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def available_total(self) -> int:
        with self._lock:
            return sum(len(items) for items in self._free.values())

    def available(self, buffer_class: BufferClass) -> int:
        if not isinstance(buffer_class, BufferClass):
            raise TypeError("buffer_class must be BufferClass")
        with self._lock:
            return len(self._free[buffer_class])


class RequestCoalescer(Generic[T]):
    """Share one in-flight fetch among concurrent callers for the same key."""

    def __init__(self, fetch: Callable[[str], Awaitable[T]], *, max_in_flight: int = 256) -> None:
        if not callable(fetch):
            raise TypeError("fetch must be callable")
        if not isinstance(max_in_flight, int) or isinstance(max_in_flight, bool) or not 1 <= max_in_flight <= 4096:
            raise ValueError("max_in_flight must be in [1, 4096]")
        self._max_in_flight = max_in_flight
        self._fetch = fetch
        self._in_flight: dict[str, asyncio.Future[T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T:
        if not isinstance(key, str) or not key or len(key) > 1024:
            raise ValueError("key is required")
        leader = False
        async with self._lock:
            future = self._in_flight.get(key)
            if future is None:
                if len(self._in_flight) >= self._max_in_flight:
                    raise RuntimeError("coalescer capacity reached")
                future = asyncio.get_running_loop().create_future()
                self._in_flight[key] = future
                leader = True

        if not leader:
            return await asyncio.shield(future)

        try:
            value = await self._fetch(key)
        except asyncio.CancelledError:
            if not future.done():
                future.cancel()
            raise
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
                future.exception()  # mark observed even when there are no followers
            raise
        else:
            if not future.done():
                future.set_result(value)
            return value
        finally:
            async with self._lock:
                self._in_flight.pop(key, None)

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)
