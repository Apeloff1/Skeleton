"""
security.py — defensive middleware for the FastAPI app.

Provides:
  1. RateLimitMiddleware — bounded per-client+route token bucket
  2. AuditMiddleware     — bounded, sanitized in-memory request audit
  3. SizeLimitMiddleware — streaming request-body and framing enforcement
  4. safe_relative_path  — strict path traversal protection

The core middleware is imported unconditionally by server.py, so AuditMiddleware
also installs a minimum browser-security header baseline. This means optional
observability/reliability imports cannot accidentally leave the service without
basic response hardening.
"""
from __future__ import annotations

import os
import re
import time
from collections import OrderedDict, deque
from pathlib import Path
from threading import Lock
from typing import Deque, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

try:
    from .client_identity import client_ip, sanitize_request_id
except ImportError:
    from middleware.client_identity import client_ip, sanitize_request_id


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client, per-route-prefix token bucket with bounded LRU state.

    The critical section contains no await points, so a process-local threading
    lock is safer than an asyncio lock created at import time: it cannot bind to
    the wrong event loop when uvicorn/gunicorn workers create fresh loops.
    """

    _buckets: OrderedDict[Tuple[str, str], _Bucket] = OrderedDict()
    _lock = Lock()
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

        selected_rps = env_rps if rps is None else float(rps)
        selected_burst = env_burst if burst is None else int(burst)
        RateLimitMiddleware._rps = min(max(selected_rps, 0.01), 100_000.0)
        RateLimitMiddleware._burst = min(max(selected_burst, 1), 1_000_000)
        RateLimitMiddleware._max_buckets = min(max(env_max, 100), 1_000_000)
        self.prefix = prefix

    @staticmethod
    def _is_exempt(path: str) -> bool:
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
        with RateLimitMiddleware._lock:
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
        with cls._lock:
            lowest = [
                {"route": key[1], "tokens_remaining": round(bucket.tokens, 2)}
                for key, bucket in sorted(cls._buckets.items(), key=lambda kv: kv[1].tokens)[:20]
            ]
            active = len(cls._buckets)
        return {
            "rps": cls._rps,
            "burst": cls._burst,
            "active_buckets": active,
            "max_buckets": cls._max_buckets,
            "lowest_tokens": lowest,
        }


class AuditMiddleware(BaseHTTPMiddleware):
    """Record bounded request metadata and enforce baseline response headers."""

    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        max_entries = min(max(int(max_entries), 100), 50_000)
        if max_entries != AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            AuditMiddleware._buf = deque(AuditMiddleware._buf, maxlen=max_entries)

    @staticmethod
    def _apply_security_headers(request: Request, response: Response) -> None:
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=(), usb=()")
        headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.scheme == "https" or _env_truthy("FORCE_HSTS"):
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        path = request.url.path
        embeddable = path.startswith("/api/playable/") and path.endswith("/raw")
        if embeddable:
            headers.setdefault(
                "Content-Security-Policy",
                "sandbox allow-scripts; default-src 'self' data: blob:; "
                "img-src 'self' data: blob:; media-src 'self' data: blob:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' blob:; "
                "connect-src 'self'",
            )
        else:
            headers.setdefault("X-Frame-Options", "DENY")

        if path.startswith(("/api/auth", "/api/security", "/api/admin", "/api/_telemetry", "/api/metrics")):
            headers.setdefault("Cache-Control", "no-store, max-age=0")
            headers.setdefault("Pragma", "no-cache")

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            response = await call_next(request)
            self._apply_security_headers(request, response)
            return response

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
            self._apply_security_headers(request, response)
        except Exception as exc:
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
    def snapshot(
        cls,
        limit: int = 200,
        since_ts: float | None = None,
        *,
        include_sensitive: bool = False,
    ) -> dict:
        """Return audit rows; client IP/User-Agent are redacted by default."""
        limit = min(max(int(limit), 1), 1000)
        rows = list(cls._buf)
        if since_ts:
            rows = [row for row in rows if row["ts"] >= since_ts]
        rows = rows[-limit:]
        if not include_sensitive:
            rows = [
                {key: value for key, value in row.items() if key not in {"ip", "ua"}}
                for row in rows
            ]
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


class _TooManyBodyChunks(Exception):
    pass


class SizeLimitMiddleware:
    """Enforce framing sanity and body caps from declared and streamed data.

    Duplicate Content-Length and Content-Length+Transfer-Encoding are rejected
    before application code runs. Those combinations are common HTTP request
    smuggling primitives because intermediaries can disagree about which length
    wins. Actual ASGI body bytes are always counted as a second line of defense.
    """

    def __init__(self, app, max_mb: int | None = None):
        self.app = app
        try:
            configured = int(os.environ.get("CODEDOCK_MAX_BODY_MB", "25"))
        except ValueError:
            configured = 25
        try:
            configured_chunks = int(os.environ.get("CODEDOCK_MAX_BODY_CHUNKS", "8192"))
        except ValueError:
            configured_chunks = 8192
        selected = max_mb if max_mb is not None else configured
        self.max_bytes = min(max(int(selected), 1), 1024) * 1024 * 1024
        self.max_chunks = min(max(configured_chunks, 32), 100_000)

    @staticmethod
    def _reject(status_code: int, error: str, **extra):
        return JSONResponse(status_code=status_code, content={"error": error, **extra})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if not path.startswith("/api") or method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        content_lengths: list[str] = []
        transfer_encodings: list[str] = []
        for raw_key, raw_value in scope.get("headers", []):
            key = bytes(raw_key).lower()
            if key == b"content-length":
                content_lengths.append(bytes(raw_value).decode("latin-1").strip())
            elif key == b"transfer-encoding":
                transfer_encodings.append(bytes(raw_value).decode("latin-1").strip())

        if len(content_lengths) > 1:
            response = self._reject(400, "ambiguous_body_framing")
            await response(scope, receive, send)
            return
        if content_lengths and transfer_encodings:
            response = self._reject(400, "ambiguous_body_framing")
            await response(scope, receive, send)
            return

        declared: int | None = None
        if content_lengths:
            raw_length = content_lengths[0]
            if not re.fullmatch(r"[0-9]+", raw_length):
                response = self._reject(400, "invalid_content_length")
                await response(scope, receive, send)
                return
            try:
                declared = int(raw_length, 10)
            except (TypeError, ValueError, OverflowError):
                response = self._reject(400, "invalid_content_length")
                await response(scope, receive, send)
                return
            if declared > self.max_bytes:
                response = self._reject(413, "payload_too_large", limit_bytes=self.max_bytes)
                await response(scope, receive, send)
                return

        seen = 0
        chunks = 0
        response_started = False

        async def limited_receive():
            nonlocal seen, chunks
            message = await receive()
            if message.get("type") == "http.request":
                chunks += 1
                if chunks > self.max_chunks:
                    raise _TooManyBodyChunks
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLarge
                if declared is not None and seen > declared:
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
                return
            response = self._reject(413, "payload_too_large", limit_bytes=self.max_bytes)
            await response(scope, receive, send)
        except _TooManyBodyChunks:
            if response_started:
                return
            response = self._reject(413, "too_many_body_chunks", max_chunks=self.max_chunks)
            await response(scope, receive, send)


def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """Resolve a strictly relative user path beneath *base*."""
    if not isinstance(candidate, str) or not candidate or "\x00" in candidate:
        raise ValueError("unsafe path")

    normalized = candidate.replace("\\", "/")
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
