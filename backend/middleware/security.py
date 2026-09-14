"""
security.py — defensive middleware for the FastAPI app.

Provides:
  1. RateLimitMiddleware — bounded per-client+route token bucket
  2. AuditMiddleware     — bounded, sanitized in-memory request audit
  3. SizeLimitMiddleware — streaming request-body cap
  4. safe_relative_path  — strict path traversal protection
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Deque, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

try:
    from .client_identity import client_ip, sanitize_request_id
except ImportError:
    from middleware.client_identity import client_ip, sanitize_request_id


class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client, per-route-prefix token bucket with bounded LRU state."""

    _buckets: OrderedDict[Tuple[str, str], _Bucket] = OrderedDict()
    _lock = asyncio.Lock()
    _rps: float = 2.0
    _burst: int = 120
    _max_buckets: int = 20_000

    def __init__(
        self,
        app,
        rps: float | None = None,
        burst: int | None = None,
        prefix: str = "/api",
    ):
        super().__init__(app)
        try:
            env_rps = float(os.environ.get("CODEDOCK_RATE_LIMIT_RPS", "2"))
        except ValueError:
            env_rps = 2.0
        try:
            env_burst = int(os.environ.get("CODEDOCK_RATE_LIMIT_BURST", "120"))
        except ValueError:
            env_burst = 120
        try:
            env_max = int(os.environ.get("CODEDOCK_RATE_LIMIT_MAX_BUCKETS", "20000"))
        except ValueError:
            env_max = 20_000

        RateLimitMiddleware._rps = min(max(rps or env_rps, 0.01), 100_000.0)
        RateLimitMiddleware._burst = min(max(burst or env_burst, 1), 1_000_000)
        RateLimitMiddleware._max_buckets = min(max(env_max, 100), 1_000_000)
        self.prefix = prefix

    @staticmethod
    def _is_exempt(path: str) -> bool:
        # Health checks are intentionally cheap and commonly called by ingress.
        return path == "/api/health" or path.startswith("/api/health/")

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = client_ip(request)
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(self.prefix) or self._is_exempt(path):
            return await call_next(request)

        now = time.monotonic()
        ip, route = self._key(request)
        async with RateLimitMiddleware._lock:
            key = (ip, route)
            bucket = RateLimitMiddleware._buckets.get(key)
            if bucket is None:
                if len(RateLimitMiddleware._buckets) >= RateLimitMiddleware._max_buckets:
                    RateLimitMiddleware._buckets.popitem(last=False)
                bucket = _Bucket(tokens=float(RateLimitMiddleware._burst), last_refill=now)
                RateLimitMiddleware._buckets[key] = bucket
            else:
                RateLimitMiddleware._buckets.move_to_end(key)

            elapsed = max(0.0, now - bucket.last_refill)
            bucket.tokens = min(
                float(RateLimitMiddleware._burst),
                bucket.tokens + elapsed * RateLimitMiddleware._rps,
            )
            bucket.last_refill = now
            if bucket.tokens < 1.0:
                retry_after = max(
                    1,
                    int((1.0 - bucket.tokens) / max(RateLimitMiddleware._rps, 0.01)),
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": "too many requests",
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.tokens -= 1.0

        return await call_next(request)

    @classmethod
    def snapshot(cls) -> dict:
        """Return limiter health without disclosing client addresses."""
        return {
            "rps": cls._rps,
            "burst": cls._burst,
            "active_buckets": len(cls._buckets),
            "max_buckets": cls._max_buckets,
            "lowest_tokens": [
                {"route": k[1], "tokens_remaining": round(v.tokens, 2)}
                for k, v in sorted(cls._buckets.items(), key=lambda kv: kv[1].tokens)[:20]
            ],
        }


class AuditMiddleware(BaseHTTPMiddleware):
    """Record bounded, sanitized metadata for recent API requests."""

    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        max_entries = min(max(int(max_entries), 100), 50_000)
        if max_entries != AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            AuditMiddleware._buf = deque(AuditMiddleware._buf, maxlen=max_entries)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        start = time.perf_counter()
        ip = client_ip(request)
        ua = request.headers.get("user-agent", "")[:200].replace("\r", " ").replace("\n", " ")
        rid = sanitize_request_id(request.headers.get("x-request-id"))
        try:
            body_size = max(0, int(request.headers.get("content-length", "0") or 0))
        except ValueError:
            body_size = 0
        error = None
        status = 0
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            # Exception messages can contain tokens, paths, SQL fragments, or
            # user data. Keep only the class for operational correlation.
            error = type(exc).__name__
            status = 500
            raise
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            AuditMiddleware._buf.append(
                {
                    "ts": time.time(),
                    "method": request.method,
                    "path": request.url.path[:512],
                    "status": status,
                    "duration_ms": dur_ms,
                    "ip": ip,
                    "ua": ua,
                    "rid": rid,
                    "req_bytes": body_size,
                    "error": error,
                }
            )
        return response

    @classmethod
    def snapshot(cls, limit: int = 200, since_ts: float | None = None) -> dict:
        limit = min(max(int(limit), 1), 1000)
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
        for row in cls._buf:
            statuses[row["status"]] = statuses.get(row["status"], 0) + 1
            methods[row["method"]] = methods.get(row["method"], 0) + 1
            path = row["path"]
            path_counts[path] = path_counts.get(path, 0) + 1
            path_times.setdefault(path, []).append(row["duration_ms"])
            if row["status"] >= 500 or row["error"]:
                errors += 1
            total_ms += row["duration_ms"]
        top_paths = sorted(path_counts.items(), key=lambda kv: -kv[1])[:15]
        slowest = sorted(
            [(p, max(t), sum(t) / len(t)) for p, t in path_times.items()],
            key=lambda x: -x[1],
        )[:10]
        return {
            "total_requests": len(cls._buf),
            "errors": errors,
            "error_rate": round(errors / max(len(cls._buf), 1), 4),
            "avg_ms": round(total_ms / len(cls._buf), 2),
            "statuses": dict(sorted(statuses.items())),
            "methods": methods,
            "top_paths": [{"path": p, "count": c} for p, c in top_paths],
            "slowest": [
                {"path": p, "p_max_ms": round(mx, 1), "p_avg_ms": round(av, 1)}
                for p, mx, av in slowest
            ],
        }


class _BodyTooLarge(Exception):
    pass


class SizeLimitMiddleware:
    """Enforce the body cap from both Content-Length and actual ASGI chunks."""

    def __init__(self, app, max_mb: int | None = None):
        self.app = app
        try:
            configured = int(os.environ.get("CODEDOCK_MAX_BODY_MB", "25"))
        except ValueError:
            configured = 25
        selected = max_mb if max_mb is not None else configured
        self.max_bytes = min(max(int(selected), 1), 1024) * 1024 * 1024

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if not path.startswith("/api") or method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        raw_length = headers.get("content-length")
        if raw_length is not None:
            try:
                declared = int(raw_length)
            except ValueError:
                response = JSONResponse(status_code=400, content={"error": "invalid_content_length"})
                await response(scope, receive, send)
                return
            if declared < 0:
                response = JSONResponse(status_code=400, content={"error": "invalid_content_length"})
                await response(scope, receive, send)
                return
            if declared > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={"error": "payload_too_large", "limit_bytes": self.max_bytes},
                )
                await response(scope, receive, send)
                return

        seen = 0
        response_started = False

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if response_started:
                # The downstream application started a response before fully
                # consuming an oversized body; terminate instead of emitting an
                # invalid second response.
                return
            response = JSONResponse(
                status_code=413,
                content={"error": "payload_too_large", "limit_bytes": self.max_bytes},
            )
            await response(scope, receive, send)


def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """Resolve a strictly relative user path beneath *base*."""
    if not isinstance(candidate, str) or not candidate or "\x00" in candidate:
        raise ValueError("unsafe path")

    normalized = candidate.replace("\\", "/")
    # Reject POSIX absolute paths and Windows drive/UNC forms rather than
    # silently rewriting them as relative input.
    if normalized.startswith("/") or normalized.startswith("//") or re.match(r"^[A-Za-z]:", normalized):
        raise ValueError("unsafe path")

    base_path = Path(base).resolve()
    target = (base_path / normalized).resolve()
    if base_path != target and base_path not in target.parents:
        raise ValueError("unsafe path")
    return target


_audit_mw: AuditMiddleware | None = None
_rate_mw: RateLimitMiddleware | None = None


def register(audit: AuditMiddleware, rate: RateLimitMiddleware) -> None:
    global _audit_mw, _rate_mw
    _audit_mw = audit
    _rate_mw = rate


def get_audit() -> AuditMiddleware | None:
    return _audit_mw


def get_rate() -> RateLimitMiddleware | None:
    return _rate_mw
