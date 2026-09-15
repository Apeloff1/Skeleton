"""
api_middleware — request ID injection, structured logging, and an in-memory
token-bucket rate limiter.

Everything here is dependency-free (stdlib only) so it ships with the rest
of the FastAPI app and adds zero install steps.

Public surface:
  • RequestIdMiddleware   — adds X-Request-Id header (existing or generated)
  • AccessLogMiddleware   — single-line structured log per request
  • RateLimiterMiddleware — per-IP token-bucket; 429 on overflow
  • get_stats()           — observability snapshot (for the /api/_telemetry route)

Tunable via env:
  RATE_LIMIT_PER_MIN      (int)   default 600        — 10 rps per IP, generous
  RATE_LIMIT_BURST        (int)   default 60         — initial bucket size
  RATE_LIMIT_EXEMPT       (csv)   default "127.0.0.1,::1,localhost"
  RATE_LIMIT_MAX_BUCKETS  (int)   default 4096       — hard cap on tracked IPs
  RATE_LIMIT_BUCKET_TTL   (float) default 300        — idle seconds before expiry
  ACCESS_LOG              (0|1)   default 1
"""
from __future__ import annotations
import asyncio
import logging
import math
import os
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger("api.middleware")

# ── Configuration ─────────────────────────────────────────────────────
_RATE_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "600"))
_RATE_BURST = int(os.environ.get("RATE_LIMIT_BURST", "60"))
_EXEMPT_RAW = os.environ.get("RATE_LIMIT_EXEMPT", "127.0.0.1,::1,localhost")
_EXEMPT_IPS = {ip.strip() for ip in _EXEMPT_RAW.split(",") if ip.strip()}
_MAX_BUCKETS = int(os.environ.get("RATE_LIMIT_MAX_BUCKETS", "4096"))
_BUCKET_TTL = float(os.environ.get("RATE_LIMIT_BUCKET_TTL", "300"))
_ACCESS_LOG = os.environ.get("ACCESS_LOG", "1") != "0"
_MAX_RETRY_AFTER_SECONDS = 86_400

# Telemetry counters (in-memory) ────────────────────────────────────
# Last 1024 latencies as a ring buffer for p50/p95 computation.
_lat_ring: Deque[float] = deque(maxlen=1024)
# Lazy-init Lock to avoid event-loop binding issues in production
# (creating asyncio primitives at module import time can bind to the
# wrong loop in K8s where uvicorn workers may use a fresh loop).
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


def _is_api_path(path: str) -> bool:
    """Match only the /api route boundary, never lookalikes such as /apiary."""
    return path == "/api" or path.startswith("/api/")


def _bounded_retry_after(retry: float) -> int:
    """Return a finite advisory Retry-After value even under hostile config."""
    if not math.isfinite(retry):
        return _MAX_RETRY_AFTER_SECONDS
    return max(1, min(_MAX_RETRY_AFTER_SECONDS, math.ceil(max(0.0, retry))))


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
            "exempt_ips": sorted(_EXEMPT_IPS),
            "buckets": _counts.get("rate_limit_buckets", 0),
            "max_buckets": _MAX_BUCKETS,
            "evictions": _counts.get("rate_limit_evictions", 0),
            "expired_pruned": _counts.get("rate_limit_expired_pruned", 0),
            "saturation_rejections": _counts.get("rate_limit_saturation_rejections", 0),
        },
    }


# ── Request ID ────────────────────────────────────────────────────────
class RequestIdMiddleware(BaseHTTPMiddleware):
    """Pulls X-Request-Id from the inbound header if present, otherwise mints
    one. The id is exposed on `request.state.request_id` and echoed back on
    the response header. Useful for cross-service correlation."""

    async def dispatch(self, request: Request, call_next: Callable):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        try:
            response: Response = await call_next(request)
        except RuntimeError as e:
            # Starlette BaseHTTPMiddleware raises "No response returned."
            # when the client disconnects mid-response. This is benign —
            # there's no response object to attach the header to, so just
            # propagate the disconnect as a 499 (nginx convention for
            # client-closed-request). Logged at debug to avoid noise.
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
    """Single structured log line per request. Format:
       method=GET path=/api/health status=200 dur_ms=3.21 rid=abcd1234 ip=10.0.0.5
    """

    async def dispatch(self, request: Request, call_next: Callable):
        if not _ACCESS_LOG:
            return await call_next(request)
        t0 = time.perf_counter()
        rid = getattr(request.state, "request_id", "-")
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            # Log the failure then re-raise; the global handler will still 500.
            dur = (time.perf_counter() - t0) * 1000
            log.exception(
                "method=%s path=%s status=500 dur_ms=%.2f rid=%s ip=%s err=unhandled",
                request.method, request.url.path, dur, rid, _client_ip(request),
            )
            raise

        dur = (time.perf_counter() - t0) * 1000
        bucket = "2xx" if 200 <= status < 300 else "4xx" if 400 <= status < 500 else "5xx" if 500 <= status < 600 else "other"
        _counts["requests"] += 1
        _counts[bucket] += 1
        await _push_latency(dur)
        # Skip the high-frequency health pings from access log to keep it clean.
        if request.url.path not in ("/api/health", "/api/_telemetry"):
            log.info(
                "method=%s path=%s status=%d dur_ms=%.2f rid=%s ip=%s",
                request.method, request.url.path, status, dur, rid, _client_ip(request),
            )
        return response


def _client_ip(request: Request) -> str:
    # Honour X-Forwarded-For when behind an ingress, fall back to peer.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = request.client
    return client.host if client else "-"


# ── Rate limiter ──────────────────────────────────────────────────────
class _Bucket:
    """Tiny token-bucket. Refills `_refill_per_sec` tokens per second up to
    `capacity`. take() returns True if a token was consumed."""
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
        # Seconds until the next token will be available.
        deficit = n - self.tokens
        retry = deficit / self.refill_per_sec if self.refill_per_sec > 0 else 60.0
        return False, retry


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Per-IP token bucket with bounded idle state.

    Exempt IPs (loopback) skip the check. State is pruned after the idle TTL
    and capped at `max_buckets`. When all slots are occupied by active
    identities, unseen identities are rejected until a slot expires instead
    of evicting active state and receiving a fresh burst. Buckets are kept in
    least-recently-used activity order so expiry and saturation checks do not
    scan the entire attacker-fillable table on every request. Mutation is
    serialized per middleware instance so cleanup/admission cannot race.

    NOTE: This is *in-memory* and per-process. Sufficient for single-replica
    deployments and dev. For horizontal scaling, swap in a shared store.
    """

    def __init__(
        self,
        app,
        per_minute: int | None = None,
        burst: int | None = None,
        max_buckets: int | None = None,
        bucket_ttl: float | None = None,
    ):
        super().__init__(app)
        configured_rate = per_minute if per_minute is not None else _RATE_PER_MIN
        configured_burst = burst if burst is not None else _RATE_BURST
        configured_max = max_buckets if max_buckets is not None else _MAX_BUCKETS
        configured_ttl = bucket_ttl if bucket_ttl is not None else _BUCKET_TTL
        if not math.isfinite(float(configured_rate)) or configured_rate <= 0:
            raise ValueError("per_minute must be finite and positive")
        if not math.isfinite(float(configured_burst)) or configured_burst <= 0:
            raise ValueError("burst must be finite and positive")
        if configured_max <= 0:
            raise ValueError("max_buckets must be positive")
        if not math.isfinite(float(configured_ttl)) or configured_ttl <= 0:
            raise ValueError("bucket_ttl must be finite and positive")
        self.per_minute = configured_rate
        self.burst = configured_burst
        self.max_buckets = int(configured_max)
        self.bucket_ttl = float(configured_ttl)
        self._refill_per_sec = self.per_minute / 60.0
        self._buckets: "OrderedDict[str, _Bucket]" = OrderedDict()
        self._state_lock: asyncio.Lock | None = None
        self._evictions = 0
        self._expired_pruned = 0
        self._saturation_rejections = 0

    def _get_state_lock(self) -> asyncio.Lock:
        if self._state_lock is None:
            self._state_lock = asyncio.Lock()
        return self._state_lock

    def _prune_expired(self, now: float) -> int:
        pruned = 0
        while self._buckets:
            oldest_ip = next(iter(self._buckets))
            oldest = self._buckets[oldest_ip]
            if now - oldest.last < self.bucket_ttl:
                break
            self._buckets.popitem(last=False)
            pruned += 1
        if pruned:
            self._evictions += pruned
            self._expired_pruned += pruned
            _counts["rate_limit_evictions"] += pruned
            _counts["rate_limit_expired_pruned"] += pruned
        return pruned

    def _retry_until_capacity(self, now: float) -> float:
        if not self._buckets:
            return self.bucket_ttl
        oldest = next(iter(self._buckets.values()))
        return max(0.01, self.bucket_ttl - (now - oldest.last))

    def _bucket_for(self, ip: str, now: float | None = None) -> Tuple[_Bucket | None, float]:
        now = time.monotonic() if now is None else now
        self._prune_expired(now)
        bucket = self._buckets.get(ip)
        if bucket is None:
            if len(self._buckets) >= self.max_buckets:
                self._saturation_rejections += 1
                _counts["rate_limit_saturation_rejections"] += 1
                _counts["rate_limit_buckets"] = len(self._buckets)
                return None, self._retry_until_capacity(now)
            bucket = _Bucket(self.burst, self._refill_per_sec)
            self._buckets[ip] = bucket
        else:
            self._buckets.move_to_end(ip)
        _counts["rate_limit_buckets"] = len(self._buckets)
        return bucket, 0.0

    async def dispatch(self, request: Request, call_next: Callable):
        # Bypass non-API routes (Expo serves /, /assets, etc. from same origin)
        if not _is_api_path(request.url.path):
            return await call_next(request)
        ip = _client_ip(request)
        if ip in _EXEMPT_IPS or ip == "-":
            return await call_next(request)
        async with self._get_state_lock():
            bucket, retry = self._bucket_for(ip)
            if bucket is None:
                ok = False
            else:
                ok, retry = bucket.take(1)
        if not ok:
            _counts["rate_limited"] += 1
            rid = getattr(request.state, "request_id", "-")
            retry_after = _bounded_retry_after(retry)
            log.warning("rate_limited ip=%s path=%s retry=%.1fs rid=%s", ip, request.url.path, retry, rid)
            return JSONResponse(
                {
                    "error": "rate_limited",
                    "message": "Too many requests; please slow down.",
                    "retry_after_seconds": retry_after,
                    "request_id": rid,
                },
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-Request-Id": rid,
                    "X-RateLimit-Limit": str(self.per_minute),
                },
            )
        return await call_next(request)


def install_middleware(app) -> None:
    """Idempotent wiring helper. Order matters: rate limit OUTERMOST so we
    short-circuit cheap; request-id MUST wrap access-log so the log line
    can read request.state.request_id (set by RequestIdMiddleware).

    Starlette wraps middleware in reverse-add order (LIFO), so calling
    add_middleware in the order below results in:
        Client → RateLimiter → RequestId → AccessLog → handler
    (AccessLog runs INSIDE RequestId so request_id is populated by then.)
    """
    app.add_middleware(AccessLogMiddleware)   # add 1st → innermost
    app.add_middleware(RequestIdMiddleware)   # add 2nd → wraps AccessLog
    app.add_middleware(RateLimiterMiddleware) # add 3rd → outermost
