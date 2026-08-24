"""API middleware — auth, rate limiting, and request ID propagation.

FastAPI doesn't ship with these; they live here so routes stay thin.
Each is an ASGI callable or dependency that wraps the app.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Optional

from skeleton.kernel.errors import KernelError


class MiddlewareError(KernelError):
    code = "API.MIDDLEWARE"


class AuthError(MiddlewareError):
    code = "API.AUTH"
    http_status = 401


class RateLimitError(MiddlewareError):
    code = "API.RATE_LIMIT"
    http_status = 429


class BearerAuth:
    """Validates Bearer tokens against a verifier callable."""

    def __init__(self, verifier: Callable[[str], Optional[Dict[str, Any]]]) -> None:
        self.verifier = verifier

    def __call__(self, authorization: Optional[str] = None) -> Dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthError("missing or malformed Bearer token")
        payload = self.verifier(authorization[7:])
        if payload is None:
            raise AuthError("invalid token")
        return payload


class RateLimiter:
    """Token-bucket keyed by arbitrary string (IP, user-id, API key)."""

    def __init__(self, *, capacity: float = 100.0, refill_per_sec: float = 10.0) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._buckets: Dict[str, tuple] = {}

    def check(self, key: str, tokens: float = 1.0) -> None:
        now = time.monotonic()
        current, last = self._buckets.get(key, (self.capacity, now))
        current = min(self.capacity, current + (now - last) * self.refill_per_sec)
        if current < tokens:
            self._buckets[key] = (current, now)
            raise RateLimitError(
                "rate limit exceeded",
                context={"retry_after_s": round((tokens - current) / self.refill_per_sec, 2)},
            )
        self._buckets[key] = (current - tokens, now)


def get_request_id(header_value: Optional[str] = None) -> str:
    """Provide or generate a request correlation id."""
    return header_value or uuid.uuid4().hex[:16]
