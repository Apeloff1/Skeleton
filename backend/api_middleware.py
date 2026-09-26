"""
api_middleware — request ID injection, structured logging, and an in-memory
token-bucket rate limiter.

Everything here is dependency-free (stdlib only) so it ships with the rest
of the FastAPI app and adds zero install steps.

Public surface:
  • RequestIdMiddleware   — adds a canonical X-Request-Id header
  • AccessLogMiddleware   — single-line structured log per request
  • RateLimiterMiddleware — bounded per-IP token-bucket; 429 on overflow
  • get_stats()           — observability snapshot (for /api/_telemetry)

Tunable via env:
  RATE_LIMIT_PER_MIN      (int)   default 600        — 10 rps per IP
  RATE_LIMIT_BURST        (int)   default 60         — initial bucket size
  RATE_LIMIT_EXEMPT       (csv)   default "127.0.0.1,::1,localhost,testclient"
  RATE_LIMIT_MAX_BUCKETS  (int)   default 4096       — hard cap on tracked IPs
  RATE_LIMIT_BUCKET_TTL   (float) default 300        — idle seconds before expiry
  TRUSTED_PROXY_CIDRS     (csv)   default ""         — peers allowed to supply XFF
  ACCESS_LOG              (0|1)   default 1
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import os
import re
import time
from collections import OrderedDict, defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.route_privacy import bind_route_privacy, reset_route_privacy

log = logging.getLogger("api.middleware")


# ── Configuration ─────────────────────────────────────────────────────
def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive finite number") from exc
    if value <= 0 or not math.isfinite(value):
        raise RuntimeError(f"{name} must be a positive finite number")
    return value


def _parse_trusted_proxy_networks(
    raw: str,
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parse proxy CIDRs fail-closed: one malformed entry disables XFF trust."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            log.error("invalid TRUSTED_PROXY_CIDRS configuration; disabling proxy trust")
            return ()
    return tuple(networks)


_RATE_PER_MIN = _positive_int_env("RATE_LIMIT_PER_MIN", 600)
_RATE_BURST = _positive_int_env("RATE_LIMIT_BURST", 60)
_EXEMPT_RAW = os.environ.get("RATE_LIMIT_EXEMPT", "127.0.0.1,::1,localhost,testclient")
_EXEMPT_IPS = {ip.strip() for ip in _EXEMPT_RAW.split(",") if ip.strip()}
_MAX_BUCKETS = _positive_int_env("RATE_LIMIT_MAX_BUCKETS", 4096)
_BUCKET_TTL = _positive_float_env("RATE_LIMIT_BUCKET_TTL", 300.0)
_TRUSTED_PROXY_NETWORKS = _parse_trusted_proxy_networks(
    os.environ.get("TRUSTED_PROXY_CIDRS", "")
)
_ACCESS_LOG = os.environ.get("ACCESS_LOG", "1") != "0"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_MAX_RETRY_AFTER_SECONDS = 86_400
_MAX_XFF_HOPS = 32
_MAX_XFF_CHARS = 2048

# Telemetry counters (in-memory) ───────────────────────────────────────
_lat_ring: Deque[float] = deque(maxlen=1024)
_counts: Dict[str, int] = defaultdict(int)
_started_at: float = time.time()


def _push_latency(ms: float) -> None:
    """Record one sample without scheduling or lock contention."""
    _lat_ring.append(ms)


def _percentile(sorted_vals, pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(pct / 100.0 * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def _bounded_retry_after(retry: float) -> int:
    """Return finite Retry-After metadata for any token-bucket result."""
    if not math.isfinite(retry):
        return _MAX_RETRY_AFTER_SECONDS
    return max(1, min(_MAX_RETRY_AFTER_SECONDS, math.ceil(max(0.0, retry))))


def get_stats() -> dict:
    """Snapshot for /api/_telemetry. Cheap O(n log n) over ≤1024 samples."""
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
            "trusted_proxy_count": len(_TRUSTED_PROXY_NETWORKS),
        },
    }


# ── Request identity ──────────────────────────────────────────────────
def _request_id(request: Request) -> str:
    """Return one bounded header-safe request ID or mint a compact UUID4 token."""
    candidates = request.headers.getlist("x-request-id")
    if len(candidates) == 1 and _REQUEST_ID_RE.fullmatch(candidates[0]):
        return candidates[0]
    return os.urandom(16).hex()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Canonicalize request identity and echo it on the response."""

    async def dispatch(self, request: Request, call_next: Callable):
        rid = _request_id(request)
        request.state.request_id = rid
        try:
            response: Response = await call_next(request)
        except RuntimeError as exc:
            if "No response returned" in str(exc):
                from fastapi.responses import Response as _Resp

                log.debug(
                    "client disconnected mid-request rid=%s path=%s",
                    rid,
                    request.url.path,
                )
                response = _Resp(status_code=499)
                response.headers["X-Request-Id"] = rid
                return response
            raise
        response.headers["X-Request-Id"] = rid
        return response


# ── Client identity / proxy trust ─────────────────────────────────────
def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    value = value.strip()
    if not value:
        return None
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _canonical_ip(value: str) -> str | None:
    address = _parse_ip(value)
    return str(address) if address is not None else None


def _is_trusted_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return any(address in network for network in _TRUSTED_PROXY_NETWORKS)


def _is_trusted_proxy(value: str) -> bool:
    address = _parse_ip(value)
    return address is not None and _is_trusted_address(address)


def _resolve_client_ip(request: Request) -> str:
    """Resolve client identity without trusting attacker-controlled XFF."""
    client = request.client
    peer = client.host.strip() if client and client.host else "-"
    if peer == "-":
        return peer

    peer_address = _parse_ip(peer)
    canonical_peer = str(peer_address) if peer_address is not None else peer
    if peer_address is None or not _is_trusted_address(peer_address):
        return canonical_peer

    forwarded_headers = request.headers.getlist("x-forwarded-for")
    if len(forwarded_headers) != 1:
        return canonical_peer
    forwarded_value = forwarded_headers[0]
    if len(forwarded_value) > _MAX_XFF_CHARS:
        return canonical_peer

    parts = forwarded_value.split(",")
    if not parts or len(parts) > _MAX_XFF_HOPS:
        return canonical_peer

    forwarded: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for part in parts:
        address = _parse_ip(part)
        if address is None:
            return canonical_peer
        forwarded.append(address)

    for address in reversed(forwarded):
        if not _is_trusted_address(address):
            return str(address)
    return canonical_peer


def _client_ip(request: Request) -> str:
    """Resolve once per request and reuse across rate limiting and logging."""
    cached = getattr(request.state, "_middleware_client_ip", None)
    if cached is not None:
        return cached
    resolved = _resolve_client_ip(request)
    request.state._middleware_client_ip = resolved
    return resolved


def _matches_path_prefix(path: str, prefix: str = "/api") -> bool:
    """Match a route root exactly or one of its descendants, never lookalikes."""
    return path == prefix or path.startswith(prefix + "/")


def _is_api_path(path: str) -> bool:
    """Publicly testable API-boundary predicate; reject lookalike prefixes."""
    return _matches_path_prefix(path, "/api")


# ── Route privacy ─────────────────────────────────────────────────────
class RoutePrivacyMiddleware(BaseHTTPMiddleware):
    """Bind one fail-closed route-domain privacy context around each API request."""

    async def dispatch(self, request: Request, call_next: Callable):
        if not _is_api_path(request.url.path):
            return await call_next(request)
        token = bind_route_privacy(request.url.path)
        try:
            return await call_next(request)
        finally:
            reset_route_privacy(token)


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
            duration = (time.perf_counter() - t0) * 1000
            log.exception(
                "method=%s path=%s status=500 dur_ms=%.2f rid=%s ip=%s err=unhandled",
                request.method,
                request.url.path,
                duration,
                rid,
                _client_ip(request),
            )
            raise

        duration = (time.perf_counter() - t0) * 1000
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
        _push_latency(duration)
        if request.url.path not in ("/api/health", "/api/_telemetry"):
            log.info(
                "method=%s path=%s status=%d dur_ms=%.2f rid=%s ip=%s",
                request.method,
                request.url.path,
                status,
                duration,
                rid,
                _client_ip(request),
            )
        return response


# ── Rate limiter ──────────────────────────────────────────────────────
class _Bucket:
    """Small monotonic token bucket."""

    __slots__ = ("tokens", "last", "capacity", "refill_per_sec")

    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = float(capacity)
        self.last = time.monotonic()

    def take(self, n: int = 1, *, now: float | None = None) -> Tuple[bool, float]:
        now = time.monotonic() if now is None else now
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
    """Per-IP token bucket with bounded, fail-closed identity state.

    Idle buckets expire after `bucket_ttl`; total identity state is capped by
    `max_buckets`. At saturation, unseen identities are rejected instead of
    evicting active buckets and gaining a fresh burst. Admission, pruning and
    token consumption are serialized per middleware instance. Activity ordering
    keeps steady-state expiry and saturation checks O(1) plus expired entries.
    """

    def __init__(
        self,
        app,
        per_minute: int | float | None = None,
        burst: int | float | None = None,
        max_buckets: int | None = None,
        bucket_ttl: float | None = None,
    ):
        super().__init__(app)
        configured_rate = per_minute if per_minute is not None else _RATE_PER_MIN
        configured_burst = burst if burst is not None else _RATE_BURST
        configured_max = max_buckets if max_buckets is not None else _MAX_BUCKETS
        configured_ttl = bucket_ttl if bucket_ttl is not None else _BUCKET_TTL

        if isinstance(configured_rate, bool) or not math.isfinite(float(configured_rate)) or configured_rate <= 0:
            raise ValueError("per_minute must be finite and positive")
        if isinstance(configured_burst, bool) or not math.isfinite(float(configured_burst)) or configured_burst <= 0:
            raise ValueError("burst must be finite and positive")
        if isinstance(configured_max, bool) or not isinstance(configured_max, int) or configured_max <= 0:
            raise ValueError("max_buckets must be a positive integer")
        if not math.isfinite(float(configured_ttl)) or configured_ttl <= 0:
            raise ValueError("bucket_ttl must be a positive finite number")

        self.per_minute = configured_rate
        self.burst = configured_burst
        self.max_buckets = configured_max
        self.bucket_ttl = float(configured_ttl)
        self._refill_per_sec = float(self.per_minute) / 60.0
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
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

    def _bucket_for(
        self, ip: str, now: float | None = None
    ) -> Tuple[_Bucket | None, float]:
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
        if not _matches_path_prefix(request.url.path):
            return await call_next(request)

        ip = _client_ip(request)
        if ip in _EXEMPT_IPS:
            return await call_next(request)

        async with self._get_state_lock():
            now = time.monotonic()
            bucket, retry = self._bucket_for(ip, now)
            if bucket is None:
                ok = False
            else:
                ok, retry = bucket.take(1, now=now)

        if not ok:
            _counts["rate_limited"] += 1
            rid = _request_id(request)
            request.state.request_id = rid
            retry_after = _bounded_retry_after(retry)
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
    """Install middleware in the intentional Starlette LIFO order.

    Client → RoutePrivacy → RateLimiter → RequestId → AccessLog → handler
    """
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(RoutePrivacyMiddleware)