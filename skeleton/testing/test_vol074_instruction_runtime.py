from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "skeleton/learning/instruction_runtime.py"
SPEC = importlib.util.spec_from_file_location(
    "vol074_instruction_runtime",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

InstructionMode = MODULE.InstructionMode
InstructionPlan = MODULE.InstructionPlan
InstructionPlanner = MODULE.InstructionPlanner
InstructionRuntime = MODULE.InstructionRuntime
InstructionRuntimeError = MODULE.InstructionRuntimeError
InstructionStep = MODULE.InstructionStep
LearnerEvidence = MODULE.LearnerEvidence
LearnerEvidenceKind = MODULE.LearnerEvidenceKind
LearnerEvidenceLedger = MODULE.LearnerEvidenceLedger
LearnerSkillState = MODULE.LearnerSkillState
LearnerStateEstimator = MODULE.LearnerStateEstimator
LearningObjective = MODULE.LearningObjective
LearningObjectiveGraph = MODULE.LearningObjectiveGraph
LearningOutcome = MODULE.LearningOutcome
LearningSnapshot = MODULE.LearningSnapshot
OutcomeEvaluator = MODULE.OutcomeEvaluator
OutcomeStatus = MODULE.OutcomeStatus


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def evidence(
    evidence_id: str,
    *,
    objective_id: str = "objective.basics",
    attempt_id: str | None = None,
    kind: LearnerEvidenceKind = LearnerEvidenceKind.ATTEMPT,
    observed_at: float = 1.0,
    success: bool = True,
    score: float = 1.0,
    hints_used: int = 0,
    learner_id: str = "learner.test",
    prior_attempt_id: str | None = None,
    success_threshold: float = 0.5,
) -> LearnerEvidence:
    return LearnerEvidence(
        evidence_id=evidence_id,
        learner_id=learner_id,
        objective_id=objective_id,
        attempt_id=attempt_id or f"attempt.{evidence_id}",
        kind=kind,
        observed_at=observed_at,
        success=success,
        score=score,
        hints_used=hints_used,
        source_ref=f"exercise:{evidence_id}",
        response_digest=digest(f"response:{evidence_id}"),
        success_threshold=success_threshold,
        prior_attempt_id=prior_attempt_id,
    )


def objective(
    objective_id: str = "objective.basics",
    *,
    prerequisites: tuple[str, ...] = (),
    mastery_target: float = 0.70,
    max_uncertainty: float = 0.60,
    minimum_effective_evidence: float = 1.0,
    require_transfer: bool = False,
    require_retention: bool = False,
) -> LearningObjective:
    return LearningObjective(
        objective_id=objective_id,
        skill_id=f"skill.{objective_id.split('.')[-1]}",
        description=f"Learn {objective_id}.",
        prerequisites=prerequisites,
        mastery_target=mastery_target,
        max_uncertainty=max_uncertainty,
        minimum_effective_evidence=minimum_effective_evidence,
        require_transfer=require_transfer,
        require_retention=require_retention,
    )


def graph(*objectives: LearningObjective) -> LearningObjectiveGraph:
    return LearningObjectiveGraph(objectives or (objective(),))


def state(
    *,
    objective_id: str = "objective.basics",
    mastery: float = 0.70,
    uncertainty: float = 0.30,
    effective_evidence: float = 3.0,
    evidence_count: int = 3,
    successes: int = 2,
    failures: int = 1,
    correction_attempts: int = 0,
    correction_successes: int = 0,
    correction_success_rate: float | None = None,
    transfer_evidence: int = 0,
    retention_evidence: int = 0,
    latest_success: bool | None = True,
    learner_id: str = "learner.test",
) -> LearnerSkillState:
    return LearnerSkillState(
        learner_id=learner_id,
        objective_id=objective_id,
        mastery=mastery,
        uncertainty=uncertainty,
        effective_evidence=effective_evidence,
        evidence_count=evidence_count,
        successes=successes,
        failures=failures,
        correction_attempts=correction_attempts,
        correction_successes=correction_successes,
        correction_success_rate=correction_success_rate,
        transfer_evidence=transfer_evidence,
        retention_evidence=retention_evidence,
        last_observed_at=0.0 if evidence_count else None,
        latest_success=latest_success if evidence_count else None,
        evidence_digest=digest(
            f"{objective_id}:{mastery}:{uncertainty}:{effective_evidence}"
        ),
    )


def runtime(
    *objectives: LearningObjective,
) -> InstructionRuntime:
    return InstructionRuntime(graph(*objectives))


def test_observed_evidence_contains_no_mastery_or_inferred_confidence() -> None:
    record = evidence("e1")

    assert not hasattr(record, "mastery")
    assert not hasattr(record, "confidence")
    assert record.score == 1.0
    assert record.success is True


def test_evidence_digest_is_deterministic() -> None:
    first = evidence("e1")
    second = evidence("e1")

    assert first == second
    assert first.digest == second.digest


def test_correction_evidence_requires_prior_attempt() -> None:
    with pytest.raises(
        InstructionRuntimeError,
        match="requires prior_attempt_id",
    ):
        evidence(
            "correction",
            kind=LearnerEvidenceKind.CORRECTION,
        )


def test_non_correction_evidence_cannot_smuggle_prior_attempt() -> None:
    with pytest.raises(
        InstructionRuntimeError,
        match="reserved for correction",
    ):
        evidence(
            "attempt",
            prior_attempt_id="attempt.old",
        )


def test_correction_cannot_reference_itself() -> None:
    with pytest.raises(
        InstructionRuntimeError,
        match="own attempt_id",
    ):
        evidence(
            "correction",
            attempt_id="attempt.same",
            kind=LearnerEvidenceKind.CORRECTION,
            prior_attempt_id="attempt.same",
        )


def test_nonfinite_or_out_of_range_evidence_values_fail_closed() -> None:
    with pytest.raises(InstructionRuntimeError, match="score"):
        evidence("bad.score", score=float("nan"))
    with pytest.raises(InstructionRuntimeError, match="score"):
        evidence("bad.range", score=1.1)
    with pytest.raises(InstructionRuntimeError, match="observed_at"):
        evidence("bad.time", observed_at=float("inf"))


def test_estimator_is_order_independent_for_same_observed_sequence() -> None:
    estimator = LearnerStateEstimator()
    first = evidence("a", observed_at=1.0, score=0.8)
    second = evidence(
        "b",
        observed_at=2.0,
        success=False,
        score=0.2,
    )

    left = estimator.infer(
        "learner.test",
        "objective.basics",
        (second, first),
    )
    right = estimator.infer(
        "learner.test",
        "objective.basics",
        (first, second),
    )

    assert left == right
    assert left.digest == right.digest


def test_estimator_keeps_observed_records_unchanged() -> None:
    estimator = LearnerStateEstimator()
    records = (
        evidence("a", score=0.8),
        evidence("b", observed_at=2.0, score=0.9),
    )
    before = tuple(record.digest for record in records)

    estimator.infer(
        "learner.test",
        "objective.basics",
        records,
    )

    assert tuple(record.digest for record in records) == before


def test_more_consistent_evidence_reduces_uncertainty() -> None:
    estimator = LearnerStateEstimator()
    one = estimator.infer(
        "learner.test",
        "objective.basics",
        (evidence("a"),),
    )
    many = estimator.infer(
        "learner.test",
        "objective.basics",
        tuple(
            evidence(
                f"e{index}",
                observed_at=float(index),
            )
            for index in range(1, 11)
        ),
    )

    assert many.uncertainty < one.uncertainty
    assert many.mastery > one.mastery


def test_hints_reduce_effective_evidence_strength() -> None:
    estimator = LearnerStateEstimator()
    unsupported = estimator.infer(
        "learner.test",
        "objective.basics",
        (evidence("plain", hints_used=0),),
    )
    heavily_supported = estimator.infer(
        "learner.test",
        "objective.basics",
        (evidence("hinted", hints_used=8),),
    )

    assert (
        heavily_supported.effective_evidence
        < unsupported.effective_evidence
    )
    assert heavily_supported.mastery < unsupported.mastery


def test_transfer_and_retention_are_stronger_than_plain_attempts() -> None:
    estimator = LearnerStateEstimator()
    attempt = estimator.infer(
        "learner.test",
        "objective.basics",
        (evidence("attempt"),),
    )
    transfer = estimator.infer(
        "learner.test",
        "objective.basics",
        (
            evidence(
                "transfer",
                kind=LearnerEvidenceKind.TRANSFER,
            ),
        ),
    )
    retention = estimator.infer(
        "learner.test",
        "objective.basics",
        (
            evidence(
                "retention",
                kind=LearnerEvidenceKind.RETENTION,
            ),
        ),
    )

    assert transfer.effective_evidence > attempt.effective_evidence
    assert retention.effective_evidence > attempt.effective_evidence
    assert transfer.mastery > attempt.mastery
    assert retention.mastery > attempt.mastery


def test_estimator_rejects_cross_learner_or_objective_evidence() -> None:
    estimator = LearnerStateEstimator()

    with pytest.raises(
        InstructionRuntimeError,
        match="learner identity mismatch",
    ):
        estimator.infer(
            "learner.test",
            "objective.basics",
            (evidence("wrong", learner_id="learner.other"),),
        )

    with pytest.raises(
        InstructionRuntimeError,
        match="objective identity mismatch",
    ):
        estimator.infer(
            "learner.test",
            "objective.basics",
            (
                evidence(
                    "wrong",
                    objective_id="objective.other",
                ),
            ),
        )


def test_estimator_rejects_duplicate_evidence_identity() -> None:
    estimator = LearnerStateEstimator()
    first = evidence("duplicate", attempt_id="attempt.a")
    second = evidence(
        "duplicate",
        attempt_id="attempt.b",
        observed_at=2.0,
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="duplicate evidence identity",
    ):
        estimator.infer(
            "learner.test",
            "objective.basics",
            (first, second),
        )


def test_empty_inference_is_uncertain_prior_not_fake_zero_mastery() -> None:
    inferred = LearnerStateEstimator().infer(
        "learner.test",
        "objective.basics",
        (),
    )

    assert inferred.mastery == pytest.approx(0.5)
    assert inferred.uncertainty == pytest.approx(1.0)
    assert inferred.evidence_count == 0
    assert inferred.effective_evidence == 0.0


def test_objective_graph_is_deterministic_topological_order() -> None:
    basics = objective("objective.basics")
    advanced = objective(
        "objective.advanced",
        prerequisites=("objective.basics",),
    )

    first = graph(advanced, basics)
    second = graph(basics, advanced)

    assert first.objectives == second.objectives
    assert first.digest == second.digest
    assert [item.objective_id for item in first.objectives] == [
        "objective.basics",
        "objective.advanced",
    ]


def test_objective_graph_rejects_unknown_prerequisite() -> None:
    with pytest.raises(
        InstructionRuntimeError,
        match="unknown prerequisite",
    ):
        graph(
            objective(
                "objective.advanced",
                prerequisites=("objective.missing",),
            )
        )


def test_objective_graph_rejects_cycle() -> None:
    left = objective(
        "objective.left",
        prerequisites=("objective.right",),
    )
    right = objective(
        "objective.right",
        prerequisites=("objective.left",),
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="prerequisite cycle",
    ):
        graph(left, right)


def test_objective_graph_rejects_duplicate_identity() -> None:
    with pytest.raises(
        InstructionRuntimeError,
        match="duplicate objective identity",
    ):
        graph(objective(), objective())


def test_objective_self_dependency_fails_at_construction() -> None:
    with pytest.raises(
        InstructionRuntimeError,
        match="cannot require itself",
    ):
        objective(
            "objective.self",
            prerequisites=("objective.self",),
        )


def test_objective_satisfaction_requires_mastery_uncertainty_and_evidence() -> None:
    target = objective(
        mastery_target=0.75,
        max_uncertainty=0.30,
        minimum_effective_evidence=2.0,
    )

    assert target.is_satisfied(
        state(
            mastery=0.80,
            uncertainty=0.20,
            effective_evidence=3.0,
        )
    )
    assert not target.is_satisfied(
        state(
            mastery=0.70,
            uncertainty=0.20,
            effective_evidence=3.0,
        )
    )
    assert not target.is_satisfied(
        state(
            mastery=0.80,
            uncertainty=0.40,
            effective_evidence=3.0,
        )
    )
    assert not target.is_satisfied(
        state(
            mastery=0.80,
            uncertainty=0.20,
            effective_evidence=1.0,
        )
    )


def test_objective_can_require_transfer_and_retention_evidence() -> None:
    target = objective(
        mastery_target=0.70,
        max_uncertainty=0.50,
        require_transfer=True,
        require_retention=True,
    )

    assert not target.is_satisfied(
        state(
            transfer_evidence=0,
            retention_evidence=1,
        )
    )
    assert not target.is_satisfied(
        state(
            transfer_evidence=1,
            retention_evidence=0,
        )
    )
    assert target.is_satisfied(
        state(
            transfer_evidence=1,
            retention_evidence=1,
        )
    )


def test_prerequisite_gates_advanced_objective() -> None:
    basics = objective(
        "objective.basics",
        mastery_target=0.70,
        max_uncertainty=0.50,
    )
    advanced = objective(
        "objective.advanced",
        prerequisites=("objective.basics",),
    )
    curriculum = graph(basics, advanced)

    not_ready = curriculum.ready(
        {
            "objective.basics": state(
                mastery=0.60,
                uncertainty=0.20,
            )
        }
    )
    ready = curriculum.ready(
        {
            "objective.basics": state(
                mastery=0.90,
                uncertainty=0.20,
            )
        }
    )

    assert [item.objective_id for item in not_ready] == [
        "objective.basics",
    ]
    assert [item.objective_id for item in ready] == [
        "objective.basics",
        "objective.advanced",
    ]


def test_planner_collects_baseline_before_inferring_mastery() -> None:
    planner = InstructionPlanner()
    curriculum = graph(objective())

    plan = planner.plan(
        learner_id="learner.test",
        graph=curriculum,
        states={},
    )

    assert len(plan.steps) == 1
    assert plan.steps[0].mode is InstructionMode.ASSESS
    assert (
        plan.steps[0].required_evidence_kind
        is LearnerEvidenceKind.ATTEMPT
    )


def test_planner_prioritizes_correction_after_observed_failure() -> None:
    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=graph(objective()),
        states={
            "objective.basics": state(
                mastery=0.50,
                uncertainty=0.30,
                latest_success=False,
            )
        },
    )

    assert plan.steps[0].mode is InstructionMode.CORRECT
    assert (
        plan.steps[0].required_evidence_kind
        is LearnerEvidenceKind.CORRECTION
    )


def test_planner_assesses_when_state_uncertainty_is_too_high() -> None:
    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=graph(
            objective(
                max_uncertainty=0.20,
                minimum_effective_evidence=1.0,
            )
        ),
        states={
            "objective.basics": state(
                mastery=0.60,
                uncertainty=0.50,
                effective_evidence=4.0,
            )
        },
    )

    assert plan.steps[0].mode is InstructionMode.ASSESS
    assert (
        plan.steps[0].required_evidence_kind
        is LearnerEvidenceKind.EXPLANATION_CHECK
    )


def test_planner_uses_explanation_for_low_supported_mastery() -> None:
    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=graph(
            objective(
                mastery_target=0.80,
                max_uncertainty=0.50,
                minimum_effective_evidence=1.0,
            )
        ),
        states={
            "objective.basics": state(
                mastery=0.30,
                uncertainty=0.20,
                effective_evidence=3.0,
            )
        },
    )

    assert plan.steps[0].mode is InstructionMode.EXPLAIN


def test_planner_uses_practice_below_mastery_target() -> None:
    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=graph(
            objective(
                mastery_target=0.80,
                max_uncertainty=0.50,
            )
        ),
        states={
            "objective.basics": state(
                mastery=0.60,
                uncertainty=0.20,
            )
        },
    )

    assert plan.steps[0].mode is InstructionMode.PRACTICE


def test_planner_requests_transfer_before_objective_completion() -> None:
    target = objective(
        mastery_target=0.70,
        max_uncertainty=0.50,
        require_transfer=True,
    )
    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=graph(target),
        states={
            "objective.basics": state(
                mastery=0.85,
                uncertainty=0.20,
                transfer_evidence=0,
            )
        },
    )

    assert plan.steps[0].mode is InstructionMode.TRANSFER
    assert (
        plan.steps[0].required_evidence_kind
        is LearnerEvidenceKind.TRANSFER
    )


def test_planner_requests_retention_before_objective_completion() -> None:
    target = objective(
        mastery_target=0.70,
        max_uncertainty=0.50,
        require_retention=True,
    )
    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=graph(target),
        states={
            "objective.basics": state(
                mastery=0.85,
                uncertainty=0.20,
                retention_evidence=0,
            )
        },
    )

    assert plan.steps[0].mode is InstructionMode.REVIEW
    assert (
        plan.steps[0].required_evidence_kind
        is LearnerEvidenceKind.RETENTION
    )


def test_completed_prerequisite_unlocks_next_plan_step() -> None:
    basics = objective(
        "objective.basics",
        mastery_target=0.70,
        max_uncertainty=0.50,
    )
    advanced = objective(
        "objective.advanced",
        prerequisites=("objective.basics",),
        mastery_target=0.80,
        max_uncertainty=0.50,
    )
    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=graph(advanced, basics),
        states={
            "objective.basics": state(
                objective_id="objective.basics",
                mastery=0.90,
                uncertainty=0.20,
            )
        },
    )

    assert [step.objective_id for step in plan.steps] == [
        "objective.advanced",
    ]
    assert plan.steps[0].mode is InstructionMode.ASSESS


def test_planner_is_deterministic_across_state_mapping_order() -> None:
    basics = objective("objective.basics")
    other = objective("objective.other")
    curriculum = graph(other, basics)
    states_a = {
        "objective.basics": state(
            objective_id="objective.basics",
            mastery=0.60,
        ),
        "objective.other": state(
            objective_id="objective.other",
            mastery=0.60,
        ),
    }
    states_b = {
        "objective.other": states_a["objective.other"],
        "objective.basics": states_a["objective.basics"],
    }

    left = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=curriculum,
        states=states_a,
    )
    right = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=curriculum,
        states=states_b,
    )

    assert left == right
    assert left.digest == right.digest


def test_plan_limit_is_hard_bounded() -> None:
    curriculum = graph(
        *(objective(f"objective.o{index}") for index in range(10))
    )

    plan = InstructionPlanner().plan(
        learner_id="learner.test",
        graph=curriculum,
        states={},
        max_steps=3,
    )

    assert len(plan.steps) == 3


def test_outcome_improves_on_mastery_gain() -> None:
    evaluator = OutcomeEvaluator(minimum_mastery_gain=0.05)
    before = state(mastery=0.50, uncertainty=0.50)
    after = state(mastery=0.65, uncertainty=0.35)

    outcome = evaluator.evaluate(
        before=before,
        after=after,
        new_evidence=(evidence("new"),),
    )

    assert outcome.status is OutcomeStatus.IMPROVED
    assert outcome.mastery_delta == pytest.approx(0.15)
    assert outcome.uncertainty_reduction == pytest.approx(0.15)


def test_outcome_marks_meaningful_regression() -> None:
    evaluator = OutcomeEvaluator(regression_tolerance=0.03)
    before = state(mastery=0.70)
    after = state(mastery=0.60)

    outcome = evaluator.evaluate(
        before=before,
        after=after,
        new_evidence=(
            evidence(
                "failure",
                success=False,
                score=0.0,
            ),
        ),
    )

    assert outcome.status is OutcomeStatus.REGRESSED


def test_outcome_without_new_evidence_is_insufficient() -> None:
    baseline = state()

    outcome = OutcomeEvaluator().evaluate(
        before=baseline,
        after=baseline,
        new_evidence=(),
    )

    assert outcome.status is OutcomeStatus.INSUFFICIENT_EVIDENCE


def test_successful_correction_counts_as_learning_outcome() -> None:
    before = state(
        mastery=0.50,
        uncertainty=0.40,
        latest_success=False,
    )
    after = state(
        mastery=0.52,
        uncertainty=0.39,
        correction_attempts=1,
        correction_successes=1,
        correction_success_rate=1.0,
    )
    failed = evidence(
        "failed",
        attempt_id="attempt.failed",
        success=False,
        score=0.0,
    )
    correction = evidence(
        "correction",
        attempt_id="attempt.correction",
        kind=LearnerEvidenceKind.CORRECTION,
        observed_at=2.0,
        prior_attempt_id="attempt.failed",
    )

    outcome = OutcomeEvaluator(
        minimum_mastery_gain=0.10
    ).evaluate(
        before=before,
        after=after,
        new_evidence=(correction,),
        prior_evidence=(failed,),
    )

    assert outcome.status is OutcomeStatus.IMPROVED
    assert outcome.corrected_after_failure is True
    assert outcome.correction_successes == 1


def test_transfer_and_retention_success_count_as_outcomes() -> None:
    baseline = state(mastery=0.70)
    followup = state(mastery=0.70)

    transfer = OutcomeEvaluator().evaluate(
        before=baseline,
        after=followup,
        new_evidence=(
            evidence(
                "transfer",
                kind=LearnerEvidenceKind.TRANSFER,
            ),
        ),
    )
    retention = OutcomeEvaluator().evaluate(
        before=baseline,
        after=followup,
        new_evidence=(
            evidence(
                "retention",
                kind=LearnerEvidenceKind.RETENTION,
            ),
        ),
    )

    assert transfer.status is OutcomeStatus.IMPROVED
    assert transfer.transfer_successes == 1
    assert retention.status is OutcomeStatus.IMPROVED
    assert retention.retention_successes == 1


def test_outcome_evaluator_has_no_engagement_input_surface() -> None:
    fields = LearningOutcome.__dataclass_fields__

    assert "time_on_task" not in fields
    assert "clicks" not in fields
    assert "messages" not in fields
    assert "engagement" not in fields


def test_ledger_append_is_idempotent_for_identical_evidence() -> None:
    ledger = LearnerEvidenceLedger()
    record = evidence("same")

    first = ledger.append(record)
    second = ledger.append(record)

    assert first is second
    assert ledger.records(
        learner_id="learner.test"
    ) == (record,)


def test_ledger_rejects_evidence_identity_collision() -> None:
    ledger = LearnerEvidenceLedger()
    ledger.append(evidence("same", attempt_id="attempt.one"))

    with pytest.raises(
        InstructionRuntimeError,
        match="evidence identity collision",
    ):
        ledger.append(
            evidence(
                "same",
                attempt_id="attempt.two",
                observed_at=2.0,
            )
        )


def test_ledger_rejects_attempt_identity_collision() -> None:
    ledger = LearnerEvidenceLedger()
    ledger.append(evidence("first", attempt_id="attempt.same"))

    with pytest.raises(
        InstructionRuntimeError,
        match="attempt identity collision",
    ):
        ledger.append(
            evidence(
                "second",
                attempt_id="attempt.same",
                observed_at=2.0,
            )
        )


def test_ledger_requires_correction_prior_to_exist() -> None:
    ledger = LearnerEvidenceLedger()

    with pytest.raises(
        InstructionRuntimeError,
        match="unknown prior attempt",
    ):
        ledger.append(
            evidence(
                "correction",
                kind=LearnerEvidenceKind.CORRECTION,
                prior_attempt_id="attempt.missing",
            )
        )


def test_ledger_correction_requires_unsuccessful_prior() -> None:
    ledger = LearnerEvidenceLedger()
    ledger.append(
        evidence(
            "success",
            attempt_id="attempt.success",
            success=True,
        )
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="unsuccessful attempt",
    ):
        ledger.append(
            evidence(
                "correction",
                attempt_id="attempt.correction",
                kind=LearnerEvidenceKind.CORRECTION,
                observed_at=2.0,
                prior_attempt_id="attempt.success",
            )
        )


def test_ledger_correction_cannot_cross_learner_boundary() -> None:
    ledger = LearnerEvidenceLedger()
    ledger.append(
        evidence(
            "failed",
            attempt_id="attempt.failed",
            success=False,
            score=0.0,
        )
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="crosses learner/objective boundary",
    ):
        ledger.append(
            evidence(
                "correction",
                learner_id="learner.other",
                attempt_id="attempt.correction",
                kind=LearnerEvidenceKind.CORRECTION,
                observed_at=2.0,
                prior_attempt_id="attempt.failed",
            )
        )


def test_ledger_correction_cannot_cross_objective_boundary() -> None:
    ledger = LearnerEvidenceLedger()
    ledger.append(
        evidence(
            "failed",
            attempt_id="attempt.failed",
            success=False,
            score=0.0,
        )
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="crosses learner/objective boundary",
    ):
        ledger.append(
            evidence(
                "correction",
                objective_id="objective.other",
                attempt_id="attempt.correction",
                kind=LearnerEvidenceKind.CORRECTION,
                observed_at=2.0,
                prior_attempt_id="attempt.failed",
            )
        )


def test_ledger_correction_cannot_predate_failure() -> None:
    ledger = LearnerEvidenceLedger()
    ledger.append(
        evidence(
            "failed",
            attempt_id="attempt.failed",
            observed_at=10.0,
            success=False,
            score=0.0,
        )
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="cannot predate",
    ):
        ledger.append(
            evidence(
                "correction",
                attempt_id="attempt.correction",
                kind=LearnerEvidenceKind.CORRECTION,
                observed_at=9.0,
                prior_attempt_id="attempt.failed",
            )
        )


def test_full_ledger_still_allows_idempotent_replay() -> None:
    ledger = LearnerEvidenceLedger(max_records=1)
    record = evidence("one")
    ledger.append(record)

    assert ledger.append(record) is record

    with pytest.raises(
        InstructionRuntimeError,
        match="capacity reached",
    ):
        ledger.append(
            evidence("two", observed_at=2.0)
        )


def test_runtime_state_keeps_raw_evidence_and_inference_separate() -> None:
    rt = runtime()
    record = evidence("observed")
    rt.record(record)

    inferred = rt.state(
        learner_id="learner.test",
        objective_id="objective.basics",
    )

    assert inferred.evidence_count == 1
    assert rt.ledger.records(
        learner_id="learner.test",
        objective_id="objective.basics",
    ) == (record,)
    assert not hasattr(record, "mastery")


def test_runtime_plan_changes_from_assessment_to_correction() -> None:
    target = objective(
        mastery_target=0.80,
        max_uncertainty=0.90,
        minimum_effective_evidence=0.5,
    )
    rt = runtime(target)

    initial = rt.plan("learner.test")
    assert initial.steps[0].mode is InstructionMode.ASSESS

    rt.record(
        evidence(
            "failed",
            attempt_id="attempt.failed",
            success=False,
            score=0.0,
        )
    )
    after_failure = rt.plan("learner.test")

    assert after_failure.steps[0].mode is InstructionMode.CORRECT


def test_runtime_correction_updates_state_and_outcome() -> None:
    target = objective(
        mastery_target=0.70,
        max_uncertainty=0.90,
        minimum_effective_evidence=0.5,
    )
    rt = runtime(target)
    failure = evidence(
        "failed",
        attempt_id="attempt.failed",
        observed_at=1.0,
        success=False,
        score=0.0,
    )
    rt.record(failure)
    baseline_ids = ("failed",)

    correction = evidence(
        "corrected",
        attempt_id="attempt.corrected",
        kind=LearnerEvidenceKind.CORRECTION,
        observed_at=2.0,
        success=True,
        score=1.0,
        prior_attempt_id="attempt.failed",
    )
    rt.record(correction)

    outcome = rt.evaluate(
        learner_id="learner.test",
        objective_id="objective.basics",
        baseline_evidence_ids=baseline_ids,
    )

    assert outcome.corrected_after_failure is True
    assert outcome.status is OutcomeStatus.IMPROVED
    assert outcome.evidence_ids == ("corrected",)


def test_runtime_outcome_baseline_must_be_chronological_prefix() -> None:
    rt = runtime()
    rt.record(evidence("first", observed_at=1.0))
    rt.record(evidence("second", observed_at=2.0))

    with pytest.raises(
        InstructionRuntimeError,
        match="chronological evidence prefix",
    ):
        rt.evaluate(
            learner_id="learner.test",
            objective_id="objective.basics",
            baseline_evidence_ids=("second",),
        )


def test_runtime_outcome_rejects_unknown_baseline_identity() -> None:
    rt = runtime()
    rt.record(evidence("first"))

    with pytest.raises(
        InstructionRuntimeError,
        match="unknown evidence",
    ):
        rt.evaluate(
            learner_id="learner.test",
            objective_id="objective.basics",
            baseline_evidence_ids=("missing",),
        )


def test_snapshot_binds_ledger_graph_state_and_plan() -> None:
    rt = runtime()
    rt.record(evidence("first"))
    snapshot = rt.snapshot("learner.test")

    assert snapshot.ledger_digest == rt.ledger.digest
    assert snapshot.graph_digest == rt.graph.digest
    assert snapshot.plan.objective_graph_digest == rt.graph.digest
    assert snapshot.digest


def test_snapshot_rejects_plan_state_substitution() -> None:
    rt = runtime()
    snapshot = rt.snapshot("learner.test")
    forged_plan = replace(
        snapshot.plan,
        state_digest="0" * 64,
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="plan/state identity mismatch",
    ):
        replace(snapshot, plan=forged_plan)


def test_snapshot_rejects_graph_substitution() -> None:
    rt = runtime()
    snapshot = rt.snapshot("learner.test")
    forged_plan = replace(
        snapshot.plan,
        objective_graph_digest="1" * 64,
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="plan/graph identity mismatch",
    ):
        replace(snapshot, plan=forged_plan)


def test_runtime_unlocks_prerequisite_sequence_from_real_evidence() -> None:
    basics = objective(
        "objective.basics",
        mastery_target=0.65,
        max_uncertainty=0.90,
        minimum_effective_evidence=0.5,
    )
    advanced = objective(
        "objective.advanced",
        prerequisites=("objective.basics",),
        mastery_target=0.70,
        max_uncertainty=0.90,
        minimum_effective_evidence=0.5,
    )
    rt = runtime(basics, advanced)

    before = rt.plan("learner.test")
    assert [step.objective_id for step in before.steps] == [
        "objective.basics",
    ]

    rt.record(
        evidence(
            "basics.success",
            objective_id="objective.basics",
            score=1.0,
        )
    )
    after = rt.plan("learner.test")

    assert [step.objective_id for step in after.steps] == [
        "objective.advanced",
    ]


def test_runtime_requires_transfer_and_retention_when_objective_demands_them() -> None:
    target = objective(
        mastery_target=0.60,
        max_uncertainty=0.90,
        minimum_effective_evidence=0.5,
        require_transfer=True,
        require_retention=True,
    )
    rt = runtime(target)
    rt.record(evidence("attempt.success"))

    first = rt.plan("learner.test")
    assert first.steps[0].mode is InstructionMode.TRANSFER

    rt.record(
        evidence(
            "transfer.success",
            attempt_id="attempt.transfer",
            kind=LearnerEvidenceKind.TRANSFER,
            observed_at=2.0,
        )
    )
    second = rt.plan("learner.test")
    assert second.steps[0].mode is InstructionMode.REVIEW

    rt.record(
        evidence(
            "retention.success",
            attempt_id="attempt.retention",
            kind=LearnerEvidenceKind.RETENTION,
            observed_at=3.0,
        )
    )
    completed = rt.plan("learner.test")
    assert completed.steps == ()


def test_canonical_and_ai_instruction_runtime_are_byte_identical() -> None:
    canonical = ROOT / "skeleton/learning/instruction_runtime.py"
    mirror = ROOT / "skeleton/ai/learning/instruction_runtime.py"

    assert canonical.read_bytes() == mirror.read_bytes()


def test_estimator_rejects_forged_correction_lineage_without_ledger() -> None:
    correction = evidence(
        "forged.correction",
        attempt_id="attempt.correction",
        kind=LearnerEvidenceKind.CORRECTION,
        observed_at=2.0,
        prior_attempt_id="attempt.missing",
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="unknown prior attempt",
    ):
        LearnerStateEstimator().infer(
            "learner.test",
            "objective.basics",
            (correction,),
        )


def test_estimator_rejects_correction_of_success_without_ledger() -> None:
    successful = evidence(
        "successful",
        attempt_id="attempt.successful",
        success=True,
    )
    correction = evidence(
        "correction.success",
        attempt_id="attempt.correction",
        kind=LearnerEvidenceKind.CORRECTION,
        observed_at=2.0,
        prior_attempt_id="attempt.successful",
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="unsuccessful attempt",
    ):
        LearnerStateEstimator().infer(
            "learner.test",
            "objective.basics",
            (successful, correction),
        )


def test_estimator_rejects_duplicate_attempt_identity() -> None:
    first = evidence(
        "first",
        attempt_id="attempt.same",
        observed_at=1.0,
    )
    second = evidence(
        "second",
        attempt_id="attempt.same",
        observed_at=2.0,
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="duplicate attempt identity",
    ):
        LearnerStateEstimator().infer(
            "learner.test",
            "objective.basics",
            (first, second),
        )


def test_outcome_evaluator_rejects_unproven_correction_lineage() -> None:
    correction = evidence(
        "correction",
        attempt_id="attempt.correction",
        kind=LearnerEvidenceKind.CORRECTION,
        observed_at=2.0,
        prior_attempt_id="attempt.missing",
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="unknown prior attempt",
    ):
        OutcomeEvaluator().evaluate(
            before=state(latest_success=False),
            after=state(
                mastery=0.75,
                correction_attempts=1,
                correction_successes=1,
                correction_success_rate=1.0,
            ),
            new_evidence=(correction,),
        )


def test_evidence_success_is_bound_to_declared_score_threshold() -> None:
    passing = evidence(
        "passing",
        score=0.80,
        success=True,
        success_threshold=0.75,
    )
    failing = evidence(
        "failing",
        score=0.70,
        success=False,
        success_threshold=0.75,
    )

    assert passing.success is True
    assert failing.success is False

    with pytest.raises(
        InstructionRuntimeError,
        match="success must match score",
    ):
        evidence(
            "inconsistent",
            score=0.20,
            success=True,
            success_threshold=0.75,
        )


def test_outcome_evaluator_rejects_evidence_older_than_baseline_state() -> None:
    before = replace(
        state(),
        last_observed_at=10.0,
    )
    after = replace(
        state(mastery=0.75),
        last_observed_at=10.0,
    )

    with pytest.raises(
        InstructionRuntimeError,
        match="predates baseline state",
    ):
        OutcomeEvaluator().evaluate(
            before=before,
            after=after,
            new_evidence=(
                evidence(
                    "old",
                    observed_at=9.0,
                ),
            ),
        )


def test_instruction_policy_is_identity_neutral_for_equal_learning_state() -> None:
    curriculum = graph(
        objective(
            mastery_target=0.80,
            max_uncertainty=0.50,
        )
    )
    first_state = state(
        learner_id="learner.alpha",
        mastery=0.60,
        uncertainty=0.20,
    )
    second_state = replace(
        first_state,
        learner_id="learner.beta",
        evidence_digest=digest("same-evidence-shape-beta"),
    )

    first = InstructionPlanner().plan(
        learner_id="learner.alpha",
        graph=curriculum,
        states={"objective.basics": first_state},
    )
    second = InstructionPlanner().plan(
        learner_id="learner.beta",
        graph=curriculum,
        states={"objective.basics": second_state},
    )

    first_policy = tuple(
        (
            step.objective_id,
            step.mode,
            step.required_evidence_kind,
            step.success_threshold,
            step.max_hints,
        )
        for step in first.steps
    )
    second_policy = tuple(
        (
            step.objective_id,
            step.mode,
            step.required_evidence_kind,
            step.success_threshold,
            step.max_hints,
        )
        for step in second.steps
    )

    assert first_policy == second_policy


def test_learning_package_exports_remain_byte_identical() -> None:
    canonical = ROOT / "skeleton/learning/__init__.py"
    mirror = ROOT / "skeleton/ai/learning/__init__.py"

    assert canonical.read_bytes() == mirror.read_bytes()

def test_latest_success_fails_closed_on_conflicting_newest_evidence_cohort() -> None:
    failed = evidence(
        "latest.a.failure",
        attempt_id="attempt.latest.failure",
        observed_at=10.0,
        success=False,
        score=0.0,
    )
    passed = evidence(
        "latest.z.success",
        attempt_id="attempt.latest.success",
        observed_at=10.0,
        success=True,
        score=1.0,
    )

    estimator = LearnerStateEstimator()
    first = estimator.infer(
        "learner.test",
        "objective.basics",
        (failed, passed),
    )
    second = estimator.infer(
        "learner.test",
        "objective.basics",
        (passed, failed),
    )

    assert first.latest_success is False
    assert second.latest_success is False
    assert first.digest == second.digest
