"""
hardening middleware — additional safety nets for the FastAPI backend.

  • RequestTimeoutMiddleware — kills any /api/* request running longer
    than DEFAULT_TIMEOUT_S, returning 504 instead of letting the worker
    hang. Configurable per-path via the PATH_TIMEOUTS map.
  • ProcessHealthRouter — adds GET /api/health/detailed with a deliberately
    low-information health payload. Sensitive process details are emitted only
    when HEALTH_DIAGNOSTICS_VERBOSE is explicitly enabled by the deployment.

Wired into server.py via:
    from middleware.hardening import RequestTimeoutMiddleware, hardening_router
    app.add_middleware(RequestTimeoutMiddleware, default_timeout_s=30)
    app.include_router(hardening_router, prefix="/api")
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("api.hardening")

# Per-path overrides (longest-prefix match). Paths NOT listed use the
# middleware-level default_timeout_s. Tune for known slow endpoints.
PATH_TIMEOUTS: dict[str, float] = {
    "/api/binary/build": 120.0,
    "/api/binary/rebuild": 120.0,
    "/api/agents": 60.0,
    "/api/imagine": 90.0,
    "/api/music": 90.0,
    "/api/galaxy/build": 180.0,
    "/api/discourse/deliberate": 180.0,
    "/api/design-spec/compile": 90.0,
    "/api/playable/generate": 180.0,
    "/api/llm-router/complete": 90.0,
    "/api/llm-router/game": 90.0,
}


def _resolve_timeout(path: str, default: float) -> float:
    best_key = ""
    for key in PATH_TIMEOUTS:
        if path.startswith(key) and len(key) > len(best_key):
            best_key = key
    return PATH_TIMEOUTS.get(best_key, default)


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Enforce a hard wall-clock timeout on every /api/* request."""

    def __init__(self, app, default_timeout_s: float = 30.0):
        super().__init__(app)
        self.default = max(0.1, float(default_timeout_s))

    async def dispatch(self, request: Request, call_next: Callable):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        timeout = _resolve_timeout(request.url.path, self.default)
        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            log.warning("request_timeout path=%s timeout_s=%.1f", request.url.path, timeout)
            # Do not reflect endpoint-specific internal timeout configuration to
            # unauthenticated clients; it provides no recovery value.
            return JSONResponse(
                status_code=504,
                content={"detail": "Request timed out"},
                headers={"Cache-Control": "no-store"},
            )


hardening_router = APIRouter(tags=["hardening"])


@hardening_router.get("/health/detailed")
def health_detailed():
    """Resource health with information-minimising defaults.

    By default the endpoint returns only status/degraded and coarse percentage
    metrics. Set HEALTH_DIAGNOSTICS_VERBOSE=true only on deployments where the
    endpoint is protected by an authenticated/internal ingress; verbose mode
    adds PID, process RSS/thread count, uptime, and capacity figures.
    """
    verbose = _env_truthy("HEALTH_DIAGNOSTICS_VERBOSE", False)
    out: dict = {
        "status": "ok",
        "ts": time.time(),
        "degraded": False,
    }
    try:
        import psutil  # type: ignore

        proc = psutil.Process(os.getpid())
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        cpu_pct = psutil.cpu_percent(interval=None)
        out.update(
            {
                "cpu_percent": round(float(cpu_pct), 1),
                "memory_percent": round(float(mem.percent), 1),
                "disk_percent": round(float(disk.percent), 1),
            }
        )
        out["degraded"] = mem.percent > 92.0 or disk.percent > 95.0 or cpu_pct > 95.0

        if verbose:
            with proc.oneshot():
                out.update(
                    {
                        "pid": os.getpid(),
                        "memory_total": mem.total,
                        "memory_used": mem.used,
                        "disk_total": disk.total,
                        "disk_used": disk.used,
                        "process_rss": proc.memory_info().rss,
                        "process_threads": proc.num_threads(),
                        "process_uptime_seconds": round(time.time() - proc.create_time(), 1),
                    }
                )
    except Exception:
        # Health checks should remain available even when optional telemetry is
        # unavailable. Do not echo exception text: paths/module names may leak
        # deployment details.
        out["telemetry_available"] = False

    return JSONResponse(out, headers={"Cache-Control": "no-store"})
