"""
Skeleton API — Idempotency guard for retry-sensitive operations

Provides:
- IdempotencyGuard: Deduplicate repeated requests by idempotency key
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class IdempotencyEntry:
    """Cached response for an idempotent request."""
    response: Any
    timestamp: float
    ttl_seconds: float = 300.0  # 5 minute default TTL

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl_seconds


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

    def _extract_key(self, headers: Dict[str, str]) -> Optional[str]:
        """Extract idempotency key from headers."""
        for key in ("Idempotency-Key", "X-Idempotency-Key", "idempotency-key"):
            if key in headers:
                return headers[key]
        return None

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
        expired = [k for k, e in self._cache.items() if e.is_expired()]
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
