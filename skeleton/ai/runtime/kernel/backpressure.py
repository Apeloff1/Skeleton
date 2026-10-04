"""Backpressure governor for the kernel event bus.

The bus is only as healthy as its slowest subscriber. When publish rates
outrun drain rates, queues grow silently until memory balloons and the
whole fabric stalls. This module gives the kernel a closed-loop governor:

- :class:`TokenBucket` — classic rate limiter, refill-per-second.
- :class:`LoadShedder` — drops low-priority events first when the pending
  backlog crosses a watermark, preserving CRITICAL traffic.
- :class:`BackpressureGovernor` — wires both together behind one
  ``admit(event)`` gate the bus calls before enqueueing.

Decisions are pure and synchronous; no threads, no deps.
"""

from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, Optional, Tuple

from .errors import EventBusError


class Priority(IntEnum):
    BACKGROUND = 0
    NORMAL = 10
    HIGH = 20
    CRITICAL = 30


class BackpressureError(EventBusError):
    code = "KRN.BACKPRESSURE"


class TokenBucket:
    """Fixed-capacity token bucket refilled at a steady rate."""

    __slots__ = ("capacity", "refill_per_sec", "_tokens", "_last")

    def __init__(self, capacity: float, refill_per_sec: float) -> None:
        if capacity <= 0 or refill_per_sec <= 0:
            raise BackpressureError(
                "bucket capacity and refill rate must be positive",
                context={"capacity": capacity, "refill_per_sec": refill_per_sec},
            )
        self.capacity = float(capacity)
        self.refill_per_sec = float(refill_per_sec)
        self._tokens = float(capacity)
        self._last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)
        self._last = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens


@dataclass(frozen=True)
class ShedDecision:
    admitted: bool
    reason: str
    queue_depth: int
    priority: Priority


class LoadShedder:
    """Watermark-based shedding: below low watermark admit everything,
    above high watermark admit only CRITICAL, between them admit
    HIGH and CRITICAL. Hysteresis prevents flapping.
    """

    def __init__(self, low_watermark: int, high_watermark: int) -> None:
        if not 0 < low_watermark < high_watermark:
            raise BackpressureError(
                "watermarks must satisfy 0 < low < high",
                context={"low": low_watermark, "high": high_watermark},
            )
        self.low = low_watermark
        self.high = high_watermark

    def decide(self, queue_depth: int, priority: Priority) -> ShedDecision:
        if queue_depth >= self.high:
            admitted = priority >= Priority.CRITICAL
            return ShedDecision(admitted, "high-watermark" if not admitted else "critical-bypass", queue_depth, priority)
        if queue_depth >= self.low:
            admitted = priority >= Priority.HIGH
            return ShedDecision(admitted, "low-watermark" if not admitted else "priority-bypass", queue_depth, priority)
        return ShedDecision(True, "nominal", queue_depth, priority)


@dataclass
class GovernorStats:
    admitted: int = 0
    shed: int = 0
    throttled: int = 0
    by_reason: Dict[str, int] = field(default_factory=dict)

    def record(self, key: str) -> None:
        self.by_reason[key] = self.by_reason.get(key, 0) + 1


class BackpressureGovernor:
    """Single admission gate for the event bus."""

    def __init__(
        self,
        *,
        max_events_per_sec: float = 10_000,
        burst: float = 2_000,
        low_watermark: int = 5_000,
        high_watermark: int = 20_000,
        depth_probe: Optional[Callable[[], int]] = None,
    ) -> None:
        self.bucket = TokenBucket(burst, max_events_per_sec)
        self.shedder = LoadShedder(low_watermark, high_watermark)
        self._depth_probe = depth_probe or (lambda: 0)
        self.stats = GovernorStats()

    def admit(self, event_id: str, priority: Priority = Priority.NORMAL) -> ShedDecision:
        depth = self._depth_probe()
        decision = self.shedder.decide(depth, priority)
        if not decision.admitted:
            self.stats.shed += 1
            self.stats.record(f"shed:{decision.reason}")
            return decision
        if not self.bucket.try_acquire():
            self.stats.throttled += 1
            self.stats.record("throttled:bucket")
            return ShedDecision(False, "rate-limited", depth, priority)
        self.stats.admitted += 1
        self.stats.record(f"admit:{decision.reason}")
        return decision

    def report(self) -> Dict[str, object]:
        return {
            "admitted": self.stats.admitted,
            "shed": self.stats.shed,
            "throttled": self.stats.throttled,
            "by_reason": dict(self.stats.by_reason),
            "bucket_available": round(self.bucket.available, 2),
        }


# ---------------------------------------------------------------------------
# Cross-service propagation contract (G022)
# ---------------------------------------------------------------------------

_PROPAGATION_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PressureLevel(IntEnum):
    NORMAL = 0
    SOFT = 1
    HARD = 2
    SHED = 3


class WorkClass(str, Enum):
    CONTROL = "control"
    INTERACTIVE = "interactive"
    BACKGROUND = "background"
    BULK = "bulk"


class AdmissionAction(str, Enum):
    ACCEPT = "accept"
    THROTTLE = "throttle"
    REJECT = "reject"


def _bp_text(value: object, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BackpressureError(
            f"{field} must be canonical non-empty text",
            context={"field": field},
        )
    if len(value) > maximum or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise BackpressureError(
            f"{field} is not canonical",
            context={"field": field},
        )
    return value


def _bp_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 1_000_000_000,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise BackpressureError(
            f"{field} out of range",
            context={"field": field, "value": value},
        )
    return value


def _bp_ratio(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise BackpressureError(
            f"{field} must be in [0, 1]",
            context={"field": field, "value": value},
        )
    return float(value)


def _bp_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _PROPAGATION_SHA256.fullmatch(value) is None:
        raise BackpressureError(
            f"{field} must be lowercase sha256",
            context={"field": field},
        )
    return value


@dataclass(frozen=True, slots=True)
class PropagationNodePolicy:
    name: str
    clear_fraction: float = 0.50
    soft_fraction: float = 0.70
    hard_fraction: float = 0.85
    shed_fraction: float = 0.95
    default_retry_after_ms: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _bp_text(self.name, "node.name"))
        clear = _bp_ratio(self.clear_fraction, "clear_fraction")
        soft = _bp_ratio(self.soft_fraction, "soft_fraction")
        hard = _bp_ratio(self.hard_fraction, "hard_fraction")
        shed = _bp_ratio(self.shed_fraction, "shed_fraction")
        if not 0.0 <= clear < soft < hard < shed <= 1.0:
            raise BackpressureError(
                "thresholds must satisfy clear < soft < hard < shed",
                context={"node": self.name},
            )
        object.__setattr__(self, "clear_fraction", clear)
        object.__setattr__(self, "soft_fraction", soft)
        object.__setattr__(self, "hard_fraction", hard)
        object.__setattr__(self, "shed_fraction", shed)
        object.__setattr__(
            self,
            "default_retry_after_ms",
            _bp_int(
                self.default_retry_after_ms,
                "default_retry_after_ms",
                minimum=1,
                maximum=3_600_000,
            ),
        )


@dataclass(frozen=True, slots=True)
class PressureEdge:
    upstream: str
    downstream: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "upstream", _bp_text(self.upstream, "upstream"))
        object.__setattr__(
            self, "downstream", _bp_text(self.downstream, "downstream")
        )
        if self.upstream == self.downstream:
            raise BackpressureError(
                "pressure edge cannot self-reference",
                context={"node": self.upstream},
            )


@dataclass(frozen=True, slots=True)
class BackpressureTopology:
    nodes: tuple[PropagationNodePolicy, ...]
    edges: tuple[PressureEdge, ...]

    def __post_init__(self) -> None:
        nodes = tuple(self.nodes)
        edges = tuple(self.edges)
        names = [node.name for node in nodes]
        if not nodes or len(names) != len(set(names)):
            raise BackpressureError(
                "topology requires unique nodes",
                context={"nodes": names},
            )
        known = set(names)
        children: dict[str, list[str]] = {name: [] for name in names}
        indegree: dict[str, int] = {name: 0 for name in names}
        seen_edges: set[tuple[str, str]] = set()
        for edge in edges:
            if edge.upstream not in known or edge.downstream not in known:
                raise BackpressureError(
                    "pressure edge references unknown node",
                    context={
                        "upstream": edge.upstream,
                        "downstream": edge.downstream,
                    },
                )
            pair = (edge.upstream, edge.downstream)
            if pair in seen_edges:
                raise BackpressureError(
                    "duplicate pressure edge",
                    context={"edge": pair},
                )
            seen_edges.add(pair)
            children[edge.upstream].append(edge.downstream)
            indegree[edge.downstream] += 1
        queue = sorted(name for name, degree in indegree.items() if degree == 0)
        ordered: list[str] = []
        while queue:
            node = queue.pop(0)
            ordered.append(node)
            for child in sorted(children[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
                    queue.sort()
        if len(ordered) != len(names):
            raise BackpressureError(
                "pressure topology must be acyclic",
                context={"nodes": names},
            )
        object.__setattr__(self, "nodes", tuple(sorted(nodes, key=lambda n: n.name)))
        object.__setattr__(
            self,
            "edges",
            tuple(sorted(edges, key=lambda e: (e.upstream, e.downstream))),
        )

    def policy(self, node: str) -> PropagationNodePolicy:
        canonical = _bp_text(node, "node")
        for policy in self.nodes:
            if policy.name == canonical:
                return policy
        raise BackpressureError(
            "unknown pressure node",
            context={"node": canonical},
        )

    def downstream(self, node: str) -> tuple[str, ...]:
        canonical = self.policy(node).name
        return tuple(
            edge.downstream for edge in self.edges if edge.upstream == canonical
        )


@dataclass(frozen=True, slots=True)
class PressureObservation:
    node: str
    generation: int
    queue_depth: int
    queue_capacity: int
    service_utilization: float
    cause_digest: str
    retry_after_ms: int = 0
    ttl_ticks: int = 8

    def __post_init__(self) -> None:
        object.__setattr__(self, "node", _bp_text(self.node, "node"))
        object.__setattr__(
            self, "generation", _bp_int(self.generation, "generation", minimum=1)
        )
        depth = _bp_int(self.queue_depth, "queue_depth")
        capacity = _bp_int(self.queue_capacity, "queue_capacity", minimum=1)
        if depth > capacity:
            raise BackpressureError(
                "queue depth exceeds capacity",
                context={"depth": depth, "capacity": capacity},
            )
        object.__setattr__(self, "queue_depth", depth)
        object.__setattr__(self, "queue_capacity", capacity)
        object.__setattr__(
            self,
            "service_utilization",
            _bp_ratio(self.service_utilization, "service_utilization"),
        )
        object.__setattr__(
            self, "cause_digest", _bp_digest(self.cause_digest, "cause_digest")
        )
        object.__setattr__(
            self,
            "retry_after_ms",
            _bp_int(
                self.retry_after_ms,
                "retry_after_ms",
                maximum=3_600_000,
            ),
        )
        object.__setattr__(
            self,
            "ttl_ticks",
            _bp_int(self.ttl_ticks, "ttl_ticks", minimum=1, maximum=1_000_000),
        )

    @property
    def load_fraction(self) -> float:
        return max(
            self.queue_depth / self.queue_capacity,
            self.service_utilization,
        )

    @property
    def identity(self) -> tuple[Any, ...]:
        return (
            self.node,
            self.generation,
            self.queue_depth,
            self.queue_capacity,
            self.service_utilization,
            self.cause_digest,
            self.retry_after_ms,
            self.ttl_ticks,
        )


@dataclass(frozen=True, slots=True)
class PressureSignal:
    node: str
    level: PressureLevel
    source_node: str
    generation: int
    retry_after_ms: int
    cause_digest: str
    path: tuple[str, ...]
    observed_tick: int
    expires_tick: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "level": self.level.name.lower(),
            "source_node": self.source_node,
            "generation": self.generation,
            "retry_after_ms": self.retry_after_ms,
            "cause_digest": self.cause_digest,
            "path": list(self.path),
            "observed_tick": self.observed_tick,
            "expires_tick": self.expires_tick,
        }


@dataclass(frozen=True, slots=True)
class PropagationDecision:
    node: str
    work_class: WorkClass
    priority: int
    action: AdmissionAction
    level: PressureLevel
    retry_after_ms: int
    cause_digest: str | None
    causal_path: tuple[str, ...]

    @property
    def admitted(self) -> bool:
        return self.action is AdmissionAction.ACCEPT


class BackpressurePropagationController:
    """Propagate typed overload state from dependencies to producers."""

    def __init__(self, topology: BackpressureTopology) -> None:
        if not isinstance(topology, BackpressureTopology):
            raise TypeError("topology must be BackpressureTopology")
        self.topology = topology
        self._observations: dict[str, PressureObservation] = {}
        self._local: dict[str, PressureSignal] = {}
        self._effective: dict[str, PressureSignal] = {}
        self._tick = 0
        self._lock = threading.RLock()
        self._recompute()

    @property
    def tick(self) -> int:
        with self._lock:
            return self._tick

    def observe(self, observation: PressureObservation) -> PressureSignal:
        if not isinstance(observation, PressureObservation):
            raise TypeError("observation must be PressureObservation")
        policy = self.topology.policy(observation.node)
        with self._lock:
            prior_observation = self._observations.get(observation.node)
            if prior_observation is not None:
                if observation.generation < prior_observation.generation:
                    raise BackpressureError(
                        "stale pressure generation",
                        context={"node": observation.node},
                    )
                if observation.generation == prior_observation.generation:
                    if observation.identity != prior_observation.identity:
                        raise BackpressureError(
                            "pressure generation replay changed identity",
                            context={"node": observation.node},
                        )
                    return self._effective[observation.node]

            self._tick += 1
            prior_signal = self._local.get(observation.node)
            level = self._classify(
                policy,
                observation.load_fraction,
                None if prior_signal is None else prior_signal.level,
            )
            retry_after = (
                observation.retry_after_ms
                if observation.retry_after_ms > 0
                else policy.default_retry_after_ms
            )
            self._observations[observation.node] = observation
            self._local[observation.node] = PressureSignal(
                node=observation.node,
                level=level,
                source_node=observation.node,
                generation=observation.generation,
                retry_after_ms=0 if level is PressureLevel.NORMAL else retry_after,
                cause_digest=observation.cause_digest,
                path=(observation.node,),
                observed_tick=self._tick,
                expires_tick=self._tick + observation.ttl_ticks,
            )
            self._recompute()
            return self._effective[observation.node]

    def advance(self, steps: int = 1) -> int:
        count = _bp_int(steps, "steps", minimum=1, maximum=1_000_000)
        with self._lock:
            self._tick += count
            for node in tuple(self._local):
                if self._local[node].expires_tick <= self._tick:
                    self._local.pop(node, None)
            self._recompute()
            return self._tick

    def signal(self, node: str) -> PressureSignal:
        canonical = self.topology.policy(node).name
        with self._lock:
            return self._effective[canonical]

    def decision(
        self,
        node: str,
        work_class: WorkClass | str,
        *,
        priority: int = 5,
    ) -> PropagationDecision:
        canonical = self.topology.policy(node).name
        try:
            work = (
                work_class
                if isinstance(work_class, WorkClass)
                else WorkClass(str(work_class))
            )
        except ValueError as exc:
            raise BackpressureError(
                "unknown work class",
                context={"work_class": str(work_class)},
            ) from exc
        rank = _bp_int(priority, "priority", maximum=9)
        with self._lock:
            signal = self._effective[canonical]
            action = self._action(signal.level, work, rank)
            return PropagationDecision(
                node=canonical,
                work_class=work,
                priority=rank,
                action=action,
                level=signal.level,
                retry_after_ms=(
                    0
                    if action is AdmissionAction.ACCEPT
                    else signal.retry_after_ms
                ),
                cause_digest=(
                    None
                    if signal.level is PressureLevel.NORMAL
                    else signal.cause_digest
                ),
                causal_path=(
                    ()
                    if signal.level is PressureLevel.NORMAL
                    else signal.path
                ),
            )

    def report_propagation(self) -> dict[str, Any]:
        with self._lock:
            return {
                "kind": "backpressure_propagation",
                "gap": "G022",
                "tick": self._tick,
                "signals": {
                    node: signal.as_dict()
                    for node, signal in sorted(self._effective.items())
                },
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }

    @staticmethod
    def _classify(
        policy: PropagationNodePolicy,
        load: float,
        prior: PressureLevel | None,
    ) -> PressureLevel:
        if load >= policy.shed_fraction:
            raw = PressureLevel.SHED
        elif load >= policy.hard_fraction:
            raw = PressureLevel.HARD
        elif load >= policy.soft_fraction:
            raw = PressureLevel.SOFT
        else:
            raw = PressureLevel.NORMAL
        if prior is None or raw >= prior:
            return raw
        if load <= policy.clear_fraction:
            return PressureLevel.NORMAL
        return PressureLevel(max(int(raw), int(prior) - 1))

    @staticmethod
    def _action(
        level: PressureLevel,
        work: WorkClass,
        priority: int,
    ) -> AdmissionAction:
        if level is PressureLevel.NORMAL:
            return AdmissionAction.ACCEPT
        if level is PressureLevel.SOFT:
            if work in {WorkClass.CONTROL, WorkClass.INTERACTIVE}:
                return AdmissionAction.ACCEPT
            return AdmissionAction.THROTTLE
        if level is PressureLevel.HARD:
            if work is WorkClass.CONTROL:
                return AdmissionAction.ACCEPT
            if work is WorkClass.INTERACTIVE and priority <= 2:
                return AdmissionAction.THROTTLE
            return AdmissionAction.REJECT
        if work is WorkClass.CONTROL and priority <= 1:
            return AdmissionAction.THROTTLE
        return AdmissionAction.REJECT

    def _recompute(self) -> None:
        memo: dict[str, PressureSignal] = {}

        def effective(node: str) -> PressureSignal:
            if node in memo:
                return memo[node]
            candidates: list[PressureSignal] = []
            local = self._local.get(node)
            if local is not None and local.expires_tick > self._tick:
                candidates.append(local)
            for child in self.topology.downstream(node):
                child_signal = effective(child)
                if child_signal.level is PressureLevel.NORMAL:
                    continue
                candidates.append(
                    PressureSignal(
                        node=node,
                        level=child_signal.level,
                        source_node=child_signal.source_node,
                        generation=child_signal.generation,
                        retry_after_ms=child_signal.retry_after_ms,
                        cause_digest=child_signal.cause_digest,
                        path=(node,) + child_signal.path,
                        observed_tick=child_signal.observed_tick,
                        expires_tick=child_signal.expires_tick,
                    )
                )
            if not candidates:
                selected = PressureSignal(
                    node=node,
                    level=PressureLevel.NORMAL,
                    source_node=node,
                    generation=0,
                    retry_after_ms=0,
                    cause_digest="0" * 64,
                    path=(node,),
                    observed_tick=self._tick,
                    expires_tick=self._tick,
                )
            else:
                selected = max(
                    candidates,
                    key=lambda signal: (
                        int(signal.level),
                        signal.retry_after_ms,
                        signal.observed_tick,
                        signal.source_node,
                    ),
                )
            memo[node] = selected
            return selected

        for policy in self.topology.nodes:
            effective(policy.name)
        self._effective = memo
