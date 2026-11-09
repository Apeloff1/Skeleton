"""Rebuildable projections over OmniFabric events.

Doctrine: events are the only truth; projections are derived, disposable,
rebuildable. A projection tracks the fabric seq it has applied through
and can be wiped + rebuilt from a tail or segment stream.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from skeleton.kernel.omnifabric.errors import ProjectionStale
from skeleton.kernel.omnifabric.events import FabricEvent


Projector = Callable[[FabricEvent, dict[str, Any]], None]


@dataclass
class ProjectionState:
    name: str
    applied_seq: int = 0
    applied_hash: str = ""
    version: int = 1
    state: dict[str, Any] = field(default_factory=dict)
    apply_count: int = 0
    rebuild_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "applied_seq": self.applied_seq,
            "applied_hash": self.applied_hash,
            "version": self.version,
            "state": dict(self.state),
            "apply_count": self.apply_count,
            "rebuild_count": self.rebuild_count,
        }


class Projection(ABC):
    """Base projection — subclasses implement ``apply_one``."""

    def __init__(self, name: str) -> None:
        self.name = str(name)
        self._lock = threading.RLock()
        self._meta = ProjectionState(name=self.name)

    @abstractmethod
    def apply_one(self, ev: FabricEvent, state: dict[str, Any]) -> None:
        ...

    def apply(self, ev: FabricEvent) -> None:
        with self._lock:
            if ev.seq <= self._meta.applied_seq:
                return  # idempotent
            if self._meta.applied_seq and ev.seq != self._meta.applied_seq + 1:
                # gap — caller should rebuild; still apply if contiguous not required
                pass
            self.apply_one(ev, self._meta.state)
            self._meta.applied_seq = ev.seq
            self._meta.applied_hash = ev.hash
            self._meta.apply_count += 1

    def apply_many(self, events: Iterable[FabricEvent]) -> int:
        n = 0
        for ev in events:
            self.apply(ev)
            n += 1
        return n

    def rebuild(self, events: Iterable[FabricEvent]) -> int:
        with self._lock:
            self._meta.state = {}
            self._meta.applied_seq = 0
            self._meta.applied_hash = ""
            self._meta.rebuild_count += 1
        return self.apply_many(events)

    def require_fresh(self, fabric_seq: int) -> None:
        with self._lock:
            if self._meta.applied_seq < fabric_seq:
                raise ProjectionStale(
                    f"projection {self.name} at {self._meta.applied_seq}, fabric at {fabric_seq}"
                )

    @property
    def state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._meta.state)

    def meta(self) -> ProjectionState:
        with self._lock:
            return ProjectionState(**self._meta.to_dict())


class CallableProjection(Projection):
    """Projection backed by a plain callable."""

    def __init__(self, name: str, projector: Projector) -> None:
        super().__init__(name)
        self._projector = projector

    def apply_one(self, ev: FabricEvent, state: dict[str, Any]) -> None:
        self._projector(ev, state)


class KindCounterProjection(Projection):
    """Counts events by kind (and optionally by ledger)."""

    def __init__(self, name: str = "kind_counter", *, by_ledger: bool = True) -> None:
        super().__init__(name)
        self._by_ledger = by_ledger

    def apply_one(self, ev: FabricEvent, state: dict[str, Any]) -> None:
        kinds = state.setdefault("kinds", {})
        kinds[ev.kind] = kinds.get(ev.kind, 0) + 1
        if self._by_ledger:
            ledgers = state.setdefault("ledgers", {})
            bucket = ledgers.setdefault(ev.ledger, {})
            bucket[ev.kind] = bucket.get(ev.kind, 0) + 1
        state["total"] = int(state.get("total", 0)) + 1


class LastValueProjection(Projection):
    """Keeps the latest payload per key extracted from the event."""

    def __init__(self, name: str, key_field: str = "key") -> None:
        super().__init__(name)
        self._key_field = key_field

    def apply_one(self, ev: FabricEvent, state: dict[str, Any]) -> None:
        key = ev.payload.get(self._key_field)
        if key is None:
            key = f"{ev.ledger}:{ev.kind}"
        values = state.setdefault("values", {})
        values[str(key)] = {
            "payload": dict(ev.payload),
            "seq": ev.seq,
            "hash": ev.hash,
            "kind": ev.kind,
            "ledger": ev.ledger,
            "ts": ev.ts,
        }


class QuorumAttestationProjection(Projection):
    """Tracks attester participation across fabric events."""

    def apply_one(self, ev: FabricEvent, state: dict[str, Any]) -> None:
        attesters = state.setdefault("attesters", {})
        for a in ev.quorum:
            attesters[a] = attesters.get(a, 0) + 1
        state["events_with_quorum"] = int(state.get("events_with_quorum", 0)) + (1 if ev.quorum else 0)
        state["events_total"] = int(state.get("events_total", 0)) + 1


class ProjectionHub:
    """Fan-out hub: observe fabric appends into many projections."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projections: dict[str, Projection] = {}

    def add(self, projection: Projection) -> None:
        with self._lock:
            self._projections[projection.name] = projection

    def remove(self, name: str) -> None:
        with self._lock:
            self._projections.pop(name, None)

    def get(self, name: str) -> Projection | None:
        with self._lock:
            return self._projections.get(name)

    def observe(self, ev: FabricEvent) -> None:
        with self._lock:
            targets = list(self._projections.values())
        for p in targets:
            p.apply(ev)

    def rebuild_all(self, events: Iterable[FabricEvent]) -> dict[str, int]:
        events = list(events)
        out: dict[str, int] = {}
        with self._lock:
            targets = list(self._projections.values())
        for p in targets:
            out[p.name] = p.rebuild(events)
        return out

    def status(self) -> list[dict[str, Any]]:
        with self._lock:
            return [p.meta().to_dict() for p in self._projections.values()]
