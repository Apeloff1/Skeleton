"""Security middleware for the FastAPI application.

The middleware in this module is deliberately fail-closed around client
identity and request sizing. Forwarding headers are accepted only from
configured trusted proxies, rate-limit state is bounded, audit data avoids
raw exception leakage, and body limits are enforced on streamed/chunked
requests rather than trusting Content-Length alone.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.client_ip import resolve_client_ip

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        value = default
    if not math.isfinite(value):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_float(value: object, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not math.isfinite(parsed):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _safe_content_length(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError:
        return -1
    return parsed if parsed >= 0 else -1


def _safe_text(value: str, limit: int) -> str:
    return _CONTROL_CHARS_RE.sub(" ", value)[:limit]


class _Bucket:
    __slots__ = ("tokens", "last_refill", "last_seen")

    def __init__(self, tokens: float, now: float):
        self.tokens = tokens
        self.last_refill = now
        self.last_seen = now


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Bounded token bucket keyed by trusted client IP and route prefix."""

    _buckets: Dict[Tuple[str, str], _Bucket] = {}
    _lock = asyncio.Lock()
    _rps: float = 2.0
    _burst: int = 120
    _max_buckets: int = 20_000
    _bucket_ttl: int = 900
    _last_prune: float = 0.0

    def __init__(
        self,
        app,
        rps: float | None = None,
        burst: int | None = None,
        prefix: str = "/api",
    ):
        super().__init__(app)
        configured_rps = _env_float("CODEDOCK_RATE_LIMIT_RPS", 2.0, minimum=0.01, maximum=10_000.0)
        configured_burst = _env_int("CODEDOCK_RATE_LIMIT_BURST", 120, minimum=1, maximum=100_000)
        RateLimitMiddleware._rps = _bounded_float(
            rps if rps is not None else configured_rps,
            configured_rps,
            minimum=0.01,
            maximum=10_000.0,
        )
        RateLimitMiddleware._burst = max(
            1,
            min(100_000, int(burst) if burst is not None else configured_burst),
        )
        RateLimitMiddleware._max_buckets = _env_int(
            "CODEDOCK_RATE_LIMIT_MAX_BUCKETS", 20_000, minimum=256, maximum=1_000_000
        )
        RateLimitMiddleware._bucket_ttl = _env_int(
            "CODEDOCK_RATE_LIMIT_BUCKET_TTL_SECONDS", 900, minimum=60, maximum=86_400
        )
        self.prefix = prefix
        # Only endpoints that are intentionally safe and extremely cheap are
        # exempt. Security/audit and telemetry ingestion remain rate limited.
        self._whitelist = ("/api/health",)

    @classmethod
    def _prune_locked(cls, now: float) -> None:
        if now - cls._last_prune < 30.0 and len(cls._buckets) < cls._max_buckets:
            return
        cutoff = now - cls._bucket_ttl
        stale = [key for key, bucket in cls._buckets.items() if bucket.last_seen < cutoff]
        for key in stale:
            cls._buckets.pop(key, None)

        if len(cls._buckets) >= cls._max_buckets:
            remove_count = len(cls._buckets) - cls._max_buckets + max(1, cls._max_buckets // 10)
            oldest = sorted(cls._buckets.items(), key=lambda item: item[1].last_seen)[:remove_count]
            for key, _bucket in oldest:
                cls._buckets.pop(key, None)
        cls._last_prune = now

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = resolve_client_ip(request, unknown="unknown")
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(self.prefix) or path in self._whitelist:
            return await call_next(request)

        now = time.monotonic()
        ip, route = self._key(request)
        async with RateLimitMiddleware._lock:
            RateLimitMiddleware._prune_locked(now)
            bucket = RateLimitMiddleware._buckets.get((ip, route))
            if bucket is None:
                bucket = _Bucket(tokens=float(RateLimitMiddleware._burst), now=now)
                RateLimitMiddleware._buckets[(ip, route)] = bucket
            elapsed = max(0.0, now - bucket.last_refill)
            bucket.tokens = min(
                float(RateLimitMiddleware._burst),
                bucket.tokens + elapsed * RateLimitMiddleware._rps,
            )
            bucket.last_refill = now
            bucket.last_seen = now
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
        return {
            "rps": cls._rps,
            "burst": cls._burst,
            "active_buckets": len(cls._buckets),
            "max_buckets": cls._max_buckets,
            "bucket_ttl_seconds": cls._bucket_ttl,
            "top": [
                {"ip": k[0], "route": k[1], "tokens_remaining": round(v.tokens, 2)}
                for k, v in sorted(cls._buckets.items(), key=lambda kv: kv[1].tokens)[:20]
            ],
        }


class AuditMiddleware(BaseHTTPMiddleware):
    """Bounded in-memory audit trail with sanitized metadata."""

    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        max_entries = max(100, min(50_000, int(max_entries)))
        if max_entries > AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            old = list(AuditMiddleware._buf)
            AuditMiddleware._buf = deque(old, maxlen=max_entries)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        start = time.perf_counter()
        ip = resolve_client_ip(request, unknown="unknown")
        ua = _safe_text(request.headers.get("user-agent", ""), 200)
        state_rid = getattr(request.state, "request_id", "")
        rid = _safe_text(str(state_rid), 128) if state_rid else os.urandom(8).hex()
        audit_path = _safe_text(request.url.path, 1024)
        audit_method = _safe_text(request.method, 32)
        parsed_length = _safe_content_length(request.headers.get("content-length"))
        body_size = parsed_length if parsed_length is not None and parsed_length >= 0 else None
        error = None
        status = 0
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            # Store only the exception class. Raw exception messages can contain
            # tokens, paths, query fragments, or other sensitive input.
            error = type(exc).__name__
            status = 500
            raise
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            AuditMiddleware._buf.append(
                {
                    "ts": time.time(),
                    "method": audit_method,
                    "path": audit_path,
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
        limit = max(1, min(1000, int(limit)))
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
                {"path": path, "p_max_ms": round(max_ms, 1), "p_avg_ms": round(avg_ms, 1)}
                for path, max_ms, avg_ms in slowest
            ],
        }


class _BodyTooLarge(Exception):
    pass


class SizeLimitMiddleware:
    """Hard request-body cap that also covers streamed/chunked requests.

    Content-Length is treated only as an early rejection hint. Every ASGI
    ``http.request`` body chunk is counted, so omitting or lying about the
    header cannot bypass the configured limit.
    """

    def __init__(self, app, max_mb: int | None = None):
        self.app = app
        configured = max_mb or _env_int("CODEDOCK_MAX_BODY_MB", 25, minimum=1, maximum=1024)
        self.max_bytes = int(configured) * 1024 * 1024

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if not path.startswith("/api") or method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        try:
            length_text = raw_length.decode("ascii", "strict") if raw_length is not None else None
        except UnicodeDecodeError:
            length_text = "__invalid__"
        parsed_length = _safe_content_length(length_text)
        if parsed_length == -1:
            response = JSONResponse(
                status_code=400,
                content={"error": "invalid_content_length", "detail": "invalid Content-Length header"},
            )
            await response(scope, receive, send)
            return
        if parsed_length is not None and parsed_length > self.max_bytes:
            await self._reject(scope, receive, send, parsed_length)
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

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await self._reject(scope, receive, send, seen)

    async def _reject(self, scope, receive, send, got_bytes: int) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": "payload_too_large",
                "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                "limit_bytes": self.max_bytes,
                "got_bytes": got_bytes,
            },
        )
        await response(scope, receive, send)


def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """Resolve a user-supplied relative path without permitting traversal."""
    base_path = Path(base).resolve()
    normalized = candidate.replace("\\", "/")
    if normalized.startswith("/"):
        normalized = normalized.lstrip("/")
    target = (base_path / normalized).resolve()
    if base_path != target and base_path not in target.parents:
        raise ValueError("path traversal blocked")
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
