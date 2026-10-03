"""Dependency-aware developmental curriculum planning for local AI growth.

The curriculum layer turns absolute developmental scores into the next bounded
continual-learning target. It never promotes or activates models. It:
- scores the active developmental champion on declared capability objectives;
- respects capability dependencies before selecting training targets;
- ranks unmet eligible objectives by weighted mastery gap;
- merges target suites into acquisition evidence and mastered suites into
  retention evidence;
- carries method hints into the automatic training optimizer;
- invokes one continual-learning round and then rescans capability mastery.

All suites remain development-only; promotion holdouts are intentionally absent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from .continual_learning import (
    ContinualLearningPolicy,
    ContinualLearningRound,
    ContinualLearningState,
    run_continual_learning_round,
)
from .developmental_eval import (
    DevelopmentalEvalCase,
    DevelopmentalEvalSuite,
    DevelopmentalModelScoreReport,
    score_local_model_developmentally,
)
from .training_allocation import TrainingAllocationPolicy
from .training_methods import (
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
)
from .training_optimizer import TrainingOptimizationPolicy


_MAX_OBJECTIVES = 128
_MAX_TARGETS = 16
_MAX_MERGED_CASES = 2_048


class CurriculumError(RuntimeError):
    """Curriculum state or target selection violates bounded policy."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CurriculumError(
            "curriculum identity is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumError(f"{field} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise CurriculumError(f"{field} exceeds maximum length")
    return result


def _fraction(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurriculumError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise CurriculumError(f"{field} must be within [0, 1]")
    return result


def _positive(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurriculumError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result <= 1_000_000.0:
        raise CurriculumError(f"{field} must be finite and positive")
    return result


@dataclass(frozen=True, slots=True)
class CapabilityObjective:
    """One measurable developmental capability with optional prerequisites."""

    capability_id: str
    suite: DevelopmentalEvalSuite
    minimum_score: float
    priority: float = 1.0
    dependencies: tuple[str, ...] = ()
    method_hints: tuple[TrainingMethod, ...] = (
        TrainingMethod.SUPERVISED_INSTRUCTION,
        TrainingMethod.CAUSAL_LANGUAGE_MODELING,
        TrainingMethod.SELF_SUPERVISED_SPAN,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _text(self.capability_id, "capability_id", maximum=256),
        )
        if not isinstance(self.suite, DevelopmentalEvalSuite):
            raise TypeError("suite must be DevelopmentalEvalSuite")
        object.__setattr__(
            self,
            "minimum_score",
            _fraction(self.minimum_score, "minimum_score"),
        )
        object.__setattr__(
            self,
            "priority",
            _positive(self.priority, "priority"),
        )
        dependencies = tuple(
            dict.fromkeys(
                _text(item, "dependency", maximum=256)
                for item in self.dependencies
            )
        )
        if self.capability_id in dependencies:
            raise CurriculumError(
                "capability cannot depend on itself"
            )
        object.__setattr__(self, "dependencies", dependencies)
        methods: list[TrainingMethod] = []
        for raw in self.method_hints:
            try:
                method = TrainingMethod(raw)
            except ValueError as exc:
                raise CurriculumError(
                    "capability uses unsupported training method"
                ) from exc
            if method not in methods:
                methods.append(method)
        if not methods:
            raise CurriculumError(
                "capability requires at least one method hint"
            )
        object.__setattr__(self, "method_hints", tuple(methods))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "capability_id": self.capability_id,
                "suite_digest": self.suite.digest,
                "minimum_score": self.minimum_score,
                "priority": self.priority,
                "dependencies": list(self.dependencies),
                "method_hints": [
                    item.value for item in self.method_hints
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class CapabilityAssessment:
    """Measured mastery state for one capability objective."""

    capability_id: str
    objective_digest: str
    score_report_digest: str
    score: float
    minimum_score: float
    gap: float
    mastered: bool
    dependencies_mastered: bool
    eligible: bool
    priority: float
    rank_value: float

    @property
    def digest(self) -> str:
        return _digest(
            {
                "capability_id": self.capability_id,
                "objective_digest": self.objective_digest,
                "score_report_digest": self.score_report_digest,
                "score": self.score,
                "minimum_score": self.minimum_score,
                "gap": self.gap,
                "mastered": self.mastered,
                "dependencies_mastered": self.dependencies_mastered,
                "eligible": self.eligible,
                "priority": self.priority,
                "rank_value": self.rank_value,
            }
        )


@dataclass(frozen=True, slots=True)
class CurriculumPolicy:
    """Bounds for capability assessment and target selection."""

    max_objectives: int = 64
    max_targets_per_round: int = 4
    max_merged_cases: int = 1_024

    def __post_init__(self) -> None:
        for field, value, minimum, maximum in (
            ("max_objectives", self.max_objectives, 1, _MAX_OBJECTIVES),
            (
                "max_targets_per_round",
                self.max_targets_per_round,
                1,
                _MAX_TARGETS,
            ),
            (
                "max_merged_cases",
                self.max_merged_cases,
                1,
                _MAX_MERGED_CASES,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise CurriculumError(
                    f"{field} must be in [{minimum}, {maximum}]"
                )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "max_objectives": self.max_objectives,
                "max_targets_per_round": self.max_targets_per_round,
                "max_merged_cases": self.max_merged_cases,
            }
        )


@dataclass(frozen=True, slots=True)
class CurriculumPlan:
    """One capability map and deterministic next-target decision."""

    model_id: str
    model_digest: str
    artifact_sha256: str
    assessments: tuple[CapabilityAssessment, ...]
    target_capability_ids: tuple[str, ...]
    selected_methods: tuple[TrainingMethod, ...]
    acquisition_suite: DevelopmentalEvalSuite | None
    retention_suite: DevelopmentalEvalSuite | None
    policy_digest: str
    plan_digest: str

    @property
    def complete(self) -> bool:
        return all(item.mastered for item in self.assessments)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.capability_curriculum_plan.v1",
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "artifact_sha256": self.artifact_sha256,
            "assessment_digests": [
                item.digest for item in self.assessments
            ],
            "target_capability_ids": list(self.target_capability_ids),
            "selected_methods": [
                item.value for item in self.selected_methods
            ],
            "acquisition_suite_digest": (
                None
                if self.acquisition_suite is None
                else self.acquisition_suite.digest
            ),
            "retention_suite_digest": (
                None
                if self.retention_suite is None
                else self.retention_suite.digest
            ),
            "policy_digest": self.policy_digest,
            "plan_digest": self.plan_digest,
            "complete": self.complete,
            "production_authority": False,
        }


@dataclass(frozen=True, slots=True)
class CurriculumRoundResult:
    """Curriculum decision plus the resulting continual-learning transition."""

    before: CurriculumPlan
    continual_round: ContinualLearningRound | None
    after: CurriculumPlan
    state: ContinualLearningState

    @property
    def digest(self) -> str:
        return _digest(
            {
                "before_plan_digest": self.before.plan_digest,
                "continual_round_digest": (
                    None
                    if self.continual_round is None
                    else self.continual_round.digest
                ),
                "after_plan_digest": self.after.plan_digest,
                "state_digest": self.state.digest,
                "production_authority": False,
            }
        )


def _validate_objectives(
    objectives: Sequence[CapabilityObjective],
    *,
    policy: CurriculumPolicy,
) -> tuple[CapabilityObjective, ...]:
    rows = tuple(objectives)
    if not rows or len(rows) > policy.max_objectives:
        raise CurriculumError(
            "objectives must be bounded and non-empty"
        )
    if any(not isinstance(item, CapabilityObjective) for item in rows):
        raise TypeError(
            "objectives must contain CapabilityObjective values"
        )
    by_id = {item.capability_id: item for item in rows}
    if len(by_id) != len(rows):
        raise CurriculumError("capability ids must be unique")
    for item in rows:
        unknown = set(item.dependencies) - set(by_id)
        if unknown:
            raise CurriculumError(
                "capability dependency is not declared: "
                + ",".join(sorted(unknown))
            )

    # Deterministic DFS cycle detection.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(capability_id: str) -> None:
        if capability_id in visited:
            return
        if capability_id in visiting:
            raise CurriculumError(
                "capability dependency graph contains a cycle"
            )
        visiting.add(capability_id)
        for dependency in by_id[capability_id].dependencies:
            visit(dependency)
        visiting.remove(capability_id)
        visited.add(capability_id)

    for capability_id in sorted(by_id):
        visit(capability_id)
    return tuple(sorted(rows, key=lambda item: item.capability_id))


def _merge_suites(
    *,
    suite_id: str,
    objectives: Sequence[CapabilityObjective],
    max_cases: int,
) -> DevelopmentalEvalSuite:
    cases: list[DevelopmentalEvalCase] = []
    for objective in objectives:
        for case in objective.suite.cases:
            cases.append(
                replace(
                    case,
                    case_id=(
                        objective.capability_id
                        + "::"
                        + case.case_id
                    ),
                )
            )
            if len(cases) > max_cases:
                raise CurriculumError(
                    "merged curriculum suite exceeds case budget"
                )
    if not cases:
        raise CurriculumError(
            "merged curriculum suite requires cases"
        )
    return DevelopmentalEvalSuite(
        suite_id=suite_id,
        cases=tuple(cases),
    )


def plan_capability_curriculum(
    *,
    model_path: str | Path,
    objectives: Sequence[CapabilityObjective],
    policy: CurriculumPolicy | None = None,
) -> CurriculumPlan:
    """Score capability graph and choose the next development targets."""

    actual = policy or CurriculumPolicy()
    rows = _validate_objectives(objectives, policy=actual)

    reports: dict[str, DevelopmentalModelScoreReport] = {}
    for objective in rows:
        reports[objective.capability_id] = (
            score_local_model_developmentally(
                model_path=model_path,
                suite=objective.suite,
            )
        )
    model_ids = {item.model_id for item in reports.values()}
    model_digests = {item.model_digest for item in reports.values()}
    artifacts = {item.artifact_sha256 for item in reports.values()}
    if len(model_ids) != 1 or len(model_digests) != 1 or len(artifacts) != 1:
        raise CurriculumError(
            "capability scoring model identity drift"
        )

    mastered = {
        objective.capability_id
        for objective in rows
        if (
            reports[objective.capability_id].weighted_score
            >= objective.minimum_score
        )
    }
    assessments: list[CapabilityAssessment] = []
    for objective in rows:
        report = reports[objective.capability_id]
        score = report.weighted_score
        gap = max(0.0, objective.minimum_score - score)
        is_mastered = objective.capability_id in mastered
        dependencies_mastered = all(
            dependency in mastered
            for dependency in objective.dependencies
        )
        eligible = (not is_mastered) and dependencies_mastered
        rank_value = objective.priority * gap if eligible else 0.0
        assessments.append(
            CapabilityAssessment(
                capability_id=objective.capability_id,
                objective_digest=objective.digest,
                score_report_digest=report.digest,
                score=score,
                minimum_score=objective.minimum_score,
                gap=gap,
                mastered=is_mastered,
                dependencies_mastered=dependencies_mastered,
                eligible=eligible,
                priority=objective.priority,
                rank_value=rank_value,
            )
        )

    ranked = sorted(
        (item for item in assessments if item.eligible),
        key=lambda item: (
            -item.rank_value,
            -item.gap,
            item.capability_id,
        ),
    )
    targets = tuple(
        item.capability_id
        for item in ranked[: actual.max_targets_per_round]
    )
    by_id = {item.capability_id: item for item in rows}
    target_objectives = tuple(by_id[item] for item in targets)

    methods: list[TrainingMethod] = []
    for objective in target_objectives:
        for method in objective.method_hints:
            if method not in methods:
                methods.append(method)

    acquisition: DevelopmentalEvalSuite | None = None
    retention: DevelopmentalEvalSuite | None = None
    if target_objectives:
        acquisition = _merge_suites(
            suite_id="curriculum-acquisition-" + _digest(targets)[:16],
            objectives=target_objectives,
            max_cases=actual.max_merged_cases,
        )
        retained_objectives = tuple(
            by_id[item]
            for item in sorted(mastered)
            if item not in targets
        )
        # During bootstrap there may be no mastered capability yet. Use the
        # acquisition suite as a stability witness until retention inventory
        # exists; this is still development-only and never a promotion holdout.
        retention = (
            acquisition
            if not retained_objectives
            else _merge_suites(
                suite_id="curriculum-retention-"
                + _digest(tuple(sorted(mastered)))[:16],
                objectives=retained_objectives,
                max_cases=actual.max_merged_cases,
            )
        )

    report = next(iter(reports.values()))
    payload = {
        "schema_version": "skeleton.capability_curriculum_plan.v1",
        "model_id": report.model_id,
        "model_digest": report.model_digest,
        "artifact_sha256": report.artifact_sha256,
        "assessment_digests": [
            item.digest
            for item in sorted(
                assessments,
                key=lambda row: row.capability_id,
            )
        ],
        "target_capability_ids": list(targets),
        "selected_methods": [item.value for item in methods],
        "acquisition_suite_digest": (
            None if acquisition is None else acquisition.digest
        ),
        "retention_suite_digest": (
            None if retention is None else retention.digest
        ),
        "policy_digest": actual.digest,
        "production_authority": False,
    }
    return CurriculumPlan(
        model_id=report.model_id,
        model_digest=report.model_digest,
        artifact_sha256=report.artifact_sha256,
        assessments=tuple(
            sorted(
                assessments,
                key=lambda item: item.capability_id,
            )
        ),
        target_capability_ids=targets,
        selected_methods=tuple(methods),
        acquisition_suite=acquisition,
        retention_suite=retention,
        policy_digest=actual.digest,
        plan_digest=_digest(payload),
    )


def run_curriculum_learning_round(
    *,
    state: ContinualLearningState,
    objectives: Sequence[CapabilityObjective],
    examples_by_capability: Mapping[str, Sequence[TrainingExample]],
    work_dir: str | Path,
    challenger_output_path: str | Path,
    model_id: str,
    curriculum_policy: CurriculumPolicy | None = None,
    continual_policy: ContinualLearningPolicy | None = None,
    allocation_policy: TrainingAllocationPolicy | None = None,
    optimization_policy: TrainingOptimizationPolicy | None = None,
    efficiency_policy: TrainingEfficiencyPolicy | None = None,
    hidden_size: int = 32,
    final_epochs: int = 4,
    learning_rate: float = 0.05,
    max_vocab: int = 4_096,
    max_document_tokens: int = 1_024,
    seed: int = 0,
    temperature: float = 0.8,
) -> CurriculumRoundResult:
    """Plan and execute the next dependency-aware continual-learning round."""

    if not isinstance(state, ContinualLearningState):
        raise TypeError("state must be ContinualLearningState")
    if not isinstance(examples_by_capability, Mapping):
        raise TypeError("examples_by_capability must be a mapping")

    before = plan_capability_curriculum(
        model_path=state.active_champion.artifact_path,
        objectives=objectives,
        policy=curriculum_policy,
    )
    if before.complete or not before.target_capability_ids:
        return CurriculumRoundResult(
            before=before,
            continual_round=None,
            after=before,
            state=state,
        )
    if before.acquisition_suite is None or before.retention_suite is None:
        raise CurriculumError(
            "incomplete curriculum plan lacks evaluation suites"
        )

    examples: list[TrainingExample] = []
    seen_ids: set[str] = set()
    for capability_id in before.target_capability_ids:
        raw_examples = examples_by_capability.get(capability_id)
        if raw_examples is None:
            raise CurriculumError(
                "target capability lacks training examples: "
                + capability_id
            )
        for example in raw_examples:
            if not isinstance(example, TrainingExample):
                raise TypeError(
                    "capability examples must contain TrainingExample values"
                )
            if example.example_id in seen_ids:
                raise CurriculumError(
                    "curriculum target examples must have unique ids"
                )
            seen_ids.add(example.example_id)
            examples.append(example)
    if not examples:
        raise CurriculumError(
            "curriculum target produced no training examples"
        )

    next_state, continual_round = run_continual_learning_round(
        state=state,
        new_examples=tuple(examples),
        acquisition_suite=before.acquisition_suite,
        retention_suite=before.retention_suite,
        work_dir=work_dir,
        challenger_output_path=challenger_output_path,
        model_id=model_id,
        policy=continual_policy,
        requested_methods=before.selected_methods,
        allocation_policy=allocation_policy,
        optimization_policy=optimization_policy,
        efficiency_policy=efficiency_policy,
        hidden_size=hidden_size,
        final_epochs=final_epochs,
        learning_rate=learning_rate,
        max_vocab=max_vocab,
        max_document_tokens=max_document_tokens,
        seed=seed,
        temperature=temperature,
    )
    after = plan_capability_curriculum(
        model_path=next_state.active_champion.artifact_path,
        objectives=objectives,
        policy=curriculum_policy,
    )
    return CurriculumRoundResult(
        before=before,
        continual_round=continual_round,
        after=after,
        state=next_state,
    )


__all__ = [
    "CapabilityAssessment",
    "CapabilityObjective",
    "CurriculumError",
    "CurriculumPlan",
    "CurriculumPolicy",
    "CurriculumRoundResult",
    "plan_capability_curriculum",
    "run_curriculum_learning_round",
]
