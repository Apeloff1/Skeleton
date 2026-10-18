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
        code: str | None = None,
    ) -> None:
        super().__init__(f"{status_code} {message} ({url})")
        self.status_code = status_code
        self.message = message
        self.url = url
        self.body = body
        #: Structured context from a v1 error envelope (empty otherwise).
        self.context: dict[str, Any] = {}
        if code is None and isinstance(body, dict):
            envelope = body.get("error")
            if isinstance(envelope, dict) and isinstance(envelope.get("code"), str):
                # v1 envelope: {"error": {"code": "PROJECT.*", "message": ..., ...}}
                code = envelope["code"]
                if isinstance(envelope.get("message"), str) and envelope["message"]:
                    self.message = envelope["message"]
                ctx = envelope.get("context")
                self.context = dict(ctx) if isinstance(ctx, dict) else {}
            elif isinstance(envelope, str) and envelope:
                code = envelope  # gate form: {"error": "invalid_seal" | "seal_unavailable"}
            elif isinstance(body.get("detail"), str):
                code = body["detail"]  # legacy {"detail": "<code>"}
        #: Machine-readable error code: v1 ``error.code``, the gate's string
        #: ``error`` value, or legacy ``detail``.
        self.code = code


class SkeletonCancelledError(SkeletonClientError):
    """Operation was cancelled through a :class:`CancelToken`."""


class SkeletonSealConfigError(SkeletonClientError):
    """Request seal cannot be minted locally or the server has no seal secret."""

class SkeletonSessionConfigError(SkeletonClientError):
    """No app session token configured (``session_token=`` / SKELETON_SESSION_TOKEN)."""
