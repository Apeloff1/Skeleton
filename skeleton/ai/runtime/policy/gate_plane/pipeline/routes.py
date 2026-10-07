"""Per-route pipeline configuration and a router that builds/caches pipelines.

Routes reuse the Pack F authZ :class:`~skeleton.gate_plane.s2s.authz.RoutePattern`
grammar (``/literal``, ``{param}``, ``*``, trailing ``**``) and the same
most-specific-wins rule, so a route's timeout/retry/breaker policy lines up
with its authZ policy. Each route names an ``upstream``; breakers and retry
budgets are shared per upstream (one sick dependency trips once, not once
per route).

Extra stages (telemetry, backpressure) are plugged in through
``stage_factories``: ``{kind: factory(route_config) -> Stage | None}``.
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry
from skeleton.gate_plane.pipeline.budget import Deadline, RetryBudgetRegistry
from skeleton.gate_plane.pipeline.core import (
    CallContext,
    Handler,
    Pipeline,
    PipelineRequest,
    PipelineResponse,
    Stage,
)
from skeleton.gate_plane.pipeline.errors import PipelineConfigError
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.pipeline.stages import AttemptTimeoutStage, BreakerStage, DeadlineStage, RetryStage
from skeleton.gate_plane.s2s.authz import PolicyError, RoutePattern
from skeleton.gate_plane.s2s.clock import Clock, system_clock

ALL_METHODS: FrozenSet[str] = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class RouteConfig:
    name: str
    pattern: str
    upstream: str
    methods: FrozenSet[str] = ALL_METHODS
    timeout_s: Optional[float] = 10.0
    attempt_timeout_s: Optional[float] = None
    retry: RetrySpec = field(default_factory=RetrySpec)
    breaker: Optional[BreakerConfig] = field(default_factory=BreakerConfig)
    budget: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise PipelineConfigError("route name required")
        if not self.upstream:
            raise PipelineConfigError(f"route {self.name!r} needs an upstream")
        try:
            RoutePattern.parse(self.pattern)
        except PolicyError as exc:
            raise PipelineConfigError(str(exc)) from exc
        bad = {m.upper() for m in self.methods} - ALL_METHODS
        if bad:
            raise PipelineConfigError(f"route {self.name!r} has unknown methods {sorted(bad)}")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise PipelineConfigError(f"route {self.name!r} timeout_s must be > 0")
        if self.attempt_timeout_s is not None:
            if self.attempt_timeout_s <= 0:
                raise PipelineConfigError(f"route {self.name!r} attempt_timeout_s must be > 0")
            if self.timeout_s is not None and self.attempt_timeout_s > self.timeout_s:
                raise PipelineConfigError(f"route {self.name!r} attempt_timeout_s exceeds timeout_s")
        object.__setattr__(self, "methods", frozenset(m.upper() for m in self.methods))

    @property
    def compiled(self) -> RoutePattern:
        return RoutePattern.parse(self.pattern)

    def worst_case_s(self) -> Optional[float]:
        """Upper bound on wall time: the total deadline (attempts can't exceed it)."""
        if self.timeout_s is not None:
            return self.timeout_s
        if self.attempt_timeout_s is not None:
            return self.attempt_timeout_s * self.retry.max_attempts + sum(self.retry.schedule(random.Random(0)))
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pattern": self.pattern,
            "upstream": self.upstream,
            "methods": sorted(self.methods),
            "timeout_s": self.timeout_s,
            "attempt_timeout_s": self.attempt_timeout_s,
            "retry": self.retry.as_dict(),
            "breaker": None if self.breaker is None else self.breaker.as_dict(),
            "budget": dict(self.budget),
        }


class RouteTable:
    """Most-specific-match route lookup."""

    def __init__(self, routes: Iterable[RouteConfig] = ()) -> None:
        self._routes: List[Tuple[RouteConfig, RoutePattern]] = []
        for r in routes:
            self.add(r)

    def add(self, route: RouteConfig) -> None:
        compiled = route.compiled
        for existing, pat in self._routes:
            if existing.name == route.name:
                raise PipelineConfigError(f"duplicate route name {route.name!r}")
            if pat.shape() == compiled.shape() and existing.methods & route.methods:
                raise PipelineConfigError(
                    f"routes {existing.name!r} and {route.name!r} overlap on {sorted(existing.methods & route.methods)}"
                )
        self._routes.append((route, compiled))

    def __len__(self) -> int:
        return len(self._routes)

    def routes(self) -> List[RouteConfig]:
        return [r for r, _ in self._routes]

    def match(self, method: str, path: str) -> Optional[RouteConfig]:
        verb = (method or "GET").upper()
        best: Optional[Tuple[Tuple[int, int, int, int], RouteConfig]] = None
        for route, pat in self._routes:
            if verb not in route.methods:
                continue
            if pat.match(path) is None:
                continue
            spec = pat.specificity()
            if best is None or spec > best[0]:
                best = (spec, route)
        return None if best is None else best[1]


StageFactory = Callable[[RouteConfig], Optional[Stage]]


class PipelineRouter:
    """Builds one :class:`Pipeline` per route (cached) and dispatches calls.

    Unmatched requests fail closed with a 404-style :class:`PipelineConfigError`
    unless a ``default_route`` is supplied.
    """

    def __init__(
        self,
        table: RouteTable,
        *,
        clock: Optional[Clock] = None,
        breakers: Optional[BreakerRegistry] = None,
        budgets: Optional[RetryBudgetRegistry] = None,
        stage_factories: Optional[Mapping[str, StageFactory]] = None,
        default_route: Optional[RouteConfig] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.table = table
        self.clock = clock or system_clock()
        self.breakers = breakers or BreakerRegistry(clock=self.clock)
        self.budgets = budgets or RetryBudgetRegistry(clock=self.clock)
        self.stage_factories: Dict[str, StageFactory] = dict(stage_factories or {})
        self.default_route = default_route
        self.rng = rng or random.Random()
        self._cache: Dict[str, Pipeline] = {}
        self._lock = threading.Lock()

    def build(self, route: RouteConfig) -> Pipeline:
        stages: List[Stage] = []
        for kind in ("telemetry", "backpressure"):
            factory = self.stage_factories.get(kind)
            if factory is not None:
                st = factory(route)
                if st is not None:
                    stages.append(st)
        if route.timeout_s is not None:
            stages.append(DeadlineStage(route.timeout_s))
        if route.retry.max_attempts > 1:
            budget = self.budgets.get(route.upstream, **dict(route.budget))
            stages.append(RetryStage(route.retry, budget=budget, rng=self.rng))
        if route.breaker is not None:
            stages.append(BreakerStage(self.breakers.get(route.upstream, route.breaker), spec=route.retry))
        if route.attempt_timeout_s is not None:
            stages.append(AttemptTimeoutStage(route.attempt_timeout_s))
        factory = self.stage_factories.get("custom")
        if factory is not None:
            st = factory(route)
            if st is not None:
                stages.append(st)
        return Pipeline(stages, route=route.name, upstream=route.upstream, clock=self.clock)

    def pipeline_for(self, route: RouteConfig) -> Pipeline:
        with self._lock:
            pipe = self._cache.get(route.name)
            if pipe is None:
                pipe = self.build(route)
                self._cache[route.name] = pipe
            return pipe

    def resolve(self, request: PipelineRequest) -> RouteConfig:
        route = self.table.match(request.verb, request.path)
        if route is None:
            if self.default_route is None:
                raise PipelineConfigError(f"no pipeline route for {request.verb} {request.path}")
            route = self.default_route
        return route

    def call(
        self,
        request: PipelineRequest,
        handler: Handler,
        *,
        deadline: Optional[Deadline] = None,
    ) -> Tuple[PipelineResponse, CallContext]:
        pipe = self.pipeline_for(self.resolve(request))
        ctx = pipe.new_context(deadline)
        return pipe.run(request, handler, ctx=ctx), ctx

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    def describe(self) -> List[Dict[str, Any]]:
        out = []
        for route in self.table.routes():
            out.append({**route.as_dict(), "stages": self.pipeline_for(route).describe()})
        return out


def default_s2s_routes() -> RouteTable:
    """Conservative defaults for the gate plane's own s2s surfaces."""
    return RouteTable(
        [
            RouteConfig(
                name="s2s-read",
                pattern="/api/v1/**",
                upstream="skeleton-api",
                methods=frozenset({"GET", "HEAD", "OPTIONS"}),
                timeout_s=5.0,
                attempt_timeout_s=2.0,
                retry=RetrySpec(max_attempts=3),
            ),
            RouteConfig(
                name="s2s-write",
                pattern="/api/v1/**",
                upstream="skeleton-api",
                methods=frozenset({"POST", "PUT", "PATCH", "DELETE"}),
                timeout_s=10.0,
                attempt_timeout_s=5.0,
                retry=RetrySpec(max_attempts=2),
            ),
            RouteConfig(
                name="s2s-admit-pressure",
                pattern="/api/v1/admit/pressure/**",
                upstream="skeleton-api-admit",
                methods=frozenset({"GET"}),
                timeout_s=0.5,
                attempt_timeout_s=0.25,
                retry=RetrySpec(max_attempts=2, base_backoff_s=0.02, max_backoff_s=0.1),
                breaker=BreakerConfig(consecutive_failures=3, min_calls=5, window_size=10, cooldown_s=5.0),
            ),
        ]
    )


__all__ = [
    "ALL_METHODS",
    "PipelineRouter",
    "RouteConfig",
    "RouteTable",
    "StageFactory",
    "default_s2s_routes",
]
