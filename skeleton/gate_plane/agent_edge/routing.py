"""Capability / lane aware, load-aware agent routing.

An :class:`AgentRouter` picks a concrete recipient for a message addressed
by *capability* (``"plan.write"``) and optionally *lane* (``"backend"``)
instead of by agent id. Candidates come from an :class:`AgentRegistry`
(populated directly or from an Internal Systems swarm directory through an
adapter, see :mod:`skeleton.gate_plane.agent_edge.swarm_adapter`).

Selection, in order:

1. capability match (exact, or ``prefix.*`` wildcard on the endpoint side),
   lane match when requested, endpoint ``enabled`` and not draining;
2. circuit breaker from the gate plane (:class:`~skeleton.gate_plane.pipeline.BreakerRegistry`,
   one breaker per agent named ``agent:<id>``) not ``OPEN``;
3. conversation affinity: a conversation stays on the agent that served it
   while that agent remains eligible (keeps per-conversation ordering on one
   consumer);
4. least normalised load ``(in_flight + queued) / capacity`` with weight as a
   tie-breaker and agent id last so the choice is deterministic.

When every candidate is excluded only by its breaker the router reports
``all_breakers_open`` with the smallest breaker ``retry_after_s`` so callers
can surface a precise ``Retry-After``.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

from skeleton.gate_plane.agent_edge.envelope import validate_agent_id
from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry, BreakerState, CircuitBreaker
from skeleton.gate_plane.s2s.clock import Clock, system_clock

_CAP_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}(\.[a-z0-9_-]{1,32}){0,5}(\.\*)?$")
_LANE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
BREAKER_PREFIX = "agent:"
DEFAULT_AFFINITY_CAPACITY = 50_000

LoadProbe = Callable[[str], int]


class RoutingError(ValueError):
    pass


def validate_capability(cap: str) -> str:
    if not isinstance(cap, str) or not _CAP_RE.match(cap):
        raise RoutingError(f"invalid capability {cap!r}")
    return cap


def validate_lane(lane: str) -> str:
    if not isinstance(lane, str) or not _LANE_RE.match(lane):
        raise RoutingError(f"invalid lane {lane!r}")
    return lane


def capability_matches(offered: str, required: str) -> bool:
    """``offered`` satisfies ``required`` exactly or via a trailing ``.*`` wildcard."""
    if offered == required:
        return True
    if offered.endswith(".*"):
        prefix = offered[:-1]  # keep trailing dot
        return required.startswith(prefix) and len(required) > len(prefix)
    return False


@dataclass(frozen=True)
class AgentEndpoint:
    agent_id: str
    lane: str
    capabilities: FrozenSet[str]
    capacity: int = 8
    weight: int = 100
    enabled: bool = True
    draining: bool = False
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_agent_id(self.agent_id)
        validate_lane(self.lane)
        if not self.capabilities:
            raise RoutingError(f"agent {self.agent_id!r} declares no capabilities")
        for c in self.capabilities:
            validate_capability(c)
        if isinstance(self.capacity, bool) or not 1 <= int(self.capacity) <= 10_000:
            raise RoutingError("capacity must be within 1..10000")
        if isinstance(self.weight, bool) or not 1 <= int(self.weight) <= 1000:
            raise RoutingError("weight must be within 1..1000")

    @classmethod
    def build(cls, agent_id: str, lane: str, capabilities: Iterable[str], **kw: Any) -> "AgentEndpoint":
        return cls(agent_id=agent_id, lane=lane, capabilities=frozenset(capabilities), **kw)

    def offers(self, capability: str) -> bool:
        return any(capability_matches(c, capability) for c in self.capabilities)

    @property
    def available(self) -> bool:
        return self.enabled and not self.draining

    def as_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "lane": self.lane,
            "capabilities": sorted(self.capabilities),
            "capacity": self.capacity,
            "weight": self.weight,
            "enabled": self.enabled,
            "draining": self.draining,
            "labels": dict(sorted(self.labels.items())),
        }


class AgentRegistry:
    """Thread-safe agent endpoint directory with a monotonically bumped version."""

    def __init__(self, endpoints: Iterable[AgentEndpoint] = ()) -> None:
        self._lock = threading.Lock()
        self._endpoints: Dict[str, AgentEndpoint] = {}
        self.version = 0
        for ep in endpoints:
            self.upsert(ep)

    def upsert(self, endpoint: AgentEndpoint) -> None:
        with self._lock:
            self._endpoints[endpoint.agent_id] = endpoint
            self.version += 1

    def remove(self, agent_id: str) -> bool:
        with self._lock:
            gone = self._endpoints.pop(agent_id, None) is not None
            if gone:
                self.version += 1
            return gone

    def _update(self, agent_id: str, **changes: Any) -> AgentEndpoint:
        with self._lock:
            ep = self._endpoints.get(agent_id)
            if ep is None:
                raise KeyError(agent_id)
            ep = replace(ep, **changes)
            self._endpoints[agent_id] = ep
            self.version += 1
            return ep

    def set_draining(self, agent_id: str, draining: bool = True) -> AgentEndpoint:
        return self._update(agent_id, draining=bool(draining))

    def set_enabled(self, agent_id: str, enabled: bool) -> AgentEndpoint:
        return self._update(agent_id, enabled=bool(enabled))

    def get(self, agent_id: str) -> Optional[AgentEndpoint]:
        with self._lock:
            return self._endpoints.get(agent_id)

    def all(self) -> List[AgentEndpoint]:
        with self._lock:
            return [self._endpoints[k] for k in sorted(self._endpoints)]

    def lanes(self) -> List[str]:
        with self._lock:
            return sorted({e.lane for e in self._endpoints.values()})

    def find(self, capability: str, *, lane: Optional[str] = None) -> List[AgentEndpoint]:
        validate_capability(capability)
        if lane is not None:
            validate_lane(lane)
        return [e for e in self.all() if e.offers(capability) and (lane is None or e.lane == lane)]

    def __len__(self) -> int:
        with self._lock:
            return len(self._endpoints)

    def __contains__(self, agent_id: object) -> bool:
        with self._lock:
            return agent_id in self._endpoints


class RouteOutcome(str, Enum):
    ROUTED = "routed"
    AFFINITY = "affinity"
    DIRECT = "direct"
    NO_CANDIDATES = "no_candidates"
    ALL_UNAVAILABLE = "all_unavailable"
    ALL_BREAKERS_OPEN = "all_breakers_open"
    ALL_SATURATED = "all_saturated"


@dataclass(frozen=True)
class RouteDecision:
    outcome: RouteOutcome
    agent_id: Optional[str] = None
    lane: Optional[str] = None
    capability: Optional[str] = None
    load: Optional[float] = None
    considered: Tuple[str, ...] = ()
    excluded: Mapping[str, str] = field(default_factory=dict)
    retry_after_s: Optional[float] = None

    @property
    def routed(self) -> bool:
        return self.agent_id is not None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "agent_id": self.agent_id,
            "lane": self.lane,
            "capability": self.capability,
            "load": self.load,
            "considered": list(self.considered),
            "excluded": dict(sorted(self.excluded.items())),
            "retry_after_s": self.retry_after_s,
        }


class AgentRouter:
    """Routes capability-addressed messages to concrete agents."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        breakers: Optional[BreakerRegistry] = None,
        breaker_config: Optional[BreakerConfig] = None,
        load_probe: Optional[LoadProbe] = None,
        clock: Optional[Clock] = None,
        affinity_capacity: int = DEFAULT_AFFINITY_CAPACITY,
        saturation_limit: float = 1.0,
    ) -> None:
        self.registry = registry
        self.clock: Clock = clock if clock is not None else system_clock()
        self.breakers = breakers if breakers is not None else BreakerRegistry(clock=self.clock)
        self.breaker_config = breaker_config
        self.load_probe = load_probe
        if affinity_capacity < 1:
            raise ValueError("affinity_capacity must be >= 1")
        if saturation_limit <= 0:
            raise ValueError("saturation_limit must be > 0")
        self.affinity_capacity = int(affinity_capacity)
        self.saturation_limit = float(saturation_limit)
        self._affinity: "OrderedDict[str, str]" = OrderedDict()
        self._in_flight: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}

    # -- breakers / load ---------------------------------------------------------
    def breaker(self, agent_id: str) -> CircuitBreaker:
        return self.breakers.get(f"{BREAKER_PREFIX}{agent_id}", self.breaker_config)

    def load_of(self, endpoint: AgentEndpoint) -> float:
        with self._lock:
            local = self._in_flight.get(endpoint.agent_id, 0)
        queued = 0
        if self.load_probe is not None:
            try:
                queued = max(0, int(self.load_probe(endpoint.agent_id)))
            except Exception:  # noqa: BLE001 - a broken probe means "unknown", not "down"
                queued = 0
        return (local + queued) / float(endpoint.capacity)

    def begin(self, agent_id: str) -> None:
        with self._lock:
            self._in_flight[agent_id] = self._in_flight.get(agent_id, 0) + 1

    def end(self, agent_id: str, *, ok: Optional[bool]) -> None:
        """Finish a call started with :meth:`begin`; ``ok=None`` releases without scoring."""
        with self._lock:
            n = self._in_flight.get(agent_id, 0) - 1
            if n <= 0:
                self._in_flight.pop(agent_id, None)
            else:
                self._in_flight[agent_id] = n
        self.record(agent_id, ok=ok)

    def record(self, agent_id: str, *, ok: Optional[bool]) -> None:
        if ok is None:
            return
        br = self.breaker(agent_id)
        if ok:
            br.record_success()
        else:
            br.record_failure()

    def _count(self, key: str) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    # -- affinity -------------------------------------------------------------------
    def _affinity_get(self, conversation_id: Optional[str]) -> Optional[str]:
        if not conversation_id:
            return None
        with self._lock:
            agent = self._affinity.get(conversation_id)
            if agent is not None:
                self._affinity.move_to_end(conversation_id)
            return agent

    def _affinity_set(self, conversation_id: Optional[str], agent_id: str) -> None:
        if not conversation_id:
            return
        with self._lock:
            self._affinity[conversation_id] = agent_id
            self._affinity.move_to_end(conversation_id)
            while len(self._affinity) > self.affinity_capacity:
                self._affinity.popitem(last=False)

    def affinity_of(self, conversation_id: str) -> Optional[str]:
        with self._lock:
            return self._affinity.get(conversation_id)

    def forget_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._affinity.pop(conversation_id, None)

    # -- routing ----------------------------------------------------------------------
    def route(
        self,
        capability: str,
        *,
        lane: Optional[str] = None,
        conversation_id: Optional[str] = None,
        exclude: Iterable[str] = (),
    ) -> RouteDecision:
        validate_capability(capability)
        if lane is not None:
            validate_lane(lane)
        skip = frozenset(exclude)
        candidates = [e for e in self.registry.find(capability, lane=lane) if e.agent_id not in skip]
        if not candidates:
            self._count("no_candidates")
            return RouteDecision(RouteOutcome.NO_CANDIDATES, capability=capability, lane=lane)

        excluded: Dict[str, str] = {}
        eligible: List[Tuple[AgentEndpoint, float]] = []
        breaker_waits: List[float] = []
        saturated = 0
        for ep in candidates:
            if not ep.enabled:
                excluded[ep.agent_id] = "disabled"
                continue
            if ep.draining:
                excluded[ep.agent_id] = "draining"
                continue
            br = self.breaker(ep.agent_id)
            if br.state is BreakerState.OPEN:
                excluded[ep.agent_id] = "breaker_open"
                breaker_waits.append(br.retry_after_s())
                continue
            load = self.load_of(ep)
            if load >= self.saturation_limit:
                excluded[ep.agent_id] = "saturated"
                saturated += 1
                continue
            eligible.append((ep, load))

        considered = tuple(e.agent_id for e in candidates)
        if not eligible:
            only_breakers = bool(breaker_waits) and len(breaker_waits) == len(candidates)
            if only_breakers:
                self._count("all_breakers_open")
                return RouteDecision(
                    RouteOutcome.ALL_BREAKERS_OPEN, capability=capability, lane=lane, considered=considered,
                    excluded=excluded, retry_after_s=min(breaker_waits),
                )
            if saturated and saturated + len(breaker_waits) == len(candidates):
                self._count("all_saturated")
                return RouteDecision(
                    RouteOutcome.ALL_SATURATED, capability=capability, lane=lane, considered=considered,
                    excluded=excluded, retry_after_s=min(breaker_waits) if breaker_waits else 1.0,
                )
            self._count("all_unavailable")
            return RouteDecision(
                RouteOutcome.ALL_UNAVAILABLE, capability=capability, lane=lane, considered=considered, excluded=excluded
            )

        sticky = self._affinity_get(conversation_id)
        if sticky is not None:
            for ep, load in eligible:
                if ep.agent_id == sticky:
                    self._count("affinity")
                    return RouteDecision(
                        RouteOutcome.AFFINITY, ep.agent_id, ep.lane, capability, round(load, 6), considered, excluded
                    )

        eligible.sort(key=lambda pair: (round(pair[1], 9), -pair[0].weight, pair[0].agent_id))
        ep, load = eligible[0]
        self._affinity_set(conversation_id, ep.agent_id)
        self._count("routed")
        return RouteDecision(RouteOutcome.ROUTED, ep.agent_id, ep.lane, capability, round(load, 6), considered, excluded)

    def route_direct(self, agent_id: str) -> RouteDecision:
        """Validate a directly addressed recipient against registry + breaker."""
        ep = self.registry.get(agent_id)
        if ep is None:
            return RouteDecision(RouteOutcome.NO_CANDIDATES, considered=(agent_id,))
        if not ep.available:
            return RouteDecision(
                RouteOutcome.ALL_UNAVAILABLE, considered=(agent_id,),
                excluded={agent_id: "draining" if ep.draining else "disabled"},
            )
        br = self.breaker(agent_id)
        if br.state is BreakerState.OPEN:
            return RouteDecision(
                RouteOutcome.ALL_BREAKERS_OPEN, considered=(agent_id,), excluded={agent_id: "breaker_open"},
                retry_after_s=br.retry_after_s(),
            )
        return RouteDecision(RouteOutcome.DIRECT, agent_id, ep.lane, None, round(self.load_of(ep), 6), (agent_id,))

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            counts = dict(self._counts)
            in_flight = dict(self._in_flight)
            affinity = len(self._affinity)
        return {
            "counts": counts,
            "in_flight": in_flight,
            "affinity_entries": affinity,
            "breakers": {k: v for k, v in self.breakers.states().items() if k.startswith(BREAKER_PREFIX)},
            "registry_version": self.registry.version,
        }


__all__ = [
    "AgentEndpoint",
    "AgentRegistry",
    "AgentRouter",
    "BREAKER_PREFIX",
    "LoadProbe",
    "RouteDecision",
    "RouteOutcome",
    "RoutingError",
    "capability_matches",
    "validate_capability",
    "validate_lane",
]
