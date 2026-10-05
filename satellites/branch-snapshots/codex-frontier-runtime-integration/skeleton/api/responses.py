"""API response helpers — consistent envelopes and pagination.

Routes shouldn't invent their own pagination shape each time. This
keeps success/error wrappers and slice/k_link/text-driven pagination
consistent across routers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi.responses import JSONResponse


@dataclass
class Page:
    items: List[Any]
    total: Optional[int] = None
    limit: Optional[int] = None
    offset: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
        }


def envelope(*, data: Any, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"data": data}
    if meta:
        body["meta"] = meta
    return body


def error_response(
    *, code: str, message: str, status: int = 400, context: Optional[Dict[str, Any]] = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "context": context or {},
            }
        },
    )


def paginate(items: List[Any], *, limit: int = 50, offset: int = 0) -> Page:
    return Page(
        items=items[offset : offset + limit],
        total=len(items),
        limit=limit,
        offset=offset,
    )
