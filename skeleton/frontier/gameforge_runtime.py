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

    def __init__(self, class_cap: int = 64, *, active_cap: int = 256, max_bytes: int = 64 << 20) -> None:
        if not isinstance(class_cap, int) or isinstance(class_cap, bool) or class_cap < 1:
            raise ValueError("class_cap must be >= 1")
        if not isinstance(active_cap, int) or isinstance(active_cap, bool) or not 1 <= active_cap <= 4096:
            raise ValueError("active_cap must be in [1, 4096]")
        if class_cap > 256:
            raise ValueError("class_cap must not exceed 256")
        if type(max_bytes) is not int or not 4096 <= max_bytes <= 1 << 30:
            raise ValueError("invalid aggregate buffer budget")
        self._max_bytes = max_bytes
        self._allocated_bytes = 0
        self._lock = RLock()
        self._active_cap = active_cap
        self._cap = class_cap
        self._free: dict[BufferClass, list[bytearray]] = {c: [] for c in BufferClass}
        self._leases: dict[int, BufferLease] = {}
        self._leased = 0

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
            if self._free[cls]:
                buf = self._free[cls].pop()
            else:
                # Reclaim idle classes before rejecting active demand.
                for other in reversed(tuple(BufferClass)):
                    while self._free[other] and self._allocated_bytes + cls.value > self._max_bytes:
                        self._free[other].pop()
                        self._allocated_bytes -= other.value
                if self._allocated_bytes + cls.value > self._max_bytes:
                    raise RuntimeError("aggregate buffer byte budget reached")
                buf = bytearray(cls.value)
                self._allocated_bytes += cls.value
            lease = BufferLease(buf, cls)
            self._leases[id(lease)] = lease
            self._leased += 1
            return lease

    def reclaim(self, lease: BufferLease) -> bool:
        if not isinstance(lease, BufferLease):
            raise TypeError("lease must be BufferLease")
        with self._lock:
            owned = self._leases.pop(id(lease), None)
            if owned is not lease:
                return False
            self._leased -= 1
            self._allocated_bytes -= lease.buffer_class.value
            # A caller may still hold an alias or memoryview of the old bytearray.
            # Never expose that storage to a subsequent owner.
            if len(self._free[lease.buffer_class]) < self._cap:
                self._free[lease.buffer_class].append(bytearray(lease.buffer_class.value))
                self._allocated_bytes += lease.buffer_class.value
            return True

    @property
    def leased(self) -> int:
        with self._lock:
            return self._leased

    @property
    def allocated_bytes(self) -> int:
        """Pool-owned nominal bytes, excluding escaped caller aliases."""
        with self._lock:
            return self._allocated_bytes

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


@dataclass
class _Flight(Generic[T]):
    task: asyncio.Task[T]
    waiters: int = 0


class RequestCoalescer(Generic[T]):
    """One bounded shared fetch, independent waiter cancellation, explicit shutdown.

    Only use for read-only or independently idempotent work. Cancellation cannot
    prove that a side effect did not occur. Results are generic caller-owned objects.
    """

    def __init__(self, fetch: Callable[[str], Awaitable[T]], *,
                 max_in_flight: int = 256, max_waiters: int = 128) -> None:
        if not callable(fetch):
            raise TypeError("fetch must be callable")
        if (type(max_in_flight) is not int or not 1 <= max_in_flight <= 4096
                or type(max_waiters) is not int or not 1 <= max_waiters <= 4096):
            raise ValueError("invalid coalescer limits")
        self._max_in_flight = max_in_flight
        self._max_waiters = max_waiters
        self._fetch = fetch
        self._in_flight: dict[str, _Flight[T]] = {}
        self._loop = None
        self._closed = False

    def _finish(self, key: str, entry: _Flight[T]) -> None:
        if self._in_flight.get(key) is entry:
            del self._in_flight[key]
        if not entry.task.cancelled():
            entry.task.exception()

    async def get(self, key: str) -> T:
        if type(key) is not str or not key or len(key) > 1024:
            raise ValueError("key is required")
        loop = asyncio.get_running_loop()
        if self._closed or (self._loop is not None and self._loop is not loop):
            raise RuntimeError("coalescer closed or bound to another loop")
        self._loop = loop
        entry = self._in_flight.get(key)
        if entry is None:
            if len(self._in_flight) >= self._max_in_flight:
                raise RuntimeError("coalescer capacity reached")
            async def fetch():
                return await self._fetch(key)
            entry = _Flight(asyncio.create_task(fetch()))
            self._in_flight[key] = entry
            entry.task.add_done_callback(lambda _: self._finish(key, entry))
        if entry.waiters >= self._max_waiters or entry.task.cancelling():
            raise RuntimeError("coalescer waiter capacity reached")
        entry.waiters += 1
        try:
            return await asyncio.shield(entry.task)
        finally:
            entry.waiters -= 1
            if entry.waiters == 0 and not entry.task.done():
                entry.task.cancel()

    async def aclose(self, *, timeout: float = 10.0) -> None:
        from math import isfinite
        if type(timeout) not in (int, float) or not isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError("invalid shutdown timeout")
        if self._loop is not None and self._loop is not asyncio.get_running_loop():
            raise RuntimeError("coalescer bound to another loop")
        self._closed = True
        tasks = tuple(entry.task for entry in self._in_flight.values())
        for task in tasks:
            task.cancel()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            if pending:
                raise TimeoutError("coalescer workers failed to drain")

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)
