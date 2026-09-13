"""Bounded health-checked pooling contract mined from GameForge gf-services.

Source: Apeloff1/gameforge-rs, crates/gf-services/src/lib.rs,
revision 8f0a107e5cac31fbfe39fee07daad415fd453aca.

The contract deliberately avoids concrete database/client dependencies. Callers
provide construction and health predicates; the pool owns only bounded idle
retention and max-age policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Callable, Generic, List, TypeVar
import time

T = TypeVar("T")


@dataclass(frozen=True)
class PoolStats:
    checkouts: int
    rejected: int
    idle: int


class HealthPool(Generic[T]):
    """Small, fail-closed pool with bounded idle retention and max-age eviction."""

    def __init__(
        self,
        make: Callable[[], T],
        healthy: Callable[[T], bool],
        *,
        capacity: int = 16,
        max_age_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not callable(make) or not callable(healthy) or not callable(clock):
            raise TypeError("make, healthy, and clock must be callable")
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        if (
            not isinstance(max_age_seconds, (int, float))
            or isinstance(max_age_seconds, bool)
            or max_age_seconds <= 0
        ):
            raise ValueError("max_age_seconds must be a positive number")
        self._make = make
        self._healthy = healthy
        self._capacity = capacity
        self._max_age = float(max_age_seconds)
        self._clock = clock
        self._idle: List[tuple[T, float]] = []
        self._checked_out: set[int] = set()
        self._checkouts = 0
        self._rejected = 0
        self._lock = Lock()

    def checkout(self) -> T:
        now = self._clock()
        with self._lock:
            while self._idle:
                value, born = self._idle.pop()
                if now - born > self._max_age:
                    continue
                try:
                    healthy = self._healthy(value)
                except Exception:
                    healthy = False
                if healthy:
                    self._checked_out.add(id(value))
                    self._checkouts += 1
                    return value
            value = self._make()
            try:
                if not self._healthy(value):
                    self._rejected += 1
                    raise RuntimeError("newly created pooled resource is unhealthy")
            except Exception:
                self._rejected += 1
                raise
            self._checked_out.add(id(value))
            self._checkouts += 1
            return value

    def release(self, value: T) -> bool:
        """Return a checked-out healthy resource if capacity permits."""
        value_id = id(value)
        with self._lock:
            if value_id not in self._checked_out:
                self._rejected += 1
                return False
            if len(self._idle) >= self._capacity:
                self._checked_out.discard(value_id)
                return False
            try:
                if not self._healthy(value):
                    self._rejected += 1
                    self._checked_out.discard(value_id)
                    return False
            except Exception:
                self._rejected += 1
                self._checked_out.discard(value_id)
                return False
            self._checked_out.discard(value_id)
            self._idle.append((value, self._clock()))
            return True

    def stats(self) -> PoolStats:
        with self._lock:
            return PoolStats(
                checkouts=self._checkouts,
                rejected=self._rejected,
                idle=len(self._idle),
            )

    @property
    def idle(self) -> int:
        with self._lock:
            return len(self._idle)
