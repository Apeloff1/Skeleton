"""Developer, operations and bounded experimental controls."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Iterable, Mapping, Sequence

from .contracts import sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class DeveloperCommand:
    command_id: str
    argv: tuple[str, ...]
    ci_equivalent: tuple[str, ...]
    mutating: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        if not self.argv or any(not isinstance(item, str) or not item for item in self.argv):
            raise ValueError("argv must be non-empty")
        if not self.ci_equivalent or any(not isinstance(item, str) or not item for item in self.ci_equivalent):
            raise ValueError("ci_equivalent must be non-empty")
        if not isinstance(self.mutating, bool):
            raise TypeError("mutating must be boolean")


@dataclass(frozen=True, slots=True)
class LocalEnvironment:
    environment_id: str
    python_version: str
    dependency_digest: str
    secret_mode: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment_id", _text(self.environment_id, "environment_id"))
        object.__setattr__(self, "python_version", _text(self.python_version, "python_version"))
        object.__setattr__(self, "dependency_digest", _sha(self.dependency_digest, "dependency_digest"))
        if self.secret_mode not in {"none", "dev_only", "isolated"}:
            raise ValueError("unsupported secret_mode")


@dataclass(frozen=True, slots=True)
class Fixture:
    fixture_id: str
    digest: str
    hermetic: bool
    external_side_effects: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "fixture_id", _text(self.fixture_id, "fixture_id"))
        object.__setattr__(self, "digest", _sha(self.digest, "digest"))
        if not isinstance(self.hermetic, bool) or not isinstance(self.external_side_effects, bool):
            raise TypeError("fixture flags must be boolean")
        if self.hermetic and self.external_side_effects:
            raise ValueError("hermetic fixture cannot have external side effects")


@dataclass(frozen=True, slots=True)
class SimulationReceipt:
    operation_id: str
    adapter_id: str
    simulated: bool
    output_digest: str

    def __post_init__(self) -> None:
        for name in ("operation_id", "adapter_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.simulated, bool):
            raise TypeError("simulated must be boolean")
        object.__setattr__(self, "output_digest", _sha(self.output_digest, "output_digest"))


@dataclass(frozen=True, slots=True)
class FuzzReproducer:
    contract_id: str
    seed: int
    input_digest: str
    failure_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _text(self.contract_id, "contract_id"))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be integer")
        object.__setattr__(self, "input_digest", _sha(self.input_digest, "input_digest"))
        object.__setattr__(self, "failure_digest", _sha(self.failure_digest, "failure_digest"))

    @property
    def digest(self) -> str:
        return sha256_json({
            "contract": self.contract_id,
            "seed": self.seed,
            "input": self.input_digest,
            "failure": self.failure_digest,
        })


@dataclass(frozen=True, slots=True)
class Invariant:
    invariant_id: str
    description: str
    predicate: Callable[[object], bool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "invariant_id", _text(self.invariant_id, "invariant_id"))
        object.__setattr__(self, "description", _text(self.description, "description"))
        if not callable(self.predicate):
            raise TypeError("predicate must be callable")

    def check(self, value: object) -> None:
        result = self.predicate(value)
        if not isinstance(result, bool):
            raise TypeError("invariant predicate must return bool")
        if not result:
            raise AssertionError(f"invariant failed: {self.invariant_id}")


@dataclass(frozen=True, slots=True)
class FormalCandidate:
    candidate_id: str
    risk_score: float
    state_space_bound: int
    executable_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "executable_reference", _text(self.executable_reference, "executable_reference"))
        if isinstance(self.risk_score, bool) or not isinstance(self.risk_score, (int, float)) or not math.isfinite(float(self.risk_score)):
            raise ValueError("risk_score must be finite")
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError("risk_score must be in [0,1]")
        if isinstance(self.state_space_bound, bool) or not isinstance(self.state_space_bound, int) or self.state_space_bound < 1:
            raise ValueError("state_space_bound must be positive integer")


class FormalCandidateRanker:
    @staticmethod
    def rank(candidates: Sequence[FormalCandidate]) -> tuple[FormalCandidate, ...]:
        return tuple(sorted(
            candidates,
            key=lambda item: (-item.risk_score, item.state_space_bound, item.candidate_id),
        ))


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    dependency_id: str
    version: str
    vulnerability_count: int
    stale: bool
    supported: bool

    def __post_init__(self) -> None:
        for name in ("dependency_id", "version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if isinstance(self.vulnerability_count, bool) or not isinstance(self.vulnerability_count, int) or self.vulnerability_count < 0:
            raise ValueError("vulnerability_count must be non-negative integer")
        if not isinstance(self.stale, bool) or not isinstance(self.supported, bool):
            raise TypeError("dependency flags must be boolean")

    @property
    def healthy(self) -> bool:
        return self.vulnerability_count == 0 and not self.stale and self.supported


@dataclass(frozen=True, slots=True)
class AdminOperation:
    operation_id: str
    principal_id: str
    action: str
    preflight_digest: str
    approved: bool

    def __post_init__(self) -> None:
        for name in ("operation_id", "principal_id", "action"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "preflight_digest", _sha(self.preflight_digest, "preflight_digest"))
        if not isinstance(self.approved, bool):
            raise TypeError("approved must be boolean")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    sequence: int
    event_id: str
    actor_id: str
    action: str
    subject_id: str
    payload_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("audit sequence must be positive integer")
        for name in ("event_id", "actor_id", "action", "subject_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "payload_digest", _sha(self.payload_digest, "payload_digest"))


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        expected = len(self._events) + 1
        if event.sequence != expected:
            raise ValueError("audit event sequence gap")
        if any(item.event_id == event.event_id for item in self._events):
            raise ValueError("duplicate audit event id")
        self._events.append(event)

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)


@dataclass(frozen=True, slots=True)
class DashboardMetric:
    metric_id: str
    value: float
    unit: str
    updated_at: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _text(self.metric_id, "metric_id"))
        object.__setattr__(self, "unit", _text(self.unit, "unit"))
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(float(self.value)):
            raise ValueError("metric value must be finite")
        if isinstance(self.updated_at, bool) or not isinstance(self.updated_at, int) or self.updated_at < 0:
            raise ValueError("updated_at must be non-negative integer")


class DashboardProjection:
    def __init__(self, *, max_age_seconds: int) -> None:
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds < 1:
            raise ValueError("max_age_seconds must be positive integer")
        self.max_age_seconds = max_age_seconds
        self._metrics: dict[str, DashboardMetric] = {}

    def update(self, metric: DashboardMetric) -> None:
        prior = self._metrics.get(metric.metric_id)
        if prior is not None and metric.updated_at < prior.updated_at:
            raise ValueError("dashboard metric cannot move backward in time")
        self._metrics[metric.metric_id] = metric

    def snapshot(self, now: int) -> Mapping[str, DashboardMetric]:
        return {
            key: value
            for key, value in sorted(self._metrics.items())
            if now - value.updated_at <= self.max_age_seconds
        }


@dataclass(frozen=True, slots=True)
class ModelRevision:
    model_id: str
    version: int
    artifact_digest: str
    eval_digest: str
    status: str = "candidate"

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("model version must be positive integer")
        object.__setattr__(self, "artifact_digest", _sha(self.artifact_digest, "artifact_digest"))
        object.__setattr__(self, "eval_digest", _sha(self.eval_digest, "eval_digest"))
        if self.status not in {"candidate", "qualified", "active", "retired"}:
            raise ValueError("unsupported model status")


class ModelOperations:
    def __init__(self) -> None:
        self._versions: dict[str, list[ModelRevision]] = {}
        self._active: dict[str, ModelRevision] = {}

    def register(self, revision: ModelRevision) -> None:
        history = self._versions.setdefault(revision.model_id, [])
        if history and revision.version <= history[-1].version:
            if revision == history[-1]:
                return
            raise ValueError("model versions must increase")
        history.append(revision)

    def activate(self, model_id: str, version: int) -> None:
        candidates = [item for item in self._versions.get(model_id, ()) if item.version == version]
        if not candidates:
            raise KeyError("unknown model version")
        revision = candidates[0]
        if revision.status not in {"qualified", "active"}:
            raise ValueError("only qualified model may activate")
        self._active[model_id] = revision

    def rollback(self, model_id: str, version: int) -> None:
        self.activate(model_id, version)


@dataclass(frozen=True, slots=True)
class TrustSignal:
    signal_id: str
    confidence: float
    evidence_count: int
    warning: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_id", _text(self.signal_id, "signal_id"))
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)) or not math.isfinite(float(self.confidence)):
            raise ValueError("confidence must be finite")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        if isinstance(self.evidence_count, bool) or not isinstance(self.evidence_count, int) or self.evidence_count < 0:
            raise ValueError("evidence_count must be non-negative integer")
        if self.warning is not None:
            object.__setattr__(self, "warning", _text(self.warning, "warning"))

    @property
    def display_confidence(self) -> float:
        if self.evidence_count == 0:
            return 0.0
        return self.confidence


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    impact: str
    batchable: bool
    expires_seconds: int

    def __post_init__(self) -> None:
        if self.impact not in {"low", "medium", "high", "critical"}:
            raise ValueError("unsupported approval impact")
        if not isinstance(self.batchable, bool):
            raise TypeError("batchable must be boolean")
        if self.impact in {"high", "critical"} and self.batchable:
            raise ValueError("high-impact approvals cannot be batched")
        if isinstance(self.expires_seconds, bool) or not isinstance(self.expires_seconds, int) or self.expires_seconds < 1:
            raise ValueError("expires_seconds must be positive integer")
