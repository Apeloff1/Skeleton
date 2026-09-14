"""
api_middleware — request ID injection, structured logging, and an in-memory
token-bucket rate limiter.

Security properties:
  * Forwarded client IPs are trusted only from configured proxy CIDRs.
  * Request IDs are normalized before they reach response headers or logs.
  * Rate-limit state is bounded and stale buckets are evicted.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.client_ip import resolve_client_ip

log = logging.getLogger("api.middleware")


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        log.warning("invalid integer for %s; using default", name)
        value = default
    return max(minimum, min(maximum, value))


# ── Configuration ─────────────────────────────────────────────────────
_RATE_PER_MIN = _env_int("RATE_LIMIT_PER_MIN", 600, minimum=1, maximum=1_000_000)
_RATE_BURST = _env_int("RATE_LIMIT_BURST", 60, minimum=1, maximum=100_000)
_RATE_MAX_BUCKETS = _env_int("RATE_LIMIT_MAX_BUCKETS", 10_000, minimum=128, maximum=1_000_000)
_RATE_BUCKET_TTL = _env_int("RATE_LIMIT_BUCKET_TTL_SECONDS", 900, minimum=60, maximum=86_400)
_EXEMPT_RAW = os.environ.get("RATE_LIMIT_EXEMPT", "127.0.0.1,::1,localhost")
_EXEMPT_IPS = {ip.strip() for ip in _EXEMPT_RAW.split(",") if ip.strip()}
_ACCESS_LOG = os.environ.get("ACCESS_LOG", "1") != "0"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

# Telemetry counters (in-memory) ────────────────────────────────────
_lat_ring: Deque[float] = deque(maxlen=1024)
_lat_lock: asyncio.Lock | None = None
_counts: Dict[str, int] = defaultdict(int)
_started_at: float = time.time()


def _get_lat_lock() -> asyncio.Lock:
    global _lat_lock
    if _lat_lock is None:
        _lat_lock = asyncio.Lock()
    return _lat_lock


async def _push_latency(ms: float) -> None:
    async with _get_lat_lock():
        _lat_ring.append(ms)


def _percentile(sorted_vals, pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(pct / 100.0 * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "").strip()
    if supplied and _REQUEST_ID_RE.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex[:16]


def get_stats() -> dict:
    """Snapshot for /api/_telemetry. Cheap O(n log n) sort over ≤1024 samples."""
    vals = sorted(_lat_ring)
    return {
        "uptime_seconds": round(time.time() - _started_at, 1),
        "requests_total": _counts.get("requests", 0),
        "requests_2xx": _counts.get("2xx", 0),
        "requests_4xx": _counts.get("4xx", 0),
        "requests_5xx": _counts.get("5xx", 0),
        "rate_limited_total": _counts.get("rate_limited", 0),
        "samples": len(vals),
        "latency_ms": {
            "p50": round(_percentile(vals, 50), 2),
            "p95": round(_percentile(vals, 95), 2),
            "p99": round(_percentile(vals, 99), 2),
            "max": round(max(vals), 2) if vals else 0.0,
        },
        "rate_limit": {
            "per_minute": _RATE_PER_MIN,
            "burst": _RATE_BURST,
            "max_buckets": _RATE_MAX_BUCKETS,
            "bucket_ttl_seconds": _RATE_BUCKET_TTL,
            "exempt_ips": sorted(_EXEMPT_IPS),
        },
    }


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a safe correlation ID to the request and response."""

    async def dispatch(self, request: Request, call_next: Callable):
        rid = _request_id(request)
        request.state.request_id = rid
        try:
            response: Response = await call_next(request)
        except RuntimeError as exc:
            if "No response returned" in str(exc):
                from fastapi.responses import Response as _Resp

                log.debug("client disconnected mid-request rid=%s path=%s", rid, request.url.path)
                resp = _Resp(status_code=499)
                resp.headers["X-Request-Id"] = rid
                return resp
            raise
        response.headers["X-Request-Id"] = rid
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per request."""

    async def dispatch(self, request: Request, call_next: Callable):
        if not _ACCESS_LOG:
            return await call_next(request)
        t0 = time.perf_counter()
        rid = getattr(request.state, "request_id", "-")
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            dur = (time.perf_counter() - t0) * 1000
            log.exception(
                "method=%s path=%s status=500 dur_ms=%.2f rid=%s ip=%s err=unhandled",
                request.method,
                request.url.path,
                dur,
                rid,
                _client_ip(request),
            )
            raise

        dur = (time.perf_counter() - t0) * 1000
        bucket = (
            "2xx"
            if 200 <= status < 300
            else "4xx"
            if 400 <= status < 500
            else "5xx"
            if 500 <= status < 600
            else "other"
        )
        _counts["requests"] += 1
        _counts[bucket] += 1
        await _push_latency(dur)
        if request.url.path not in ("/api/health", "/api/_telemetry"):
            log.info(
                "method=%s path=%s status=%d dur_ms=%.2f rid=%s ip=%s",
                request.method,
                request.url.path,
                status,
                dur,
                rid,
                _client_ip(request),
            )
        return response


def _client_ip(request: Request) -> str:
    return resolve_client_ip(request)


class _Bucket:
    """Tiny token bucket."""

    __slots__ = ("tokens", "last", "capacity", "refill_per_sec")

    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = float(capacity)
        self.last = time.monotonic()

    def take(self, n: int = 1) -> Tuple[bool, float]:
        now = time.monotonic()
        elapsed = now - self.last
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.last = now
        if self.tokens >= n:
            self.tokens -= n
            return True, 0.0
        deficit = n - self.tokens
        retry = deficit / self.refill_per_sec if self.refill_per_sec > 0 else 60.0
        return False, retry


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Per-IP bounded token bucket for API routes."""

    def __init__(self, app, per_minute: int | None = None, burst: int | None = None):
        super().__init__(app)
        self.per_minute = per_minute or _RATE_PER_MIN
        self.burst = burst or _RATE_BURST
        self._refill_per_sec = self.per_minute / 60.0
        self._buckets: Dict[str, _Bucket] = {}
        self._last_prune = time.monotonic()

    def _prune_buckets(self, now: float) -> None:
        if now - self._last_prune < 30 and len(self._buckets) < _RATE_MAX_BUCKETS:
            return
        cutoff = now - _RATE_BUCKET_TTL
        stale = [key for key, bucket in self._buckets.items() if bucket.last < cutoff]
        for key in stale:
            self._buckets.pop(key, None)

        if len(self._buckets) >= _RATE_MAX_BUCKETS:
            overflow = len(self._buckets) - _RATE_MAX_BUCKETS + max(1, _RATE_MAX_BUCKETS // 10)
            oldest = sorted(self._buckets.items(), key=lambda item: item[1].last)[:overflow]
            for key, _bucket in oldest:
                self._buckets.pop(key, None)
        self._last_prune = now

    def _bucket_for(self, ip: str) -> _Bucket:
        now = time.monotonic()
        self._prune_buckets(now)
        bucket = self._buckets.get(ip)
        if bucket is None:
            bucket = _Bucket(self.burst, self._refill_per_sec)
            self._buckets[ip] = bucket
        return bucket

    async def dispatch(self, request: Request, call_next: Callable):
        if not request.url.path.startswith("/api"):
            return await call_next(request)
        ip = _client_ip(request)
        if ip in _EXEMPT_IPS or ip == "-":
            return await call_next(request)
        ok, retry = self._bucket_for(ip).take(1)
        if not ok:
            _counts["rate_limited"] += 1
            rid = getattr(request.state, "request_id", "-")
            log.warning(
                "rate_limited ip=%s path=%s retry=%.1fs rid=%s",
                ip,
                request.url.path,
                retry,
                rid,
            )
            return JSONResponse(
                {
                    "error": "rate_limited",
                    "message": "Too many requests; please slow down.",
                    "retry_after_seconds": round(retry, 1),
                    "request_id": rid,
                },
                status_code=429,
                headers={
                    "Retry-After": str(max(1, int(retry + 0.5))),
                    "X-Request-Id": rid,
                    "X-RateLimit-Limit": str(self.per_minute),
                },
            )
        return await call_next(request)


def install_middleware(app) -> None:
    """Idempotent wiring helper."""
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimiterMiddleware)
