from __future__ import annotations
"""
FastAPI middleware — app-wide Mishima Zaibatsu perimeter.
"""

import json
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gameforge.enterprise.zaibatsu_security import SECURITY


class ZaibatsuSecurityMiddleware(BaseHTTPMiddleware):
    """
    Gates every request: freeze, path abuse, rate, injection on body.
    """

    SKIP_PREFIXES = (
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path or "/"
        if any(path.startswith(s) for s in self.SKIP_PREFIXES):
            return await call_next(request)

        user_id = request.headers.get("x-user-id") or request.headers.get("x-subject") or "anon"
        body_text = ""
        if request.method.upper() in ("POST", "PUT", "PATCH"):
            try:
                raw = await request.body()
                body_text = raw.decode("utf-8", errors="replace") if raw else ""

                # re-inject body for downstream
                async def receive():
                    return {"type": "http.request", "body": raw, "more_body": False}

                request = Request(request.scope, receive)
            except Exception:
                body_text = ""

        gate = SECURITY.gate_request(
            path=path,
            method=request.method,
            user_id=user_id,
            body_text=body_text,
        )
        if gate.get("blocked"):
            return JSONResponse(
                status_code=423 if gate.get("reason") == "global_freeze" else 403,
                content={
                    "ok": False,
                    "blocked": True,
                    "zaibatsu": True,
                    "reason": gate.get("reason"),
                    "detail": gate,
                },
            )
        response = await call_next(request)
        if gate.get("integrity"):
            response.headers["X-Zaibatsu-Integrity"] = gate["integrity"]
        response.headers["X-Zaibatsu-Perimeter"] = "active"
        if SECURITY.frozen:
            response.headers["X-Zaibatsu-Frozen"] = "1"
        return response
