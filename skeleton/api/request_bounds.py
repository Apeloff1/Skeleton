"""Request-boundary limits for HTTP application systems.

The Gate already bounds request bodies. This module provides the matching
header guard as a small ASGI primitive so oversized or pathological header
sets can be rejected before application handlers allocate or parse them.
"""

from __future__ import annotations

import os
from typing import Optional, Sequence, Tuple


_DEFAULT_MAX_HEADER_BYTES = 32_768
_DEFAULT_MAX_HEADER_COUNT = 100


def _positive_limit(
    env_name: str,
    explicit: Optional[int],
    default: int,
) -> int:
    """Resolve one positive request limit with environment override support."""

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
    """Return ``(count, bytes)`` for an ASGI request header sequence.

    The byte total deliberately measures only header names and values supplied
    by the ASGI server. Framing overhead belongs to the HTTP server and can be
    bounded there independently.
    """

    total = 0
    for name, value in headers:
        total += len(name) + len(value)
    return len(headers), total


class HeaderBoundMiddleware:
    """Reject HTTP requests whose header count or aggregate bytes are too large.

    Limits can be supplied explicitly or overridden at process start with
    ``SKELETON_GATE_MAX_HEADER_BYTES`` and ``SKELETON_GATE_MAX_HEADER_COUNT``.
    Rejections use HTTP 431 and never echo attacker-controlled header content.
    Non-HTTP ASGI scopes pass through unchanged.
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
        if scope["type"] != "http":
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
