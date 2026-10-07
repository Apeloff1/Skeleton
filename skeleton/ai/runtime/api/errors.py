"""API errors — unify SkeletonError code to HTTP responses.

kernel http_status_for(exc) maps the lattice; routes still embed that
map ad hoc. These helpers produce the JSON envelope the router returns.

- :class:`ApiErrorResponse` — to_{dict,response}
- :func:`map_error` — SkeletonError → ApiErrorResponse with safe context
- :func:`install_error_handlers` — FastAPI fail-closed exception envelope
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse

from skeleton.kernel.errors import SkeletonError, http_status_for
from skeleton.observability.redaction import redact_payload, redact_text, safe_exception_text

INTERNAL_ERROR_MESSAGE = "internal server error"
INTERNAL_ERROR_BODY = {
    "error": {
        "type": "InternalError",
        "code": "SKL.INTERNAL",
        "message": INTERNAL_ERROR_MESSAGE,
        "context": {},
    }
}


@dataclass
class ApiErrorResponse:
    error: str
    code: str
    message: str
    context: Dict[str, Any]
    status: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "type": self.error,
                "code": self.code,
                "message": self.message,
                "context": self.context,
            }
        }

    def response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status, content=self.to_dict())


def map_error(exc: SkeletonError, *, include_context: bool = True) -> ApiErrorResponse:
    payload = exc.public_payload()
    context = redact_payload(payload["context"]) if include_context else {}
    return ApiErrorResponse(
        error=payload["error"],
        code=payload["code"],
        message=redact_text(payload["message"]),
        context=context if isinstance(context, dict) else {},
        status=http_status_for(exc),
    )


async def skeleton_error_handler(_request: Any, exc: SkeletonError) -> JSONResponse:
    """Map typed lattice errors onto the public HTTP envelope."""
    return map_error(exc).response()


async def unhandled_error_handler(_request: Any, exc: Exception) -> JSONResponse:
    """Fail closed: never stringify arbitrary exception text to clients."""
    _ = safe_exception_text(exc)
    return JSONResponse(status_code=500, content=INTERNAL_ERROR_BODY)


def install_error_handlers(app: Any) -> None:
    """Register lattice + unhandled handlers on a FastAPI app."""
    app.add_exception_handler(SkeletonError, skeleton_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
