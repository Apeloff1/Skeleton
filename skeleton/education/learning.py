"""Evidence-separated learner modeling and outcome-bound pedagogy for VOL-074.

Observed learner evidence and inferred mastery are different contracts. The
planner consumes an inferred learner state, but only observed assessment records
can update that state. Instruction plans bind to explicit objectives,
prerequisites, and an independently identified outcome evaluation contract.
Engagement is not a promotion criterion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Iterable, Mapping

EDUCATION_SCHEMA = "skeleton.education.learning.v1"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ITEMS = 256
_MAX_TEXT = 4096


class EducationContractError(ValueError):
    """Learner-state, pedagogy, or outcome evidence violated the contract."""


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    ASSESSMENT = "assessment"


class InstructionKind(str, Enum):
    DIAGNOSTIC = "diagnostic"
    PREREQUISITE = "prerequisite"
    EXPLANATION = "explanation"
    GUIDED_PRACTICE = "guided_practice"
    RETRIEVAL_PRACTICE = "retrieval_practice"
    ASSESSMENT = "assessment"


class OutcomeDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise EducationContractError(
            f"{field_name} must be a canonical lowercase identifier"
        )
    return value


def _text(value: object, field_name: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise EducationContractError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized or normalized != value or len(normalized) > maximum:
        raise EducationContractError(
            f"{field_name} must be canonical bounded non-empty text"
        )
    return normalized


def _digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EducationContractError(
            f"{field_name} must be lowercase canonical sha256"
        )
    return value


def _unit(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EducationContractError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise EducationContractError(
            f"{field_name} must be finite and within [0, 1]"
        )
    return result


def _count(value: object, field_name: str, *, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EducationContractError(f"{field_name} must be an integer")
    if not 0 <= value <= maximum:
        raise EducationContractError(
            f"{field_name} must be between 0 and {maximum}"
        )
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EducationContractError(
            f"{field_name} must be a timezone-aware RFC3339 timestamp"
        )
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise EducationContractError(f"{field_name} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise EducationContractError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise EducationContractError("generated time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _tokens(
    values: Iterable[str],
    field_name: str,
    *,
    maximum: int = _MAX_ITEMS,
) -> tuple[str, ...]:
    items = tuple(values)
    if len(items) > maximum:
        raise EducationContractError(f"{field_name} exceeds cardinality limit")
    normalized = tuple(sorted(_identifier(item, field_name) for item in items))
    if len(normalized) != len(set(normalized)):
        raise EducationContractError(f"{field_name} contains duplicates")
    return normalized


def _canonical_json(value: object, field_name: str) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EducationContractError(
            f"{field_name} must be deterministic JSON"
        ) from exc


def _payload_digest(value: object, field_name: str = "payload") -> str:
    return sha256(_canonical_json(value, field_name)).hexdigest()


@dataclass(frozen=True, slots=True)
class LearnerEvidence:
    """Observed evidence only; this type never contains inferred mastery."""

    evidence_id: str
    learner_id: str
    objective_id: str
    kind: EvidenceKind
    observed_at: str
    source_id: str
    content_digest: str
    attempts: int
    correct: int
    misconception_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evidence_id", _identifier(self.evidence_id, "evidence_id")
        )
        object.__setattr__(
            self, "learner_id", _identifier(self.learner_id, "learner_id")
        )
        object.__setattr__(
            self, "objective_id", _identifier(self.objective_id, "objective_id")
        )
        if not isinstance(self.kind, EvidenceKind):
            raise EducationContractError("kind must be EvidenceKind")
        _timestamp(self.observed_at, "observed_at")
        object.__setattr__(
            self, "source_id", _identifier(self.source_id, "source_id")
        )
        object.__setattr__(
            self,
            "content_digest",
            _digest(self.content_digest, "content_digest"),
        )
        object.__setattr__(
            self, "attempts", _count(self.attempts, "attempts")
        )
        object.__setattr__(
            self, "correct", _count(self.correct, "correct")
        )
        if self.attempts < 1:
            raise EducationContractError("learner evidence requires attempts")
        if self.correct > self.attempts:
            raise EducationContractError("correct cannot exceed attempts")
        object.__setattr__(
            self,
            "misconception_ids",
            _tokens(self.misconception_ids, "misconception_id"),
        )

    @property
    def score(self) -> float:
        return self.correct / self.attempts

    def to_wire(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "learner_id": self.learner_id,
            "objective_id": self.objective_id,
            "kind": self.kind.value,
            "observed_at": self.observed_at,
            "source_id": self.source_id,
            "content_digest": self.content_digest,
            "attempts": self.attempts,
            "correct": self.correct,
            "misconception_ids": list(self.misconception_ids),
        }

    @property
    def digest(self) -> str:
        return _payload_digest(
            {
                "schema": EDUCATION_SCHEMA,
                "kind": "learner-evidence",
                **self.to_wire(),
            },
            "learner evidence",
        )


@dataclass(frozen=True, slots=True)
class LearningObjective:
    objective_id: str
    description: str
    prerequisites: tuple[str, ...]
    mastery_threshold: float = 0.8
    uncertainty_ceiling: float = 0.35

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective_id", _identifier(self.objective_id, "objective_id")
        )
        object.__setattr__(
            self, "description", _text(self.description, "description")
        )
        object.__setattr__(
            self,
            "prerequisites",
            _tokens(self.prerequisites, "prerequisite"),
        )
        if self.objective_id in self.prerequisites:
            raise EducationContractError("objective cannot depend on itself")
        object.__setattr__(
            self,
            "mastery_threshold",
            _unit(self.mastery_threshold, "mastery_threshold"),
        )
        object.__setattr__(
            self,
            "uncertainty_ceiling",
            _unit(self.uncertainty_ceiling, "uncertainty_ceiling"),
        )


@dataclass(frozen=True, slots=True)
class ObjectiveBelief:
    """Inference derived from observed evidence; never source evidence itself."""

    objective_id: str
    evidence_ids: tuple[str, ...]
    attempts: int
    correct: int
    mastery_probability: float
    confidence: float
    uncertainty: float
    misconception_ids: tuple[str, ...]
    record_class: str = "inference"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "objective_id", _identifier(self.objective_id, "objective_id")
        )
        object.__setattr__(
            self, "evidence_ids", _tokens(self.evidence_ids, "evidence_id")
        )
        object.__setattr__(
            self, "attempts", _count(self.attempts, "attempts")
        )
        object.__setattr__(self, "correct", _count(self.correct, "correct"))
        if self.correct > self.attempts:
            raise EducationContractError("correct cannot exceed attempts")
        for field_name in ("mastery_probability", "confidence", "uncertainty"):
            object.__setattr__(
                self,
                field_name,
                _unit(getattr(self, field_name), field_name),
            )
        if abs((self.confidence + self.uncertainty) - 1.0) > 1e-12:
            raise EducationContractError(
                "confidence and uncertainty must be complementary"
            )
        object.__setattr__(
            self,
            "misconception_ids",
            _tokens(self.misconception_ids, "misconception_id"),
        )
        if self.record_class != "inference":
            raise EducationContractError(
                "objective belief must remain an inference record"
            )

    @property
    def can_masquerade_as_observed_evidence(self) -> bool:
        return False

    def to_wire(self) -> dict[str, object]:
        return {
            "objective_id": self.objective_id,
            "evidence_ids": list(self.evidence_ids),
            "attempts": self.attempts,
            "correct": self.correct,
            "mastery_probability": self.mastery_probability,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "misconception_ids": list(self.misconception_ids),
            "record_class": self.record_class,
        }


@dataclass(frozen=True, slots=True)
class LearnerState:
    learner_id: str
    generated_at: str
    evidence_set_digest: str
    beliefs: tuple[ObjectiveBelief, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "learner_id", _identifier(self.learner_id, "learner_id")
        )
        _timestamp(self.generated_at, "generated_at")
        object.__setattr__(
            self,
            "evidence_set_digest",
            _digest(self.evidence_set_digest, "evidence_set_digest"),
        )
        if not isinstance(self.beliefs, tuple):
            raise EducationContractError("beliefs must be a tuple")
        by_id: dict[str, ObjectiveBelief] = {}
        for belief in self.beliefs:
            if not isinstance(belief, ObjectiveBelief):
                raise EducationContractError(
                    "beliefs must contain ObjectiveBelief"
                )
            if belief.objective_id in by_id:
                raise EducationContractError("duplicate objective belief")
            by_id[belief.objective_id] = belief
        object.__setattr__(
            self,
            "beliefs",
            tuple(by_id[key] for key in sorted(by_id)),
        )
        object.__setattr__(
            self, "receipt_digest", _digest(self.receipt_digest, "receipt_digest")
        )

    def belief(self, objective_id: str) -> ObjectiveBelief:
        objective_id = _identifier(objective_id, "objective_id")
        for belief in self.beliefs:
            if belief.objective_id == objective_id:
                return belief
        raise EducationContractError(
            f"learner state has no objective belief for {objective_id}"
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "learner_id": self.learner_id,
            "generated_at": self.generated_at,
            "evidence_set_digest": self.evidence_set_digest,
            "beliefs": [belief.to_wire() for belief in self.beliefs],
            "receipt_digest": self.receipt_digest,
        }


class LearningObjectiveGraph:
    """Objective DAG plus deterministic evidence-to-belief estimator."""

    def __init__(self, objectives: Iterable[LearningObjective]) -> None:
        items = tuple(objectives)
        if not items:
            raise EducationContractError(
                "objective graph requires at least one objective"
            )
        if len(items) > _MAX_ITEMS:
            raise EducationContractError(
                "objective graph exceeds cardinality limit"
            )
        by_id: dict[str, LearningObjective] = {}
        for objective in items:
            if not isinstance(objective, LearningObjective):
                raise EducationContractError(
                    "objective graph must contain LearningObjective"
                )
            if objective.objective_id in by_id:
                raise EducationContractError("duplicate objective_id")
            by_id[objective.objective_id] = objective
        for objective in by_id.values():
            missing = set(objective.prerequisites) - set(by_id)
            if missing:
                raise EducationContractError(
                    f"unknown prerequisite {sorted(missing)[0]}"
                )
        self._objectives = dict(sorted(by_id.items()))
        self._assert_acyclic()

    @property
    def objective_ids(self) -> tuple[str, ...]:
        return tuple(self._objectives)

    def objective(self, objective_id: str) -> LearningObjective:
        objective_id = _identifier(objective_id, "objective_id")
        try:
            return self._objectives[objective_id]
        except KeyError as exc:
            raise EducationContractError(
                f"unknown objective {objective_id}"
            ) from exc

    @property
    def digest(self) -> str:
        return _payload_digest(
            {
                "schema": EDUCATION_SCHEMA,
                "kind": "objective-graph",
                "objectives": [
                    {
                        "objective_id": objective.objective_id,
                        "description": objective.description,
                        "prerequisites": list(objective.prerequisites),
                        "mastery_threshold": objective.mastery_threshold,
                        "uncertainty_ceiling": objective.uncertainty_ceiling,
                    }
                    for objective in self._objectives.values()
                ],
            },
            "objective graph",
        )

    def estimate(
        self,
        *,
        learner_id: str,
        evidence: Iterable[LearnerEvidence],
        generated_at: datetime,
    ) -> LearnerState:
        learner_id = _identifier(learner_id, "learner_id")
        generated = _canonical_timestamp(generated_at)
        items = tuple(evidence)
        if len(items) > 10_000:
            raise EducationContractError(
                "learner evidence exceeds bounded cardinality"
            )
        by_evidence: dict[str, LearnerEvidence] = {}
        for item in items:
            if not isinstance(item, LearnerEvidence):
                raise EducationContractError(
                    "evidence must contain LearnerEvidence"
                )
            if item.learner_id != learner_id:
                raise EducationContractError("cross-learner evidence rejected")
            if item.objective_id not in self._objectives:
                raise EducationContractError(
                    f"evidence references unknown objective {item.objective_id}"
                )
            if item.evidence_id in by_evidence:
                raise EducationContractError("duplicate evidence_id")
            if _timestamp(item.observed_at, "observed_at") > generated_at.astimezone(
                timezone.utc
            ):
                raise EducationContractError(
                    "future learner evidence rejected"
                )
            by_evidence[item.evidence_id] = item

        beliefs: list[ObjectiveBelief] = []
        for objective_id in self._objectives:
            objective_evidence = sorted(
                (
                    item
                    for item in by_evidence.values()
                    if item.objective_id == objective_id
                ),
                key=lambda item: item.evidence_id,
            )
            attempts = sum(item.attempts for item in objective_evidence)
            correct = sum(item.correct for item in objective_evidence)
            # Beta(1,1) posterior mean with evidence-volume confidence.
            mastery = (correct + 1.0) / (attempts + 2.0)
            confidence = attempts / (attempts + 2.0)
            uncertainty = 1.0 - confidence
            misconception_ids = tuple(
                sorted(
                    {
                        misconception
                        for item in objective_evidence
                        for misconception in item.misconception_ids
                    }
                )
            )
            beliefs.append(
                ObjectiveBelief(
                    objective_id=objective_id,
                    evidence_ids=tuple(
                        item.evidence_id for item in objective_evidence
                    ),
                    attempts=attempts,
                    correct=correct,
                    mastery_probability=mastery,
                    confidence=confidence,
                    uncertainty=uncertainty,
                    misconception_ids=misconception_ids,
                )
            )

        evidence_set_digest = _payload_digest(
            {
                "schema": EDUCATION_SCHEMA,
                "kind": "learner-evidence-set",
                "learner_id": learner_id,
                "evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "digest": item.digest,
                    }
                    for item in sorted(
                        by_evidence.values(),
                        key=lambda item: item.evidence_id,
                    )
                ],
            },
            "learner evidence set",
        )
        payload = {
            "schema": EDUCATION_SCHEMA,
            "kind": "learner-state",
            "learner_id": learner_id,
            "generated_at": generated,
            "objective_graph_digest": self.digest,
            "evidence_set_digest": evidence_set_digest,
            "beliefs": [belief.to_wire() for belief in beliefs],
        }
        return LearnerState(
            learner_id=learner_id,
            generated_at=generated,
            evidence_set_digest=evidence_set_digest,
            beliefs=tuple(beliefs),
            receipt_digest=_payload_digest(payload, "learner state"),
        )

    def verify_state(self, state: LearnerState) -> None:
        if not isinstance(state, LearnerState):
            raise TypeError("state must be LearnerState")
        payload = {
            "schema": EDUCATION_SCHEMA,
            "kind": "learner-state",
            "learner_id": state.learner_id,
            "generated_at": state.generated_at,
            "objective_graph_digest": self.digest,
            "evidence_set_digest": state.evidence_set_digest,
            "beliefs": [belief.to_wire() for belief in state.beliefs],
        }
        if _payload_digest(payload, "learner state") != state.receipt_digest:
            raise EducationContractError(
                "learner-state receipt failed integrity verification"
            )
        if tuple(b.objective_id for b in state.beliefs) != self.objective_ids:
            raise EducationContractError(
                "learner-state objective coverage drift"
            )

    def prerequisite_order(self, objective_id: str) -> tuple[str, ...]:
        target = self.objective(objective_id)
        ordered: list[str] = []
        visited: set[str] = set()

        def visit(current: str) -> None:
            if current in visited:
                return
            for prerequisite in self._objectives[current].prerequisites:
                visit(prerequisite)
            visited.add(current)
            if current != target.objective_id:
                ordered.append(current)

        visit(target.objective_id)
        return tuple(ordered)

    def _assert_acyclic(self) -> None:
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(node: str) -> None:
            if node in permanent:
                return
            if node in temporary:
                raise EducationContractError(
                    "objective prerequisite graph contains cycle"
                )
            temporary.add(node)
            for prerequisite in self._objectives[node].prerequisites:
                visit(prerequisite)
            temporary.remove(node)
            permanent.add(node)

        for objective_id in self._objectives:
            visit(objective_id)


@dataclass(frozen=True, slots=True)
class OutcomeBinding:
    owner_id: str
    suite_id: str
    minimum_post_score: float
    minimum_gain: float
    max_allowed_regression: float = 0.02
    require_misconception_correction: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "owner_id", _identifier(self.owner_id, "owner_id")
        )
        object.__setattr__(
            self, "suite_id", _identifier(self.suite_id, "suite_id")
        )
        for field_name in (
            "minimum_post_score",
            "minimum_gain",
            "max_allowed_regression",
        ):
            object.__setattr__(
                self,
                field_name,
                _unit(getattr(self, field_name), field_name),
            )
        if not isinstance(self.require_misconception_correction, bool):
            raise EducationContractError(
                "require_misconception_correction must be boolean"
            )


@dataclass(frozen=True, slots=True)
class InstructionStep:
    step_id: str
    kind: InstructionKind
    objective_id: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "step_id", _identifier(self.step_id, "step_id")
        )
        if not isinstance(self.kind, InstructionKind):
            raise EducationContractError("kind must be InstructionKind")
        object.__setattr__(
            self,
            "objective_id",
            _identifier(self.objective_id, "objective_id"),
        )
        object.__setattr__(
            self, "rationale", _text(self.rationale, "rationale")
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "kind": self.kind.value,
            "objective_id": self.objective_id,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class InstructionPlan:
    plan_id: str
    learner_id: str
    target_objective_id: str
    learner_state_receipt: str
    objective_graph_digest: str
    steps: tuple[InstructionStep, ...]
    outcome_binding: OutcomeBinding
    receipt_digest: str

    def __post_init__(self) -> None:
        for field_name in ("plan_id", "learner_id", "target_objective_id"):
            object.__setattr__(
                self,
                field_name,
                _identifier(getattr(self, field_name), field_name),
            )
        for field_name in ("learner_state_receipt", "objective_graph_digest"):
            object.__setattr__(
                self,
                field_name,
                _digest(getattr(self, field_name), field_name),
            )
        if not isinstance(self.steps, tuple) or not self.steps:
            raise EducationContractError(
                "instruction plan requires at least one step"
            )
        step_ids: set[str] = set()
        for step in self.steps:
            if not isinstance(step, InstructionStep):
                raise EducationContractError(
                    "steps must contain InstructionStep"
                )
            if step.step_id in step_ids:
                raise EducationContractError("duplicate instruction step_id")
            step_ids.add(step.step_id)
        if not isinstance(self.outcome_binding, OutcomeBinding):
            raise EducationContractError(
                "outcome_binding must be OutcomeBinding"
            )
        object.__setattr__(
            self, "receipt_digest", _digest(self.receipt_digest, "receipt_digest")
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "learner_id": self.learner_id,
            "target_objective_id": self.target_objective_id,
            "learner_state_receipt": self.learner_state_receipt,
            "objective_graph_digest": self.objective_graph_digest,
            "steps": [step.to_wire() for step in self.steps],
            "outcome_binding": {
                "owner_id": self.outcome_binding.owner_id,
                "suite_id": self.outcome_binding.suite_id,
                "minimum_post_score": self.outcome_binding.minimum_post_score,
                "minimum_gain": self.outcome_binding.minimum_gain,
                "max_allowed_regression": (
                    self.outcome_binding.max_allowed_regression
                ),
                "require_misconception_correction": (
                    self.outcome_binding.require_misconception_correction
                ),
            },
            "receipt_digest": self.receipt_digest,
        }


class InstructionPlanner:
    """Deterministic objective/prerequisite planner driven by learner uncertainty."""

    def __init__(
        self,
        graph: LearningObjectiveGraph,
        *,
        outcome_binding: OutcomeBinding,
    ) -> None:
        if not isinstance(graph, LearningObjectiveGraph):
            raise TypeError("graph must be LearningObjectiveGraph")
        if not isinstance(outcome_binding, OutcomeBinding):
            raise TypeError("outcome_binding must be OutcomeBinding")
        self.graph = graph
        self.outcome_binding = outcome_binding

    def plan(
        self,
        *,
        plan_id: str,
        state: LearnerState,
        target_objective_id: str,
    ) -> InstructionPlan:
        plan_id = _identifier(plan_id, "plan_id")
        self.graph.verify_state(state)
        target = self.graph.objective(target_objective_id)
        steps: list[InstructionStep] = []

        unmet_prerequisite: str | None = None
        for prerequisite_id in self.graph.prerequisite_order(
            target.objective_id
        ):
            prerequisite = self.graph.objective(prerequisite_id)
            belief = state.belief(prerequisite_id)
            if (
                belief.mastery_probability < prerequisite.mastery_threshold
                or belief.uncertainty > prerequisite.uncertainty_ceiling
            ):
                unmet_prerequisite = prerequisite_id
                break

        focus_id = unmet_prerequisite or target.objective_id
        focus = self.graph.objective(focus_id)
        belief = state.belief(focus_id)
        prefix = "prerequisite" if unmet_prerequisite else "target"

        if belief.uncertainty > focus.uncertainty_ceiling:
            steps.append(
                InstructionStep(
                    step_id=f"{prefix}-diagnostic",
                    kind=InstructionKind.DIAGNOSTIC,
                    objective_id=focus_id,
                    rationale=(
                        "Resolve high learner-state uncertainty before "
                        "stronger mastery claims."
                    ),
                )
            )

        mastered = (
            belief.mastery_probability >= focus.mastery_threshold
            and belief.uncertainty <= focus.uncertainty_ceiling
        )
        if unmet_prerequisite is not None:
            steps.append(
                InstructionStep(
                    step_id="prerequisite-explanation",
                    kind=InstructionKind.PREREQUISITE,
                    objective_id=focus_id,
                    rationale=(
                        "Satisfy the earliest unmet prerequisite before "
                        "advancing to the target objective."
                    ),
                )
            )
            steps.append(
                InstructionStep(
                    step_id="prerequisite-practice",
                    kind=InstructionKind.GUIDED_PRACTICE,
                    objective_id=focus_id,
                    rationale=(
                        "Collect new outcome evidence on the prerequisite."
                    ),
                )
            )
        elif mastered:
            steps.append(
                InstructionStep(
                    step_id="target-retrieval",
                    kind=InstructionKind.RETRIEVAL_PRACTICE,
                    objective_id=focus_id,
                    rationale=(
                        "Recheck retained mastery rather than optimize for "
                        "engagement."
                    ),
                )
            )
        else:
            steps.append(
                InstructionStep(
                    step_id="target-explanation",
                    kind=InstructionKind.EXPLANATION,
                    objective_id=focus_id,
                    rationale=(
                        "Address the explicit objective using current "
                        "misconception and mastery evidence."
                    ),
                )
            )
            steps.append(
                InstructionStep(
                    step_id="target-practice",
                    kind=InstructionKind.GUIDED_PRACTICE,
                    objective_id=focus_id,
                    rationale=(
                        "Generate observable practice outcomes before "
                        "re-estimating mastery."
                    ),
                )
            )

        steps.append(
            InstructionStep(
                step_id=f"{prefix}-assessment",
                kind=InstructionKind.ASSESSMENT,
                objective_id=focus_id,
                rationale=(
                    "Measure learning outcome and correction behavior; "
                    "engagement alone cannot promote the plan."
                ),
            )
        )
        payload = {
            "schema": EDUCATION_SCHEMA,
            "kind": "instruction-plan",
            "plan_id": plan_id,
            "learner_id": state.learner_id,
            "target_objective_id": target.objective_id,
            "learner_state_receipt": state.receipt_digest,
            "objective_graph_digest": self.graph.digest,
            "steps": [step.to_wire() for step in steps],
            "outcome_binding": {
                "owner_id": self.outcome_binding.owner_id,
                "suite_id": self.outcome_binding.suite_id,
                "minimum_post_score": self.outcome_binding.minimum_post_score,
                "minimum_gain": self.outcome_binding.minimum_gain,
                "max_allowed_regression": (
                    self.outcome_binding.max_allowed_regression
                ),
                "require_misconception_correction": (
                    self.outcome_binding.require_misconception_correction
                ),
            },
        }
        return InstructionPlan(
            plan_id=plan_id,
            learner_id=state.learner_id,
            target_objective_id=target.objective_id,
            learner_state_receipt=state.receipt_digest,
            objective_graph_digest=self.graph.digest,
            steps=tuple(steps),
            outcome_binding=self.outcome_binding,
            receipt_digest=_payload_digest(payload, "instruction plan"),
        )

    def verify(self, plan: InstructionPlan) -> None:
        if not isinstance(plan, InstructionPlan):
            raise TypeError("plan must be InstructionPlan")
        if plan.objective_graph_digest != self.graph.digest:
            raise EducationContractError("instruction-plan objective graph drift")
        payload = plan.to_wire()
        receipt = payload.pop("receipt_digest")
        expected = _payload_digest(
            {"schema": EDUCATION_SCHEMA, "kind": "instruction-plan", **payload},
            "instruction plan",
        )
        if receipt != expected:
            raise EducationContractError(
                "instruction-plan receipt failed integrity verification"
            )


@dataclass(frozen=True, slots=True)
class LearningOutcomeEvaluation:
    evaluation_id: str
    plan_receipt: str
    owner_id: str
    suite_id: str
    evaluated_at: str
    pre_score: float
    post_score: float
    initial_misconception_count: int
    corrected_misconception_count: int
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evaluation_id", _identifier(self.evaluation_id, "evaluation_id")
        )
        object.__setattr__(
            self, "plan_receipt", _digest(self.plan_receipt, "plan_receipt")
        )
        object.__setattr__(
            self, "owner_id", _identifier(self.owner_id, "owner_id")
        )
        object.__setattr__(
            self, "suite_id", _identifier(self.suite_id, "suite_id")
        )
        _timestamp(self.evaluated_at, "evaluated_at")
        object.__setattr__(
            self, "pre_score", _unit(self.pre_score, "pre_score")
        )
        object.__setattr__(
            self, "post_score", _unit(self.post_score, "post_score")
        )
        object.__setattr__(
            self,
            "initial_misconception_count",
            _count(
                self.initial_misconception_count,
                "initial_misconception_count",
            ),
        )
        object.__setattr__(
            self,
            "corrected_misconception_count",
            _count(
                self.corrected_misconception_count,
                "corrected_misconception_count",
            ),
        )
        if (
            self.corrected_misconception_count
            > self.initial_misconception_count
        ):
            raise EducationContractError(
                "corrected misconceptions cannot exceed initial count"
            )
        object.__setattr__(
            self,
            "evidence_digest",
            _digest(self.evidence_digest, "evidence_digest"),
        )


@dataclass(frozen=True, slots=True)
class OutcomeVerdict:
    evaluation_id: str
    decision: OutcomeDecision
    reasons: tuple[str, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evaluation_id",
            _identifier(self.evaluation_id, "evaluation_id"),
        )
        if not isinstance(self.decision, OutcomeDecision):
            raise EducationContractError("decision must be OutcomeDecision")
        object.__setattr__(
            self, "reasons", _tokens(self.reasons, "reason")
        )
        if self.decision is OutcomeDecision.FAIL and not self.reasons:
            raise EducationContractError("failed outcome requires reasons")
        if self.decision is OutcomeDecision.PASS and self.reasons:
            raise EducationContractError("passed outcome cannot carry failures")
        object.__setattr__(
            self, "receipt_digest", _digest(self.receipt_digest, "receipt_digest")
        )


class OutcomeEvaluator:
    """Evaluate instruction by learning/correction outcomes, never engagement."""

    def evaluate(
        self,
        plan: InstructionPlan,
        evaluation: LearningOutcomeEvaluation,
    ) -> OutcomeVerdict:
        if not isinstance(plan, InstructionPlan):
            raise TypeError("plan must be InstructionPlan")
        if not isinstance(evaluation, LearningOutcomeEvaluation):
            raise TypeError("evaluation must be LearningOutcomeEvaluation")
        binding = plan.outcome_binding
        reasons: list[str] = []
        if evaluation.plan_receipt != plan.receipt_digest:
            reasons.append("plan-receipt-mismatch")
        if evaluation.owner_id != binding.owner_id:
            reasons.append("evaluation-owner-mismatch")
        if evaluation.suite_id != binding.suite_id:
            reasons.append("evaluation-suite-mismatch")

        gain = evaluation.post_score - evaluation.pre_score
        if evaluation.pre_score < binding.minimum_post_score:
            if evaluation.post_score < binding.minimum_post_score:
                reasons.append("post-score-below-threshold")
            if gain < binding.minimum_gain:
                reasons.append("learning-gain-below-threshold")
        elif gain < -binding.max_allowed_regression:
            reasons.append("outcome-regression")

        if (
            binding.require_misconception_correction
            and evaluation.initial_misconception_count > 0
            and evaluation.corrected_misconception_count < 1
        ):
            reasons.append("misconception-not-corrected")

        canonical_reasons = tuple(sorted(set(reasons)))
        decision = (
            OutcomeDecision.FAIL
            if canonical_reasons
            else OutcomeDecision.PASS
        )
        payload = {
            "schema": EDUCATION_SCHEMA,
            "kind": "outcome-verdict",
            "evaluation_id": evaluation.evaluation_id,
            "plan_receipt": plan.receipt_digest,
            "evaluation_evidence_digest": evaluation.evidence_digest,
            "decision": decision.value,
            "reasons": list(canonical_reasons),
        }
        return OutcomeVerdict(
            evaluation_id=evaluation.evaluation_id,
            decision=decision,
            reasons=canonical_reasons,
            receipt_digest=_payload_digest(payload, "outcome verdict"),
        )


__all__ = [
    "EDUCATION_SCHEMA",
    "EducationContractError",
    "EvidenceKind",
    "InstructionKind",
    "InstructionPlan",
    "InstructionPlanner",
    "InstructionStep",
    "LearnerEvidence",
    "LearnerState",
    "LearningObjective",
    "LearningObjectiveGraph",
    "LearningOutcomeEvaluation",
    "ObjectiveBelief",
    "OutcomeBinding",
    "OutcomeDecision",
    "OutcomeEvaluator",
    "OutcomeVerdict",
]
