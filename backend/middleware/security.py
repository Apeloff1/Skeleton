"""
security.py — Lightweight security middleware for the FastAPI app.

Provides independent edge controls wired by server.py:

  1. RateLimitMiddleware       — bounded per-client+route token buckets
  2. AuditMiddleware           — bounded ring buffer of /api request metadata
  3. SizeLimitMiddleware       — hard cap on declared and streamed body bytes
  4. safe_relative_path()      — path-traversal protection helper

Proxy-provided client identity is trusted only when the immediate peer is in
``CODEDOCK_TRUSTED_PROXY_CIDRS``. Forwarding chains are parsed right-to-left
and malformed chains fail closed to the immediate peer.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from collections import OrderedDict, deque
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Deque, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def _matches_path_prefix(path: str, prefix: str) -> bool:
    """Match one route or a true child route, never a string lookalike."""
    current = path or "/"
    expected = (prefix or "").rstrip("/") or "/"
    if expected == "/":
        return current == "/"
    return current == expected or current.startswith(expected + "/")


def _trusted_proxy_networks():
    """Return configured proxy networks; any malformed entry disables trust."""
    raw = os.environ.get("CODEDOCK_TRUSTED_PROXY_CIDRS", "")
    networks = []
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ip_network(value, strict=False))
        except ValueError:
            return ()
    return tuple(networks)


def _request_client_ip(request: Request) -> str:
    """Resolve the nearest untrusted client hop behind explicitly trusted proxies."""
    peer = request.client.host if request.client else "unknown"
    networks = _trusted_proxy_networks()
    if not networks:
        return peer

    try:
        peer_addr = ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_addr in network for network in networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    values = [value.strip() for value in forwarded.split(",") if value.strip()]
    if not values:
        return peer

    parsed = []
    for value in values:
        try:
            parsed.append(ip_address(value))
        except ValueError:
            return peer

    for address in reversed(parsed):
        if not any(address in network for network in networks):
            return str(address)
    return peer


def _safe_content_length(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _safe_request_id(raw: str | None) -> str:
    if raw and _REQUEST_ID_RE.fullmatch(raw):
        return raw
    return os.urandom(8).hex()


# ─────────────────────────────────────────────────────────────────
# Rate limiter — token bucket per (client, route_prefix)
# ─────────────────────────────────────────────────────────────────
class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client, per-route token bucket with bounded process memory."""

    _buckets: "OrderedDict[Tuple[str, str], _Bucket]" = OrderedDict()
    _lock = asyncio.Lock()
    _rps: float = 2.0
    _burst: int = 120
    _max_buckets: int = 10_000

    def __init__(
        self,
        app,
        rps: float | None = None,
        burst: int | None = None,
        prefix: str = "/api",
        max_buckets: int | None = None,
    ):
        super().__init__(app)
        configured_rps = rps if rps is not None else float(
            os.environ.get("CODEDOCK_RATE_LIMIT_RPS", "2")
        )
        configured_burst = burst if burst is not None else int(
            os.environ.get("CODEDOCK_RATE_LIMIT_BURST", "120")
        )
        configured_max = max_buckets if max_buckets is not None else int(
            os.environ.get("CODEDOCK_RATE_LIMIT_MAX_BUCKETS", "10000")
        )
        if configured_rps <= 0:
            raise ValueError("rate limit rps must be positive")
        if configured_burst <= 0:
            raise ValueError("rate limit burst must be positive")
        if configured_max <= 0:
            raise ValueError("rate limit bucket cap must be positive")

        RateLimitMiddleware._rps = float(configured_rps)
        RateLimitMiddleware._burst = int(configured_burst)
        RateLimitMiddleware._max_buckets = int(configured_max)
        self.prefix = prefix
        self._whitelist = (
            "/api/health",
            "/api/binary/download",
            "/api/binary/inspect",
            "/api/binary/toolchain",
            "/api/binary/list",
            "/api/security",
            "/api/telemetry/event",
            "/api/telemetry/batch",
        )

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = _request_client_ip(request)
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    @classmethod
    def _evict_oldest_bucket(cls) -> None:
        if cls._buckets:
            cls._buckets.popitem(last=False)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not _matches_path_prefix(path, self.prefix):
            return await call_next(request)
        if any(_matches_path_prefix(path, allowed) for allowed in self._whitelist):
            return await call_next(request)

        now = time.monotonic()
        ip, route = self._key(request)
        key = (ip, route)
        async with RateLimitMiddleware._lock:
            bucket = RateLimitMiddleware._buckets.get(key)
            if bucket is None:
                if len(RateLimitMiddleware._buckets) >= RateLimitMiddleware._max_buckets:
                    RateLimitMiddleware._evict_oldest_bucket()
                bucket = _Bucket(
                    tokens=float(RateLimitMiddleware._burst),
                    last_refill=now,
                )
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
            "max_buckets": cls._max_buckets,
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
    """Records the last N API requests in a bounded in-memory ring buffer."""

    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        if max_entries <= 0:
            raise ValueError("audit buffer size must be positive")
        if max_entries > AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            old = list(AuditMiddleware._buf)
            AuditMiddleware._buf = deque(old, maxlen=max_entries)

    async def dispatch(self, request: Request, call_next):
        if not _matches_path_prefix(request.url.path, "/api"):
            return await call_next(request)

        start = time.perf_counter()
        ip = _request_client_ip(request)
        ua = request.headers.get("user-agent", "")[:200]
        rid = _safe_request_id(request.headers.get("x-request-id"))
        body_size = _safe_content_length(request.headers.get("content-length"))
        error = None
        status = 0
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            error = type(exc).__name__
            status = 500
            raise
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            AuditMiddleware._buf.append({
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
            key=lambda item: -item[1],
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


# ─────────────────────────────────────────────────────────────────
# Body-size cap
# ─────────────────────────────────────────────────────────────────
class SizeLimitMiddleware:
    """Enforce the body limit before application code can observe the request."""

    def __init__(self, app, max_mb: int | None = None):
        self.app = app
        configured_mb = max_mb if max_mb is not None else int(
            os.environ.get("CODEDOCK_MAX_BODY_MB", "25")
        )
        if configured_mb <= 0:
            raise ValueError("maximum body size must be positive")
        self.max_bytes = int(configured_mb) * 1024 * 1024

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        method = str(scope.get("method") or "GET").upper()
        if not _matches_path_prefix(path, "/api") or method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        raw_headers = list(scope.get("headers") or [])
        content_lengths = [
            value.decode("latin-1").strip()
            for key, value in raw_headers
            if key.lower() == b"content-length"
        ]
        transfer_encodings = [
            value.decode("latin-1").strip()
            for key, value in raw_headers
            if key.lower() == b"transfer-encoding"
        ]

        if len(content_lengths) > 1 or (content_lengths and transfer_encodings):
            response = JSONResponse(
                status_code=400,
                content={"error": "invalid_request_framing"},
            )
            await response(scope, receive, send)
            return

        if content_lengths:
            raw_declared = content_lengths[0]
            if not raw_declared.isascii() or not raw_declared.isdigit():
                response = JSONResponse(
                    status_code=400,
                    content={"error": "invalid_content_length"},
                )
                await response(scope, receive, send)
                return
            declared = int(raw_declared, 10)
            if declared > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": "payload_too_large",
                        "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                        "limit_bytes": self.max_bytes,
                        "got_bytes": declared,
                    },
                )
                await response(scope, receive, send)
                return

        buffered: list[dict] = []
        seen = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            buffered.append(message)
            if message.get("type") != "http.request":
                continue
            seen += len(message.get("body") or b"")
            if seen > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": "payload_too_large",
                        "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                        "limit_bytes": self.max_bytes,
                        "got_bytes": seen,
                    },
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive():
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


# ─────────────────────────────────────────────────────────────────
# Path traversal helper
# ─────────────────────────────────────────────────────────────────
def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """Resolve a user-relative path beneath ``base`` or raise ``ValueError``."""
    base_path = Path(base).resolve()
    candidate = candidate.replace("\\", "/")
    if candidate.startswith("/"):
        candidate = candidate.lstrip("/")
    target = (base_path / candidate).resolve()
    if base_path != target and base_path not in target.parents:
        raise ValueError(f"path traversal blocked: {candidate}")
    return target


# Singletons exposed so server.py and the telemetry router can reach them.
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
