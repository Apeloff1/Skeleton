"""Nonce store port + bounded, fail-closed in-memory TTL implementation.

Shared interface for seal v3 replay protection and service-to-service callers.
``scope`` namespaces callers (e.g. ``"seal"`` or ``"s2s:<service>"``) so the same
nonce value in two scopes never collides.

Fail-closed capacity: a store that cannot record a fresh nonce because it is at
capacity with only live entries raises :class:`NonceStoreFull` from
``check_and_record`` (it never evicts a live nonce, which would reopen a replay
window). The seal middleware maps it to ``503 {"error":"nonce_store_full"}``
with ``Retry-After``.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Any, Protocol

DEFAULT_MAX_ENTRIES = 100_000
MAX_NONCE_ENTRIES = 1_000_000
MAX_NONCE_TTL_S = 1_000_000_000_000
MAX_ENTRIES_ENV = "SKELETON_SEAL_NONCE_STORE_MAX"
FULL_METRIC = "nonce_store_full"


def _finite_number(value: object) -> bool:
    """Reject nonfinite or unrepresentably large numeric evidence without overflow."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


class NonceStoreFull(Exception):
    """Raised by ``check_and_record`` when a fresh nonce cannot be recorded.

    ``retry_after_s`` is a whole-second hint (>= 1) for when capacity frees up.
    """

    def __init__(self, retry_after_s: int = 1) -> None:
        super().__init__("nonce store full")
        self.retry_after_s = max(1, int(retry_after_s))


class NonceStore(Protocol):
    """Port: True if ``nonce`` is fresh in ``scope`` (and record it), False on replay.

    ``ts`` is the nonce's issue time (unix seconds); the entry is retained until
    ``ts + ttl_s``. Implementations must be atomic and fail closed: when they
    cannot record a fresh nonce they raise :class:`NonceStoreFull` (capacity) or
    another exception (backend error) -- never return True without recording.
    """

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool: ...


def max_entries_from_env(env: dict[str, str] | None = None) -> int:
    """``SKELETON_SEAL_NONCE_STORE_MAX`` (default 100_000); invalid values raise."""
    raw = (os.environ if env is None else env).get(MAX_ENTRIES_ENV)
    if raw is None or not str(raw).strip():
        return DEFAULT_MAX_ENTRIES
    try:
        value = int(str(raw).strip().replace("_", ""))
    except ValueError:
        raise ValueError(f"{MAX_ENTRIES_ENV} must be a positive integer") from None
    if not 1 <= value <= MAX_NONCE_ENTRIES:
        raise ValueError(f"{MAX_ENTRIES_ENV} must be a bounded positive integer")
    return value


class InMemoryNonceStore:
    """Process-local, thread-safe, bounded, fail-closed TTL nonce store.

    At capacity, expired entries are reclaimed first; if every entry is still
    live the new nonce is refused with :class:`NonceStoreFull` (live nonces are
    never evicted). Size ``max_entries`` above peak nonces-per-TTL.
    ``nonce_store_full`` rejections are counted (``stats()``) and, when a
    ``metrics`` collector with ``increment(name, value, labels)`` is supplied
    (e.g. ``skeleton.observability.metrics.MetricsCollector``), emitted there too.
    """

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        *,
        clock=time.time,
        metrics: Any = None,
    ) -> None:
        if (type(max_entries) is not int or not 1 <= max_entries <= MAX_NONCE_ENTRIES):
            raise ValueError("max_entries must be a positive integer")
        self._max = max_entries
        self._clock = clock
        self._metrics = metrics
        self._entries: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()
        self.nonce_store_full = 0
        self.reclaimed = 0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, **kwargs: Any) -> InMemoryNonceStore:
        return cls(max_entries_from_env(env), **kwargs)

    @property
    def max_entries(self) -> int:
        return self._max

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "max_entries": self._max,
                "nonce_store_full": self.nonce_store_full,
                "reclaimed": self.reclaimed,
            }

    def _purge(self, now: float) -> None:
        dead = [k for k, exp in self._entries.items() if exp < now]
        for k in dead:
            del self._entries[k]
        self.reclaimed += len(dead)

    def _full(self, scope: str, now: float) -> NonceStoreFull:
        self.nonce_store_full += 1
        if self._metrics is not None:
            try:
                self._metrics.increment(FULL_METRIC, 1.0, {"scope": scope})
            except Exception:  # noqa: BLE001, S110
                pass  # metrics must never turn a rejection into an accept
        soonest = min(self._entries.values(), default=now)
        return NonceStoreFull(math.ceil(max(0.0, soonest - now)) or 1)

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool:
        if (type(scope) is not str or not 1 <= len(scope) <= 256
                or type(nonce) is not str or not 1 <= len(nonce) <= 256
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in scope + nonce)):
            return False
        if (not _finite_number(ts) or not _finite_number(ttl_s)
                or not 0 < ttl_s <= MAX_NONCE_TTL_S):
            return False
        now = self._clock()
        if not _finite_number(now):
            return False
        expires_at = float(ts) + float(ttl_s)
        # Never admit an already-expired nonce or an unbounded future lease.
        # Otherwise a stale credential could be accepted repeatedly as fresh.
        if (ts < 0 or not math.isfinite(expires_at)
                or not now < expires_at <= now + MAX_NONCE_TTL_S):
            return False
        key = (scope, nonce)
        with self._lock:
            exp = self._entries.get(key)
            if exp is not None and exp >= now:
                return False
            if exp is None and len(self._entries) >= self._max:
                self._purge(now)
                if len(self._entries) >= self._max:
                    raise self._full(scope, now)
            self._entries[key] = expires_at
            return True
