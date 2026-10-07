"""Bounded idempotent execution with shared work and isolated waiters."""

from __future__ import annotations

import asyncio
import copy
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from skeleton.frontier.execution import RuntimeBusy, positive_int, positive_seconds


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
    ) -> None:
        self.capacity = positive_int("capacity", capacity)
        self.ttl = positive_seconds("ttl", ttl)
        self.max_inflight = positive_int("max_inflight", max_inflight)
        self.max_waiters = positive_int("max_waiters", max_waiters)
        self._clock = clock
        self._pending: dict[str, _Flight] = {}
        self._completed: OrderedDict[str, tuple[str, Any, float]] = OrderedDict()
        self._loop = None
        self.reused = 0

    @property
    def tasks(self) -> frozenset[asyncio.Task]:
        return frozenset(entry.task for entry in self._pending.values())

    def _expire(self) -> None:
        now = self._clock()
        for key in [key for key, (_, _, expires) in self._completed.items() if expires <= now]:
            del self._completed[key]

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
        loop = asyncio.get_running_loop()
        if self._pending and self._loop is not loop:
            raise RuntimeError("singleflight already has work on another event loop")
        self._loop = loop
        self._expire()
        completed = self._completed.get(key)
        if completed is not None:
            previous, result, _ = completed
            if previous != fingerprint:
                raise IdempotencyConflict("idempotency key belongs to a different request")
            self.reused += 1
            self._completed.move_to_end(key)
            return copy.deepcopy(result)
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
            entry = _Flight(fingerprint, asyncio.create_task(factory()))
            self._pending[key] = entry
        entry.waiters += 1
        try:
            return copy.deepcopy(await asyncio.shield(entry.task))
        finally:
            entry.waiters -= 1
            if entry.waiters == 0:
                try:
                    if not entry.task.done():
                        entry.task.cancel()
                        await asyncio.gather(entry.task, return_exceptions=True)
                    if not entry.task.cancelled() and entry.task.exception() is None:
                        result = entry.task.result()
                        if cacheable(result):
                            self._completed[key] = (
                                fingerprint,
                                copy.deepcopy(result),
                                self._clock() + self.ttl,
                            )
                            while len(self._completed) > self.capacity:
                                self._completed.popitem(last=False)
                finally:
                    self._pending.pop(key, None)
