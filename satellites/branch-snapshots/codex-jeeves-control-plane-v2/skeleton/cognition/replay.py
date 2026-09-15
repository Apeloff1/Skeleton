"""Deterministic replay and divergence detection for cognitive traces."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode()).hexdigest()


@dataclass(slots=True, frozen=True)
class ReplayEvent:
    sequence: int
    kind: str
    payload: dict[str, Any]
    digest: str = ""

    def sealed(self) -> "ReplayEvent":
        return ReplayEvent(self.sequence, self.kind, dict(self.payload), _digest({"sequence": self.sequence, "kind": self.kind, "payload": self.payload}))


@dataclass(slots=True)
class ReplayTape:
    events: list[ReplayEvent] = field(default_factory=list)

    def append(self, kind: str, payload: dict[str, Any]) -> ReplayEvent:
        event = ReplayEvent(len(self.events), kind, dict(payload)).sealed()
        self.events.append(event)
        return event

    def verify(self) -> bool:
        return all(event == event.sealed() for event in self.events)

    def export(self) -> list[dict[str, Any]]:
        return [{"sequence": e.sequence, "kind": e.kind, "payload": e.payload, "digest": e.digest} for e in self.events]

    @classmethod
    def from_events(cls, events: Iterable[dict[str, Any]]) -> "ReplayTape":
        tape = cls([ReplayEvent(int(e["sequence"]), str(e["kind"]), dict(e["payload"]), str(e["digest"])) for e in events])
        if not tape.verify():
            raise ValueError("replay tape integrity check failed")
        return tape

    def divergence(self, other: "ReplayTape") -> int | None:
        for left, right in zip(self.events, other.events):
            if left != right:
                return left.sequence
        return len(self.events) if len(self.events) != len(other.events) else None
