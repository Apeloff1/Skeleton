"""Typed errors for the Skeleton HTTP client."""

from __future__ import annotations

from typing import Any


class SkeletonClientError(Exception):
    """Base class for client failures."""


class SkeletonTransportError(SkeletonClientError):
    """Network / connection failure before an HTTP response arrived."""


class SkeletonTimeoutError(SkeletonClientError):
    """Request exceeded the configured timeout budget."""


class SkeletonHTTPError(SkeletonClientError):
    """HTTP response indicated failure (status >= 400)."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        url: str = "",
        body: Any = None,
    ) -> None:
        super().__init__(f"{status_code} {message} ({url})")
        self.status_code = status_code
        self.message = message
        self.url = url
        self.body = body
