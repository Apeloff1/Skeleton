"""Safe error responses. Never return raw exceptions or tracebacks to clients."""
from __future__ import annotations
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger("Skeleton.SafeErrors")

async def safe_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global handler that logs the real exception and returns a generic message."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "internal_error", "detail": "An unexpected error occurred."},
    )

def safe_str(exc: Exception, max_len: int = 120) -> str:
    """Return a truncated, non-traceback string suitable for client responses."""
    msg = str(exc)
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."
    # strip any traceback-like content
    if "Traceback" in msg or "File \"" in msg:
        return "error"
    return msg
