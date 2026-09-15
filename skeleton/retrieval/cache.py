"""Result cache for retrieval — TTL-based memoisation for queries.

Querying an index repeatedly is wasteful; the cache holds ranked results
per query key for a bounded TTL and bounded entry count.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Tuple

from skeleton.retrieval.fusion import ScoredResult


@dataclass(slots=True)
class CacheEntry:
    results: Tuple[ScoredResult, ...]
    expires_at: float


class ResultCache:
    """TTL cache with LRU eviction and a hard entry bound."""

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

    def get(self, query: str) -> Optional[Tuple[ScoredResult, ...]]:
        now = time.monotonic()
        entry = self._entries.get(query)
        if entry is None:
            return None
        if entry.expires_at <= now:
            del self._entries[query]
            return None

        # A hot query should not be evicted before colder entries.
        self._entries.move_to_end(query)
        return entry.results

    def put(self, query: str, results: Tuple[ScoredResult, ...]) -> None:
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
            results=results,
            expires_at=now + self.ttl_s,
        )

    def invalidate(self, query: str) -> bool:
        return self._entries.pop(query, None) is not None

    def clear(self) -> None:
        self._entries.clear()

    def size(self) -> int:
        return len(self._entries)
