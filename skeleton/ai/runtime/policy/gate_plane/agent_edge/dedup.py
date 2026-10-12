"""Bounded, time-windowed duplicate suppression for the agent bus."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Dict, Optional


class DedupWindow:
    """Remembers keys for ``window_s`` seconds, bounded to ``capacity`` entries.

    Entries are kept in insertion order; expired entries are evicted lazily on
    every call and the oldest entries are dropped once capacity is exceeded
    (counted in :attr:`evicted_early` so operators can size the window).
    Each key can carry a small state string (``"pending"``/``"done"``) so the
    bus can distinguish "already queued" from "already processed".
    """

    def __init__(self, *, window_s: float = 600.0, capacity: int = 100_000) -> None:
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.window_s = float(window_s)
        self.capacity = int(capacity)
        self._entries: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
        self._lock = threading.Lock()
        self.evicted_early = 0
        self.hits = 0

    def _evict(self, now: float) -> None:
        while self._entries:
            key, (expires, _state) = next(iter(self._entries.items()))
            if expires > now:
                break
            self._entries.popitem(last=False)

    def seen(self, key: str, now: float) -> Optional[str]:
        """Return the stored state for ``key`` if it is inside the window."""
        with self._lock:
            self._evict(now)
            entry = self._entries.get(key)
            if entry is None:
                return None
            self.hits += 1
            return entry[1]

    def remember(self, key: str, now: float, state: str = "pending") -> bool:
        """Record ``key``; returns False when it was already present (a duplicate)."""
        with self._lock:
            self._evict(now)
            if key in self._entries:
                self.hits += 1
                return False
            self._entries[key] = (now + self.window_s, state)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
                self.evicted_early += 1
            return True

    def mark(self, key: str, now: float, state: str) -> None:
        """Update state and refresh the window for ``key`` (insert if missing)."""
        with self._lock:
            self._entries.pop(key, None)
            self._entries[key] = (now + self.window_s, state)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
                self.evicted_early += 1

    def forget(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def stats(self) -> Dict[str, float]:
        with self._lock:
            return {
                "size": len(self._entries),
                "capacity": self.capacity,
                "window_s": self.window_s,
                "hits": self.hits,
                "evicted_early": self.evicted_early,
            }


__all__ = ["DedupWindow"]
