"""tiered_cache — L1/L2 hot-warm cache (gameforge-rs cache::TieredCache port).

L1 hot (60s TTL, cap 512), L2 warm (300s TTL, cap 4096). L3 = durable
store owned by the caller. Promotion: an L2 entry with >= 2 hits
graduates to L1 on read.

Separate from ``skeleton.data.cache_layer.CacheLayer`` (namespaced TTL
API cache) — that module is left untouched.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


L1_CAP = 512
L2_CAP = 4096
L1_TTL_S = 60.0
L2_TTL_S = 300.0


@dataclass
class _Entry:
    value: Any
    inserted: float
    hits: int = 0


class TieredCache:
    """Sync port of gf ``cache::TieredCache``. FIFO eviction within each tier."""

    def __init__(self) -> None:
        self._l1: Dict[str, _Entry] = {}
        self._l2: Dict[str, _Entry] = {}
        self._l1_order: list[str] = []
        self._l2_order: list[str] = []
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            e = self._l1.get(key)
            if e is not None:
                if (now - e.inserted) < L1_TTL_S:
                    self._hits += 1
                    return e.value
                self._remove_l1_unlocked(key)

            e2 = self._l2.get(key)
            if e2 is not None:
                if (now - e2.inserted) < L2_TTL_S:
                    e2.hits += 1
                    value = e2.value
                    promote = e2.hits >= 2
                    self._hits += 1
                    if promote:
                        self._put_l1_unlocked(key, value)
                    return value
                self._remove_l2_unlocked(key)

            self._misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            # L2 remains the warm source, but an already-hot key must be updated
            # atomically as well or reads could return the stale L1 value until
            # its TTL expires.
            was_hot = key in self._l1
            self._put_l2_unlocked(key, value)
            if was_hot:
                self._put_l1_unlocked(key, value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._remove_l1_unlocked(key)
            self._remove_l2_unlocked(key)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "l1_entries": len(self._l1),
                "l2_entries": len(self._l2),
                "hits": self._hits,
                "misses": self._misses,
                "l1_cap": L1_CAP,
                "l2_cap": L2_CAP,
            }

    def _remove_l1_unlocked(self, key: str) -> None:
        self._l1.pop(key, None)
        if key in self._l1_order:
            self._l1_order.remove(key)

    def _remove_l2_unlocked(self, key: str) -> None:
        self._l2.pop(key, None)
        if key in self._l2_order:
            self._l2_order.remove(key)

    def _put_l1_unlocked(self, key: str, value: Any) -> None:
        if len(self._l1) >= L1_CAP and key not in self._l1:
            if self._l1_order:
                victim = self._l1_order.pop(0)
                self._l1.pop(victim, None)
        if key not in self._l1:
            self._l1_order.append(key)
        self._l1[key] = _Entry(value=value, inserted=time.monotonic(), hits=0)

    def _put_l2_unlocked(self, key: str, value: Any) -> None:
        if len(self._l2) >= L2_CAP and key not in self._l2:
            if self._l2_order:
                victim = self._l2_order.pop(0)
                self._l2.pop(victim, None)
        if key not in self._l2:
            self._l2_order.append(key)
        self._l2[key] = _Entry(value=value, inserted=time.monotonic(), hits=0)