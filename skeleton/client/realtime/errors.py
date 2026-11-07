"""Realtime client errors; all subclass the SDK ``SkeletonClientError``."""

from __future__ import annotations

from typing import Optional

from ._compat import SkeletonClientError


class RealtimeError(SkeletonClientError):
    """Base class for realtime transport failures."""


class RealtimeConnectError(RealtimeError):
    """The stream could not be opened (network error or retryable status)."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RealtimeAuthError(RealtimeError):
    """401/403 from the stream or presence endpoint. Never retried."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RealtimeHeartbeatTimeout(RealtimeError):
    """No bytes (events or ``: hb``) for the dead-stream window (45 s)."""


class RealtimeGaveUp(RealtimeError):
    """``RetryPolicy.max_attempts`` consecutive connects failed."""


class RealtimeProtocolError(RealtimeError):
    """The server sent a frame that violates envelope v1."""


__all__ = [
    "RealtimeAuthError",
    "RealtimeConnectError",
    "RealtimeError",
    "RealtimeGaveUp",
    "RealtimeHeartbeatTimeout",
    "RealtimeProtocolError",
]
