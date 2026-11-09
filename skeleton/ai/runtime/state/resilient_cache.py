"""Bounded resilient TTL cache evolved from Newsay's weather-cache pattern.

Newsay cached external weather data for a fixed TTL and fell back to defaults
when the upstream request failed. This module generalizes that idea without
hiding total upstream failure: fresh values are served immediately, stale
values may be served only inside an explicit stale-on-error window, and the
original exception propagates when no safe cached value exists.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Dict, Generic, Optional, TypeVar

from skeleton.kernel.events import EventBus

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class CacheResult(Generic[V]):
    value: V
    source: str
    age_seconds: float

    @property
    def stale(self) -> bool:
        return self.source == "stale"


@dataclass
class _Entry(Generic[V]):
    value: V
    stored_at: float


class ResilientTTLCache(Generic[K, V]):
    """Small LRU cache with explicit stale-on-error semantics."""

    def __init__(
        self,
        *,
        fresh_ttl: float = 300.0,
        stale_ttl: float = 1800.0,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
        bus: Optional[EventBus] = None,
    ) -> None:
        self.fresh_ttl = self._finite_nonnegative(fresh_ttl, "fresh_ttl")
        self.stale_ttl = self._finite_nonnegative(stale_ttl, "stale_ttl")
        if self.stale_ttl < self.fresh_ttl:
            raise ValueError("stale_ttl must be greater than or equal to fresh_ttl")
        if type(max_entries) is not int or max_entries <= 0:
            raise ValueError("max_entries must be a positive integer")
        self.max_entries = max_entries
        self._clock = clock
        self._bus = bus
        self._entries: "OrderedDict[K, _Entry[V]]" = OrderedDict()
        self._lock = threading.RLock()
        self._stats: Dict[str, int] = {
            "fresh_hits": 0,
            "stale_hits": 0,
            "misses": 0,
            "loads": 0,
            "load_errors": 0,
            "evictions": 0,
        }

    @staticmethod
    def _finite_nonnegative(value: float, name: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a finite non-negative number")
        number = float(value)
        if not (number >= 0.0 and number < float("inf")):
            raise ValueError(f"{name} must be a finite non-negative number")
        return number

    def _now(self) -> float:
        now = float(self._clock())
        if not (now >= 0.0 and now < float("inf")):
            raise RuntimeError("cache clock returned a non-finite or negative value")
        return now

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._entries[key] = _Entry(value=value, stored_at=self._now())
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
                self._stats["evictions"] += 1
            if self._bus:
                self._bus.emit("acquired.cache.stored", {"entries": len(self._entries)})

    def invalidate(self, key: K) -> bool:
        with self._lock:
            removed = self._entries.pop(key, None) is not None
            if removed and self._bus:
                self._bus.emit("acquired.cache.invalidated", {})
            return removed

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _candidate(self, key: K, now: float) -> tuple[Optional[_Entry[V]], float]:
        entry = self._entries.get(key)
        if entry is None:
            return None, 0.0
        age = max(0.0, now - entry.stored_at)
        if age > self.stale_ttl:
            self._entries.pop(key, None)
            return None, age
        self._entries.move_to_end(key)
        return entry, age

    def get(self, key: K) -> Optional[CacheResult[V]]:
        """Return only a fresh value; stale entries remain for error fallback."""
        with self._lock:
            now = self._now()
            entry, age = self._candidate(key, now)
            if entry is None or age > self.fresh_ttl:
                self._stats["misses"] += 1
                return None
            self._stats["fresh_hits"] += 1
            return CacheResult(entry.value, "fresh", round(age, 6))

    def get_or_load(self, key: K, loader: Callable[[], V]) -> CacheResult[V]:
        """Load a value, serving bounded stale data only on ordinary failures."""
        with self._lock:
            now = self._now()
            entry, age = self._candidate(key, now)
            if entry is not None and age <= self.fresh_ttl:
                self._stats["fresh_hits"] += 1
                return CacheResult(entry.value, "fresh", round(age, 6))

        try:
            value = loader()
        except Exception:
            with self._lock:
                self._stats["load_errors"] += 1
                now = self._now()
                entry, age = self._candidate(key, now)
                if entry is not None and age <= self.stale_ttl:
                    self._stats["stale_hits"] += 1
                    if self._bus:
                        self._bus.emit(
                            "acquired.cache.stale_served",
                            {"age_seconds": round(age, 6)},
                        )
                    return CacheResult(entry.value, "stale", round(age, 6))
            raise

        with self._lock:
            self._stats["loads"] += 1
        self.set(key, value)
        return CacheResult(value, "loaded", 0.0)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {**self._stats, "entries": len(self._entries)}


__all__ = ["CacheResult", "ResilientTTLCache"]
