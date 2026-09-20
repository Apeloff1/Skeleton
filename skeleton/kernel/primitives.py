"""
Skeleton Kernel — Core primitives for the v16 platform.

Provides:
- EntropyPool: seeded randomness for reproducible runs
- VectorClock: distributed event ordering
- InvariantLattice: runtime constraint checking
- DomainEvent + EventBus: typed pub/sub messaging with bounded replay
"""

from __future__ import annotations

import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional


class SkeletonError(Exception):
    """Base error for all skeleton operations."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}


class BlueprintError(SkeletonError):
    """Error in blueprint construction or validation."""

    pass


class MaterialisationError(SkeletonError):
    """Error during blueprint materialization."""

    pass


@dataclass(frozen=True)
class DomainEvent:
    """Typed event for the event bus.

    Causal identity fields are excluded from dataclass equality so existing
    callers retain the original value-comparison contract.
    """

    topic: str
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex, compare=False)
    causation_id: Optional[str] = field(default=None, compare=False)

    @property
    def occurred_at(self) -> float:
        """Compatibility alias for causal consumers."""

        return self.timestamp

    def derive(
        self,
        topic: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        correlation_id: Optional[str] = None,
    ) -> "DomainEvent":
        """Create a child event preserving this event's causal context."""

        return DomainEvent(
            topic=topic,
            payload=dict(payload or {}),
            correlation_id=self.correlation_id if correlation_id is None else correlation_id,
            causation_id=self.event_id,
        )


_correlation_fallback: Optional[Callable[[], str]] = None


def register_correlation_fallback(provider: Optional[Callable[[], str]]) -> None:
    """Optionally supply active correlation when an event omits it.

    Observability installs a ContextVar-backed provider. Passing ``None``
    clears the provider (tests). Failures in the provider are ignored.
    """

    global _correlation_fallback
    _correlation_fallback = provider


def _resolve_correlation_fallback() -> str:
    provider = _correlation_fallback
    if provider is None:
        return ""
    try:
        value = provider()
    except Exception:
        return ""
    if isinstance(value, str):
        return value.strip()
    return ""


class EventBus:
    """Lightweight pub/sub event bus with bounded diagnostic replay."""

    _CORRELATION_KEYS = (
        "correlation_id",
        "request_id",
        "run_id",
        "task_id",
        "call_id",
        "rid",
    )

    def __init__(self, replay_capacity: int = 4096):
        if replay_capacity <= 0:
            raise ValueError("replay_capacity must be positive")
        self._subscribers: Dict[str, List[Callable[[DomainEvent], None]]] = {}
        self._stats: Dict[str, int] = {"published": 0, "subscribed": 0}
        self._replay: Deque[DomainEvent] = deque(maxlen=replay_capacity)

    def subscribe(self, topic: str, handler: Callable[[DomainEvent], None]) -> None:
        """Subscribe a handler to a topic pattern."""

        self._subscribers.setdefault(topic, []).append(handler)
        self._stats["subscribed"] += 1

    def publish(self, event: DomainEvent) -> DomainEvent:
        """Publish an event and retain it in the bounded replay window."""

        if not event.correlation_id:
            fallback = _resolve_correlation_fallback()
            if fallback:
                event = DomainEvent(
                    topic=event.topic,
                    payload=dict(event.payload),
                    correlation_id=fallback,
                    timestamp=event.timestamp,
                    event_id=event.event_id,
                    causation_id=event.causation_id,
                )
        self._replay.append(event)
        for topic, handlers in self._subscribers.items():
            if self._matches(topic, event.topic):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        pass  # Subscribers should not crash the bus
        self._stats["published"] += 1
        return event

    def emit(
        self,
        topic: str,
        payload: Dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> DomainEvent:
        """Create an event and preserve or infer its correlation context."""

        resolved = correlation_id
        if not resolved:
            for key in self._CORRELATION_KEYS:
                candidate = payload.get(key)
                if isinstance(candidate, str) and candidate:
                    resolved = candidate
                    break
        if not resolved:
            resolved = _resolve_correlation_fallback()
        return self.publish(
            DomainEvent(
                topic=topic,
                payload=payload,
                correlation_id=resolved,
            )
        )

    def replay(self, topic: str = "*") -> List[DomainEvent]:
        """Return retained events matching ``topic`` in publication order."""

        return [event for event in self._replay if self._matches(topic, event.topic)]

    def trace(self, correlation_id: str) -> List[DomainEvent]:
        """Return retained events belonging to one correlation context."""

        return [event for event in self._replay if event.correlation_id == correlation_id]

    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        """Simple wildcard matching: 'kernel.*' matches 'kernel.genesis'."""

        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            return topic.startswith(pattern[:-1])
        return pattern == topic


class EntropyPool:
    """Seeded randomness source for reproducible runs."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self._seed = seed

    def random(self) -> float:
        return self._rng.random()

    def choice(self, seq):
        return self._rng.choice(seq)

    def shuffle(self, seq):
        self._rng.shuffle(seq)

    def stats(self) -> Dict[str, Any]:
        return {"seed": self._seed, "calls": 0}


class VectorClock:
    """Lamport-style vector clock for distributed event ordering."""

    def __init__(self):
        self._time: Dict[str, int] = {}

    def tick(self, node: str) -> None:
        self._time[node] = self._time.get(node, 0) + 1

    def merge(self, other: "VectorClock") -> None:
        for node, t in other._time.items():
            self._time[node] = max(self._time.get(node, 0), t)

    def snapshot(self) -> Dict[str, int]:
        return dict(self._time)


@dataclass
class Invariant:
    """A runtime constraint to be checked by the lattice."""

    name: str
    subject: str
    snapshot: Callable[[], Any]
    predicate: Callable[[Any], bool]
    severity: str = "ERROR"


class InvariantLattice:
    """Registry and evaluator for runtime invariants."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._invariants: List[Invariant] = []
        self._bus = bus

    def register(self, invariant: Invariant) -> None:
        self._invariants.append(invariant)
        if self._bus:
            self._bus.emit("lattice.invariant.registered", {"name": invariant.name})

    def evaluate(self) -> List[str]:
        """Evaluate all invariants, return list of violations."""

        violations = []
        for inv in self._invariants:
            try:
                state = inv.snapshot()
                if not inv.predicate(state):
                    violations.append(inv.name)
                    if self._bus:
                        self._bus.emit(
                            "lattice.invariant.violated",
                            {
                                "name": inv.name,
                                "subject": inv.subject,
                                "severity": inv.severity,
                            },
                        )
            except Exception as e:
                violations.append(f"{inv.name}: {e}")
        return violations


class CapabilityRegistry:
    """Registry for subsystem capabilities."""

    def __init__(self):
        self._capabilities: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._capabilities[name] = metadata or {}

    def list(self) -> List[Any]:
        return [
            type("Cap", (), {"name": k, "to_dict": lambda self: {"name": self.name}})()
            for k in self._capabilities
        ]


class UserId:
    """Identity primitive."""

    @staticmethod
    def new() -> str:
        return str(uuid.uuid4())


class BlueprintId:
    """Identity primitive for blueprints."""

    @staticmethod
    def new() -> str:
        return f"bp-{uuid.uuid4().hex[:12]}"
