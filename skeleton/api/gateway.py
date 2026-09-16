"""API gateway — request routing with auth, rate limits, and transforms.

Single entry point for all Skeleton API traffic. Routes requests to
subsystem handlers through a middleware chain: RBAC auth check →
per-key rate limiting → request logging → response caching →
transform hooks. Produces per-route stats for the dashboard.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional


@dataclass
class Route:
    path: str
    handler: Callable[[Dict[str, Any]], Any]
    scope: str = "public"
    action: str = "read"
    rate_limit_per_s: float = 0.0
    cache_ttl_s: float = 0.0
    calls: int = 0
    errors: int = 0
    total_ms: float = 0.0

    def mean_ms(self) -> float:
        return self.total_ms / self.calls if self.calls else 0.0


@dataclass
class GatewayRequest:
    path: str
    actor: str = "anonymous"
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayResponse:
    status: int
    body: Any
    duration_ms: float
    cached: bool = False


class APIGateway:
    """Middleware-chained API gateway."""

    _RATE_WINDOW_S = 1.0
    _BUCKET_SWEEP_INTERVAL_S = 1.0

    def __init__(self, rbac: Any = None, rate_limiter: Any = None,
                 cache: Any = None, logger: Any = None):
        self._routes: Dict[str, Route] = {}
        self._rbac = rbac
        self._rate_limiter = rate_limiter
        self._cache = cache
        self._logger = logger
        self._transforms: List[Callable[[Any], Any]] = []
        self._buckets: Dict[str, Deque[float]] = {}
        self._last_bucket_sweep: Optional[float] = None
        self._bucket_lock = threading.Lock()
        self._stats_lock = threading.Lock()

    def route(self, path: str, handler: Callable[[Dict[str, Any]], Any], *,
              scope: str = "public", action: str = "read",
              rate_limit_per_s: float = 0.0, cache_ttl_s: float = 0.0) -> Route:
        r = Route(path=path, handler=handler, scope=scope, action=action,
                  rate_limit_per_s=rate_limit_per_s, cache_ttl_s=cache_ttl_s)
        self._routes[path] = r
        return r

    def add_transform(self, fn: Callable[[Any], Any]) -> None:
        self._transforms.append(fn)

    @staticmethod
    def _cache_key(path: str, payload: Dict[str, Any]) -> Optional[str]:
        """Build a stable cache key for JSON payloads; skip unsupported values."""
        try:
            canonical = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError):
            return None
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{path}:{digest}"

    def _sweep_rate_buckets(self, now: float) -> None:
        """Drop inactive limiter keys after their one-second window expires."""
        last_sweep = self._last_bucket_sweep
        if last_sweep is not None and now - last_sweep < self._BUCKET_SWEEP_INTERVAL_S:
            return

        cutoff = now - self._RATE_WINDOW_S
        stale = [
            key
            for key, timestamps in self._buckets.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for key in stale:
            self._buckets.pop(key, None)
        self._last_bucket_sweep = now

    def _rate_ok(self, key: str, per_s: float) -> bool:
        if per_s <= 0:
            # Unlimited routes dominate normal traffic. Avoid a monotonic clock
            # read and lock attempt entirely when there is no limiter state to
            # reclaim.
            if not self._buckets:
                return True
            now = time.monotonic()
            last_sweep = self._last_bucket_sweep
            sweep_due = (
                last_sweep is None
                or now - last_sweep >= self._BUCKET_SWEEP_INTERVAL_S
            )
            if sweep_due and self._bucket_lock.acquire(blocking=False):
                try:
                    self._sweep_rate_buckets(now)
                finally:
                    self._bucket_lock.release()
            return True

        now = time.monotonic()
        with self._bucket_lock:
            self._sweep_rate_buckets(now)
            window = self._buckets.get(key)
            if window is None:
                window = deque()
                self._buckets[key] = window

            cutoff = now - self._RATE_WINDOW_S
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= per_s:
                return False
            window.append(now)
            return True

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        route = self._routes.get(request.path)
        if not route:
            return GatewayResponse(404, {"error": "not found"}, 0.0)

        start = time.perf_counter_ns()
        if self._rbac and route.scope != "public":
            if not self._rbac.check_scope(request.actor, route.scope, route.action):
                return GatewayResponse(
                    403,
                    {"error": "forbidden"},
                    (time.perf_counter_ns() - start) / 1e6,
                )

        rate_limit_per_s = route.rate_limit_per_s
        rate_key = (
            f"{request.actor}:{route.path}" if rate_limit_per_s > 0 else ""
        )
        if not self._rate_ok(rate_key, rate_limit_per_s):
            return GatewayResponse(
                429,
                {"error": "rate limited"},
                (time.perf_counter_ns() - start) / 1e6,
            )

        cache_key: Optional[str] = None
        if self._cache and route.cache_ttl_s > 0:
            cache_key = self._cache_key(route.path, request.payload)
            if cache_key is not None:
                hit = self._cache.get("gateway", cache_key)
                if hit is not None:
                    return GatewayResponse(
                        200,
                        hit,
                        (time.perf_counter_ns() - start) / 1e6,
                        cached=True,
                    )

        error = False
        try:
            body = route.handler(request.payload)
            for transform in self._transforms:
                body = transform(body)
            status = 200
        except Exception:  # noqa: BLE001
            body = {"error": "internal server error"}
            status = 500
            error = True
        duration = (time.perf_counter_ns() - start) / 1e6
        with self._stats_lock:
            route.calls += 1
            route.total_ms += duration
            if error:
                route.errors += 1

        if self._cache and cache_key is not None and status == 200:
            self._cache.set("gateway", cache_key, body, ttl_s=route.cache_ttl_s)
        if self._logger:
            self._logger.info("gateway", f"{request.path} → {status}", actor=request.actor, ms=round(duration, 2))
        return GatewayResponse(status, body, duration)

    def card(self) -> Dict[str, Any]:
        with self._stats_lock:
            routes = {p: {
                "calls": r.calls,
                "errors": r.errors,
                "mean_ms": round(r.mean_ms(), 2),
                "scope": r.scope,
            } for p, r in self._routes.items()}
        return {
            "kind": "api-gateway-card",
            "routes": routes,
            "transforms": len(self._transforms),
        }
