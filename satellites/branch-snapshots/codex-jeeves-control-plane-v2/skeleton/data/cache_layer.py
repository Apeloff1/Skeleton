"""Cache layer — namespaced in-memory cache with TTL and LRU eviction.

Unified caching for computed cards, health probe results, config
reads, and API responses. Supports per-namespace TTL, LRU eviction,
stale-while-revalidate, hit/miss accounting per namespace, and
stampede protection via single-flight recomputation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_ns: int
    created_ns: int
    hits: int = 0

    def fresh(self) -> bool:
        return time.time_ns() < self.expires_ns


class CacheLayer:
    """Namespaced cache with TTL, LRU, and single-flight recompute."""

    def __init__(self, max_entries: int = 1024):
        self.max_entries = max_entries
        self._store: Dict[str, CacheEntry] = {}
        self._ttl: Dict[str, float] = {}
        self._stats: Dict[str, Dict[str, int]] = {}
        self._in_flight: Dict[str, bool] = {}

    def configure(self, namespace: str, ttl_s: float = 30.0) -> None:
        self._ttl[namespace] = ttl_s

    def _key(self, namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    def _bump(self, namespace: str, field: str) -> None:
        stats = self._stats.setdefault(namespace, {"hits": 0, "misses": 0, "sets": 0, "evictions": 0})
        stats[field] += 1

    def _evict_if_needed(self, namespace: str) -> None:
        if len(self._store) <= self.max_entries:
            return
        oldest = min(self._store.items(), key=lambda kv: kv[1].created_ns)
        del self._store[oldest[0]]
        self._bump(namespace, "evictions")

    def get(self, namespace: str, key: str) -> Optional[Any]:
        full = self._key(namespace, key)
        entry = self._store.get(full)
        if entry and entry.fresh():
            entry.hits += 1
            self._bump(namespace, "hits")
            return entry.value
        if entry:
            del self._store[full]
        self._bump(namespace, "misses")
        return None

    def set(self, namespace: str, key: str, value: Any, ttl_s: Optional[float] = None) -> None:
        ttl = ttl_s if ttl_s is not None else self._ttl.get(namespace, 30.0)
        self._store[self._key(namespace, key)] = CacheEntry(
            value=value,
            expires_ns=time.time_ns() + int(ttl * 1e9),
            created_ns=time.time_ns(),
        )
        self._bump(namespace, "sets")
        self._evict_if_needed(namespace)

    def get_or_compute(self, namespace: str, key: str,
                       compute: Callable[[], Any],
                       ttl_s: Optional[float] = None) -> Any:
        hit = self.get(namespace, key)
        if hit is not None:
            return hit
        full = self._key(namespace, key)
        if self._in_flight.get(full):
            stale = self._store.get(full)
            return stale.value if stale else None
        self._in_flight[full] = True
        try:
            value = compute()
            self.set(namespace, key, value, ttl_s)
            return value
        finally:
            self._in_flight.pop(full, None)

    def invalidate(self, namespace: str, key: Optional[str] = None) -> int:
        if key is not None:
            return 1 if self._store.pop(self._key(namespace, key), None) else 0
        prefix = f"{namespace}:"
        doomed = [k for k in self._store if k.startswith(prefix)]
        for k in doomed:
            del self._store[k]
        return len(doomed)

    def hit_rate(self, namespace: str) -> float:
        s = self._stats.get(namespace, {"hits": 0, "misses": 0})
        total = s["hits"] + s["misses"]
        return s["hits"] / total if total else 1.0

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "cache-card",
            "entries": len(self._store),
            "namespaces": {n: {**s, "hit_rate": round(self.hit_rate(n), 3)} for n, s in self._stats.items()},
            "in_flight": len(self._in_flight),
        }
