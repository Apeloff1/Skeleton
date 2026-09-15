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
  RATE_LIMIT_PER_MIN  (int)   default 600        — 10 rps per IP, generous
  RATE_LIMIT_BURST    (int)   default 60         — initial bucket size
  RATE_LIMIT_EXEMPT   (csv)   default "127.0.0.1,::1,localhost"
  ACCESS_LOG          (0|1)   default 1
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

log = logging.getLogger("api.middleware")

# ── Configuration ─────────────────────────────────────────────────────
_RATE_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "600"))
_RATE_BURST = int(os.environ.get("RATE_LIMIT_BURST", "60"))
_EXEMPT_RAW = os.environ.get("RATE_LIMIT_EXEMPT", "127.0.0.1,::1,localhost")
_EXEMPT_IPS = {ip.strip() for ip in _EXEMPT_RAW.split(",") if ip.strip()}
_ACCESS_LOG = os.environ.get("ACCESS_LOG", "1") != "0"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

# Telemetry counters (in-memory) ────────────────────────────────────
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
            "exempt_ips": sorted(_EXEMPT_IPS),
        },
    }


# ── Request ID ────────────────────────────────────────────────────────
def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id", "")
    if candidate and _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex[:16]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Accept a safe X-Request-Id or mint one and echo it on the response."""

    async def dispatch(self, request: Request, call_next: Callable):
        rid = _request_id(request)
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
    """Single structured log line per request."""

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
                request.method, request.url.path, dur, rid, _client_ip(request),
            )
            raise

        dur = (time.perf_counter() - t0) * 1000
        bucket = "2xx" if 200 <= status < 300 else "4xx" if 400 <= status < 500 else "5xx" if 500 <= status < 600 else "other"
        _counts["requests"] += 1
        _counts[bucket] += 1
        await _push_latency(dur)
        if request.url.path not in ("/api/health", "/api/_telemetry"):
            log.info(
                "method=%s path=%s status=%d dur_ms=%.2f rid=%s ip=%s",
                request.method, request.url.path, status, dur, rid, _client_ip(request),
            )
        return response


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = request.client
    return client.host if client else "-"


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
    """Per-IP token bucket. Exempt IPs (loopback) skip the check."""

    def __init__(self, app, per_minute: int | None = None, burst: int | None = None):
        super().__init__(app)
        self.per_minute = per_minute or _RATE_PER_MIN
        self.burst = burst or _RATE_BURST
        self._refill_per_sec = self.per_minute / 60.0
        self._buckets: Dict[str, _Bucket] = {}

    def _bucket_for(self, ip: str) -> _Bucket:
        b = self._buckets.get(ip)
        if b is None:
            b = _Bucket(self.burst, self._refill_per_sec)
            self._buckets[ip] = b
        return b

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
            log.warning("rate_limited ip=%s path=%s retry=%.1fs rid=%s", ip, request.url.path, retry, rid)
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
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimiterMiddleware)
