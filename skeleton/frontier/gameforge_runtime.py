"""Provider-neutral runtime contracts distilled from gameforge-rs gf-services.

Source revision: 8f0a107e5cac31fbfe39fee07daad415fd453aca.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class BufferClass(Enum):
    SMALL = 4096
    MEDIUM = 65536
    LARGE = 1 << 20


@dataclass
class BufferLease:
    data: bytearray
    buffer_class: BufferClass


class BufferPool:
    """Hard-capped reusable buffer classes; no unbounded retention."""

    def __init__(self, class_cap: int = 64) -> None:
        if not isinstance(class_cap, int) or isinstance(class_cap, bool) or class_cap < 1:
            raise ValueError("class_cap must be >= 1")
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
        return BufferClass.LARGE

    def lease(self, min_size: int) -> BufferLease:
        cls = self.classify(min_size)
        buf = self._free[cls].pop() if self._free[cls] else bytearray(cls.value)
        lease = BufferLease(buf, cls)
        self._leases[id(lease)] = lease
        self.leased += 1
        return lease

    def reclaim(self, lease: BufferLease) -> bool:
        if not isinstance(lease, BufferLease):
            raise TypeError("lease must be BufferLease")
        owned = self._leases.pop(id(lease), None)
        if owned is not lease:
            return False
        if not isinstance(lease.buffer_class, BufferClass):
            self.leased -= 1
            raise TypeError("lease has invalid buffer class")
        lease.data.clear()
        if len(self._free[lease.buffer_class]) < self._cap:
            self._free[lease.buffer_class].append(lease.data)
        self.leased -= 1
        return True

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def available_total(self) -> int:
        return sum(len(items) for items in self._free.values())

    def available(self, buffer_class: BufferClass) -> int:
        if not isinstance(buffer_class, BufferClass):
            raise TypeError("buffer_class must be BufferClass")
        return len(self._free[buffer_class])


class RequestCoalescer(Generic[T]):
    """Share one in-flight fetch among concurrent callers for the same key."""

    def __init__(self, fetch: Callable[[str], Awaitable[T]]) -> None:
        self._fetch = fetch
        self._in_flight: dict[str, asyncio.Future[T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T:
        if not isinstance(key, str) or not key:
            raise ValueError("key is required")
        leader = False
        async with self._lock:
            future = self._in_flight.get(key)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._in_flight[key] = future
                leader = True

        if not leader:
            return await asyncio.shield(future)

        try:
            value = await self._fetch(key)
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
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
