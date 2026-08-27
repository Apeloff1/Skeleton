"""Pipeline caching — TTL memoisation of stage outputs.

Certain stages recompute identical inputs; the cache wraps pipelines
at the boundary, not stage-by-stage resource calls.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from skeleton.pipelines.validation import StageResult


class PipelineCache:
    """TTL cache of pipeline outputs keyed by input signature."""

    def __init__(self, *, ttl_s: float = 300.0, max_entries: int = 256) -> None:
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._entries: Dict[str, Tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, expires = entry
        if expires <= time.monotonic():
            del self._entries[key]
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        if len(self._entries) >= self.max_entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[key] = (value, time.monotonic() + self.ttl_s)

    def invalidate(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None
