"""
security.py — Lightweight security middleware for the FastAPI app.

Provides three independent layers, each is opt-in via wire-up in server.py:

  1. RateLimitMiddleware       — bounded per-IP+route token bucket
  2. AuditMiddleware           — bounded ring buffer of every /api/* request
  3. SizeLimitMiddleware       — hard cap on inbound request body
  4. safe_relative_path()      — path-traversal protection helper

The audit buffer is also exposed via /api/security/audit (see telemetry router).
None of these layers persist data outside RAM — they're zero-overhead at idle.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
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

log = logging.getLogger("middleware.security")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_MAX_XFF_HOPS = 32
_MAX_XFF_CHARS = 2048


def _matches_route_boundary(path: str, route: str) -> bool:
    """Match one exact route or a real child route, never a prefix lookalike."""
    normalized = route.rstrip("/") or "/"
    if normalized == "/":
        return path.startswith("/")
    return path == normalized or path.startswith(normalized + "/")


def _matches_api_boundary(path: str) -> bool:
    """Match /api itself or a true child route, never /apiary-style lookalikes."""
    return _matches_route_boundary(path, "/api")


def _canonical_ip(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1].strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _parse_trusted_proxy_networks(
    raw: str,
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parse proxy CIDRs fail-closed: one malformed entry disables XFF trust."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            log.error(
                "invalid CODEDOCK_TRUSTED_PROXY_CIDRS configuration; disabling proxy trust"
            )
            return ()
    return tuple(networks)


def _trusted_proxy_networks() -> tuple[
    ipaddress.IPv4Network | ipaddress.IPv6Network, ...
]:
    return _parse_trusted_proxy_networks(
        os.environ.get(
            "CODEDOCK_TRUSTED_PROXY_CIDRS",
            os.environ.get("TRUSTED_PROXY_CIDRS", ""),
        )
    )


def _is_trusted_proxy(
    value: str,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    canonical = _canonical_ip(value)
    if canonical is None:
        return False
    address = ipaddress.ip_address(canonical)
    return any(address in network for network in networks)


def _client_ip(
    request: Request,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] | None = None,
) -> str:
    """Resolve client identity without trusting attacker-controlled XFF.

    The direct peer is authoritative unless it is explicitly configured as a
    trusted proxy. Trusted proxy chains are walked right-to-left; duplicate,
    empty, malformed, oversized, overlong, or entirely trusted chains fail
    closed to the direct peer.
    """
    networks = _trusted_proxy_networks() if networks is None else networks
    peer = (
        request.client.host.strip()
        if request.client is not None and request.client.host
        else "unknown"
    )
    canonical_peer = _canonical_ip(peer)
    peer_identity = canonical_peer or peer

    if not _is_trusted_proxy(peer, networks):
        return peer_identity

    forwarded_values = request.headers.getlist("x-forwarded-for")
    if len(forwarded_values) != 1:
        return peer_identity

    forwarded_value = forwarded_values[0]
    if len(forwarded_value) > _MAX_XFF_CHARS:
        return peer_identity
    parts = forwarded_value.split(",")
    if not parts or len(parts) > _MAX_XFF_HOPS or any(not part.strip() for part in parts):
        return peer_identity

    forwarded = [_canonical_ip(part) for part in parts]
    if any(value is None for value in forwarded):
        return peer_identity

    for value in reversed(forwarded):
        assert value is not None
        if not _is_trusted_proxy(value, networks):
            return value

    return peer_identity


def _safe_request_id(request: Request) -> str:
    values = request.headers.getlist("x-request-id")
    if len(values) == 1 and _REQUEST_ID_RE.fullmatch(values[0] or ""):
        return values[0]
    state_id = getattr(request.state, "request_id", None)
    if isinstance(state_id, str) and _REQUEST_ID_RE.fullmatch(state_id):
        return state_id
    return os.urandom(8).hex()


def _bounded_text(value: object, limit: int) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")[:limit]


# ─────────────────────────────────────────────────────────────────
# Rate limiter — bounded token bucket per (ip, route_prefix)
# ─────────────────────────────────────────────────────────────────
class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Bounded per-IP, per-route-prefix token bucket.

    New identities fail closed at capacity rather than evicting active buckets
    and receiving a fresh burst. State mutation is serialized per process.
    """

    _buckets: Dict[Tuple[str, str], _Bucket] = {}
    _lock: asyncio.Lock | None = None
    _rps: float = 2.0
    _burst: int = 120
    _max_buckets: int = 4096
    _bucket_ttl: float = 300.0
    _saturation_rejections: int = 0
    _expired_pruned: int = 0

    def __init__(
        self,
        app,
        rps: float | None = None,
        burst: int | None = None,
        prefix: str = "/api",
        max_buckets: int | None = None,
        bucket_ttl: float | None = None,
    ):
        super().__init__(app)
        configured_rps = (
            rps
            if rps is not None
            else float(os.environ.get("CODEDOCK_RATE_LIMIT_RPS", "2"))
        )
        configured_burst = (
            burst
            if burst is not None
            else int(os.environ.get("CODEDOCK_RATE_LIMIT_BURST", "120"))
        )
        configured_max = (
            max_buckets
            if max_buckets is not None
            else int(os.environ.get("CODEDOCK_RATE_LIMIT_MAX_BUCKETS", "4096"))
        )
        configured_ttl = (
            bucket_ttl
            if bucket_ttl is not None
            else float(os.environ.get("CODEDOCK_RATE_LIMIT_BUCKET_TTL", "300"))
        )

        if not math.isfinite(configured_rps) or configured_rps <= 0:
            raise ValueError("rate-limit rps must be finite and positive")
        if configured_burst <= 0:
            raise ValueError("rate-limit burst must be positive")
        if configured_max <= 0:
            raise ValueError("rate-limit max_buckets must be positive")
        if not math.isfinite(configured_ttl) or configured_ttl <= 0:
            raise ValueError("rate-limit bucket_ttl must be finite and positive")

        RateLimitMiddleware._rps = float(configured_rps)
        RateLimitMiddleware._burst = int(configured_burst)
        RateLimitMiddleware._max_buckets = int(configured_max)
        RateLimitMiddleware._bucket_ttl = float(configured_ttl)
        self.prefix = prefix.rstrip("/") or "/"
        self._trusted_proxy_networks = _trusted_proxy_networks()
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

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    def _prune_expired(cls, now: float) -> int:
        expired = [
            key
            for key, bucket in cls._buckets.items()
            if now - bucket.last_refill >= cls._bucket_ttl
        ]
        for key in expired:
            del cls._buckets[key]
        cls._expired_pruned += len(expired)
        return len(expired)

    @classmethod
    def _retry_until_capacity(cls, now: float) -> int:
        if not cls._buckets:
            return 1
        seconds = min(
            max(0.0, cls._bucket_ttl - (now - bucket.last_refill))
            for bucket in cls._buckets.values()
        )
        return min(3600, max(1, math.ceil(seconds)))

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = _client_ip(request, self._trusted_proxy_networks)
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not _matches_route_boundary(path, self.prefix) or any(
            _matches_route_boundary(path, route) for route in self._whitelist
        ):
            return await call_next(request)

        now = time.monotonic()
        ip, route = self._key(request)
        key = (ip, route)

        async with self._get_lock():
            self._prune_expired(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_buckets:
                    type(self)._saturation_rejections += 1
                    retry_after = self._retry_until_capacity(now)
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "rate_limited",
                            "detail": "rate-limit identity capacity exhausted",
                            "retry_after_seconds": retry_after,
                            "burst": self._burst,
                            "rps": self._rps,
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
                bucket = _Bucket(tokens=float(self._burst), last_refill=now)
                self._buckets[key] = bucket

            elapsed = max(0.0, now - bucket.last_refill)
            bucket.tokens = min(
                float(self._burst), bucket.tokens + elapsed * self._rps
            )
            bucket.last_refill = now
            if bucket.tokens < 1.0:
                retry_after = min(
                    3600,
                    max(1, math.ceil((1.0 - bucket.tokens) / self._rps)),
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": f"too many requests on {route}",
                        "retry_after_seconds": retry_after,
                        "burst": self._burst,
                        "rps": self._rps,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.tokens -= 1.0

        return await call_next(request)

    @classmethod
    def snapshot(cls) -> dict:
        """Read-only view of bounded rate-limit state."""
        return {
            "rps": cls._rps,
            "burst": cls._burst,
            "active_buckets": len(cls._buckets),
            "max_buckets": cls._max_buckets,
            "bucket_ttl_seconds": cls._bucket_ttl,
            "expired_pruned": cls._expired_pruned,
            "saturation_rejections": cls._saturation_rejections,
            "top": [
                {
                    "ip": key[0],
                    "route": key[1],
                    "tokens_remaining": round(bucket.tokens, 2),
                }
                for key, bucket in sorted(
                    cls._buckets.items(), key=lambda item: item[1].tokens
                )[:20]
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Audit — bounded ring buffer of every true /api request
# ─────────────────────────────────────────────────────────────────
class AuditMiddleware(BaseHTTPMiddleware):
    """Records a bounded, sanitized audit trail for true /api requests."""

    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        if max_entries <= 0:
            raise ValueError("audit max_entries must be positive")
        self._trusted_proxy_networks = _trusted_proxy_networks()
        if max_entries > AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            AuditMiddleware._buf = deque(
                list(AuditMiddleware._buf), maxlen=max_entries
            )

    @staticmethod
    def _declared_size(request: Request) -> int | None:
        values = request.headers.getlist("content-length")
        if not values:
            return 0
        if len(values) != 1:
            return None
        raw = values[0].strip(" \t")
        if not raw.isascii() or not raw.isdigit() or len(raw) > 64:
            return None
        normalized = raw.lstrip("0") or "0"
        if len(normalized) > 20:
            return None
        try:
            return int(normalized, 10)
        except ValueError:
            return None

    async def dispatch(self, request: Request, call_next):
        if not _matches_api_boundary(request.url.path):
            return await call_next(request)

        start = time.perf_counter()
        ip = _client_ip(request, self._trusted_proxy_networks)
        ua = _bounded_text(request.headers.get("user-agent", ""), 200)
        rid = _safe_request_id(request)
        body_size = self._declared_size(request)
        error = None
        status = 0
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            error = _bounded_text(f"{type(exc).__name__}: {exc}", 500)
            status = 500
            raise
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            AuditMiddleware._buf.append(
                {
                    "ts": time.time(),
                    "method": request.method[:16],
                    "path": request.url.path[:2048],
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
        rows = list(cls._buf)
        if since_ts:
            rows = [row for row in rows if row["ts"] >= since_ts]
        rows = rows[-max(1, min(limit, cls._max_entries)) :]
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
        top_paths = sorted(path_counts.items(), key=lambda item: -item[1])[:15]
        slowest = sorted(
            [
                (path, max(times), sum(times) / len(times))
                for path, times in path_times.items()
            ],
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
                {
                    "path": path,
                    "p_max_ms": round(maximum, 1),
                    "p_avg_ms": round(average, 1),
                }
                for path, maximum, average in slowest
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Body-size cap
# ─────────────────────────────────────────────────────────────────
class SizeLimitMiddleware:
    """Fail closed on malformed request framing and oversized API bodies.

    The middleware is a raw ASGI boundary rather than BaseHTTPMiddleware so it
    can count every streamed body chunk before application code runs. Bodies are
    buffered only after reserving space from a bounded aggregate in-flight
    budget, then replayed verbatim to the downstream application.
    """

    def __init__(
        self,
        app,
        max_mb: int | None = None,
        max_inflight_mb: int | None = None,
    ):
        self.app = app
        configured_mb = max_mb if max_mb is not None else int(
            os.environ.get("CODEDOCK_MAX_BODY_MB", "25")
        )
        configured_inflight_mb = (
            max_inflight_mb
            if max_inflight_mb is not None
            else int(os.environ.get("CODEDOCK_MAX_INFLIGHT_BODY_MB", "128"))
        )
        if configured_mb <= 0:
            raise ValueError("maximum body size must be positive")
        if configured_inflight_mb <= 0:
            raise ValueError("maximum in-flight body budget must be positive")

        self.max_bytes = int(configured_mb) * 1024 * 1024
        self.max_inflight_bytes = int(configured_inflight_mb) * 1024 * 1024
        self._inflight_body_bytes = 0
        self._inflight_lock = asyncio.Lock()

    async def _reserve_body_bytes(self, amount: int) -> bool:
        if amount <= 0:
            return True
        async with self._inflight_lock:
            if amount > self.max_inflight_bytes - self._inflight_body_bytes:
                return False
            self._inflight_body_bytes += amount
            return True

    async def _release_body_bytes(self, amount: int) -> None:
        if amount <= 0:
            return
        async with self._inflight_lock:
            self._inflight_body_bytes = max(0, self._inflight_body_bytes - amount)

    async def _reject(
        self,
        scope,
        receive,
        send,
        *,
        status_code: int,
        content: dict,
        headers=None,
    ):
        response = JSONResponse(status_code=status_code, content=content, headers=headers)
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        if not _matches_api_boundary(path):
            await self.app(scope, receive, send)
            return

        raw_headers = list(scope.get("headers") or [])
        content_lengths = [
            value.decode("latin-1").strip(" \t")
            for key, value in raw_headers
            if key.lower() == b"content-length"
        ]
        transfer_encodings = [
            value.decode("latin-1").strip(" \t")
            for key, value in raw_headers
            if key.lower() == b"transfer-encoding"
        ]

        if len(content_lengths) > 1 or len(transfer_encodings) > 1:
            await self._reject(
                scope,
                receive,
                send,
                status_code=400,
                content={"error": "invalid_request_framing"},
            )
            return
        if content_lengths and transfer_encodings:
            await self._reject(
                scope,
                receive,
                send,
                status_code=400,
                content={"error": "invalid_request_framing"},
            )
            return

        declared: int | None = None
        if content_lengths:
            raw_declared = content_lengths[0]
            if not raw_declared.isascii() or not raw_declared.isdigit():
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    content={"error": "invalid_content_length"},
                )
                return

            normalized_declared = raw_declared.lstrip("0") or "0"
            limit_text = str(self.max_bytes)
            if len(normalized_declared) > len(limit_text) or (
                len(normalized_declared) == len(limit_text)
                and normalized_declared > limit_text
            ):
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    content={
                        "error": "payload_too_large",
                        "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                        "limit_bytes": self.max_bytes,
                        "got_bytes_at_least": self.max_bytes + 1,
                    },
                )
                return
            declared = int(normalized_declared, 10)

        buffered: list[dict] = []
        seen = 0
        reserved = 0
        try:
            while True:
                message = await receive()
                message_type = message.get("type")
                if message_type == "http.disconnect":
                    return
                if message_type != "http.request":
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=400,
                        content={"error": "invalid_request_body_stream"},
                    )
                    return

                body = message.get("body") or b""
                if not isinstance(body, (bytes, bytearray)):
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=400,
                        content={"error": "invalid_request_body_stream"},
                    )
                    return
                chunk_size = len(body)

                if seen + chunk_size > self.max_bytes:
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=413,
                        content={
                            "error": "payload_too_large",
                            "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                            "limit_bytes": self.max_bytes,
                            "got_bytes": seen + chunk_size,
                        },
                    )
                    return

                if not await self._reserve_body_bytes(chunk_size):
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=503,
                        content={
                            "error": "body_capacity_exhausted",
                            "detail": "in-flight request body budget exhausted",
                            "limit_bytes": self.max_inflight_bytes,
                        },
                        headers={"Retry-After": "1"},
                    )
                    return

                reserved += chunk_size
                seen += chunk_size
                buffered.append(
                    {
                        **message,
                        "body": bytes(body),
                    }
                )
                if not message.get("more_body", False):
                    break

            if declared is not None and seen != declared:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    content={"error": "invalid_content_length"},
                )
                return

            index = 0

            async def replay_receive():
                nonlocal index
                if index < len(buffered):
                    message = buffered[index]
                    index += 1
                    return message
                return {"type": "http.request", "body": b"", "more_body": False}

            await self.app(scope, replay_receive, send)
        finally:
            await self._release_body_bytes(reserved)


# ─────────────────────────────────────────────────────────────────
# Path traversal helper
# ─────────────────────────────────────────────────────────────────
def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """Resolve candidate under base or raise ValueError on traversal."""
    base_path = Path(base).resolve()
    candidate = candidate.replace("\\", "/")
    if "\x00" in candidate:
        raise ValueError("path traversal blocked: NUL byte")
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
