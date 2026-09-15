"""
security.py — Lightweight security middleware for the FastAPI app.

Provides independent edge controls wired by server.py:

  1. RateLimitMiddleware       — bounded per-client+route token buckets
  2. AuditMiddleware           — bounded ring buffer of /api request metadata
  3. SizeLimitMiddleware       — hard cap on declared and streamed body bytes
  4. safe_relative_path()      — path-traversal protection helper

Proxy-provided client identity is trusted only when the immediate peer is in
``CODEDOCK_TRUSTED_PROXY_CIDRS``. Forwarding chains are parsed right-to-left
and malformed or ambiguous chains fail closed to the immediate peer.
"""
from __future__ import annotations

import asyncio
import math
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
_MAX_RETRY_AFTER_SECONDS = 86_400
_monotonic = time.monotonic


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

    forwarded_values = request.headers.getlist("x-forwarded-for")
    if len(forwarded_values) != 1:
        return peer

    values = [value.strip() for value in forwarded_values[0].split(",")]
    if not values or any(not value for value in values):
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

    # A chain containing only trusted proxies has no trustworthy client identity.
    return peer


def _safe_content_length(raw: str | None) -> int:
    """Parse audit metadata without ever raising on hostile header values."""
    if not raw:
        return 0
    value = raw.strip(" \t")
    if not value.isascii() or not value.isdigit():
        return 0
    try:
        return int(value, 10)
    except ValueError:
        return 0


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
    _bucket_ttl: float = 300.0
    _capacity_rejections: int = 0
    _expired_prunes: int = 0

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
        configured_rps = rps if rps is not None else float(
            os.environ.get("CODEDOCK_RATE_LIMIT_RPS", "2")
        )
        configured_burst = burst if burst is not None else int(
            os.environ.get("CODEDOCK_RATE_LIMIT_BURST", "120")
        )
        configured_max = max_buckets if max_buckets is not None else int(
            os.environ.get("CODEDOCK_RATE_LIMIT_MAX_BUCKETS", "10000")
        )
        configured_ttl = bucket_ttl if bucket_ttl is not None else float(
            os.environ.get("CODEDOCK_RATE_LIMIT_BUCKET_TTL", "300")
        )
        if not math.isfinite(float(configured_rps)) or configured_rps <= 0:
            raise ValueError("rate limit rps must be finite and positive")
        if configured_burst <= 0:
            raise ValueError("rate limit burst must be positive")
        if configured_max <= 0:
            raise ValueError("rate limit bucket cap must be positive")
        if not math.isfinite(float(configured_ttl)) or configured_ttl <= 0:
            raise ValueError("rate limit bucket ttl must be finite and positive")

        RateLimitMiddleware._rps = float(configured_rps)
        RateLimitMiddleware._burst = int(configured_burst)
        RateLimitMiddleware._max_buckets = int(configured_max)
        RateLimitMiddleware._bucket_ttl = float(configured_ttl)
        # Keep the advertised hard cap true even when a live process reloads with
        # a smaller configured maximum. This is configuration-time pruning only;
        # request-driven churn never evicts active buckets.
        while len(RateLimitMiddleware._buckets) > RateLimitMiddleware._max_buckets:
            RateLimitMiddleware._buckets.popitem(last=False)

        self.prefix = prefix
        # Leaf endpoints are exact exemptions. Only namespaces that are
        # intentionally exempt as a subtree are prefix-matched.
        self._exact_whitelist = frozenset(
            {
                "/api/binary/download",
                "/api/binary/inspect",
                "/api/binary/toolchain",
                "/api/binary/list",
                "/api/telemetry/event",
                "/api/telemetry/batch",
            }
        )
        self._prefix_whitelist = (
            "/api/health",
            "/api/security",
        )

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = _request_client_ip(request)
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    def _is_whitelisted(self, path: str) -> bool:
        return path in self._exact_whitelist or any(
            _matches_path_prefix(path, allowed) for allowed in self._prefix_whitelist
        )

    @classmethod
    def _prune_expired_buckets(cls, now: float) -> None:
        while cls._buckets:
            key = next(iter(cls._buckets))
            bucket = cls._buckets[key]
            if max(0.0, now - bucket.last_refill) < cls._bucket_ttl:
                break
            cls._buckets.popitem(last=False)
            cls._expired_prunes += 1

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not _matches_path_prefix(path, self.prefix):
            return await call_next(request)
        if self._is_whitelisted(path):
            return await call_next(request)

        now = _monotonic()
        ip, route = self._key(request)
        key = (ip, route)
        async with RateLimitMiddleware._lock:
            RateLimitMiddleware._prune_expired_buckets(now)
            bucket = RateLimitMiddleware._buckets.get(key)
            if bucket is None:
                if len(RateLimitMiddleware._buckets) >= RateLimitMiddleware._max_buckets:
                    # Never evict active state to admit attacker-chosen new keys: that
                    # would mint a fresh burst and turn the memory cap into a bypass.
                    RateLimitMiddleware._capacity_rejections += 1
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "rate_limited",
                            "detail": "rate limit identity capacity reached",
                            "retry_after_seconds": 1,
                        },
                        headers={"Retry-After": "1"},
                    )
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
            # Do not move refill state backwards if a clock seam/mock regresses.
            bucket.last_refill = max(bucket.last_refill, now)
            if bucket.tokens < 1.0:
                retry_delay = (1.0 - bucket.tokens) / RateLimitMiddleware._rps
                if math.isfinite(retry_delay):
                    retry_after = max(
                        1,
                        min(_MAX_RETRY_AFTER_SECONDS, math.ceil(retry_delay)),
                    )
                else:
                    retry_after = _MAX_RETRY_AFTER_SECONDS
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
            "bucket_ttl_seconds": cls._bucket_ttl,
            "active_buckets": len(cls._buckets),
            "capacity_rejections": cls._capacity_rejections,
            "expired_prunes": cls._expired_prunes,
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
    """Enforce per-request and aggregate in-flight body limits before app code."""

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

    async def _reject_too_large(
        self, scope, receive, send, *, got_bytes: int | None = None,
        got_bytes_at_least: int | None = None,
    ) -> None:
        content = {
            "error": "payload_too_large",
            "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
            "limit_bytes": self.max_bytes,
        }
        if got_bytes is not None:
            content["got_bytes"] = got_bytes
        if got_bytes_at_least is not None:
            content["got_bytes_at_least"] = got_bytes_at_least
        response = JSONResponse(status_code=413, content=content)
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        if not _matches_path_prefix(path, "/api"):
            await self.app(scope, receive, send)
            return

        raw_headers = list(scope.get("headers") or [])
        content_lengths = [
            value.decode("latin-1").strip(" \t")
            for key, value in raw_headers
            if key.lower() == b"content-length"
        ]
        transfer_encodings = [
            value.decode("latin-1").strip(" \t").lower()
            for key, value in raw_headers
            if key.lower() == b"transfer-encoding"
        ]

        # Reject ambiguous or unsupported HTTP framing before consuming a body.
        if (
            len(content_lengths) > 1
            or (content_lengths and transfer_encodings)
            or len(transfer_encodings) > 1
        ):
            response = JSONResponse(
                status_code=400,
                content={"error": "invalid_request_framing"},
            )
            await response(scope, receive, send)
            return
        if transfer_encodings and transfer_encodings[0] != "chunked":
            response = JSONResponse(
                status_code=400,
                content={"error": "invalid_request_framing"},
            )
            await response(scope, receive, send)
            return

        declared: int | None = None
        if content_lengths:
            raw_declared = content_lengths[0]
            if not raw_declared.isascii() or not raw_declared.isdigit():
                response = JSONResponse(
                    status_code=400,
                    content={"error": "invalid_content_length"},
                )
                await response(scope, receive, send)
                return

            # Compare as a normalized decimal string before int() so hostile
            # multi-kilobyte digit strings cannot trigger Python's parse limit.
            normalized_declared = raw_declared.lstrip("0") or "0"
            limit_text = str(self.max_bytes)
            if len(normalized_declared) > len(limit_text) or (
                len(normalized_declared) == len(limit_text)
                and normalized_declared > limit_text
            ):
                await self._reject_too_large(
                    scope,
                    receive,
                    send,
                    got_bytes_at_least=self.max_bytes + 1,
                )
                return
            declared = int(normalized_declared, 10)

        # Drain and count the complete API body before application code sees it.
        # This prevents endpoints that read only one chunk (or no body at all) from
        # bypassing the cap with an oversized unread tail. Reservations bound
        # aggregate memory across concurrent request prebuffers.
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
                    response = JSONResponse(
                        status_code=400,
                        content={"error": "invalid_request_body"},
                    )
                    await response(scope, receive, send)
                    return

                body = message.get("body") or b""
                chunk_size = len(body)
                if seen + chunk_size > self.max_bytes:
                    await self._reject_too_large(
                        scope, receive, send, got_bytes=seen + chunk_size
                    )
                    return
                if not await self._reserve_body_bytes(chunk_size):
                    response = JSONResponse(
                        status_code=503,
                        content={
                            "error": "body_capacity_exhausted",
                            "detail": "in-flight request body budget exhausted",
                            "limit_bytes": self.max_inflight_bytes,
                        },
                        headers={"Retry-After": "1"},
                    )
                    await response(scope, receive, send)
                    return

                reserved += chunk_size
                seen += chunk_size
                buffered.append(message)
                if not message.get("more_body", False):
                    break

            if declared is not None and seen != declared:
                response = JSONResponse(
                    status_code=400,
                    content={"error": "invalid_content_length"},
                )
                await response(scope, receive, send)
                return

            index = 0

            async def replay_receive():
                nonlocal index
                if index < len(buffered):
                    message = buffered[index]
                    index += 1
                    return message
                return await receive()

            await self.app(scope, replay_receive, send)
        finally:
            await self._release_body_bytes(reserved)


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
