"""Evidence-bound agent performance records for VOL-203.

The model separates outcome dimensions so a single self-reported success flag can
never stand in for correctness, recovery, cost, or human-intervention evidence.
Records are deterministic and bind every observation to exact execution identity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence


class AgentEvidenceError(ValueError):
    """Raised when performance evidence is incomplete or unsafe."""


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    task_id: str
    config_digest: str
    model_id: str

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if not isinstance(value, str) or not value.strip():
                raise AgentEvidenceError(f"{name} must be non-empty")


@dataclass(frozen=True)
class AgentMetric:
    name: str
    value: float
    evidence_refs: tuple[str, ...]
    unit: str = "ratio"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise AgentEvidenceError("metric name must be non-empty")
        if not math.isfinite(self.value):
            raise AgentEvidenceError("metric value must be finite")
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise AgentEvidenceError("every metric requires evidence refs")


@dataclass(frozen=True)
class AgentOutcome:
    completion: AgentMetric
    correctness: AgentMetric
    recovery: AgentMetric
    cost: AgentMetric
    human_intervention: AgentMetric

    def metrics(self) -> tuple[AgentMetric, ...]:
        values = (
            self.completion,
            self.correctness,
            self.recovery,
            self.cost,
            self.human_intervention,
        )
        expected = ("completion", "correctness", "recovery", "cost", "human_intervention")
        if tuple(metric.name for metric in values) != expected:
            raise AgentEvidenceError("outcome metrics must use canonical dimensions")
        return values


@dataclass(frozen=True)
class AgentPerformanceRecord:
    identity: AgentIdentity
    outcome: AgentOutcome
    observed_at: str
    evaluator_id: str
    sequence: int
    predecessor_digest: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.observed_at.strip() or not self.evaluator_id.strip():
            raise AgentEvidenceError("observation time and evaluator are required")
        if self.sequence < 0:
            raise AgentEvidenceError("sequence must be non-negative")
        self.outcome.metrics()
        if self.sequence == 0 and self.predecessor_digest is not None:
            raise AgentEvidenceError("genesis record cannot have predecessor")
        if self.sequence > 0 and not self.predecessor_digest:
            raise AgentEvidenceError("non-genesis record requires predecessor")
        if any(not str(k).strip() or not str(v).strip() for k, v in self.metadata.items()):
            raise AgentEvidenceError("metadata keys and values must be non-empty")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "identity": vars(self.identity),
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "unit": m.unit,
                    "evidence_refs": list(m.evidence_refs),
                }
                for m in self.outcome.metrics()
            ],
            "observed_at": self.observed_at,
            "evaluator_id": self.evaluator_id,
            "sequence": self.sequence,
            "predecessor_digest": self.predecessor_digest,
            "metadata": dict(sorted(self.metadata.items())),
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        return sha256(encoded).hexdigest()


class AgentPerformanceLedger:
    """Append-only evidence ledger with identity and hash-chain enforcement."""

    def __init__(self) -> None:
        self._records: list[AgentPerformanceRecord] = []

    def append(self, record: AgentPerformanceRecord) -> str:
        if record.sequence != len(self._records):
            raise AgentEvidenceError("sequence does not match ledger position")
        expected = self._records[-1].digest if self._records else None
        if record.predecessor_digest != expected:
            raise AgentEvidenceError("predecessor digest mismatch")
        self._records.append(record)
        return record.digest

    def records(self) -> tuple[AgentPerformanceRecord, ...]:
        return tuple(self._records)

    def compare(self, left: int, right: int) -> Mapping[str, float]:
        a, b = self._records[left], self._records[right]
        if a.identity.task_id != b.identity.task_id:
            raise AgentEvidenceError("comparison requires the same task identity")
        am = {m.name: m.value for m in a.outcome.metrics()}
        bm = {m.name: m.value for m in b.outcome.metrics()}
        return {name: bm[name] - am[name] for name in sorted(am)}


def build_outcome(
    *,
    completion: tuple[float, Sequence[str]],
    correctness: tuple[float, Sequence[str]],
    recovery: tuple[float, Sequence[str]],
    cost: tuple[float, Sequence[str]],
    human_intervention: tuple[float, Sequence[str]],
) -> AgentOutcome:
    def metric(name: str, spec: tuple[float, Sequence[str]]) -> AgentMetric:
        return AgentMetric(name, float(spec[0]), tuple(spec[1]))
    return AgentOutcome(
        completion=metric("completion", completion),
        correctness=metric("correctness", correctness),
        recovery=metric("recovery", recovery),
        cost=metric("cost", cost),
        human_intervention=metric("human_intervention", human_intervention),
    )
