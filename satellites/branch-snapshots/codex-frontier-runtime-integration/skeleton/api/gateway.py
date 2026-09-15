"""API gateway — request routing with auth, rate limits, and transforms.

Single entry point for all Skeleton API traffic. Routes requests to
subsystem handlers through a middleware chain: RBAC auth check →
per-key rate limiting → request logging → response caching →
transform hooks. Produces per-route stats for the dashboard.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


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

    def __init__(self, rbac: Any = None, rate_limiter: Any = None,
                 cache: Any = None, logger: Any = None):
        self._routes: Dict[str, Route] = {}
        self._rbac = rbac
        self._rate_limiter = rate_limiter
        self._cache = cache
        self._logger = logger
        self._transforms: List[Callable[[Any], Any]] = []
        self._buckets: Dict[str, List[float]] = {}

    def route(self, path: str, handler: Callable[[Dict[str, Any]], Any], *,
              scope: str = "public", action: str = "read",
              rate_limit_per_s: float = 0.0, cache_ttl_s: float = 0.0) -> Route:
        r = Route(path=path, handler=handler, scope=scope, action=action,
                  rate_limit_per_s=rate_limit_per_s, cache_ttl_s=cache_ttl_s)
        self._routes[path] = r
        return r

    def add_transform(self, fn: Callable[[Any], Any]) -> None:
        self._transforms.append(fn)

    def _rate_ok(self, key: str, per_s: float) -> bool:
        if per_s <= 0:
            return True
        now = time.time()
        window = [t for t in self._buckets.get(key, []) if now - t < 1.0]
        if len(window) >= per_s:
            self._buckets[key] = window
            return False
        window.append(now)
        self._buckets[key] = window
        return True

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        start = time.time_ns()
        route = self._routes.get(request.path)
        if not route:
            return GatewayResponse(404, {"error": "not found"}, 0.0)

        if self._rbac and route.scope != "public":
            if not self._rbac.check_scope(request.actor, route.scope, route.action):
                return GatewayResponse(403, {"error": "forbidden"}, (time.time_ns() - start) / 1e6)

        if not self._rate_ok(f"{request.actor}:{route.path}", route.rate_limit_per_s):
            return GatewayResponse(429, {"error": "rate limited"}, (time.time_ns() - start) / 1e6)

        cache_key = f"{route.path}:{hash(frozenset(request.payload.items())) if request.payload else 0}"
        if self._cache and route.cache_ttl_s > 0:
            hit = self._cache.get("gateway", cache_key)
            if hit is not None:
                return GatewayResponse(200, hit, (time.time_ns() - start) / 1e6, cached=True)

        route.calls += 1
        try:
            body = route.handler(request.payload)
            for transform in self._transforms:
                body = transform(body)
            status = 200
        except Exception as exc:  # noqa: BLE001
            route.errors += 1
            body = {"error": str(exc)}
            status = 500
        duration = (time.time_ns() - start) / 1e6
        route.total_ms += duration

        if self._cache and route.cache_ttl_s > 0 and status == 200:
            self._cache.set("gateway", cache_key, body, ttl_s=route.cache_ttl_s)
        if self._logger:
            self._logger.info("gateway", f"{request.path} → {status}", actor=request.actor, ms=round(duration, 2))
        return GatewayResponse(status, body, duration)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "api-gateway-card",
            "routes": {p: {
                "calls": r.calls,
                "errors": r.errors,
                "mean_ms": round(r.mean_ms(), 2),
                "scope": r.scope,
            } for p, r in self._routes.items()},
            "transforms": len(self._transforms),
        }
