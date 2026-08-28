"""Consolidated endpoint error envelope.

Every SkeletonError subclass carries a ``code`` (e.g. ``KRN.WORK_QUEUE``)
and many carry an ``http_status``. This module renders them all through one
shape so API consumers get a stable error contract regardless of which
subsystem raised.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.kernel.errors import SkeletonError, http_status_for


def error_envelope(exc: Exception) -> Dict[str, Any]:
    """Render any exception as a stable error envelope dict."""
    if isinstance(exc, SkeletonError):
        return {
            "error": {
                "code": getattr(exc, "code", "SKELETON"),
                "message": str(exc),
                "context": getattr(exc, "context", {}),
                "status": http_status_for(exc),
            }
        }
    return {
        "error": {
            "code": "INTERNAL",
            "message": str(exc)[:200],
            "context": {},
            "status": 500,
        }
    }


def status_for(exc: Exception, default: int = 500) -> int:
    """HTTP status for an exception, falling back to ``default``."""
    try:
        return http_status_for(exc)
    except Exception:
        return default
