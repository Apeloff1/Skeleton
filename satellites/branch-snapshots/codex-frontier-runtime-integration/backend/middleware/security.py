"""
security.py — Lightweight security middleware for the FastAPI app.

Provides three independent layers, each is opt-in via wire-up in server.py:

  1. RateLimitMiddleware       — Per-IP+route token bucket (in-memory)
  2. AuditMiddleware           — Bounded ring buffer of every /api/* request
  3. SizeLimitMiddleware       — Hard cap on inbound request body
  4. safe_relative_path()      — Path-traversal protection helper

The audit buffer is also exposed via /api/security/audit (see telemetry router).
None of these layers persist data outside RAM — they're zero-overhead at idle.
"""
from __future__ import annotations
import os
import time
import asyncio
from collections import deque
from typing import Deque, Dict, Tuple
from pathlib import Path

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ─────────────────────────────────────────────────────────────────
# Rate limiter — token bucket per (ip, route_prefix)
# ─────────────────────────────────────────────────────────────────
class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP, per-route-prefix token bucket. State is module-level so all
    middleware instances share it (FastAPI may construct multiple)."""

    # Shared across all instances (module-level singletons)
    _buckets: Dict[Tuple[str, str], _Bucket] = {}
    _lock = asyncio.Lock()
    _rps: float = 2.0
    _burst: int = 120

    def __init__(
        self,
        app,
        rps: float | None = None,
        burst: int | None = None,
        prefix: str = "/api",
    ):
        super().__init__(app)
        RateLimitMiddleware._rps = rps or float(os.environ.get("CODEDOCK_RATE_LIMIT_RPS", "2"))
        RateLimitMiddleware._burst = burst or int(os.environ.get("CODEDOCK_RATE_LIMIT_BURST", "120"))
        self.prefix = prefix
        self._whitelist = (
            "/api/health",
            "/api/binary/download",
            "/api/binary/inspect",         # cheap GET, called by inspector UI
            "/api/binary/toolchain",       # cheap GET
            "/api/binary/list",            # cheap GET
            "/api/security/",              # security endpoints exempt
            "/api/telemetry/event",        # ingest endpoint exempt (batched)
            "/api/telemetry/batch",
        )

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip:
            ip = request.client.host if request.client else "unknown"
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(self.prefix) or any(path.startswith(w) for w in self._whitelist):
            return await call_next(request)

        now = time.time()
        ip, route = self._key(request)
        async with RateLimitMiddleware._lock:
            bucket = RateLimitMiddleware._buckets.get((ip, route))
            if bucket is None:
                bucket = _Bucket(tokens=float(RateLimitMiddleware._burst), last_refill=now)
                RateLimitMiddleware._buckets[(ip, route)] = bucket
            elapsed = now - bucket.last_refill
            bucket.tokens = min(float(RateLimitMiddleware._burst), bucket.tokens + elapsed * RateLimitMiddleware._rps)
            bucket.last_refill = now
            if bucket.tokens < 1.0:
                retry_after = max(1, int((1.0 - bucket.tokens) / max(RateLimitMiddleware._rps, 0.01)))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": f"too many requests on {route}",
                        "retry_after_seconds": retry_after,
                        "burst": RateLimitMiddleware._burst,
                        "rps": RateLimitMiddleware._rps,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.tokens -= 1.0

        return await call_next(request)

    @classmethod
    def snapshot(cls) -> dict:
        """Read-only view of current bucket state."""
        return {
            "rps": cls._rps,
            "burst": cls._burst,
            "active_buckets": len(cls._buckets),
            "top": [
                {"ip": k[0], "route": k[1], "tokens_remaining": round(v.tokens, 2)}
                for k, v in sorted(cls._buckets.items(), key=lambda kv: kv[1].tokens)[:20]
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Audit — bounded ring buffer of every /api/* request
# ─────────────────────────────────────────────────────────────────
class AuditMiddleware(BaseHTTPMiddleware):
    """Records the last N /api/* requests in a ring buffer (module-level
    shared state so all middleware instances contribute to the same log)."""

    # Module-level shared buffer
    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        if max_entries > AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            # Replace deque preserving existing entries
            old = list(AuditMiddleware._buf)
            AuditMiddleware._buf = deque(old, maxlen=max_entries)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        start = time.perf_counter()
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )
        ua = request.headers.get("user-agent", "")[:200]
        rid = request.headers.get("x-request-id") or os.urandom(4).hex()
        body_size = int(request.headers.get("content-length", "0") or 0)
        error = None
        status = 0
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            status = 500
            raise
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            AuditMiddleware._buf.append({
                "ts":          time.time(),
                "method":      request.method,
                "path":        request.url.path,
                "status":      status,
                "duration_ms": dur_ms,
                "ip":          ip,
                "ua":          ua,
                "rid":         rid,
                "req_bytes":   body_size,
                "error":       error,
            })
        return response

    @classmethod
    def snapshot(cls, limit: int = 200, since_ts: float | None = None) -> dict:
        rows = list(cls._buf)
        if since_ts:
            rows = [r for r in rows if r["ts"] >= since_ts]
        rows = rows[-limit:]
        return {
            "count": len(rows),
            "buffer_capacity": cls._max_entries,
            "buffer_size_now": len(cls._buf),
            "entries": rows,
        }

    @classmethod
    def summary(cls) -> dict:
        if not cls._buf:
            return {"empty": True}
        statuses: Dict[int, int] = {}
        methods: Dict[str, int] = {}
        path_counts: Dict[str, int] = {}
        path_times: Dict[str, list] = {}
        errors = 0
        total_ms = 0.0
        for r in cls._buf:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            methods[r["method"]] = methods.get(r["method"], 0) + 1
            p = r["path"]
            path_counts[p] = path_counts.get(p, 0) + 1
            path_times.setdefault(p, []).append(r["duration_ms"])
            if r["status"] >= 500 or r["error"]:
                errors += 1
            total_ms += r["duration_ms"]
        top_paths = sorted(path_counts.items(), key=lambda kv: -kv[1])[:15]
        slowest = sorted(
            [(p, max(t), sum(t) / len(t)) for p, t in path_times.items()],
            key=lambda x: -x[1],
        )[:10]
        return {
            "total_requests": len(cls._buf),
            "errors":         errors,
            "error_rate":     round(errors / max(len(cls._buf), 1), 4),
            "avg_ms":         round(total_ms / len(cls._buf), 2),
            "statuses":       dict(sorted(statuses.items())),
            "methods":        methods,
            "top_paths":      [{"path": p, "count": c} for p, c in top_paths],
            "slowest":        [
                {"path": p, "p_max_ms": round(mx, 1), "p_avg_ms": round(av, 1)}
                for p, mx, av in slowest
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Body-size cap
# ─────────────────────────────────────────────────────────────────
class SizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject any /api/* request whose Content-Length exceeds the cap.
    Defaults to 25 MB (covers chunked file uploads). Configurable via env
    CODEDOCK_MAX_BODY_MB."""

    def __init__(self, app, max_mb: int | None = None):
        super().__init__(app)
        self.max_bytes = (max_mb or int(os.environ.get("CODEDOCK_MAX_BODY_MB", "25"))) * 1024 * 1024

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api") and request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl and int(cl) > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "payload_too_large",
                        "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                        "limit_bytes": self.max_bytes,
                        "got_bytes":   int(cl),
                    },
                )
        return await call_next(request)


# ─────────────────────────────────────────────────────────────────
# Path traversal helper
# ─────────────────────────────────────────────────────────────────
def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """
    Resolve `candidate` (a user-supplied filename / relative path) against
    `base`, raising ValueError if the result escapes `base`. Use this
    anywhere a path-like value comes from JSON / query params.

        safe_relative_path("/app/uploads", request_json["filename"])
    """
    base = Path(base).resolve()
    candidate = candidate.replace("\\", "/")
    if candidate.startswith("/"):
        candidate = candidate.lstrip("/")
    target = (base / candidate).resolve()
    if base != target and base not in target.parents:
        raise ValueError(f"path traversal blocked: {candidate}")
    return target


# Singletons exposed so server.py and the telemetry router can reach them.
_audit_mw: AuditMiddleware | None = None
_rate_mw:  RateLimitMiddleware | None = None


def register(audit: AuditMiddleware, rate: RateLimitMiddleware) -> None:
    global _audit_mw, _rate_mw
    _audit_mw = audit
    _rate_mw = rate


def get_audit() -> AuditMiddleware | None:
    return _audit_mw


def get_rate() -> RateLimitMiddleware | None:
    return _rate_mw
