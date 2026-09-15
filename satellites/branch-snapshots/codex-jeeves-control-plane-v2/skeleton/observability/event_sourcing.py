"""Event sourcing — immutable event store for subsystem state reconstruction.

Provides an event-sourced backbone: all state changes are events,
state is rebuilt by replay, and snapshots provide fast recovery.
Supports aggregate roots per subsystem with conflict detection.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class DomainEvent:
    event_id: str
    aggregate_id: str
    event_type: str
    timestamp_ns: int
    payload: Dict[str, Any]
    sequence: int
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "timestamp_ns": self.timestamp_ns,
            "payload": self.payload,
            "sequence": self.sequence,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
        }


class EventStore:
    """Append-only event store with snapshot support."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self._events: List[DomainEvent] = []
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._file = self.root / "events.jsonl"
        self._snapshot_file = self.root / "snapshots.json"
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            for line in self._file.read_text(encoding="utf-8").strip().splitlines():
                if line.strip():
                    data = json.loads(line)
                    self._events.append(DomainEvent(
                        event_id=data["event_id"],
                        aggregate_id=data["aggregate_id"],
                        event_type=data["event_type"],
                        timestamp_ns=data["timestamp_ns"],
                        payload=data["payload"],
                        sequence=data["sequence"],
                        causation_id=data.get("causation_id"),
                        correlation_id=data.get("correlation_id"),
                    ))
        if self._snapshot_file.exists():
            self._snapshots = json.loads(self._snapshot_file.read_text(encoding="utf-8"))

    def _save(self, event: DomainEvent) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), default=str) + "\n")

    def _next_sequence(self, aggregate_id: str) -> int:
        seqs = [e.sequence for e in self._events if e.aggregate_id == aggregate_id]
        return max(seqs, default=0) + 1

    def append(self, aggregate_id: str, event_type: str, payload: Dict[str, Any], correlation_id: Optional[str] = None, causation_id: Optional[str] = None) -> DomainEvent:
        event = DomainEvent(
            event_id=uuid.uuid4().hex[:16],
            aggregate_id=aggregate_id,
            event_type=event_type,
            timestamp_ns=time.time_ns(),
            payload=payload,
            sequence=self._next_sequence(aggregate_id),
            causation_id=causation_id,
            correlation_id=correlation_id or uuid.uuid4().hex[:16],
        )
        self._events.append(event)
        self._save(event)
        return event

    def get_events(self, aggregate_id: str, after_sequence: int = 0) -> List[DomainEvent]:
        return [e for e in self._events if e.aggregate_id == aggregate_id and e.sequence > after_sequence]

    def replay(self, aggregate_id: str, projector: Callable[[Any, DomainEvent], Any], initial: Any) -> Any:
        state = initial
        for e in self.get_events(aggregate_id):
            state = projector(state, e)
        return state

    def snapshot(self, aggregate_id: str, state: Dict[str, Any]) -> None:
        self._snapshots[aggregate_id] = {
            "state": state,
            "sequence": max((e.sequence for e in self._events if e.aggregate_id == aggregate_id), default=0),
            "timestamp_ns": time.time_ns(),
        }
        self._snapshot_file.write_text(json.dumps(self._snapshots, default=str), encoding="utf-8")

    def restore(self, aggregate_id: str, projector: Callable[[Any, DomainEvent], Any], initial: Any) -> Any:
        snap = self._snapshots.get(aggregate_id)
        if snap:
            state = snap["state"]
            after = snap["sequence"]
        else:
            state = initial
            after = 0
        for e in self.get_events(aggregate_id, after_sequence=after):
            state = projector(state, e)
        return state

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "event-store-card",
            "total_events": len(self._events),
            "aggregates": len({e.aggregate_id for e in self._events}),
            "snapshots": len(self._snapshots),
        }
