"""
Skeleton API — Idempotency guard for retry-sensitive operations

Provides:
- IdempotencyGuard: Deduplicate repeated requests by idempotency key
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

IDEMPOTENCY_HEADER = "Idempotency-Key"
_IDEMPOTENCY_HEADER_ALIASES = frozenset({"idempotency-key", "x-idempotency-key"})


@dataclass
class IdempotencyEntry:
    """Cached response for an idempotent request."""
    response: Any
    timestamp: float
    ttl_seconds: float = 300.0  # 5 minute default TTL
    request_digest: Optional[str] = None
    pending: bool = False

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl_seconds


class IdempotencyConflict(Exception):
    """A key is unbound, in flight, or bound to another request body."""


class IdempotencyGuard:
    """Deduplicate retry-sensitive POST operations.

    A client retry replays the first recorded response
    instead of re-executing the operation.
    """

    def __init__(self, default_ttl: float = 300.0):
        self._cache: Dict[str, IdempotencyEntry] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._lock = threading.RLock()

    @contextmanager
    def operation(self, headers: Dict[str, str], *, scope: tuple[str, ...], body: Any):
        """Fence one authenticated HTTP operation in this existing cache.

        Legacy unscoped entries cannot establish ownership. A pending entry
        fences concurrent retries, and failed operations release their claim.
        """
        raw_key = self._extract_key(headers)
        if not raw_key:
            yield None
            return
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                          allow_nan=False).encode()).hexdigest()
        key = "scoped:" + hashlib.sha256(json.dumps([*scope, raw_key],
                                                     separators=(",", ":")).encode()).hexdigest()
        with self._lock:
            legacy = self._cache.get(raw_key)
            if legacy is not None and not legacy.is_expired():
                raise IdempotencyConflict("idempotency key has no authenticated request binding")
            entry = self._cache.get(key)
            if entry is not None and not entry.pending and entry.is_expired():
                del self._cache[key]
                entry = None
            if entry is not None:
                if entry.request_digest != digest:
                    raise IdempotencyConflict("idempotency key was already used with a different body")
                if entry.pending:
                    raise IdempotencyConflict("idempotency request is still in progress")
                self._hits += 1
                replay = copy.deepcopy(entry.response)
            else:
                self._misses += 1
                entry = IdempotencyEntry(None, time.time(), self._default_ttl, digest, True)
                self._cache[key] = entry
                replay = None
        try:
            yield replay
        finally:
            with self._lock:
                if entry.pending and self._cache.get(key) is entry:
                    del self._cache[key]

    def complete(self, headers: Dict[str, str], response: Any, *, scope: tuple[str, ...], body: Any) -> None:
        """Commit the response only to its pending authenticated request."""
        raw_key = self._extract_key(headers)
        if not raw_key:
            return
        key = "scoped:" + hashlib.sha256(json.dumps([*scope, raw_key],
                                                     separators=(",", ":")).encode()).hexdigest()
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                          allow_nan=False).encode()).hexdigest()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None or not entry.pending or entry.request_digest != digest:
                raise IdempotencyConflict("idempotency request binding changed")
            entry.response = copy.deepcopy(response)
            entry.timestamp = time.time()
            entry.pending = False

    def _extract_key(self, headers: Dict[str, str]) -> Optional[str]:
        """Extract idempotency key from headers.

        Starlette lower-cases header names, so lookups must be
        case-insensitive. Canonical ``Idempotency-Key`` and the
        ``X-Idempotency-Key`` alias both resolve.
        """
        values = {value for key, value in headers.items() if key.lower() in _IDEMPOTENCY_HEADER_ALIASES}
        if len(values) > 1:
            raise ValueError("idempotency key headers disagree")
        return next(iter(values), None)

    def replay(self, headers: Dict[str, str]) -> Optional[Any]:
        """Return cached response if idempotency key matches."""
        key = self._extract_key(headers)
        if not key:
            self._misses += 1
            return None

        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry.response

    def remember(self, headers: Dict[str, str], response: Any, ttl: Optional[float] = None) -> None:
        """Cache a response for future replays."""
        key = self._extract_key(headers)
        if key:
            self._cache[key] = IdempotencyEntry(
                response=response,
                timestamp=time.time(),
                ttl_seconds=ttl or self._default_ttl,
            )

    def cleanup(self) -> int:
        """Remove expired entries, return count removed."""
        with self._lock:
            expired = [k for k, e in self._cache.items() if not e.pending and e.is_expired()]
            for k in expired:
                del self._cache[k]
            return len(expired)

    def stats(self) -> Dict[str, Any]:
        return {
            "cached": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0,
        }
