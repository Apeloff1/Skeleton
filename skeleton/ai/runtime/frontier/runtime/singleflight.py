"""Bounded idempotent execution with shared work and isolated waiters."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from skeleton.frontier.execution import RuntimeBusy, positive_int, positive_seconds
from skeleton.frontier.payloads import json_snapshot


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for different request content."""


@dataclass
class _Flight:
    fingerprint: str
    task: asyncio.Task
    waiters: int = 0


class SingleFlight:
    """Cache successful results only; cancellation of one waiter is isolated.

    Keys are scoped by the caller (for example tenant + endpoint + request key).
    Retention is an in-process retry window, not durable exactly-once delivery.
    """

    def __init__(
        self,
        *,
        capacity: int = 1024,
        ttl: float = 60,
        max_inflight: int = 72,
        max_waiters: int = 128,
        clock: Callable[[], float] = time.monotonic,
        shutdown_timeout: float = 10.0,
    ) -> None:
        self.capacity = positive_int("capacity", capacity)
        self.ttl = positive_seconds("ttl", ttl)
        self.max_inflight = positive_int("max_inflight", max_inflight)
        self.max_waiters = positive_int("max_waiters", max_waiters)
        self.shutdown_timeout = positive_seconds("shutdown_timeout", shutdown_timeout)
        if self.shutdown_timeout > 300:
            raise ValueError("shutdown timeout exceeds hard bound")
        if self.capacity > 65536 or self.max_inflight > 4096 or self.max_waiters > 4096 or self.ttl > 86400:
            raise ValueError("singleflight configuration exceeds hard bounds")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._last_time = None
        self._pending: dict[str, _Flight] = {}
        self._completed: OrderedDict[str, tuple[str, Any, float]] = OrderedDict()
        self._loop = None
        self._cache_bytes = 0
        self._closed = False
        self.reused = 0

    @property
    def tasks(self) -> frozenset[asyncio.Task]:
        return frozenset(entry.task for entry in self._pending.values())

    def _now(self) -> float:
        now = self._clock()
        if type(now) not in (float, int) or not math.isfinite(now):
            raise ValueError("clock must be finite")
        if self._last_time is not None and now < self._last_time:
            raise ValueError("clock must be monotonic")
        self._last_time = now
        return now

    def _expire(self) -> None:
        now = self._now()
        for key in [key for key, (_, _, expires) in self._completed.items() if expires <= now]:
            self._cache_bytes -= len(self._completed.pop(key)[1])

    def stats(self) -> dict[str, int]:
        self._expire()
        return {"inflight": len(self._pending), "cached": len(self._completed), "reused": self.reused}

    async def run(
        self,
        key: str,
        fingerprint: str,
        factory: Callable[[], Awaitable[Any]],
        *,
        cacheable: Callable[[Any], bool] = lambda _: True,
    ) -> Any:
        if not isinstance(key, str) or not key.strip() or len(key) > 256:
            raise ValueError("idempotency key must contain 1 to 256 characters")
        if type(fingerprint) is not str or not fingerprint.strip() or len(fingerprint) > 256:
            raise ValueError("invalid fingerprint")
        if not callable(factory) or not callable(cacheable):
            raise TypeError("factory and cacheable must be callable")
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError("singleflight already has work on another event loop")
        if self._closed:
            raise RuntimeError("singleflight is closed")
        self._loop = loop
        self._expire()
        completed = self._completed.get(key)
        if completed is not None:
            previous, result, _ = completed
            if previous != fingerprint:
                raise IdempotencyConflict("idempotency key belongs to a different request")
            self.reused += 1
            self._completed.move_to_end(key)
            return json.loads(result)
        entry = self._pending.get(key)
        if entry is not None:
            if entry.fingerprint != fingerprint:
                raise IdempotencyConflict("idempotency key belongs to a different request")
            if entry.task.cancelling() or entry.waiters >= self.max_waiters:
                raise RuntimeBusy("idempotent request cannot accept another waiter")
            self.reused += 1
        else:
            if len(self._pending) >= self.max_inflight:
                raise RuntimeBusy("idempotent execution capacity reached")
            async def work():
                result = json_snapshot(await factory(), max_bytes=262144)
                encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
                decision = cacheable(json.loads(encoded))
                if type(decision) is not bool:
                    raise ValueError("cacheability must be an explicit boolean")
                return encoded, decision

            entry = _Flight(fingerprint, asyncio.create_task(work()))
            self._pending[key] = entry
            entry.task.add_done_callback(lambda _: self._finish(key, entry))
        entry.waiters += 1
        try:
            encoded, _ = await asyncio.shield(entry.task)
            return json.loads(encoded)
        finally:
            entry.waiters -= 1
            if entry.waiters == 0 and not entry.task.done():
                entry.task.cancel()

    def _finish(self, key: str, entry: _Flight) -> None:
        if self._pending.get(key) is not entry:
            return
        del self._pending[key]
        try:
            encoded, cacheable = entry.task.result()
            if self._closed or not cacheable:
                return
            now = self._now()
            self._expire()
            self._completed[key] = (entry.fingerprint, encoded, now + self.ttl)
            self._cache_bytes += len(encoded)
            while len(self._completed) > self.capacity or self._cache_bytes > 8_388_608:
                _, row = self._completed.popitem(last=False)
                self._cache_bytes -= len(row[1])
        except (Exception, asyncio.CancelledError):
            return

    async def aclose(self) -> None:
        """Fence new admissions and wait for cooperative task cancellation."""
        if self._loop is not None and self._loop is not asyncio.get_running_loop():
            raise RuntimeError("singleflight is bound to another event loop")
        self._closed = True
        self._completed.clear()
        self._cache_bytes = 0
        tasks = self.tasks
        for task in tasks:
            task.cancel()
        if tasks:
            # Keep admission closed even when a worker suppresses cancellation.
            _, pending = await asyncio.wait(tasks, timeout=self.shutdown_timeout)
            if pending:
                raise TimeoutError("singleflight workers did not stop before shutdown deadline")
