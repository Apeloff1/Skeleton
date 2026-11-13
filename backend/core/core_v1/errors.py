"""Error contract for backend core v1.

Every failure crosses the HTTP boundary as::

    {"error": {"type": <kind>, "code": "CORE.<AREA>.<REASON>",
               "message": <safe text>, "context": {...}}}

which matches the envelope already used by skeleton.projects.v1. ``context``
only ever carries caller-safe values (ids, field names, limits) - never
secrets, stack traces or upstream response bodies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class CoreError(Exception):
    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "error"
    http_status: int = 400

    def __post_init__(self) -> None:
        super().__init__(self.message)
        if not self.code.startswith("CORE."):
            raise ValueError("core error codes must start with 'CORE.'")

    def envelope(self) -> dict[str, Any]:
        return {"error": {"type": self.kind, "code": self.code,
                          "message": self.message, "context": dict(self.context)}}


def validation(code: str, message: str, **context: Any) -> CoreError:
    return CoreError(code, message, context, "validation_error", 400)


def unauthenticated(message: str = "authentication required") -> CoreError:
    return CoreError("CORE.AUTH.UNAUTHENTICATED", message, {}, "auth_error", 401)


def forbidden(message: str = "insufficient role", **context: Any) -> CoreError:
    return CoreError("CORE.AUTH.FORBIDDEN", message, context, "auth_error", 403)


def not_found(resource: str, resource_id: str) -> CoreError:
    return CoreError(f"CORE.{resource.upper()}.NOT_FOUND", f"{resource} not found",
                     {"id": resource_id}, "not_found", 404)


def conflict(code: str, message: str, **context: Any) -> CoreError:
    return CoreError(code, message, context, "conflict", 409)


def precondition_failed(current_etag: str) -> CoreError:
    return CoreError("CORE.CONCURRENCY.PRECONDITION_FAILED",
                     "resource changed since it was read", {"current_etag": current_etag},
                     "conflict", 412)


def precondition_required() -> CoreError:
    return CoreError("CORE.CONCURRENCY.PRECONDITION_REQUIRED",
                     "If-Match header is required for this operation", {}, "conflict", 428)


def unavailable(message: str = "backend core store unavailable") -> CoreError:
    return CoreError("CORE.STORE.UNAVAILABLE", message, {}, "unavailable", 503)


# Stable registry so Middleware / Frontend can switch on codes.
CODES: dict[str, int] = {
    "CORE.AUTH.UNAUTHENTICATED": 401,
    "CORE.AUTH.FORBIDDEN": 403,
    "CORE.PAGINATION.INVALID_CURSOR": 400,
    "CORE.PAGINATION.INVALID_LIMIT": 400,
    "CORE.IDEMPOTENCY.INVALID_KEY": 400,
    "CORE.IDEMPOTENCY.KEY_REUSED": 409,
    "CORE.IDEMPOTENCY.IN_FLIGHT": 409,
    "CORE.CONCURRENCY.PRECONDITION_FAILED": 412,
    "CORE.CONCURRENCY.PRECONDITION_REQUIRED": 428,
    "CORE.WEBHOOK.INVALID": 400,
    "CORE.WEBHOOK.INVALID_URL": 400,
    "CORE.WEBHOOK.NOT_FOUND": 404,
    "CORE.WEBHOOK.LIMIT_REACHED": 409,
    "CORE.WEBHOOK.DISABLED": 409,
    "CORE.EVENT.INVALID": 400,
    "CORE.EVENT.NOT_FOUND": 404,
    "CORE.DELIVERY.NOT_FOUND": 404,
    "CORE.DELIVERY.NOT_REPLAYABLE": 409,
    "CORE.STORE.UNAVAILABLE": 503,
    "CORE.REQUEST.INVALID_JSON": 400,
}
