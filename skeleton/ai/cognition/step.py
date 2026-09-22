"""Small, serialisable primitives for disciplined agent execution.

These objects deliberately contain no model/provider dependencies. They form a
stable seam between planning, tool execution, evaluation, and provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Evidence:
    source: str
    claim: str
    confidence: float = 0.5
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.claim.strip():
            raise ValueError("evidence source and claim are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("evidence confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "claim": self.claim, "confidence": self.confidence, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class Action:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    risk: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("action name is required")
        if not 0.0 <= self.risk <= 1.0:
            raise ValueError("action risk must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "arguments": dict(self.arguments), "risk": self.risk}


@dataclass(frozen=True)
class Outcome:
    status: str
    value: Any = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"success", "failure", "blocked", "skipped"}:
            raise ValueError("invalid outcome status")
        if self.status == "failure" and not self.error:
            raise ValueError("failure outcomes require an error")

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "value": self.value, "error": self.error}


@dataclass
class StepTrace:
    step_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def event(self, name: str, **payload: Any) -> None:
        self.events.append({"at": _now(), "name": name, **payload})

    def close(self) -> None:
        self.finished_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "started_at": self.started_at, "finished_at": self.finished_at, "events": list(self.events)}


@dataclass
class CognitiveStep:
    goal: str
    evidence: list[Evidence] = field(default_factory=list)
    action: Action | None = None
    outcome: Outcome | None = None
    trace: StepTrace = field(default_factory=StepTrace)

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("step goal is required")

    @property
    def confidence(self) -> float:
        if not self.evidence:
            return 0.0
        return sum(item.confidence for item in self.evidence) / len(self.evidence)

    def bind_action(self, action: Action) -> None:
        if self.outcome is not None:
            raise RuntimeError("completed steps cannot be mutated")
        self.action = action
        self.trace.event("action_bound", action=action.name)

    def complete(self, outcome: Outcome) -> Outcome:
        if self.outcome is not None:
            raise RuntimeError("step already completed")
        self.outcome = outcome
        self.trace.event("completed", status=outcome.status)
        self.trace.close()
        return outcome

    def to_dict(self) -> dict[str, Any]:
        return {"goal": self.goal, "evidence": [item.to_dict() for item in self.evidence], "action": self.action.to_dict() if self.action else None, "outcome": self.outcome.to_dict() if self.outcome else None, "trace": self.trace.to_dict(), "confidence": self.confidence}
