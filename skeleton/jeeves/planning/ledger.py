from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from threading import RLock
from typing import Iterable

from .admission import AdmissionDecision, AdmissionResult
from .models import Plan


class EventKind(str, Enum):
    CREATED = "created"
    ADMITTED = "admitted"
    REJECTED = "rejected"
    REPLANNED = "replanned"
    EXECUTION_REPORTED = "execution_reported"


@dataclass(frozen=True, slots=True)
class PlanEvent:
    sequence: int
    plan_id: str
    kind: EventKind
    detail: str
    previous_hash: str
    event_hash: str


class PlanLedger:
    """Thread-safe append-only planning ledger; it records plans, not execution authority."""
    def __init__(self) -> None:
        self._lock = RLock()
        self._events: list[PlanEvent] = []
        self._seen: set[tuple[str, EventKind, str]] = set()

    @property
    def events(self) -> tuple[PlanEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def append(self, plan_id: str, kind: EventKind, detail: str) -> PlanEvent:
        if not plan_id or len(plan_id) != 64:
            raise ValueError("invalid plan id")
        if not detail or len(detail) > 4096:
            raise ValueError("invalid event detail")
        key = (plan_id, kind, detail)
        with self._lock:
            if key in self._seen:
                raise ValueError("duplicate ledger event")
            previous = self._events[-1].event_hash if self._events else "0" * 64
            sequence = len(self._events)
            payload = {"sequence": sequence, "plan_id": plan_id, "kind": kind.value, "detail": detail, "previous_hash": previous}
            digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            event = PlanEvent(sequence, plan_id, kind, detail, previous, digest)
            self._events.append(event)
            self._seen.add(key)
            return event

    def record_plan(self, plan: Plan) -> PlanEvent:
        return self.append(plan.id, EventKind.CREATED, plan.state.value)

    def record_admission(self, result: AdmissionResult) -> PlanEvent:
        kind = EventKind.ADMITTED if result.decision is AdmissionDecision.ACCEPT else EventKind.REJECTED
        return self.append(result.plan_id, kind, result.decision.value)

    def verify(self) -> bool:
        with self._lock:
            previous = "0" * 64
            for expected_sequence, event in enumerate(self._events):
                if event.sequence != expected_sequence or event.previous_hash != previous:
                    return False
                payload = {"sequence": event.sequence, "plan_id": event.plan_id, "kind": event.kind.value, "detail": event.detail, "previous_hash": event.previous_hash}
                expected = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                if event.event_hash != expected:
                    return False
                previous = event.event_hash
            return True

    def by_plan(self, plan_id: str) -> tuple[PlanEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.plan_id == plan_id)
