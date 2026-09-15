"""Result cache for retrieval — TTL-based memoisation for queries.

Querying an index repeatedly is wasteful; the cache holds ranked results
per (normalised) query string for a bounded TTL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from skeleton.retrieval.fusion import ScoredResult


@dataclass
class CacheEntry:
    results: Tuple[ScoredResult, ...]
    expires_at: float


class ResultCache:
    """TTL cache keyed by query string; space-bounded via FIFO eviction."""

    def __init__(self, *, ttl_s: float = 60.0, max_entries: int = 512) -> None:
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._entries: Dict[str, CacheEntry] = {}

    def get(self, query: str) -> Optional[Tuple[ScoredResult, ...]]:
        now = time.monotonic()
        entry = self._entries.get(query)
        if entry is None:
            return None
        if entry.expires_at <= now:
            del self._entries[query]
            return None
        return entry.results

    def put(self, query: str, results: Tuple[ScoredResult, ...]) -> None:
        if len(self._entries) >= self.max_entries:
            # FIFO eviction
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[query] = CacheEntry(
            results=results,
            expires_at=time.monotonic() + self.ttl_s,
        )

    def invalidate(self, query: str) -> bool:
        return self._entries.pop(query, None) is not None

    def size(self) -> int:
        return len(self._entries)
