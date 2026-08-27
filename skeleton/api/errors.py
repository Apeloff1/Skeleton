"""API errors — unify SkeletonError code to HTTP responses.

kernel http_status_for(exc) maps the lattice; routes still embed that
map ad hoc. These helpers produce the JSON envelope the router returns.

- :class:`ApiErrorResponse` — to_{dict,response}
- :func:`map_error` — SkeletonError → ApiErrorResponse with safe context
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse

from skeleton.kernel.errors import SkeletonError, http_status_for


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
    return ApiErrorResponse(
        error=type(exc).__name__,
        code=exc.code,
        message=exc.message,
        context=dict(exc.context) if include_context else {},
        status=http_status_for(exc),
    )
