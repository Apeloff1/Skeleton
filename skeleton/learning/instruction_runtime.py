"""Evidence-grounded instruction runtime for VOL-074.

The runtime deliberately separates three planes:

1. observed learner evidence -- immutable records of what happened;
2. inferred learner state -- mastery/uncertainty derived from evidence;
3. instructional policy -- plans chosen from objective/prerequisite state.

Engagement is never treated as a learning outcome. Outcome evaluation is based
on mastery change, uncertainty change, correction behavior, transfer evidence,
and retention evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Iterable, Mapping, Sequence

INSTRUCTION_SCHEMA = "skeleton.learning.instruction-runtime.v1"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 4096
_MAX_OBJECTIVES = 4096
_MAX_EVIDENCE = 100_000
_MAX_PLAN_STEPS = 64
_PRIOR_ALPHA = 1.0
_PRIOR_BETA = 1.0
_PRIOR_STDDEV = math.sqrt(1.0 / 12.0)


class InstructionRuntimeError(RuntimeError):
    """Learning evidence, inference, planning, or outcome contract failed."""


class LearnerEvidenceKind(str, Enum):
    ATTEMPT = "attempt"
    CORRECTION = "correction"
    EXPLANATION_CHECK = "explanation_check"
    TRANSFER = "transfer"
    RETENTION = "retention"


class InstructionMode(str, Enum):
    ASSESS = "assess"
    EXPLAIN = "explain"
    PRACTICE = "practice"
    CORRECT = "correct"
    REVIEW = "review"
    TRANSFER = "transfer"


class OutcomeStatus(str, Enum):
    IMPROVED = "improved"
    STABLE = "stable"
    REGRESSED = "regressed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def _token(value: object, field: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise InstructionRuntimeError(f"{field} must be text")
    if value != value.strip() or not value or len(value) > maximum:
        raise InstructionRuntimeError(f"{field} must be canonical non-empty text")
    if maximum <= 128 and not _TOKEN_RE.fullmatch(value):
        raise InstructionRuntimeError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise InstructionRuntimeError(f"{field} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise InstructionRuntimeError(f"{field} must be non-empty bounded text")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in normalized):
        raise InstructionRuntimeError(f"{field} contains control characters")
    return normalized


def _unit(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InstructionRuntimeError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise InstructionRuntimeError(f"{field} must be finite within [0, 1]")
    return result


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InstructionRuntimeError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise InstructionRuntimeError(f"{field} must be finite and non-negative")
    return result


def _nonnegative_int(value: object, field: str, *, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InstructionRuntimeError(f"{field} must be an integer")
    if not 0 <= value <= maximum:
        raise InstructionRuntimeError(f"{field} must be within [0, {maximum}]")
    return value


def _positive_int(value: object, field: str, *, maximum: int = 1_000_000) -> int:
    result = _nonnegative_int(value, field, maximum=maximum)
    if result == 0:
        raise InstructionRuntimeError(f"{field} must be positive")
    return result


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise InstructionRuntimeError(f"{field} must be lowercase sha256")
    return value


def _canonical_json(value: object, field: str = "payload") -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InstructionRuntimeError(
            f"{field} must be deterministic JSON"
        ) from exc


def _digest(value: object, field: str = "payload") -> str:
    return sha256(_canonical_json(value, field)).hexdigest()


def _kind_weight(kind: LearnerEvidenceKind) -> float:
    return {
        LearnerEvidenceKind.ATTEMPT: 1.00,
        LearnerEvidenceKind.CORRECTION: 0.90,
        LearnerEvidenceKind.EXPLANATION_CHECK: 0.75,
        LearnerEvidenceKind.TRANSFER: 1.40,
        LearnerEvidenceKind.RETENTION: 1.30,
    }[kind]


@dataclass(frozen=True, slots=True)
class LearnerEvidence:
    """One observed learner event.

    This record intentionally contains no inferred mastery or inferred
    confidence. Those values are produced by LearnerStateEstimator.
    """

    evidence_id: str
    learner_id: str
    objective_id: str
    attempt_id: str
    kind: LearnerEvidenceKind
    observed_at: float
    success: bool
    score: float
    hints_used: int
    source_ref: str
    response_digest: str
    success_threshold: float = 0.5
    prior_attempt_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _token(self.evidence_id, "evidence_id"),
        )
        object.__setattr__(
            self,
            "learner_id",
            _token(self.learner_id, "learner_id"),
        )
        object.__setattr__(
            self,
            "objective_id",
            _token(self.objective_id, "objective_id"),
        )
        object.__setattr__(
            self,
            "attempt_id",
            _token(self.attempt_id, "attempt_id"),
        )
        if not isinstance(self.kind, LearnerEvidenceKind):
            raise InstructionRuntimeError(
                "kind must be LearnerEvidenceKind"
            )
        object.__setattr__(
            self,
            "observed_at",
            _finite_nonnegative(self.observed_at, "observed_at"),
        )
        if not isinstance(self.success, bool):
            raise InstructionRuntimeError("success must be boolean")
        object.__setattr__(self, "score", _unit(self.score, "score"))
        object.__setattr__(
            self,
            "hints_used",
            _nonnegative_int(
                self.hints_used,
                "hints_used",
                maximum=10_000,
            ),
        )
        object.__setattr__(
            self,
            "source_ref",
            _text(self.source_ref, "source_ref", maximum=1024),
        )
        object.__setattr__(
            self,
            "response_digest",
            _sha256(self.response_digest, "response_digest"),
        )
        object.__setattr__(
            self,
            "success_threshold",
            _unit(self.success_threshold, "success_threshold"),
        )
        observed_success = self.score >= self.success_threshold
        if self.success is not observed_success:
            raise InstructionRuntimeError(
                "success must match score against success_threshold"
            )

        if self.kind is LearnerEvidenceKind.CORRECTION:
            if self.prior_attempt_id is None:
                raise InstructionRuntimeError(
                    "correction evidence requires prior_attempt_id"
                )
            object.__setattr__(
                self,
                "prior_attempt_id",
                _token(self.prior_attempt_id, "prior_attempt_id"),
            )
            if self.prior_attempt_id == self.attempt_id:
                raise InstructionRuntimeError(
                    "correction cannot reference its own attempt_id"
                )
        elif self.prior_attempt_id is not None:
            raise InstructionRuntimeError(
                "prior_attempt_id is reserved for correction evidence"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "learner-evidence",
                "evidence_id": self.evidence_id,
                "learner_id": self.learner_id,
                "objective_id": self.objective_id,
                "attempt_id": self.attempt_id,
                "evidence_kind": self.kind.value,
                "observed_at": self.observed_at,
                "success": self.success,
                "score": self.score,
                "hints_used": self.hints_used,
                "source_ref": self.source_ref,
                "response_digest": self.response_digest,
                "success_threshold": self.success_threshold,
                "prior_attempt_id": self.prior_attempt_id,
            }
        )


@dataclass(frozen=True, slots=True)
class LearnerSkillState:
    """Inferred state derived from immutable learner evidence."""

    learner_id: str
    objective_id: str
    mastery: float
    uncertainty: float
    effective_evidence: float
    evidence_count: int
    successes: int
    failures: int
    correction_attempts: int
    correction_successes: int
    correction_success_rate: float | None
    transfer_evidence: int
    retention_evidence: int
    last_observed_at: float | None
    latest_success: bool | None
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "learner_id",
            _token(self.learner_id, "learner_id"),
        )
        object.__setattr__(
            self,
            "objective_id",
            _token(self.objective_id, "objective_id"),
        )
        object.__setattr__(
            self,
            "mastery",
            _unit(self.mastery, "mastery"),
        )
        object.__setattr__(
            self,
            "uncertainty",
            _unit(self.uncertainty, "uncertainty"),
        )
        object.__setattr__(
            self,
            "effective_evidence",
            _finite_nonnegative(
                self.effective_evidence,
                "effective_evidence",
            ),
        )
        for field in (
            "evidence_count",
            "successes",
            "failures",
            "correction_attempts",
            "correction_successes",
            "transfer_evidence",
            "retention_evidence",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        if self.successes + self.failures != self.evidence_count:
            raise InstructionRuntimeError(
                "success/failure counts must equal evidence_count"
            )
        if self.correction_successes > self.correction_attempts:
            raise InstructionRuntimeError(
                "correction successes exceed correction attempts"
            )
        if self.correction_success_rate is not None:
            object.__setattr__(
                self,
                "correction_success_rate",
                _unit(
                    self.correction_success_rate,
                    "correction_success_rate",
                ),
            )
        if self.correction_attempts == 0 and self.correction_success_rate is not None:
            raise InstructionRuntimeError(
                "correction_success_rate requires correction evidence"
            )
        if self.correction_attempts > 0 and self.correction_success_rate is None:
            raise InstructionRuntimeError(
                "correction evidence requires correction_success_rate"
            )
        if self.last_observed_at is not None:
            object.__setattr__(
                self,
                "last_observed_at",
                _finite_nonnegative(
                    self.last_observed_at,
                    "last_observed_at",
                ),
            )
        if self.latest_success is not None and not isinstance(
            self.latest_success,
            bool,
        ):
            raise InstructionRuntimeError(
                "latest_success must be boolean or None"
            )
        object.__setattr__(
            self,
            "evidence_digest",
            _sha256(self.evidence_digest, "evidence_digest"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "learner-skill-state",
                "learner_id": self.learner_id,
                "objective_id": self.objective_id,
                "mastery": self.mastery,
                "uncertainty": self.uncertainty,
                "effective_evidence": self.effective_evidence,
                "evidence_count": self.evidence_count,
                "successes": self.successes,
                "failures": self.failures,
                "correction_attempts": self.correction_attempts,
                "correction_successes": self.correction_successes,
                "correction_success_rate": self.correction_success_rate,
                "transfer_evidence": self.transfer_evidence,
                "retention_evidence": self.retention_evidence,
                "last_observed_at": self.last_observed_at,
                "latest_success": self.latest_success,
                "evidence_digest": self.evidence_digest,
            }
        )


class LearnerStateEstimator:
    """Deterministic uncertainty-aware state inference.

    A Beta posterior is used as an interpretable evidence accumulator. Hints
    reduce evidence independence rather than being treated as engagement.
    Transfer and retention evidence receive stronger weights than ordinary
    attempts. The estimator never mutates or rewrites observed evidence.
    """

    def infer(
        self,
        learner_id: str,
        objective_id: str,
        evidence: Iterable[LearnerEvidence],
    ) -> LearnerSkillState:
        normalized_learner = _token(learner_id, "learner_id")
        normalized_objective = _token(objective_id, "objective_id")

        records = tuple(
            sorted(
                evidence,
                key=lambda item: (
                    item.observed_at,
                    item.evidence_id,
                ),
            )
        )
        if len(records) > _MAX_EVIDENCE:
            raise InstructionRuntimeError(
                f"evidence exceeds {_MAX_EVIDENCE} records"
            )

        alpha = _PRIOR_ALPHA
        beta = _PRIOR_BETA
        effective = 0.0
        successes = 0
        failures = 0
        correction_attempts = 0
        correction_successes = 0
        transfer_evidence = 0
        retention_evidence = 0
        latest_success: bool | None = None
        last_observed_at: float | None = None

        seen_ids: set[str] = set()
        by_attempt: dict[str, LearnerEvidence] = {}
        digests: list[str] = []
        for record in records:
            if not isinstance(record, LearnerEvidence):
                raise TypeError(
                    "evidence must contain LearnerEvidence"
                )
            if record.learner_id != normalized_learner:
                raise InstructionRuntimeError(
                    "evidence learner identity mismatch"
                )
            if record.objective_id != normalized_objective:
                raise InstructionRuntimeError(
                    "evidence objective identity mismatch"
                )
            if record.evidence_id in seen_ids:
                raise InstructionRuntimeError(
                    "duplicate evidence identity"
                )
            if record.attempt_id in by_attempt:
                raise InstructionRuntimeError(
                    "duplicate attempt identity"
                )
            seen_ids.add(record.evidence_id)
            by_attempt[record.attempt_id] = record
            digests.append(record.digest)

        for record in records:
            if record.kind is LearnerEvidenceKind.CORRECTION:
                prior = by_attempt.get(record.prior_attempt_id or "")
                if prior is None:
                    raise InstructionRuntimeError(
                        "correction references unknown prior attempt"
                    )
                if prior.success:
                    raise InstructionRuntimeError(
                        "correction must reference an unsuccessful attempt"
                    )
                if prior.observed_at > record.observed_at:
                    raise InstructionRuntimeError(
                        "correction cannot predate prior attempt"
                    )

        for record in records:
            weight = _kind_weight(record.kind)
            weight /= 1.0 + (0.25 * record.hints_used)
            effective += weight

            alpha += weight * record.score
            beta += weight * (1.0 - record.score)
            successes += int(record.success)
            failures += int(not record.success)

            if record.kind is LearnerEvidenceKind.CORRECTION:
                correction_attempts += 1
                correction_successes += int(record.success)
            elif record.kind is LearnerEvidenceKind.TRANSFER:
                transfer_evidence += 1
            elif record.kind is LearnerEvidenceKind.RETENTION:
                retention_evidence += 1

            last_observed_at = record.observed_at

        if records:
            assert last_observed_at is not None
            latest_success = all(
                record.success
                for record in records
                if record.observed_at == last_observed_at
            )

        total = alpha + beta
        mastery = alpha / total
        variance = (alpha * beta) / (
            (total * total) * (total + 1.0)
        )
        uncertainty = min(
            1.0,
            max(0.0, math.sqrt(variance) / _PRIOR_STDDEV),
        )
        correction_rate = (
            None
            if correction_attempts == 0
            else correction_successes / correction_attempts
        )
        evidence_digest = _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "learner-evidence-set",
                "learner_id": normalized_learner,
                "objective_id": normalized_objective,
                "records": digests,
            }
        )

        return LearnerSkillState(
            learner_id=normalized_learner,
            objective_id=normalized_objective,
            mastery=mastery,
            uncertainty=uncertainty,
            effective_evidence=effective,
            evidence_count=len(records),
            successes=successes,
            failures=failures,
            correction_attempts=correction_attempts,
            correction_successes=correction_successes,
            correction_success_rate=correction_rate,
            transfer_evidence=transfer_evidence,
            retention_evidence=retention_evidence,
            last_observed_at=last_observed_at,
            latest_success=latest_success,
            evidence_digest=evidence_digest,
        )


@dataclass(frozen=True, slots=True)
class LearningObjective:
    objective_id: str
    skill_id: str
    description: str
    prerequisites: tuple[str, ...] = ()
    mastery_target: float = 0.75
    max_uncertainty: float = 0.35
    minimum_effective_evidence: float = 2.0
    require_transfer: bool = False
    require_retention: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_id",
            _token(self.objective_id, "objective_id"),
        )
        object.__setattr__(
            self,
            "skill_id",
            _token(self.skill_id, "skill_id"),
        )
        object.__setattr__(
            self,
            "description",
            _text(self.description, "description"),
        )
        if not isinstance(self.prerequisites, tuple):
            raise InstructionRuntimeError(
                "prerequisites must be a tuple"
            )
        normalized: list[str] = []
        for prerequisite in self.prerequisites:
            token = _token(prerequisite, "prerequisite")
            if token == self.objective_id:
                raise InstructionRuntimeError(
                    "objective cannot require itself"
                )
            if token in normalized:
                raise InstructionRuntimeError(
                    "duplicate prerequisite"
                )
            normalized.append(token)
        object.__setattr__(
            self,
            "prerequisites",
            tuple(sorted(normalized)),
        )
        object.__setattr__(
            self,
            "mastery_target",
            _unit(self.mastery_target, "mastery_target"),
        )
        object.__setattr__(
            self,
            "max_uncertainty",
            _unit(self.max_uncertainty, "max_uncertainty"),
        )
        object.__setattr__(
            self,
            "minimum_effective_evidence",
            _finite_nonnegative(
                self.minimum_effective_evidence,
                "minimum_effective_evidence",
            ),
        )
        if not isinstance(self.require_transfer, bool):
            raise InstructionRuntimeError(
                "require_transfer must be boolean"
            )
        if not isinstance(self.require_retention, bool):
            raise InstructionRuntimeError(
                "require_retention must be boolean"
            )

    def is_satisfied(
        self,
        state: LearnerSkillState | None,
    ) -> bool:
        if state is None:
            return False
        if state.objective_id != self.objective_id:
            raise InstructionRuntimeError(
                "state/objective identity mismatch"
            )
        if state.mastery < self.mastery_target:
            return False
        if state.uncertainty > self.max_uncertainty:
            return False
        if state.effective_evidence < self.minimum_effective_evidence:
            return False
        if self.require_transfer and state.transfer_evidence == 0:
            return False
        if self.require_retention and state.retention_evidence == 0:
            return False
        return True

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "learning-objective",
                "objective_id": self.objective_id,
                "skill_id": self.skill_id,
                "description": self.description,
                "prerequisites": list(self.prerequisites),
                "mastery_target": self.mastery_target,
                "max_uncertainty": self.max_uncertainty,
                "minimum_effective_evidence": (
                    self.minimum_effective_evidence
                ),
                "require_transfer": self.require_transfer,
                "require_retention": self.require_retention,
            }
        )


@dataclass(frozen=True, slots=True)
class LearningObjectiveGraph:
    objectives: tuple[LearningObjective, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.objectives, tuple) or not self.objectives:
            raise InstructionRuntimeError(
                "objectives must be a non-empty tuple"
            )
        if len(self.objectives) > _MAX_OBJECTIVES:
            raise InstructionRuntimeError(
                f"objectives exceed {_MAX_OBJECTIVES}"
            )
        by_id: dict[str, LearningObjective] = {}
        for objective in self.objectives:
            if not isinstance(objective, LearningObjective):
                raise InstructionRuntimeError(
                    "objectives must contain LearningObjective"
                )
            if objective.objective_id in by_id:
                raise InstructionRuntimeError(
                    "duplicate objective identity"
                )
            by_id[objective.objective_id] = objective

        for objective in by_id.values():
            for prerequisite in objective.prerequisites:
                if prerequisite not in by_id:
                    raise InstructionRuntimeError(
                        f"unknown prerequisite {prerequisite}"
                    )

        ordered = self._topological(by_id)
        object.__setattr__(self, "objectives", ordered)

    @staticmethod
    def _topological(
        by_id: Mapping[str, LearningObjective],
    ) -> tuple[LearningObjective, ...]:
        visiting: set[str] = set()
        visited: set[str] = set()
        output: list[LearningObjective] = []

        def visit(objective_id: str) -> None:
            if objective_id in visiting:
                raise InstructionRuntimeError(
                    "objective prerequisite cycle"
                )
            if objective_id in visited:
                return
            visiting.add(objective_id)
            objective = by_id[objective_id]
            for prerequisite in objective.prerequisites:
                visit(prerequisite)
            visiting.remove(objective_id)
            visited.add(objective_id)
            output.append(objective)

        for objective_id in sorted(by_id):
            visit(objective_id)
        return tuple(output)

    @property
    def by_id(self) -> dict[str, LearningObjective]:
        return {
            objective.objective_id: objective
            for objective in self.objectives
        }

    def ready(
        self,
        states: Mapping[str, LearnerSkillState],
    ) -> tuple[LearningObjective, ...]:
        by_id = self.by_id
        ready: list[LearningObjective] = []
        for objective in self.objectives:
            prerequisites_satisfied = all(
                by_id[prerequisite].is_satisfied(
                    states.get(prerequisite)
                )
                for prerequisite in objective.prerequisites
            )
            if prerequisites_satisfied:
                ready.append(objective)
        return tuple(ready)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "objective-graph",
                "objectives": [
                    objective.digest for objective in self.objectives
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class InstructionStep:
    step_id: str
    objective_id: str
    mode: InstructionMode
    rationale: str
    required_evidence_kind: LearnerEvidenceKind
    success_threshold: float
    max_hints: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step_id",
            _token(self.step_id, "step_id"),
        )
        object.__setattr__(
            self,
            "objective_id",
            _token(self.objective_id, "objective_id"),
        )
        if not isinstance(self.mode, InstructionMode):
            raise InstructionRuntimeError(
                "mode must be InstructionMode"
            )
        object.__setattr__(
            self,
            "rationale",
            _text(self.rationale, "rationale"),
        )
        if not isinstance(
            self.required_evidence_kind,
            LearnerEvidenceKind,
        ):
            raise InstructionRuntimeError(
                "required_evidence_kind must be LearnerEvidenceKind"
            )
        object.__setattr__(
            self,
            "success_threshold",
            _unit(self.success_threshold, "success_threshold"),
        )
        object.__setattr__(
            self,
            "max_hints",
            _nonnegative_int(
                self.max_hints,
                "max_hints",
                maximum=100,
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "instruction-step",
                "step_id": self.step_id,
                "objective_id": self.objective_id,
                "mode": self.mode.value,
                "rationale": self.rationale,
                "required_evidence_kind": (
                    self.required_evidence_kind.value
                ),
                "success_threshold": self.success_threshold,
                "max_hints": self.max_hints,
            }
        )


@dataclass(frozen=True, slots=True)
class InstructionPlan:
    learner_id: str
    objective_graph_digest: str
    state_digest: str
    steps: tuple[InstructionStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "learner_id",
            _token(self.learner_id, "learner_id"),
        )
        object.__setattr__(
            self,
            "objective_graph_digest",
            _sha256(
                self.objective_graph_digest,
                "objective_graph_digest",
            ),
        )
        object.__setattr__(
            self,
            "state_digest",
            _sha256(self.state_digest, "state_digest"),
        )
        if not isinstance(self.steps, tuple):
            raise InstructionRuntimeError(
                "steps must be a tuple"
            )
        if len(self.steps) > _MAX_PLAN_STEPS:
            raise InstructionRuntimeError(
                f"steps exceed {_MAX_PLAN_STEPS}"
            )
        ids: set[str] = set()
        for step in self.steps:
            if not isinstance(step, InstructionStep):
                raise InstructionRuntimeError(
                    "steps must contain InstructionStep"
                )
            if step.step_id in ids:
                raise InstructionRuntimeError(
                    "duplicate instruction step identity"
                )
            ids.add(step.step_id)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "instruction-plan",
                "learner_id": self.learner_id,
                "objective_graph_digest": (
                    self.objective_graph_digest
                ),
                "state_digest": self.state_digest,
                "steps": [step.digest for step in self.steps],
            }
        )


class InstructionPlanner:
    """Choose bounded instruction steps from objective and learner state."""

    @staticmethod
    def _state_digest(
        learner_id: str,
        states: Mapping[str, LearnerSkillState],
    ) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "instruction-state-set",
                "learner_id": learner_id,
                "states": [
                    {
                        "objective_id": objective_id,
                        "digest": states[objective_id].digest,
                    }
                    for objective_id in sorted(states)
                ],
            }
        )

    @staticmethod
    def _mode_for(
        objective: LearningObjective,
        state: LearnerSkillState | None,
    ) -> tuple[
        InstructionMode,
        LearnerEvidenceKind,
        str,
        int,
    ]:
        if state is None or state.evidence_count == 0:
            return (
                InstructionMode.ASSESS,
                LearnerEvidenceKind.ATTEMPT,
                "Collect direct baseline evidence before inferring mastery.",
                0,
            )
        if state.latest_success is False:
            return (
                InstructionMode.CORRECT,
                LearnerEvidenceKind.CORRECTION,
                "Correct the latest observed failure before adding new material.",
                2,
            )
        if (
            state.effective_evidence
            < objective.minimum_effective_evidence
            or state.uncertainty > objective.max_uncertainty
        ):
            return (
                InstructionMode.ASSESS,
                LearnerEvidenceKind.EXPLANATION_CHECK,
                "Reduce learner-state uncertainty with direct evidence.",
                1,
            )
        if state.mastery < min(0.40, objective.mastery_target):
            return (
                InstructionMode.EXPLAIN,
                LearnerEvidenceKind.EXPLANATION_CHECK,
                "Mastery is low enough to justify explicit explanation and checking.",
                3,
            )
        if state.mastery < objective.mastery_target:
            return (
                InstructionMode.PRACTICE,
                LearnerEvidenceKind.ATTEMPT,
                "Practice the objective until the mastery target is supported.",
                2,
            )
        if objective.require_transfer and state.transfer_evidence == 0:
            return (
                InstructionMode.TRANSFER,
                LearnerEvidenceKind.TRANSFER,
                "Demonstrate the skill in a distinct transfer context.",
                1,
            )
        if objective.require_retention and state.retention_evidence == 0:
            return (
                InstructionMode.REVIEW,
                LearnerEvidenceKind.RETENTION,
                "Collect delayed retention evidence before completion.",
                1,
            )
        return (
            InstructionMode.PRACTICE,
            LearnerEvidenceKind.ATTEMPT,
            "Objective is ready for a final mastery-confirming attempt.",
            1,
        )

    def plan(
        self,
        *,
        learner_id: str,
        graph: LearningObjectiveGraph,
        states: Mapping[str, LearnerSkillState],
        max_steps: int = 8,
    ) -> InstructionPlan:
        normalized_learner = _token(learner_id, "learner_id")
        if not isinstance(graph, LearningObjectiveGraph):
            raise TypeError("graph must be LearningObjectiveGraph")
        step_limit = _positive_int(
            max_steps,
            "max_steps",
            maximum=_MAX_PLAN_STEPS,
        )

        for objective_id, state in states.items():
            _token(objective_id, "state objective_id")
            if not isinstance(state, LearnerSkillState):
                raise TypeError(
                    "states must contain LearnerSkillState"
                )
            if state.learner_id != normalized_learner:
                raise InstructionRuntimeError(
                    "state learner identity mismatch"
                )
            if state.objective_id != objective_id:
                raise InstructionRuntimeError(
                    "state mapping key/objective mismatch"
                )

        ready = graph.ready(states)
        steps: list[InstructionStep] = []
        for objective in ready:
            state = states.get(objective.objective_id)
            if objective.is_satisfied(state):
                continue
            mode, evidence_kind, rationale, max_hints = self._mode_for(
                objective,
                state,
            )
            step_id = "step-" + _digest(
                {
                    "schema": INSTRUCTION_SCHEMA,
                    "learner_id": normalized_learner,
                    "objective_id": objective.objective_id,
                    "objective_digest": objective.digest,
                    "state_digest": None if state is None else state.digest,
                    "mode": mode.value,
                }
            )[:24]
            steps.append(
                InstructionStep(
                    step_id=step_id,
                    objective_id=objective.objective_id,
                    mode=mode,
                    rationale=rationale,
                    required_evidence_kind=evidence_kind,
                    success_threshold=objective.mastery_target,
                    max_hints=max_hints,
                )
            )
            if len(steps) >= step_limit:
                break

        return InstructionPlan(
            learner_id=normalized_learner,
            objective_graph_digest=graph.digest,
            state_digest=self._state_digest(
                normalized_learner,
                states,
            ),
            steps=tuple(steps),
        )


@dataclass(frozen=True, slots=True)
class LearningOutcome:
    learner_id: str
    objective_id: str
    status: OutcomeStatus
    mastery_before: float
    mastery_after: float
    mastery_delta: float
    uncertainty_before: float
    uncertainty_after: float
    uncertainty_reduction: float
    new_evidence_count: int
    correction_attempts: int
    correction_successes: int
    corrected_after_failure: bool
    transfer_successes: int
    retention_successes: int
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "learner_id",
            _token(self.learner_id, "learner_id"),
        )
        object.__setattr__(
            self,
            "objective_id",
            _token(self.objective_id, "objective_id"),
        )
        if not isinstance(self.status, OutcomeStatus):
            raise InstructionRuntimeError(
                "status must be OutcomeStatus"
            )
        for field in (
            "mastery_before",
            "mastery_after",
            "uncertainty_before",
            "uncertainty_after",
        ):
            object.__setattr__(
                self,
                field,
                _unit(getattr(self, field), field),
            )
        for field in (
            "mastery_delta",
            "uncertainty_reduction",
        ):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise InstructionRuntimeError(
                    f"{field} must be finite numeric"
                )
            object.__setattr__(self, field, float(value))
        for field in (
            "new_evidence_count",
            "correction_attempts",
            "correction_successes",
            "transfer_successes",
            "retention_successes",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        if self.correction_successes > self.correction_attempts:
            raise InstructionRuntimeError(
                "correction successes exceed attempts"
            )
        if not isinstance(self.corrected_after_failure, bool):
            raise InstructionRuntimeError(
                "corrected_after_failure must be boolean"
            )
        if not isinstance(self.evidence_ids, tuple):
            raise InstructionRuntimeError(
                "evidence_ids must be a tuple"
            )
        normalized: list[str] = []
        for evidence_id in self.evidence_ids:
            token = _token(evidence_id, "evidence_id")
            if token in normalized:
                raise InstructionRuntimeError(
                    "duplicate outcome evidence identity"
                )
            normalized.append(token)
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(normalized),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "learning-outcome",
                "learner_id": self.learner_id,
                "objective_id": self.objective_id,
                "status": self.status.value,
                "mastery_before": self.mastery_before,
                "mastery_after": self.mastery_after,
                "mastery_delta": self.mastery_delta,
                "uncertainty_before": self.uncertainty_before,
                "uncertainty_after": self.uncertainty_after,
                "uncertainty_reduction": self.uncertainty_reduction,
                "new_evidence_count": self.new_evidence_count,
                "correction_attempts": self.correction_attempts,
                "correction_successes": self.correction_successes,
                "corrected_after_failure": self.corrected_after_failure,
                "transfer_successes": self.transfer_successes,
                "retention_successes": self.retention_successes,
                "evidence_ids": list(self.evidence_ids),
            }
        )


class OutcomeEvaluator:
    """Measure learning change and correction behavior.

    No time-on-task, click, message-count, or engagement metric contributes to
    the outcome status.
    """

    def __init__(
        self,
        *,
        minimum_mastery_gain: float = 0.05,
        regression_tolerance: float = 0.03,
    ) -> None:
        self.minimum_mastery_gain = _unit(
            minimum_mastery_gain,
            "minimum_mastery_gain",
        )
        self.regression_tolerance = _unit(
            regression_tolerance,
            "regression_tolerance",
        )

    def evaluate(
        self,
        *,
        before: LearnerSkillState,
        after: LearnerSkillState,
        new_evidence: Sequence[LearnerEvidence],
        prior_evidence: Sequence[LearnerEvidence] = (),
    ) -> LearningOutcome:
        if not isinstance(before, LearnerSkillState):
            raise TypeError("before must be LearnerSkillState")
        if not isinstance(after, LearnerSkillState):
            raise TypeError("after must be LearnerSkillState")
        if (
            before.learner_id != after.learner_id
            or before.objective_id != after.objective_id
        ):
            raise InstructionRuntimeError(
                "before/after learner-state identity mismatch"
            )
        if isinstance(new_evidence, (str, bytes)) or not isinstance(
            new_evidence,
            Sequence,
        ):
            raise InstructionRuntimeError(
                "new_evidence must be a finite sequence"
            )
        if isinstance(prior_evidence, (str, bytes)) or not isinstance(
            prior_evidence,
            Sequence,
        ):
            raise InstructionRuntimeError(
                "prior_evidence must be a finite sequence"
            )

        records: list[LearnerEvidence] = []
        prior_records: list[LearnerEvidence] = []
        correction_attempts = 0
        correction_successes = 0
        corrected_after_failure = False
        transfer_successes = 0
        retention_successes = 0
        seen_ids: set[str] = set()

        for record in new_evidence:
            if not isinstance(record, LearnerEvidence):
                raise TypeError(
                    "new_evidence must contain LearnerEvidence"
                )
            if (
                record.learner_id != after.learner_id
                or record.objective_id != after.objective_id
            ):
                raise InstructionRuntimeError(
                    "outcome evidence identity mismatch"
                )
            if record.evidence_id in seen_ids:
                raise InstructionRuntimeError(
                    "duplicate outcome evidence identity"
                )
            if (
                before.last_observed_at is not None
                and record.observed_at < before.last_observed_at
            ):
                raise InstructionRuntimeError(
                    "new outcome evidence predates baseline state"
                )
            seen_ids.add(record.evidence_id)
            records.append(record)

        prior_ids: set[str] = set()
        prior_by_attempt: dict[str, LearnerEvidence] = {}
        for record in prior_evidence:
            if not isinstance(record, LearnerEvidence):
                raise TypeError(
                    "prior_evidence must contain LearnerEvidence"
                )
            if (
                record.learner_id != after.learner_id
                or record.objective_id != after.objective_id
            ):
                raise InstructionRuntimeError(
                    "prior outcome evidence identity mismatch"
                )
            if record.evidence_id in prior_ids:
                raise InstructionRuntimeError(
                    "duplicate prior outcome evidence identity"
                )
            if record.attempt_id in prior_by_attempt:
                raise InstructionRuntimeError(
                    "duplicate prior outcome attempt identity"
                )
            prior_ids.add(record.evidence_id)
            prior_by_attempt[record.attempt_id] = record

        for record in records:
            if record.evidence_id in prior_ids:
                raise InstructionRuntimeError(
                    "new/prior outcome evidence overlap"
                )
            if record.attempt_id in prior_by_attempt:
                raise InstructionRuntimeError(
                    "new/prior outcome attempt overlap"
                )
            prior_by_attempt[record.attempt_id] = record

        for record in records:
            if record.kind is LearnerEvidenceKind.CORRECTION:
                correction_attempts += 1
                prior = prior_by_attempt.get(
                    record.prior_attempt_id or ""
                )
                if prior is None or prior is record:
                    raise InstructionRuntimeError(
                        "outcome correction references unknown prior attempt"
                    )
                if prior.success:
                    raise InstructionRuntimeError(
                        "outcome correction must reference a failed attempt"
                    )
                if prior.observed_at > record.observed_at:
                    raise InstructionRuntimeError(
                        "outcome correction predates prior attempt"
                    )
                correction_successes += int(record.success)
                if record.success:
                    corrected_after_failure = True
            elif (
                record.kind is LearnerEvidenceKind.TRANSFER
                and record.success
            ):
                transfer_successes += 1
            elif (
                record.kind is LearnerEvidenceKind.RETENTION
                and record.success
            ):
                retention_successes += 1

        mastery_delta = after.mastery - before.mastery
        uncertainty_reduction = (
            before.uncertainty - after.uncertainty
        )

        if not records:
            status = OutcomeStatus.INSUFFICIENT_EVIDENCE
        elif mastery_delta < -self.regression_tolerance:
            status = OutcomeStatus.REGRESSED
        elif (
            mastery_delta >= self.minimum_mastery_gain
            or corrected_after_failure
            or transfer_successes > 0
            or retention_successes > 0
        ):
            status = OutcomeStatus.IMPROVED
        else:
            status = OutcomeStatus.STABLE

        return LearningOutcome(
            learner_id=after.learner_id,
            objective_id=after.objective_id,
            status=status,
            mastery_before=before.mastery,
            mastery_after=after.mastery,
            mastery_delta=mastery_delta,
            uncertainty_before=before.uncertainty,
            uncertainty_after=after.uncertainty,
            uncertainty_reduction=uncertainty_reduction,
            new_evidence_count=len(records),
            correction_attempts=correction_attempts,
            correction_successes=correction_successes,
            corrected_after_failure=corrected_after_failure,
            transfer_successes=transfer_successes,
            retention_successes=retention_successes,
            evidence_ids=tuple(
                record.evidence_id for record in records
            ),
        )


class LearnerEvidenceLedger:
    """Append-only learner evidence with correction lineage checks."""

    def __init__(self, *, max_records: int = _MAX_EVIDENCE) -> None:
        self.max_records = _positive_int(
            max_records,
            "max_records",
            maximum=_MAX_EVIDENCE,
        )
        self._records: dict[str, LearnerEvidence] = {}
        self._attempts: dict[str, LearnerEvidence] = {}

    def append(self, record: LearnerEvidence) -> LearnerEvidence:
        if not isinstance(record, LearnerEvidence):
            raise TypeError("record must be LearnerEvidence")
        if record.evidence_id in self._records:
            existing = self._records[record.evidence_id]
            if existing == record:
                return existing
            raise InstructionRuntimeError(
                "evidence identity collision"
            )
        if len(self._records) >= self.max_records:
            raise InstructionRuntimeError(
                "learner evidence ledger capacity reached"
            )
        if record.attempt_id in self._attempts:
            raise InstructionRuntimeError(
                "attempt identity collision"
            )

        if record.kind is LearnerEvidenceKind.CORRECTION:
            prior = self._attempts.get(
                record.prior_attempt_id or ""
            )
            if prior is None:
                raise InstructionRuntimeError(
                    "correction references unknown prior attempt"
                )
            if (
                prior.learner_id != record.learner_id
                or prior.objective_id != record.objective_id
            ):
                raise InstructionRuntimeError(
                    "correction prior attempt crosses learner/objective boundary"
                )
            if prior.success:
                raise InstructionRuntimeError(
                    "correction must reference an unsuccessful attempt"
                )
            if record.observed_at < prior.observed_at:
                raise InstructionRuntimeError(
                    "correction cannot predate prior attempt"
                )

        self._records[record.evidence_id] = record
        self._attempts[record.attempt_id] = record
        return record

    def records(
        self,
        *,
        learner_id: str,
        objective_id: str | None = None,
    ) -> tuple[LearnerEvidence, ...]:
        learner = _token(learner_id, "learner_id")
        objective = (
            None
            if objective_id is None
            else _token(objective_id, "objective_id")
        )
        return tuple(
            sorted(
                (
                    record
                    for record in self._records.values()
                    if record.learner_id == learner
                    and (
                        objective is None
                        or record.objective_id == objective
                    )
                ),
                key=lambda item: (
                    item.observed_at,
                    item.evidence_id,
                ),
            )
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "learner-evidence-ledger",
                "records": [
                    self._records[key].digest
                    for key in sorted(self._records)
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    learner_id: str
    ledger_digest: str
    graph_digest: str
    states: tuple[LearnerSkillState, ...]
    plan: InstructionPlan

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "learner_id",
            _token(self.learner_id, "learner_id"),
        )
        object.__setattr__(
            self,
            "ledger_digest",
            _sha256(self.ledger_digest, "ledger_digest"),
        )
        object.__setattr__(
            self,
            "graph_digest",
            _sha256(self.graph_digest, "graph_digest"),
        )
        if not isinstance(self.states, tuple):
            raise InstructionRuntimeError(
                "states must be a tuple"
            )
        seen: set[str] = set()
        for state in self.states:
            if not isinstance(state, LearnerSkillState):
                raise InstructionRuntimeError(
                    "states must contain LearnerSkillState"
                )
            if state.learner_id != self.learner_id:
                raise InstructionRuntimeError(
                    "snapshot state learner mismatch"
                )
            if state.objective_id in seen:
                raise InstructionRuntimeError(
                    "duplicate snapshot objective state"
                )
            seen.add(state.objective_id)
        if not isinstance(self.plan, InstructionPlan):
            raise TypeError("plan must be InstructionPlan")
        if self.plan.learner_id != self.learner_id:
            raise InstructionRuntimeError(
                "snapshot plan learner mismatch"
            )
        if self.plan.objective_graph_digest != self.graph_digest:
            raise InstructionRuntimeError(
                "snapshot plan/graph identity mismatch"
            )
        expected_state_digest = _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "instruction-state-set",
                "learner_id": self.learner_id,
                "states": [
                    {
                        "objective_id": state.objective_id,
                        "digest": state.digest,
                    }
                    for state in sorted(
                        self.states,
                        key=lambda item: item.objective_id,
                    )
                ],
            }
        )
        if self.plan.state_digest != expected_state_digest:
            raise InstructionRuntimeError(
                "snapshot plan/state identity mismatch"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": INSTRUCTION_SCHEMA,
                "kind": "learning-snapshot",
                "learner_id": self.learner_id,
                "ledger_digest": self.ledger_digest,
                "graph_digest": self.graph_digest,
                "states": [
                    state.digest for state in self.states
                ],
                "plan_digest": self.plan.digest,
            }
        )


class InstructionRuntime:
    """Usable orchestration surface for VOL-074."""

    def __init__(
        self,
        graph: LearningObjectiveGraph,
        *,
        ledger: LearnerEvidenceLedger | None = None,
        estimator: LearnerStateEstimator | None = None,
        planner: InstructionPlanner | None = None,
        evaluator: OutcomeEvaluator | None = None,
    ) -> None:
        if not isinstance(graph, LearningObjectiveGraph):
            raise TypeError("graph must be LearningObjectiveGraph")
        self.graph = graph
        self.ledger = ledger or LearnerEvidenceLedger()
        self.estimator = estimator or LearnerStateEstimator()
        self.planner = planner or InstructionPlanner()
        self.evaluator = evaluator or OutcomeEvaluator()

    def record(
        self,
        evidence: LearnerEvidence,
    ) -> LearnerEvidence:
        return self.ledger.append(evidence)

    def state(
        self,
        *,
        learner_id: str,
        objective_id: str,
    ) -> LearnerSkillState:
        return self.estimator.infer(
            learner_id,
            objective_id,
            self.ledger.records(
                learner_id=learner_id,
                objective_id=objective_id,
            ),
        )

    def states(
        self,
        learner_id: str,
    ) -> dict[str, LearnerSkillState]:
        learner = _token(learner_id, "learner_id")
        return {
            objective.objective_id: self.state(
                learner_id=learner,
                objective_id=objective.objective_id,
            )
            for objective in self.graph.objectives
        }

    def plan(
        self,
        learner_id: str,
        *,
        max_steps: int = 8,
    ) -> InstructionPlan:
        learner = _token(learner_id, "learner_id")
        return self.planner.plan(
            learner_id=learner,
            graph=self.graph,
            states=self.states(learner),
            max_steps=max_steps,
        )

    def snapshot(
        self,
        learner_id: str,
        *,
        max_steps: int = 8,
    ) -> LearningSnapshot:
        learner = _token(learner_id, "learner_id")
        states = self.states(learner)
        plan = self.planner.plan(
            learner_id=learner,
            graph=self.graph,
            states=states,
            max_steps=max_steps,
        )
        return LearningSnapshot(
            learner_id=learner,
            ledger_digest=self.ledger.digest,
            graph_digest=self.graph.digest,
            states=tuple(
                states[key] for key in sorted(states)
            ),
            plan=plan,
        )

    def evaluate(
        self,
        *,
        learner_id: str,
        objective_id: str,
        baseline_evidence_ids: Sequence[str],
    ) -> LearningOutcome:
        learner = _token(learner_id, "learner_id")
        objective = _token(objective_id, "objective_id")
        all_records = self.ledger.records(
            learner_id=learner,
            objective_id=objective,
        )
        if isinstance(baseline_evidence_ids, (str, bytes)) or not isinstance(
            baseline_evidence_ids,
            Sequence,
        ):
            raise InstructionRuntimeError(
                "baseline_evidence_ids must be a finite sequence"
            )
        baseline_ids = tuple(
            _token(item, "baseline evidence_id")
            for item in baseline_evidence_ids
        )
        if len(baseline_ids) != len(set(baseline_ids)):
            raise InstructionRuntimeError(
                "duplicate baseline evidence identity"
            )
        by_id = {
            record.evidence_id: record
            for record in all_records
        }
        missing = [
            evidence_id
            for evidence_id in baseline_ids
            if evidence_id not in by_id
        ]
        if missing:
            raise InstructionRuntimeError(
                "baseline references unknown evidence"
            )
        baseline = tuple(by_id[item] for item in baseline_ids)
        baseline_set = set(baseline_ids)
        expected_prefix = tuple(
            record.evidence_id
            for record in all_records[: len(baseline_ids)]
        )
        if baseline_ids != expected_prefix:
            raise InstructionRuntimeError(
                "baseline_evidence_ids must be the chronological evidence prefix"
            )
        followup = tuple(all_records[len(baseline_ids):])
        before = self.estimator.infer(
            learner,
            objective,
            baseline,
        )
        after = self.estimator.infer(
            learner,
            objective,
            all_records,
        )
        return self.evaluator.evaluate(
            before=before,
            after=after,
            new_evidence=followup,
            prior_evidence=baseline,
        )


__all__ = [
    "INSTRUCTION_SCHEMA",
    "InstructionMode",
    "InstructionPlan",
    "InstructionPlanner",
    "InstructionRuntime",
    "InstructionRuntimeError",
    "InstructionStep",
    "LearnerEvidence",
    "LearnerEvidenceKind",
    "LearnerEvidenceLedger",
    "LearnerSkillState",
    "LearnerStateEstimator",
    "LearningObjective",
    "LearningObjectiveGraph",
    "LearningOutcome",
    "LearningSnapshot",
    "OutcomeEvaluator",
    "OutcomeStatus",
]
