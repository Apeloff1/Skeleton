"""Result cache for retrieval — TTL-based memoisation for queries.

Querying an index repeatedly is wasteful; the cache holds ranked results
per query key for a bounded TTL and bounded entry count.
"""

from __future__ import annotations

import copy
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Optional, Tuple

from skeleton.retrieval.fusion import ScoredResult


@dataclass(slots=True)
class CacheEntry:
    results: Tuple[ScoredResult, ...]
    expires_at: float


class ResultCache:
    """TTL cache with LRU eviction, isolation, and a hard entry bound.

    Cache operations are synchronized so the same instance can safely back
    concurrent retrieval requests. Mutable result objects are deep-copied on
    both insertion and retrieval so callers cannot poison later cache hits by
    mutating a result or nested metadata they received from another request.
    """

    def __init__(self, *, ttl_s: float = 60.0, max_entries: int = 512) -> None:
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)):
            raise TypeError("ttl_s must be a number")
        if ttl_s <= 0:
            raise ValueError("ttl_s must be greater than zero")
        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise TypeError("max_entries must be an integer")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")

        self.ttl_s = float(ttl_s)
        self.max_entries = max_entries
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = RLock()

    def get(self, query: str) -> Optional[Tuple[ScoredResult, ...]]:
        with self._lock:
            now = time.monotonic()
            entry = self._entries.get(query)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._entries[query]
                return None

            # A hot query should not be evicted before colder entries.
            self._entries.move_to_end(query)
            stored_results = entry.results

        # Do not execute arbitrary metadata copy hooks while holding the cache
        # lock. If a payload cannot be isolated, evict it rather than exposing
        # the cache's private mutable objects to a caller.
        try:
            return copy.deepcopy(stored_results)
        except Exception:
            with self._lock:
                if self._entries.get(query) is entry:
                    self._entries.pop(query, None)
            return None

    def put(self, query: str, results: Tuple[ScoredResult, ...]) -> None:
        try:
            cached_results = copy.deepcopy(tuple(results))
        except Exception:
            # Caching is an optimization. A value that cannot be safely isolated
            # must not make retrieval fail or enter the shared cache by reference.
            return

        with self._lock:
            now = time.monotonic()

            # Updating an existing key refreshes both TTL and LRU position.
            self._entries.pop(query, None)

            # Avoid evicting a live entry while expired entries are still occupying
            # capacity. The bounded scan runs only when the cache is full.
            if len(self._entries) >= self.max_entries:
                expired = [
                    key
                    for key, entry in self._entries.items()
                    if entry.expires_at <= now
                ]
                for key in expired:
                    self._entries.pop(key, None)

            while len(self._entries) >= self.max_entries:
                self._entries.popitem(last=False)

            self._entries[query] = CacheEntry(
                results=cached_results,
                expires_at=now + self.ttl_s,
            )

    def invalidate(self, query: str) -> bool:
        with self._lock:
            return self._entries.pop(query, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)
