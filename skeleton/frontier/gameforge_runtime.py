"""Provider-neutral runtime contracts distilled from gameforge-rs gf-services.

Source revision: 8f0a107e5cac31fbfe39fee07daad415fd453aca.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Dict, Generic, TypeVar

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
        if class_cap < 1:
            raise ValueError("class_cap must be >= 1")
        self._cap = class_cap
        self._free: Dict[BufferClass, list[bytearray]] = {c: [] for c in BufferClass}
        self.leased = 0

    @staticmethod
    def classify(min_size: int) -> BufferClass:
        if min_size <= 4096:
            return BufferClass.SMALL
        if min_size <= 65536:
            return BufferClass.MEDIUM
        return BufferClass.LARGE

    def lease(self, min_size: int) -> BufferLease:
        if min_size < 0:
            raise ValueError("min_size must be non-negative")
        cls = self.classify(min_size)
        buf = self._free[cls].pop() if self._free[cls] else bytearray(cls.value)
        self.leased += 1
        return BufferLease(buf, cls)

    def reclaim(self, lease: BufferLease) -> None:
        if self.leased <= 0:
            return
        lease.data.clear()
        if len(self._free[lease.buffer_class]) < self._cap:
            self._free[lease.buffer_class].append(lease.data)
        self.leased -= 1

    def available(self, buffer_class: BufferClass) -> int:
        return len(self._free[buffer_class])


class RequestCoalescer(Generic[T]):
    """Share one in-flight fetch among concurrent callers for the same key."""

    def __init__(self, fetch: Callable[[str], Awaitable[T]]) -> None:
        self._fetch = fetch
        self._in_flight: Dict[str, asyncio.Future[T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T:
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
