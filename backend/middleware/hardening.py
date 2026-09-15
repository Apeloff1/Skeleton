"""
hardening middleware — additional safety nets for the FastAPI backend.

  • RequestTimeoutMiddleware — kills any /api/* request running longer
    than DEFAULT_TIMEOUT_S, returning 504 instead of letting the worker
    hang. Configurable per-path via the PATH_TIMEOUTS map. The middleware
    also protects the privileged /api/advanced surface with a server-side
    admin token so legacy handler-level unlock logic cannot be bypassed.
  • ProcessHealthRouter — adds GET /api/health/detailed with CPU /
    memory / disk numbers so the frontend (or external monitoring)
    can detect resource exhaustion before requests start failing.

Wired into server.py via:
    from middleware.hardening import RequestTimeoutMiddleware, hardening_router
    app.add_middleware(RequestTimeoutMiddleware, default_timeout_s=30)
    app.include_router(hardening_router, prefix="/api")
"""
from __future__ import annotations
import asyncio
import hmac
import logging
import os
import time
from typing import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("api.hardening")

# Privileged API boundary. Keep the secret server-side; do not embed it in
# browser/mobile bundles. An unset or obviously weak token intentionally
# disables the advanced API instead of falling back to legacy unlock logic.
ADVANCED_API_PREFIX = "/api/advanced"
ADVANCED_ADMIN_TOKEN_ENV = "CODEDOCK_ADVANCED_ADMIN_TOKEN"
ADVANCED_ADMIN_TOKEN_HEADER = "x-codedock-admin-token"
MIN_ADVANCED_ADMIN_TOKEN_BYTES = 32

# Per-path overrides (longest-prefix match). Paths NOT listed use the
# middleware-level default_timeout_s. Tune for known slow endpoints.
PATH_TIMEOUTS: dict[str, float] = {
    "/api/binary/build":      120.0,   # APK compile may take a while
    "/api/binary/rebuild":    120.0,
    "/api/agents":             60.0,
    "/api/imagine":            90.0,
    "/api/music":              90.0,
    "/api/galaxy/build":      180.0,
    "/api/discourse/deliberate": 180.0,  # multi-model debate + critique + judge
    "/api/design-spec/compile":  90.0,   # reasoning-model GDD synthesis
    "/api/playable/generate":   180.0,   # full HTML5 game codegen (large output)
    "/api/llm-router/complete":  90.0,   # may route to slow reasoning models
    "/api/llm-router/game":      90.0,
}


def _resolve_timeout(path: str, default: float) -> float:
    best_key = ""
    for k in PATH_TIMEOUTS:
        if path.startswith(k) and len(k) > len(best_key):
            best_key = k
    return PATH_TIMEOUTS.get(best_key, default)


def _is_advanced_api_path(path: str) -> bool:
    """Match only the privileged route namespace, not look-alike prefixes."""
    return path == ADVANCED_API_PREFIX or path.startswith(f"{ADVANCED_API_PREFIX}/")


def _advanced_api_auth_failure(request: Request) -> JSONResponse | None:
    """Return a fail-closed auth response, or None for an authorized request."""
    configured = os.environ.get(ADVANCED_ADMIN_TOKEN_ENV, "").strip()
    if len(configured.encode("utf-8")) < MIN_ADVANCED_ADMIN_TOKEN_BYTES:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Advanced API is disabled until a strong "
                    f"{ADVANCED_ADMIN_TOKEN_ENV} is configured"
                )
            },
            headers={"Cache-Control": "no-store"},
        )

    supplied = request.headers.get(ADVANCED_ADMIN_TOKEN_HEADER, "")
    if not supplied or not hmac.compare_digest(
        supplied.encode("utf-8"), configured.encode("utf-8")
    ):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing advanced admin token"},
            headers={
                "Cache-Control": "no-store",
                "WWW-Authenticate": "Bearer",
            },
        )
    return None


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Enforce API timeout and the privileged advanced-API auth boundary."""

    def __init__(self, app, default_timeout_s: float = 30.0):
        super().__init__(app)
        self.default = float(default_timeout_s)

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip non-API paths (Metro / docs / etc.)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        if _is_advanced_api_path(request.url.path):
            auth_failure = _advanced_api_auth_failure(request)
            if auth_failure is not None:
                return auth_failure

        timeout = _resolve_timeout(request.url.path, self.default)
        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            log.warning("request_timeout path=%s timeout_s=%.1f", request.url.path, timeout)
            return JSONResponse(
                status_code=504,
                content={
                    "detail":     "Request timed out",
                    "path":       request.url.path,
                    "timeout_s":  timeout,
                },
                headers={"X-Timeout-Cause": "RequestTimeoutMiddleware"},
            )


hardening_router = APIRouter(tags=["hardening"])


@hardening_router.get("/health/detailed")
def health_detailed():
    """Resource-level health: CPU%, memory, disk, uptime, process info.

    Falls back to a minimal payload if psutil isn't available so we
    never break the endpoint in environments without it.
    """
    out: dict = {
        "status": "ok",
        "ts":     time.time(),
        "pid":    os.getpid(),
    }
    try:
        import psutil  # type: ignore
        proc = psutil.Process(os.getpid())
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        with proc.oneshot():
            out["cpu_percent"]   = psutil.cpu_percent(interval=None)
            out["memory_total"]  = mem.total
            out["memory_used"]   = mem.used
            out["memory_pct"]    = mem.percent
            out["disk_total"]    = disk.total
            out["disk_used"]     = disk.used
            out["disk_pct"]      = disk.percent
            out["proc_rss"]      = proc.memory_info().rss
            out["proc_threads"]  = proc.num_threads()
            out["proc_uptime_s"] = time.time() - proc.create_time()
        # Surface a degraded flag the frontend can react to.
        out["degraded"] = (
            out["memory_pct"] > 92.0 or
            out["disk_pct"]   > 95.0 or
            out.get("cpu_percent", 0) > 95.0
        )
    except Exception as e:
        out["psutil_error"] = str(e)[:120]
        out["degraded"] = False
    return out
