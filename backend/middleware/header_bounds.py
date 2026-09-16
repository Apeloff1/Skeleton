"""Fail-closed request-header limits for the backend ASGI boundary.

The HTTP server owns transport/framing limits. This middleware adds a second,
application-side boundary for header sets that have already reached ASGI so
pathological cardinality or aggregate header bytes are rejected before the
backend application and its higher-cost middleware execute.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from typing import Any

_DEFAULT_MAX_HEADER_BYTES = 32_768
_DEFAULT_MAX_HEADER_COUNT = 100


def _positive_limit(env_name: str, explicit: int | None, default: int) -> int:
    """Resolve a positive integer limit with an environment override.

    Invalid configuration fails application startup rather than silently
    disabling the boundary.
    """
    raw = os.environ.get(env_name)
    if raw is not None:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
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


def measure_headers(headers: Sequence[tuple[bytes, bytes]]) -> tuple[int, int]:
    """Return ``(count, aggregate_name_and_value_bytes)`` for ASGI headers."""
    total = 0
    for name, value in headers:
        total += len(name) + len(value)
    return len(headers), total


class HeaderBoundMiddleware:
    """Reject oversized HTTP header sets with 431 before app dispatch.

    Environment overrides:
      * ``CODEDOCK_MAX_HEADER_BYTES`` (default 32768)
      * ``CODEDOCK_MAX_HEADER_COUNT`` (default 100)

    Rejections never echo attacker-controlled names or values.
    """

    def __init__(
        self,
        app: Any,
        *,
        max_header_bytes: int | None = None,
        max_header_count: int | None = None,
    ) -> None:
        self.app = app
        self.max_header_bytes = _positive_limit(
            "CODEDOCK_MAX_HEADER_BYTES",
            max_header_bytes,
            _DEFAULT_MAX_HEADER_BYTES,
        )
        self.max_header_count = _positive_limit(
            "CODEDOCK_MAX_HEADER_COUNT",
            max_header_count,
            _DEFAULT_MAX_HEADER_COUNT,
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", ())
        if not isinstance(headers, (list, tuple)):
            await self._reject(send, reason="malformed_headers")
            return

        if len(headers) > self.max_header_count:
            await self._reject(send, reason="header_count")
            return

        total = 0
        for item in headers:
            if (
                not isinstance(item, (list, tuple))
                or len(item) != 2
                or not isinstance(item[0], bytes)
                or not isinstance(item[1], bytes)
            ):
                await self._reject(send, reason="malformed_headers")
                return
            name, value = item
            total += len(name) + len(value)
            if total > self.max_header_bytes:
                await self._reject(send, reason="header_bytes")
                return

        await self.app(scope, receive, send)

    async def _reject(self, send, *, reason: str) -> None:
        payload = json.dumps(
            {
                "error": "request_headers_too_large",
                "reason": reason,
                "limit_bytes": self.max_header_bytes,
                "limit_count": self.max_header_count,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 431,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})
