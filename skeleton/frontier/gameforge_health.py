"""Bounded health-checked pooling contract mined from GameForge gf-services.

Source: Apeloff1/gameforge-rs, crates/gf-services/src/lib.rs,
revision 8f0a107e5cac31fbfe39fee07daad415fd453aca.

The contract deliberately avoids concrete database/client dependencies. Callers
provide construction and health predicates; the pool owns only bounded idle
retention and max-age policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, List, Optional, TypeVar
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
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be > 0")
        self._make = make
        self._healthy = healthy
        self._capacity = capacity
        self._max_age = max_age_seconds
        self._clock = clock
        self._idle: List[tuple[T, float]] = []
        self._checkouts = 0
        self._rejected = 0

    def checkout(self) -> T:
        now = self._clock()
        while self._idle:
            value, born = self._idle.pop()
            if now - born > self._max_age:
                continue
            try:
                healthy = self._healthy(value)
            except Exception:
                healthy = False
            if healthy:
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
        self._checkouts += 1
        return value

    def release(self, value: T) -> bool:
        """Return a healthy resource if capacity permits; otherwise drop it."""
        if len(self._idle) >= self._capacity:
            return False
        try:
            if not self._healthy(value):
                self._rejected += 1
                return False
        except Exception:
            self._rejected += 1
            return False
        self._idle.append((value, self._clock()))
        return True

    def stats(self) -> PoolStats:
        return PoolStats(
            checkouts=self._checkouts,
            rejected=self._rejected,
            idle=len(self._idle),
        )

    @property
    def idle(self) -> int:
        return len(self._idle)
