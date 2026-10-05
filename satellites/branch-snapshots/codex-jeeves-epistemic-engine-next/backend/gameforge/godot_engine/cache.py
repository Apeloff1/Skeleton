"""cache.py — TTL cache with stale-while-revalidate for engine metadata."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class _Entry:
    value: Any
    expires_at: float
    stale_until: float


class TTLCache:
    """Tiny in-process cache. Serves stale values while a refresh runs."""

    def __init__(self, maxsize: int = 256) -> None:
        self._store: dict[str, _Entry] = {}
        self._maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        e = self._store.get(key)
        if e is None:
            self.misses += 1
            return None
        if time.time() > e.stale_until:
            self._store.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return e.value

    def is_fresh(self, key: str) -> bool:
        e = self._store.get(key)
        return bool(e and time.time() <= e.expires_at)

    def set(self, key: str, value: Any, ttl: float = 300, stale: float = 900) -> None:
        if len(self._store) >= self._maxsize:
            oldest = min(self._store, key=lambda k: self._store[k].expires_at)
            self._store.pop(oldest, None)
        now = time.time()
        self._store[key] = _Entry(value, now + ttl, now + stale)

    def get_or(self, key: str, loader: Callable[[], Any], ttl: float = 300) -> Any:
        v = self.get(key)
        if v is not None:
            return v
        v = loader()
        self.set(key, v, ttl)
        return v

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def stats(self) -> dict:
        return {"size": len(self._store), "hits": self.hits, "misses": self.misses}


engine_cache = TTLCache()
