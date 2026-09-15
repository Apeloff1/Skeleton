"""
security.py — security middleware for the FastAPI app.

Provides:
  1. RateLimitMiddleware  — bounded per-client/per-route token buckets
  2. AuditMiddleware      — bounded ring buffer of /api requests
  3. SizeLimitMiddleware  — streaming-safe hard cap on inbound API bodies
  4. safe_relative_path() — path-traversal protection helper
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Deque, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from middleware.client_identity import resolve_client_ip


def _is_api_path(path: str, prefix: str = "/api") -> bool:
    """Segment-aware route-tree match; `/apiary` must not match `/api`."""
    normalized = prefix.rstrip("/") or "/"
    return path == normalized or path.startswith(normalized + "/")


# ─────────────────────────────────────────────────────────────────
# Rate limiter — token bucket per (ip, route_prefix)
# ─────────────────────────────────────────────────────────────────
class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Bounded per-client, per-route-prefix token bucket."""

    _buckets: "OrderedDict[Tuple[str, str], _Bucket]" = OrderedDict()
    _lock: asyncio.Lock | None = None
    _rps: float = 2.0
    _burst: int = 120
    _max_buckets: int = 20_000

    def __init__(
        self,
        app,
        rps: float | None = None,
        burst: int | None = None,
        prefix: str = "/api",
        max_buckets: int | None = None,
    ):
        super().__init__(app)
        RateLimitMiddleware._rps = (
            rps if rps is not None else float(os.environ.get("CODEDOCK_RATE_LIMIT_RPS", "2"))
        )
        RateLimitMiddleware._burst = (
            burst if burst is not None else int(os.environ.get("CODEDOCK_RATE_LIMIT_BURST", "120"))
        )
        RateLimitMiddleware._max_buckets = (
            max_buckets
            if max_buckets is not None
            else int(os.environ.get("CODEDOCK_RATE_LIMIT_MAX_BUCKETS", "20000"))
        )
        if RateLimitMiddleware._rps < 0:
            raise ValueError("CODEDOCK_RATE_LIMIT_RPS must be >= 0")
        if RateLimitMiddleware._burst < 1:
            raise ValueError("CODEDOCK_RATE_LIMIT_BURST must be >= 1")
        if RateLimitMiddleware._max_buckets < 1:
            raise ValueError("CODEDOCK_RATE_LIMIT_MAX_BUCKETS must be >= 1")
        self.prefix = prefix.rstrip("/") or "/"
        # Keep only the cheapest liveness endpoint unmetered. Prefix-based
        # exemptions previously made lookalikes and whole security trees free.
        self._whitelist_exact = frozenset({"/api/health"})

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = resolve_client_ip(request)
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not _is_api_path(path, self.prefix) or path in self._whitelist_exact:
            return await call_next(request)

        now = time.monotonic()
        ip, route = self._key(request)
        key = (ip, route)
        async with self._get_lock():
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
                        "detail": f"too many requests on {route}",
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.tokens -= 1.0

        return await call_next(request)

    @classmethod
    def snapshot(cls) -> dict:
        return {
            "rps": cls._rps,
            "burst": cls._burst,
            "active_buckets": len(cls._buckets),
            "max_buckets": cls._max_buckets,
            "top": [
                {"ip": k[0], "route": k[1], "tokens_remaining": round(v.tokens, 2)}
                for k, v in sorted(cls._buckets.items(), key=lambda kv: kv[1].tokens)[:20]
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Audit — bounded ring buffer of every /api request
# ─────────────────────────────────────────────────────────────────
class AuditMiddleware(BaseHTTPMiddleware):
    """Records the last N API requests in a bounded in-memory ring buffer."""

    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if max_entries != AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            old = list(AuditMiddleware._buf)[-max_entries:]
            AuditMiddleware._buf = deque(old, maxlen=max_entries)

    async def dispatch(self, request: Request, call_next):
        if not _is_api_path(request.url.path):
            return await call_next(request)

        start = time.perf_counter()
        ip = resolve_client_ip(request)
        ua = request.headers.get("user-agent", "")[:200]
        rid = request.headers.get("x-request-id") or os.urandom(4).hex()
        raw_size = request.headers.get("content-length", "0") or "0"
        try:
            body_size = max(0, int(raw_size))
        except ValueError:
            body_size = 0
        error = None
        status = 0
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            # Do not persist exception messages: they may contain secrets or user data.
            error = type(exc).__name__
            status = 500
            raise
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            AuditMiddleware._buf.append(
                {
                    "ts": time.time(),
                    "method": request.method,
                    "path": request.url.path,
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
        limit = max(0, min(int(limit), cls._max_entries))
        rows = list(cls._buf)
        if since_ts is not None:
            rows = [r for r in rows if r["ts"] >= since_ts]
        rows = rows[-limit:] if limit else []
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
            [(path, max(times), sum(times) / len(times)) for path, times in path_times.items()],
            key=lambda item: -item[1],
        )[:10]
        return {
            "total_requests": len(cls._buf),
            "errors": errors,
            "error_rate": round(errors / max(len(cls._buf), 1), 4),
            "avg_ms": round(total_ms / len(cls._buf), 2),
            "statuses": dict(sorted(statuses.items())),
            "methods": methods,
            "top_paths": [{"path": path, "count": count} for path, count in top_paths],
            "slowest": [
                {"path": path, "p_max_ms": round(mx, 1), "p_avg_ms": round(avg, 1)}
                for path, mx, avg in slowest
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Body-size cap
# ─────────────────────────────────────────────────────────────────
class SizeLimitMiddleware:
    """Enforce a hard byte cap for API request bodies.

    The old implementation trusted Content-Length, so chunked requests or a lying
    Content-Length could bypass the limit. This ASGI middleware reads at most the
    configured cap, rejects oversized/malformed requests before the application,
    and replays accepted messages downstream.
    """

    def __init__(self, app, max_mb: int | None = None):
        self.app = app
        value = max_mb if max_mb is not None else int(os.environ.get("CODEDOCK_MAX_BODY_MB", "25"))
        if value < 1:
            raise ValueError("CODEDOCK_MAX_BODY_MB must be >= 1")
        self.max_bytes = value * 1024 * 1024

    async def _reject(self, scope, receive, send, status: int, content: dict) -> None:
        response = JSONResponse(status_code=status, content=content)
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not _is_api_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        content_length_values = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if len(content_length_values) > 1:
            await self._reject(
                scope,
                receive,
                send,
                400,
                {"error": "invalid_content_length", "detail": "multiple Content-Length headers"},
            )
            return
        if content_length_values:
            try:
                declared = int(content_length_values[0].decode("ascii"))
                if declared < 0:
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                await self._reject(
                    scope,
                    receive,
                    send,
                    400,
                    {"error": "invalid_content_length", "detail": "Content-Length must be a non-negative integer"},
                )
                return
            if declared > self.max_bytes:
                await self._reject(
                    scope,
                    receive,
                    send,
                    413,
                    {
                        "error": "payload_too_large",
                        "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                        "limit_bytes": self.max_bytes,
                        "got_bytes": declared,
                    },
                )
                return

        messages = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") != "http.request":
                continue
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await self._reject(
                    scope,
                    receive,
                    send,
                    413,
                    {
                        "error": "payload_too_large",
                        "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                        "limit_bytes": self.max_bytes,
                        "got_bytes": total,
                    },
                )
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive():
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


# ─────────────────────────────────────────────────────────────────
# Path traversal helper
# ─────────────────────────────────────────────────────────────────
def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """Resolve candidate below base, raising ValueError if it escapes."""
    base = Path(base).resolve()
    candidate = candidate.replace("\\", "/")
    if candidate.startswith("/"):
        candidate = candidate.lstrip("/")
    target = (base / candidate).resolve()
    if base != target and base not in target.parents:
        raise ValueError(f"path traversal blocked: {candidate}")
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
