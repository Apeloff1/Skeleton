"""Composable request pipeline core: request/response/context and ordering.

A :class:`Pipeline` is an ordered list of :class:`Stage` objects wrapped
around a terminal handler ``handler(request, ctx) -> PipelineResponse``.
Stages are onion-style: ``stage.invoke(request, ctx, nxt)`` may short-circuit,
call ``nxt`` zero or more times (retries), or post-process the response.

Ordering is part of correctness, so it is enforced at build time. Each stage
declares a ``kind``; kinds must appear in :data:`CANONICAL_ORDER`
(outermost first)::

    telemetry      observe every outcome, including sheds and open circuits
    backpressure   shed/throttle before anything spends a retry token
    deadline       one total time budget across all attempts
    retry          re-issue retryable failures within the retry budget
    breaker        each attempt asks the breaker (a retry never bypasses it)
    attempt_timeout  per-attempt cap inside the breaker so timeouts count
    custom         caller-supplied stages, innermost

Duplicate stage names are rejected. ``Pipeline(..., strict=False)`` allows a
non-canonical order for experiments but still rejects duplicates.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable

from skeleton.gate_plane.pipeline.budget import Deadline
from skeleton.gate_plane.pipeline.errors import PipelineConfigError
from skeleton.gate_plane.s2s.clock import Clock, system_clock

CANONICAL_ORDER: Tuple[str, ...] = (
    "telemetry",
    "backpressure",
    "deadline",
    "retry",
    "breaker",
    "attempt_timeout",
    "custom",
)
_RANK = {kind: i for i, kind in enumerate(CANONICAL_ORDER)}

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class PipelineRequest:
    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    tenant_id: Optional[str] = None
    priority: int = 1
    service: Optional[str] = None

    @property
    def verb(self) -> str:
        return (self.method or "GET").upper()

    @property
    def idempotency_key(self) -> Optional[str]:
        for k, v in self.headers.items():
            if str(k).lower() == "idempotency-key" and str(v).strip():
                return str(v).strip()
        return None

    @property
    def idempotent(self) -> bool:
        return self.verb in SAFE_METHODS or self.verb in ("PUT", "DELETE") or self.idempotency_key is not None


@dataclass(frozen=True)
class PipelineResponse:
    status: int
    body: Any = None
    headers: Tuple[Tuple[str, str], ...] = ()

    def header(self, name: str) -> Optional[str]:
        low = name.lower()
        for k, v in self.headers:
            if k.lower() == low:
                return v
        return None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400


@dataclass
class CallContext:
    """Mutable per-call state shared by all stages of one pipeline run."""

    route: str
    clock: Clock
    deadline: Deadline
    upstream: Optional[str] = None
    attempt: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def event(self, name: str, **data: Any) -> None:
        self.events.append({"event": name, "attempt": self.attempt, "t": self.clock.monotonic(), **data})

    def event_names(self) -> List[str]:
        return [e["event"] for e in self.events]


Handler = Callable[[PipelineRequest, CallContext], PipelineResponse]


@runtime_checkable
class Stage(Protocol):
    name: str
    kind: str

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        ...


def validate_order(stages: Sequence[Stage], *, strict: bool = True) -> None:
    seen = set()
    last_rank = -1
    for st in stages:
        name = getattr(st, "name", None)
        kind = getattr(st, "kind", None)
        if not name or not isinstance(name, str):
            raise PipelineConfigError(f"stage {st!r} has no name")
        if name in seen:
            raise PipelineConfigError(f"duplicate stage name {name!r}")
        seen.add(name)
        if kind not in _RANK:
            raise PipelineConfigError(f"stage {name!r} has unknown kind {kind!r}")
        rank = _RANK[kind]
        if strict and rank < last_rank:
            raise PipelineConfigError(
                f"stage {name!r} ({kind}) must come before {CANONICAL_ORDER[last_rank]!r} stages"
            )
        last_rank = max(last_rank, rank)


class Pipeline:
    """Immutable ordered stage chain."""

    def __init__(
        self,
        stages: Sequence[Stage] = (),
        *,
        route: str = "*",
        upstream: Optional[str] = None,
        clock: Optional[Clock] = None,
        strict: bool = True,
    ) -> None:
        validate_order(stages, strict=strict)
        self.stages: Tuple[Stage, ...] = tuple(stages)
        self.route = route
        self.upstream = upstream
        self.clock = clock or system_clock()

    def describe(self) -> List[Dict[str, str]]:
        return [{"name": s.name, "kind": s.kind} for s in self.stages]

    def with_stage(self, stage: Stage, *, strict: bool = True) -> "Pipeline":
        """Return a new pipeline with ``stage`` inserted at its canonical slot."""
        ordered = sorted(
            list(self.stages) + [stage],
            key=lambda s: (_RANK.get(s.kind, len(_RANK)),),
        )
        return Pipeline(ordered, route=self.route, upstream=self.upstream, clock=self.clock, strict=strict)

    def new_context(self, deadline: Optional[Deadline] = None) -> CallContext:
        return CallContext(
            route=self.route,
            clock=self.clock,
            deadline=deadline or Deadline.unbounded(self.clock),
            upstream=self.upstream,
        )

    def run(
        self,
        request: PipelineRequest,
        handler: Handler,
        *,
        ctx: Optional[CallContext] = None,
    ) -> PipelineResponse:
        context = ctx or self.new_context()

        def build(i: int) -> Handler:
            if i == len(self.stages):
                return handler
            stage = self.stages[i]
            inner = build(i + 1)

            def call(req: PipelineRequest, c: CallContext) -> PipelineResponse:
                return stage.invoke(req, c, inner)

            return call

        return build(0)(request, context)


class FunctionStage:
    """Adapter turning ``fn(request, ctx, nxt)`` into a ``custom`` stage."""

    kind = "custom"

    def __init__(self, name: str, fn: Callable[[PipelineRequest, CallContext, Handler], PipelineResponse]) -> None:
        self.name = name
        self._fn = fn

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        return self._fn(request, ctx, nxt)


class StageCounter:
    """Tiny thread-safe counter helper used by stages for ``stats()``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}

    def inc(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + n

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)


__all__ = [
    "CANONICAL_ORDER",
    "CallContext",
    "FunctionStage",
    "Handler",
    "Pipeline",
    "PipelineRequest",
    "PipelineResponse",
    "SAFE_METHODS",
    "Stage",
    "StageCounter",
    "validate_order",
]
