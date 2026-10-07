"""
Skeleton Kernel — Core primitives for the v16 platform.

Provides:
- EntropyPool: seeded randomness for reproducible runs
- VectorClock: distributed event ordering
- InvariantLattice: runtime constraint checking
- DomainEvent + EventBus: typed pub/sub messaging
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


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
    """Typed event for the event bus."""
    topic: str
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Lightweight pub/sub event bus for subsystem communication."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[DomainEvent], None]]] = {}
        self._stats: Dict[str, int] = {"published": 0, "subscribed": 0}

    def subscribe(self, topic: str, handler: Callable[[DomainEvent], None]) -> None:
        """Subscribe a handler to a topic pattern."""
        self._subscribers.setdefault(topic, []).append(handler)
        self._stats["subscribed"] += 1

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all matching subscribers."""
        for topic, handlers in self._subscribers.items():
            if self._matches(topic, event.topic):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        pass  # Subscribers should not crash the bus
        self._stats["published"] += 1

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """Convenience: create and publish a DomainEvent."""
        self.publish(DomainEvent(topic=topic, payload=payload))

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
                        self._bus.emit("lattice.invariant.violated", {
                            "name": inv.name,
                            "subject": inv.subject,
                            "severity": inv.severity,
                        })
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
        return [type("Cap", (), {"name": k, "to_dict": lambda self: {"name": self.name}})()
                for k in self._capabilities]


class UserId:
    """Identity primitive."""

    @staticmethod
    def new() -> str:
        import uuid
        return str(uuid.uuid4())


class BlueprintId:
    """Identity primitive for blueprints."""

    @staticmethod
    def new() -> str:
        import uuid
        return f"bp-{uuid.uuid4().hex[:12]}"
