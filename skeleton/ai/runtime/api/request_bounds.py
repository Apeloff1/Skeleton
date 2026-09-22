"""Fail-closed request-header limits for ASGI application boundaries.

The HTTP server owns transport/framing limits; this primitive protects the
application boundary from pathological header sets that have already reached
ASGI. It is intentionally standalone so callers can compose it with an
existing middleware stack without changing authorization semantics.
"""

from __future__ import annotations

import os
from typing import Optional, Sequence, Tuple

_DEFAULT_MAX_HEADER_BYTES = 32_768
_DEFAULT_MAX_HEADER_COUNT = 100


def _positive_limit(env_name: str, explicit: Optional[int], default: int) -> int:
    """Resolve a positive integer limit, with an environment override."""
    raw = os.environ.get(env_name)
    if raw is not None:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be an integer") from exc
    elif explicit is not None:
        if isinstance(explicit, bool) or not isinstance(explicit, int):
            raise TypeError(f"{env_name} must be an integer")
        value = explicit
    else:
        value = default

    if value <= 0:
        raise ValueError(f"{env_name} must be positive")
    return value


def measure_headers(headers: Sequence[Tuple[bytes, bytes]]) -> Tuple[int, int]:
    """Return ``(count, raw_name_and_value_bytes)`` for ASGI headers."""
    total = sum(len(name) + len(value) for name, value in headers)
    return len(headers), total


class HeaderBoundMiddleware:
    """Reject oversized HTTP header sets before they reach application code.

    ``SKELETON_GATE_MAX_HEADER_BYTES`` and
    ``SKELETON_GATE_MAX_HEADER_COUNT`` can override explicit constructor
    values. Rejections use 431 and never reflect attacker-controlled header
    names or values in the response body.
    """

    def __init__(
        self,
        app,
        *,
        max_header_bytes: Optional[int] = None,
        max_header_count: Optional[int] = None,
    ) -> None:
        self.app = app
        self.max_header_bytes = _positive_limit(
            "SKELETON_GATE_MAX_HEADER_BYTES",
            max_header_bytes,
            _DEFAULT_MAX_HEADER_BYTES,
        )
        self.max_header_count = _positive_limit(
            "SKELETON_GATE_MAX_HEADER_COUNT",
            max_header_count,
            _DEFAULT_MAX_HEADER_COUNT,
        )

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers") or ()
        count = len(headers)
        if count > self.max_header_count:
            await self._reject(scope, receive, send, reason="header_count")
            return

        total = 0
        for name, value in headers:
            total += len(name) + len(value)
            if total > self.max_header_bytes:
                await self._reject(scope, receive, send, reason="header_bytes")
                return

        await self.app(scope, receive, send)

    async def _reject(self, scope, receive, send, *, reason: str) -> None:
        from starlette.responses import JSONResponse

        response = JSONResponse(
            {
                "error": "request_headers_too_large",
                "reason": reason,
                "limit_bytes": self.max_header_bytes,
                "limit_count": self.max_header_count,
            },
            status_code=431,
        )
        await response(scope, receive, send)
