"""Nonce store port + bounded in-memory LRU/TTL implementation.

Shared interface for seal v3 replay protection and service-to-service callers.
``scope`` namespaces callers (e.g. ``"seal"`` or ``"s2s:<service>"``) so the same
nonce value in two scopes never collides.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Protocol, Tuple

DEFAULT_MAX_ENTRIES = 100_000


class NonceStore(Protocol):
    """Port: True if ``nonce`` is fresh in ``scope`` (and record it), False on replay.

    ``ts`` is the nonce's issue time (unix seconds); the entry is retained until
    ``ts + ttl_s``. Shared implementations (e.g. Redis ``SET NX EXAT``) must be
    atomic and fail closed (return False or raise) when they cannot record.
    """

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool: ...


class InMemoryNonceStore:
    """Process-local, thread-safe, bounded LRU/TTL nonce store.

    Expired entries are dropped first; if still at ``max_entries`` the least
    recently recorded entry is evicted (size stays bounded). Size ``max_entries``
    above peak nonces-per-TTL so eviction never touches a live nonce.
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES, *, clock=time.time) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries <= 0:
            raise ValueError("max_entries must be a positive integer")
        self._max = max_entries
        self._clock = clock
        self._entries: "OrderedDict[Tuple[str, str], float]" = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._entries)

    def _purge(self, now: float) -> None:
        dead = [k for k, exp in self._entries.items() if exp < now]
        for k in dead:
            del self._entries[k]

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool:
        if not isinstance(scope, str) or not scope or not isinstance(nonce, str) or not nonce:
            return False
        if ttl_s is None or ttl_s <= 0:
            return False
        now = self._clock()
        key = (scope, nonce)
        with self._lock:
            exp = self._entries.get(key)
            if exp is not None and exp >= now:
                self._entries.move_to_end(key)
                return False
            if len(self._entries) >= self._max:
                self._purge(now)
                while len(self._entries) >= self._max:
                    self._entries.popitem(last=False)
            self._entries[key] = float(ts) + float(ttl_s)
            return True
