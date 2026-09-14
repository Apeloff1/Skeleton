"""
api_middleware — request identity, access logging, origin enforcement, response
hardening, and an in-memory token-bucket rate limiter.

Security properties:
  • forwarding headers are trusted only from explicitly configured proxy CIDRs
  • request IDs are bounded and validated before logging/echoing
  • token-bucket state is LRU-bounded to resist memory exhaustion
  • unknown clients and loopback peers are rate limited unless explicitly exempted
  • browser cross-origin API reads fail closed unless CORS_ORIGINS is configured
  • API responses receive defensive browser/security headers by default
  • rejected requests remain inside tracing, header, and access-log envelopes

Tunable via env:
  RATE_LIMIT_PER_MIN       default 600
  RATE_LIMIT_BURST         default 60
  RATE_LIMIT_MAX_BUCKETS   default 10000
  RATE_LIMIT_EXEMPT        default "" (no implicit exemptions)
  TRUSTED_PROXY_CIDRS      default "" (no implicit trusted proxies)
  CORS_ORIGINS             default "" (same-origin only; use explicit CSV or *)
  FORCE_HSTS               default 0 (set 1 only when HTTPS is guaranteed)
  ACCESS_LOG               default 1
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict, defaultdict, deque
from typing import Callable, Deque, Dict, Tuple
from urllib.parse import urlsplit

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


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _configured_origins() -> frozenset[str]:
    """Return explicitly trusted browser origins.

    Absence of CORS_ORIGINS intentionally means no cross-origin API access.
    This protects deployments that forget to configure CORS. A literal '*'
    remains available as an explicit operator choice for local/dev use.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if not raw:
        return frozenset()
    if raw == "*":
        return frozenset({"*"})
    return frozenset(origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip())


def _same_origin(request: Request, origin: str) -> bool:
    """Conservatively compare an Origin header to the request authority."""
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        return False
    request_origin = f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/")
    return origin.rstrip("/") == request_origin


_RATE_PER_MIN = _positive_int_env("RATE_LIMIT_PER_MIN", 600, maximum=1_000_000)
_RATE_BURST = _positive_int_env("RATE_LIMIT_BURST", 60, maximum=100_000)
_MAX_BUCKETS = _positive_int_env("RATE_LIMIT_MAX_BUCKETS", 10_000, maximum=1_000_000)
_EXEMPT_RAW = os.environ.get("RATE_LIMIT_EXEMPT", "")
_EXEMPT_IPS = {ip.strip() for ip in _EXEMPT_RAW.split(",") if ip.strip()}
_ACCESS_LOG = os.environ.get("ACCESS_LOG", "1") != "0"

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
        "origin_blocked_total": _counts.get("origin_blocked", 0),
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


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """Fail closed for browser cross-origin API requests."""

    async def dispatch(self, request: Request, call_next: Callable):
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        origin = request.headers.get("origin")
        if not origin:
            return await call_next(request)

        origin = origin.strip().rstrip("/")
        allowed = _configured_origins()
        if "*" in allowed or origin in allowed or _same_origin(request, origin):
            return await call_next(request)

        _counts["origin_blocked"] += 1
        rid = getattr(request.state, "request_id", "-")
        log.warning("origin_blocked origin=%r path=%s rid=%s", origin[:200], request.url.path, rid)
        return JSONResponse(
            status_code=403,
            content={"error": "origin_not_allowed", "request_id": rid},
            headers={"Cache-Control": "no-store", "X-Request-Id": rid},
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach defense-in-depth browser headers to API responses."""

    async def dispatch(self, request: Request, call_next: Callable):
        response: Response = await call_next(request)
        if not request.url.path.startswith("/api"):
            return response

        headers = response.headers
        headers.setdefault("Cache-Control", "no-store")
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
        )
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        if request.url.scheme == "https" or _env_truthy("FORCE_HSTS"):
            headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        if "server" in headers:
            del headers["server"]
        return response


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
    """Install security middleware in Starlette's reverse-add (LIFO) order.

    Effective request path after these calls:

        RequestId -> SecurityHeaders -> AccessLog -> OriginGuard
                  -> RateLimiter -> application

    RequestId and SecurityHeaders are deliberately outermost so every API
    response, including 403/429 short-circuits, is correlated and hardened.
    AccessLog wraps both rejection layers so denied traffic remains observable.
    """
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(OriginGuardMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
