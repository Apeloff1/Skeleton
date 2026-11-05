"""Replay-store protocol for the S2S authorization domain.

The domain does not import from ``skeleton.api``. Application composition
injects a store implementing ``check_and_record(scope, nonce, ts, ttl_s)``;
the concrete API-owned store remains an external implementation detail.
The structural protocol is always available, even before the upstream
implementation is merged.

``LocalNonceStoreDouble`` is test-only and never evicts live nonces.
Capacity exhaustion fails closed. ``is_nonce_store_full`` recognizes
external stores' ``NonceStoreFull`` exceptions without importing them.
Production replicas must share a durable replay store.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable, Dict, Optional, Protocol, Tuple, runtime_checkable

# Domain-to-API imports are forbidden. The application injects its store.
# This compatibility flag records that no upstream implementation is imported.
UPSTREAM_NONCE_STORE = False

S2S_SCOPE_PREFIX = "s2s:"


@runtime_checkable
class _LocalNonceStore(Protocol):
    """Structural nonce-store protocol for externally injected implementations."""

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool:
        ...


NonceStore = _LocalNonceStore


class _LocalNonceStoreFull(Exception):
    """Stand-in for ``skeleton.api.nonce_store.NonceStoreFull`` (same shape)."""

    def __init__(self, retry_after_s: int = 1) -> None:
        super().__init__("nonce store full")
        self.retry_after_s = max(1, int(retry_after_s))


NonceStoreFull = _LocalNonceStoreFull


def s2s_scope(service: str) -> str:
    """Nonce-store scope for tokens issued by ``service``."""
    if not isinstance(service, str) or not service:
        raise ValueError("service required for nonce scope")
    return f"{S2S_SCOPE_PREFIX}{service}"


def is_nonce_store(obj: object) -> bool:
    """Duck-typed check that ``obj`` exposes ``check_and_record``."""
    fn = getattr(obj, "check_and_record", None)
    return callable(fn)


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


class LocalNonceStoreDouble:
    """In-memory **test double** mirroring ``InMemoryNonceStore`` semantics.

    Test-only: no persistence, no sharing across replicas. Entries live until
    ``ts + ttl_s`` measured on ``clock``. At capacity, expired entries are
    reclaimed; if all are live it raises :data:`NonceStoreFull` (fail closed,
    never evicts a live nonce) exactly like Internal Systems' store.
    """

    def __init__(self, max_entries: int = 100_000, *, clock: Optional[Callable[[], float]] = None) -> None:
        if type(max_entries) is not int or not 1 <= max_entries <= 1_000_000:
            raise ValueError("max_entries must be a positive integer")
        self.max_entries = max_entries
        self._clock = clock if clock is not None else time.time
        self._seen: Dict[Tuple[str, str], float] = {}
        self._lock = threading.Lock()
        self.calls = 0
        self.full_rejections = 0

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool:
        if (type(scope) is not str or not 1 <= len(scope) <= 256
                or type(nonce) is not str or not 1 <= len(nonce) <= 256
                or any(ord(char) < 32 or ord(char) == 127 for char in scope + nonce)):
            return False
        if (not _finite_number(ts) or not _finite_number(ttl_s)
                or not 0 < ttl_s <= 1_000_000_000_000):
            return False
        now = self._clock()
        if not _finite_number(now):
            return False
        expires_at = float(ts) + float(ttl_s)
        # Match production nonce custody: stale or unbounded retention
        # must not return a fresh admission, even in the test double.
        if (ts < 0 or not math.isfinite(expires_at)
                or not now < expires_at <= now + 1_000_000_000_000):
            return False
        key = (scope, nonce)
        with self._lock:
            self.calls += 1
            until = self._seen.get(key)
            if until is not None and until >= now:
                return False
            if until is None and len(self._seen) >= self.max_entries:
                for k in [k for k, u in self._seen.items() if u < now]:
                    del self._seen[k]
                if len(self._seen) >= self.max_entries:
                    self.full_rejections += 1
                    soonest = min(self._seen.values(), default=now)
                    raise NonceStoreFull(math.ceil(max(0.0, soonest - now)) or 1)
            self._seen[key] = expires_at
            return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)

    def scopes(self) -> Dict[str, int]:
        with self._lock:
            out: Dict[str, int] = {}
            for scope, _ in self._seen:
                out[scope] = out.get(scope, 0) + 1
            return out


def is_nonce_store_full(exc: BaseException) -> bool:
    """True for upstream or local ``NonceStoreFull`` (matched by type or name)."""
    return isinstance(exc, NonceStoreFull) or type(exc).__name__ == "NonceStoreFull"


__all__ = [
    "LocalNonceStoreDouble",
    "NonceStore",
    "NonceStoreFull",
    "S2S_SCOPE_PREFIX",
    "UPSTREAM_NONCE_STORE",
    "is_nonce_store",
    "is_nonce_store_full",
    "s2s_scope",
]
