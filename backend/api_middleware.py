"""
api_middleware — request ID injection, structured logging, and an in-memory
token-bucket rate limiter.

Security properties:
  • forwarding headers are trusted only from explicitly configured proxy CIDRs
  • request IDs are bounded and validated before logging/echoing
  • token-bucket state is LRU-bounded to resist memory exhaustion
  • unknown clients and loopback peers are rate limited unless explicitly exempted

Tunable via env:
  RATE_LIMIT_PER_MIN       default 600
  RATE_LIMIT_BURST         default 60
  RATE_LIMIT_MAX_BUCKETS   default 10000
  RATE_LIMIT_EXEMPT        default "" (no implicit exemptions)
  TRUSTED_PROXY_CIDRS      default "" (no implicit trusted proxies)
  ACCESS_LOG               default 1
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict, defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

try:  # Package import in tests / installed package.
    from .middleware.client_identity import client_ip, sanitize_request_id
except ImportError:  # Direct backend/server.py execution.
    from middleware.client_identity import client_ip, sanitize_request_id

log = logging.getLogger("api.middleware")


def _positive_int_env(name: str, default: int, *, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


# ── Configuration ─────────────────────────────────────────────────────
_RATE_PER_MIN = _positive_int_env("RATE_LIMIT_PER_MIN", 600, maximum=1_000_000)
_RATE_BURST = _positive_int_env("RATE_LIMIT_BURST", 60, maximum=100_000)
_MAX_BUCKETS = _positive_int_env("RATE_LIMIT_MAX_BUCKETS", 10_000, maximum=1_000_000)
# Exemptions are an explicit deployment decision. In particular, loopback is
# not exempt by default because reverse proxies commonly connect over loopback.
_EXEMPT_RAW = os.environ.get("RATE_LIMIT_EXEMPT", "")
_EXEMPT_IPS = {ip.strip() for ip in _EXEMPT_RAW.split(",") if ip.strip()}
_ACCESS_LOG = os.environ.get("ACCESS_LOG", "1") != "0"

# Telemetry counters (in-memory) ──────────────────────────────────────
_lat_ring: Deque[float] = deque(maxlen=1024)
_lat_lock: asyncio.Lock | None = None


def _get_lat_lock() -> asyncio.Lock:
    global _lat_lock
    if _lat_lock is None:
        _lat_lock = asyncio.Lock()
    return _lat_lock


_counts: Dict[str, int] = defaultdict(int)
_started_at: float = time.time()


async def _push_latency(ms: float) -> None:
    async with _get_lat_lock():
        _lat_ring.append(ms)


def _percentile(sorted_vals, pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(pct / 100.0 * (len(sorted_vals) - 1))))
    return sorted_vals[k]


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
            "max_buckets": _MAX_BUCKETS,
            "exempt_ips": sorted(_EXEMPT_IPS),
        },
    }


# ── Request ID ────────────────────────────────────────────────────────
class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a safe bounded request ID for logs and cross-service tracing."""

    async def dispatch(self, request: Request, call_next: Callable):
        rid = sanitize_request_id(request.headers.get("x-request-id"))
        request.state.request_id = rid
        try:
            response: Response = await call_next(request)
        except RuntimeError as e:
            if "No response returned" in str(e):
                from fastapi.responses import Response as _Resp

                log.debug("client disconnected mid-request rid=%s path=%s", rid, request.url.path)
                resp = _Resp(status_code=499)
                resp.headers["X-Request-Id"] = rid
                return resp
            raise
        response.headers["X-Request-Id"] = rid
        return response


# ── Access log ────────────────────────────────────────────────────────
class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per request using validated identity."""

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
    """Compatibility wrapper around the shared trusted-proxy extractor."""
    return client_ip(request)


# ── Rate limiter ──────────────────────────────────────────────────────
class _Bucket:
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
    """Per-client token bucket with bounded LRU state.

    This limiter is process-local. Distributed deployments should also enforce
    limits at the ingress/API gateway or use a shared backend such as Redis.
    """

    def __init__(
        self,
        app,
        per_minute: int | None = None,
        burst: int | None = None,
        max_buckets: int | None = None,
    ):
        super().__init__(app)
        self.per_minute = max(1, per_minute or _RATE_PER_MIN)
        self.burst = max(1, burst or _RATE_BURST)
        self.max_buckets = max(1, max_buckets or _MAX_BUCKETS)
        self._refill_per_sec = self.per_minute / 60.0
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    def _bucket_for(self, ip: str) -> _Bucket:
        bucket = self._buckets.get(ip)
        if bucket is not None:
            self._buckets.move_to_end(ip)
            return bucket

        if len(self._buckets) >= self.max_buckets:
            self._buckets.popitem(last=False)
        bucket = _Bucket(self.burst, self._refill_per_sec)
        self._buckets[ip] = bucket
        return bucket

    async def dispatch(self, request: Request, call_next: Callable):
        if not request.url.path.startswith("/api"):
            return await call_next(request)
        ip = _client_ip(request)
        if ip in _EXEMPT_IPS:
            return await call_next(request)
        # Unknown identity is intentionally *not* exempt. All such requests
        # share a bounded bucket rather than gaining an unlimited bypass.
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
    """Install logging, request identity, and rate limiting in safe order."""
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimiterMiddleware)
