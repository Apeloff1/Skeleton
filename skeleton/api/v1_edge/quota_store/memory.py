"""Process-local :class:`CounterStore` — the default and the reference semantics.

Thread-safe (one lock around the read-modify-write), LRU-bounded so a flood of
distinct tenants or routes cannot grow memory without bound, and idle buckets
expire once they would have refilled completely (an expired bucket and a full
one are indistinguishable, so expiry never changes a verdict).

It is "shared" only within one process. Multi-replica deployments plug in a
remote store (see :mod:`.remote`) behind the same interface.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Optional, Tuple

from .store import BucketSpec, TakeResult, compute_take


class InMemoryCounterStore:
    name = "memory"

    def __init__(self, *, max_keys: int = 100_000, clock: Callable[[], float] = time.monotonic):
        if max_keys < 1:
            raise ValueError("max_keys must be >= 1")
        self._max = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        # key -> (tokens, updated, expires_at)
        self._data: "OrderedDict[str, Tuple[float, float, float]]" = OrderedDict()
        self.evictions = 0

    def _load(self, key: str, now: float) -> Tuple[Optional[float], Optional[float]]:
        row = self._data.get(key)
        if row is None:
            return None, None
        tokens, updated, expires = row
        if now >= expires:
            del self._data[key]
            return None, None
        self._data.move_to_end(key)
        return tokens, updated

    def _store(self, key: str, tokens: float, now: float, spec: BucketSpec) -> None:
        self._data[key] = (tokens, now, now + spec.full_after_s)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
            self.evictions += 1

    def take(self, key: str, spec: BucketSpec, cost: float = 1.0,
             now: Optional[float] = None) -> TakeResult:
        with self._lock:
            t = self._clock() if now is None else now
            tokens, updated = self._load(key, t)
            result, level = compute_take(tokens, updated, spec, cost, t)
            self._store(key, level, t, spec)
            return result

    def peek(self, key: str, spec: BucketSpec, now: Optional[float] = None) -> TakeResult:
        with self._lock:
            t = self._clock() if now is None else now
            tokens, updated = self._load(key, t)
        if tokens is None or updated is None:
            tokens, updated = spec.capacity, t
        level = min(spec.capacity, tokens + max(0.0, t - updated) * spec.rate_per_s)
        wait = 0.0 if level + 1e-9 >= 1 else (1 - level) / spec.rate_per_s
        return TakeResult(level + 1e-9 >= 1, level, spec.capacity, wait,
                          (spec.capacity - level) / spec.rate_per_s)

    def reset(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def healthy(self) -> bool:
        return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
