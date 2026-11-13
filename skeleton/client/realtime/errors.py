"""Realtime client errors; all subclass the SDK ``SkeletonClientError``.

Every connect-time error carries ``status_code`` (HTTP status, if any),
``error_code`` (the server's machine code parsed from the JSON error body,
e.g. ``seal_required`` / ``invalid_seal`` / ``seal_unavailable``) and
``retryable``. :class:`~skeleton.client.realtime.RealtimeClient` backs off
and reconnects only when ``retryable`` is true; anything else is raised to the
caller immediately. Messages never include headers, seal values or raw bodies.
"""

from __future__ import annotations

from typing import Optional

from ._compat import SkeletonClientError

#: Error code the gate emits (503) when the seal secret is not configured.
#: Frozen seal contract: never retried.
SEAL_UNAVAILABLE = "seal_unavailable"

#: HTTP statuses worth reconnecting on; other 4xx are permanent for the request.
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class RealtimeError(SkeletonClientError):
    """Base class for realtime transport failures."""

    status_code: Optional[int] = None
    error_code: Optional[str] = None
    retryable: bool = False


class RealtimeConnectError(RealtimeError):
    """The stream could not be opened (network error or non-auth error status).

    ``retryable`` defaults to true for network errors (no status) and for
    :data:`RETRYABLE_STATUS_CODES`, false for any other status (e.g. 422
    ``unknown_channel`` will never succeed on retry).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        retryable: Optional[bool] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        if retryable is None:
            retryable = status_code is None or status_code in RETRYABLE_STATUS_CODES
        self.retryable = bool(retryable)


class RealtimeAuthError(RealtimeError):
    """401/403 from the stream or presence endpoint. Never retried.

    ``error_code`` distinguishes ``seal_required`` (no seal sent) from
    ``invalid_seal`` (bad/expired seal) and ``channel_forbidden`` (403).
    """

    retryable = False

    def __init__(self, message: str, *, status_code: Optional[int] = None, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class RealtimeSealUnavailable(RealtimeError):
    """503 ``seal_unavailable``: the server has no seal secret configured.

    Frozen seal contract: never retried. Raised immediately by
    :class:`~skeleton.client.realtime.RealtimeClient` with no backoff.
    Deliberately *not* a :class:`RealtimeConnectError` so generic
    ``except RealtimeConnectError`` retry loops cannot swallow it.
    """

    retryable = False

    def __init__(self, message: str = "stream refused with 503 (seal_unavailable)", *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = SEAL_UNAVAILABLE


class RealtimeHeartbeatTimeout(RealtimeError):
    """No bytes (events or ``: hb``) for the dead-stream window (45 s)."""

    retryable = True


class RealtimeGaveUp(RealtimeError):
    """``RetryPolicy.max_attempts`` consecutive connects failed."""


class RealtimeProtocolError(RealtimeError):
    """The server sent a frame that violates envelope v1."""

    retryable = True


__all__ = [
    "RETRYABLE_STATUS_CODES",
    "SEAL_UNAVAILABLE",
    "RealtimeAuthError",
    "RealtimeConnectError",
    "RealtimeError",
    "RealtimeGaveUp",
    "RealtimeHeartbeatTimeout",
    "RealtimeProtocolError",
    "RealtimeSealUnavailable",
]
