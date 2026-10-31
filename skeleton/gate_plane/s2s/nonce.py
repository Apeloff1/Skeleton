"""Nonce-store adapter for the s2s replay window.

The s2s plane does **not** own a nonce store. Internal Systems owns it as
``skeleton.api.nonce_store`` (draft PR #4601 @ 84e661f2, stacked on #4594)::

    class NonceStore(Protocol):
        def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool

``True`` means the nonce is fresh (and is now recorded), ``False`` means it
was already seen inside its TTL (a replay). The production implementation
is ``InMemoryNonceStore(max_entries=100_000)``. A store that cannot record
a fresh nonce raises ``NonceStoreFull(retry_after_s)``; it never evicts a
live nonce. The s2s gate maps that to ``503 {"error": "nonce_store_full"}``
with ``Retry-After`` (fail closed - never admit an unrecorded nonce).

Until #4601 lands on the base, the import is guarded: :data:`NonceStore`
falls back to a local Protocol with the identical signature, and
:class:`LocalNonceStoreDouble` is an in-memory **test double** only. Once
#4601 merges, callers pass Internal Systems' store and nothing here changes.

Scopes used by this plane are always ``"s2s:<service>"`` (see
:func:`s2s_scope`) so service namespaces never collide with other users of
the shared store.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable, Dict, Optional, Protocol, Tuple, runtime_checkable

try:  # pragma: no cover - exercised only once #4601 is on the base
    from skeleton.api.nonce_store import NonceStore as _UpstreamNonceStore  # type: ignore[attr-defined]
    from skeleton.api.nonce_store import NonceStoreFull as _UpstreamNonceStoreFull  # type: ignore[attr-defined]

    UPSTREAM_NONCE_STORE = True
except Exception:  # noqa: BLE001 - absent until Internal Systems' #4601 merges
    _UpstreamNonceStore = None  # type: ignore[assignment]
    _UpstreamNonceStoreFull = None  # type: ignore[assignment]
    UPSTREAM_NONCE_STORE = False

S2S_SCOPE_PREFIX = "s2s:"


@runtime_checkable
class _LocalNonceStore(Protocol):
    """Signature-identical stand-in for ``skeleton.api.nonce_store.NonceStore``."""

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool:
        ...


NonceStore = _UpstreamNonceStore if _UpstreamNonceStore is not None else _LocalNonceStore


class _LocalNonceStoreFull(Exception):
    """Stand-in for ``skeleton.api.nonce_store.NonceStoreFull`` (same shape)."""

    def __init__(self, retry_after_s: int = 1) -> None:
        super().__init__("nonce store full")
        self.retry_after_s = max(1, int(retry_after_s))


NonceStoreFull = _UpstreamNonceStoreFull if _UpstreamNonceStoreFull is not None else _LocalNonceStoreFull


def s2s_scope(service: str) -> str:
    """Nonce-store scope for tokens issued by ``service``."""
    if not isinstance(service, str) or not service:
        raise ValueError("service required for nonce scope")
    return f"{S2S_SCOPE_PREFIX}{service}"


def is_nonce_store(obj: object) -> bool:
    """Duck-typed check that ``obj`` exposes ``check_and_record``."""
    fn = getattr(obj, "check_and_record", None)
    return callable(fn)


class LocalNonceStoreDouble:
    """In-memory **test double** mirroring ``InMemoryNonceStore`` semantics.

    Test-only: no persistence, no sharing across replicas. Entries live until
    ``ts + ttl_s`` measured on ``clock``. At capacity, expired entries are
    reclaimed; if all are live it raises :data:`NonceStoreFull` (fail closed,
    never evicts a live nonce) exactly like Internal Systems' store.
    """

    def __init__(self, max_entries: int = 100_000, *, clock: Optional[Callable[[], float]] = None) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries <= 0:
            raise ValueError("max_entries must be a positive integer")
        self.max_entries = max_entries
        self._clock = clock if clock is not None else time.time
        self._seen: Dict[Tuple[str, str], float] = {}
        self._lock = threading.Lock()
        self.calls = 0
        self.full_rejections = 0

    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool:
        if not isinstance(scope, str) or not scope or not isinstance(nonce, str) or not nonce:
            return False
        if ttl_s is None or ttl_s <= 0:
            return False
        now = self._clock()
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
            self._seen[key] = float(ts) + float(ttl_s)
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
    return isinstance(exc, (NonceStoreFull, _LocalNonceStoreFull)) or type(exc).__name__ == "NonceStoreFull"


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
