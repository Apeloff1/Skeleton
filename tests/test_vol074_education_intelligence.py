from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skeleton/education/learning.py"
SPEC = importlib.util.spec_from_file_location("vol074_learning_test", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

EducationContractError = MODULE.EducationContractError
EvidenceKind = MODULE.EvidenceKind
InstructionKind = MODULE.InstructionKind
InstructionPlanner = MODULE.InstructionPlanner
LearnerEvidence = MODULE.LearnerEvidence
LearningObjective = MODULE.LearningObjective
LearningObjectiveGraph = MODULE.LearningObjectiveGraph
LearningOutcomeEvaluation = MODULE.LearningOutcomeEvaluation
OutcomeBinding = MODULE.OutcomeBinding
OutcomeDecision = MODULE.OutcomeDecision
OutcomeEvaluator = MODULE.OutcomeEvaluator

NOW = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
MANIFEST = ROOT / "machine/ai_education_contract.json"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def objective(
    objective_id: str,
    *,
    prerequisites: tuple[str, ...] = (),
    mastery_threshold: float = 0.8,
    uncertainty_ceiling: float = 0.35,
) -> LearningObjective:
    return LearningObjective(
        objective_id=objective_id,
        description=f"Learn {objective_id}.",
        prerequisites=prerequisites,
        mastery_threshold=mastery_threshold,
        uncertainty_ceiling=uncertainty_ceiling,
    )


def graph() -> LearningObjectiveGraph:
    return LearningObjectiveGraph(
        (
            objective("foundation"),
            objective("target", prerequisites=("foundation",)),
        )
    )


def observed(
    evidence_id: str,
    objective_id: str,
    *,
    learner_id: str = "learner-1",
    attempts: int = 8,
    correct: int = 8,
    misconceptions: tuple[str, ...] = (),
    observed_at: datetime = NOW - timedelta(minutes=5),
) -> LearnerEvidence:
    return LearnerEvidence(
        evidence_id=evidence_id,
        learner_id=learner_id,
        objective_id=objective_id,
        kind=EvidenceKind.ASSESSMENT,
        observed_at=observed_at.isoformat(),
        source_id="assessment-engine",
        content_digest=digest(evidence_id),
        attempts=attempts,
        correct=correct,
        misconception_ids=misconceptions,
    )


def binding() -> OutcomeBinding:
    return OutcomeBinding(
        owner_id="eval-learning-outcomes",
        suite_id="education-vol074-v1",
        minimum_post_score=0.8,
        minimum_gain=0.1,
        max_allowed_regression=0.02,
        require_misconception_correction=True,
    )


def learner_state(*evidence: LearnerEvidence):
    return graph().estimate(
        learner_id="learner-1",
        evidence=evidence,
        generated_at=NOW,
    )


def planner() -> InstructionPlanner:
    return InstructionPlanner(graph(), outcome_binding=binding())


def plan_with_mastered_foundation():
    state = learner_state(observed("foundation-1", "foundation"))
    return planner().plan(
        plan_id="plan-1",
        state=state,
        target_objective_id="target",
    )


def outcome(
    plan_receipt: str,
    *,
    owner_id: str = "eval-learning-outcomes",
    suite_id: str = "education-vol074-v1",
    pre_score: float = 0.6,
    post_score: float = 0.85,
    initial_misconceptions: int = 1,
    corrected_misconceptions: int = 1,
) -> LearningOutcomeEvaluation:
    return LearningOutcomeEvaluation(
        evaluation_id="eval-1",
        plan_receipt=plan_receipt,
        owner_id=owner_id,
        suite_id=suite_id,
        evaluated_at=NOW.isoformat(),
        pre_score=pre_score,
        post_score=post_score,
        initial_misconception_count=initial_misconceptions,
        corrected_misconception_count=corrected_misconceptions,
        evidence_digest=digest("outcome-evidence"),
    )


def test_manifest_binds_outcomes_not_engagement() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["volume"] == "VOL-074"
    assert payload["status"] == "implementation_contract"
    assert payload["outcome_binding"]["owner_id"] == "eval-learning-outcomes"
    assert "click-count" in payload["forbidden_promotion_signals"]
    assert "session-length" in payload["forbidden_promotion_signals"]


def test_objective_graph_is_canonical_across_input_order() -> None:
    first = graph()
    second = LearningObjectiveGraph(
        (
            objective("target", prerequisites=("foundation",)),
            objective("foundation"),
        )
    )
    assert first.objective_ids == ("foundation", "target")
    assert first.digest == second.digest


def test_unknown_prerequisite_fails_closed() -> None:
    with pytest.raises(EducationContractError, match="unknown prerequisite"):
        LearningObjectiveGraph(
            (objective("target", prerequisites=("missing",)),)
        )


def test_objective_cycle_fails_closed() -> None:
    with pytest.raises(EducationContractError, match="cycle"):
        LearningObjectiveGraph(
            (
                objective("a", prerequisites=("b",)),
                objective("b", prerequisites=("a",)),
            )
        )


def test_duplicate_objective_identity_fails_closed() -> None:
    with pytest.raises(EducationContractError, match="duplicate objective"):
        LearningObjectiveGraph((objective("same"), objective("same")))


def test_observed_evidence_rejects_impossible_score() -> None:
    with pytest.raises(EducationContractError, match="correct cannot exceed"):
        observed("bad", "foundation", attempts=2, correct=3)


def test_evidence_digest_must_be_canonical_sha256() -> None:
    with pytest.raises(EducationContractError, match="canonical sha256"):
        LearnerEvidence(
            evidence_id="bad",
            learner_id="learner-1",
            objective_id="foundation",
            kind=EvidenceKind.ASSESSMENT,
            observed_at=NOW.isoformat(),
            source_id="assessment-engine",
            content_digest="ABC",
            attempts=1,
            correct=1,
        )


def test_cross_learner_evidence_is_rejected() -> None:
    with pytest.raises(EducationContractError, match="cross-learner"):
        graph().estimate(
            learner_id="learner-1",
            evidence=(observed("other", "foundation", learner_id="learner-2"),),
            generated_at=NOW,
        )


def test_future_evidence_is_rejected() -> None:
    with pytest.raises(EducationContractError, match="future learner evidence"):
        graph().estimate(
            learner_id="learner-1",
            evidence=(
                observed(
                    "future",
                    "foundation",
                    observed_at=NOW + timedelta(seconds=1),
                ),
            ),
            generated_at=NOW,
        )


def test_duplicate_evidence_identity_fails_closed() -> None:
    item = observed("dup", "foundation")
    with pytest.raises(EducationContractError, match="duplicate evidence"):
        learner_state(item, item)


def test_unknown_objective_evidence_fails_closed() -> None:
    with pytest.raises(EducationContractError, match="unknown objective"):
        learner_state(observed("unknown", "outside-graph"))


def test_inferred_belief_is_not_observed_evidence() -> None:
    belief = learner_state(observed("f-1", "foundation")).belief("foundation")
    assert belief.record_class == "inference"
    assert belief.can_masquerade_as_observed_evidence is False


def test_mastery_uses_bounded_beta_posterior_and_explicit_uncertainty() -> None:
    belief = learner_state(
        observed("f-1", "foundation", attempts=8, correct=8)
    ).belief("foundation")
    assert belief.mastery_probability == pytest.approx(0.9)
    assert belief.confidence == pytest.approx(0.8)
    assert belief.uncertainty == pytest.approx(0.2)
    assert belief.confidence + belief.uncertainty == pytest.approx(1.0)


def test_no_evidence_means_high_uncertainty_not_false_mastery() -> None:
    belief = learner_state().belief("foundation")
    assert belief.attempts == 0
    assert belief.mastery_probability == pytest.approx(0.5)
    assert belief.confidence == pytest.approx(0.0)
    assert belief.uncertainty == pytest.approx(1.0)


def test_learner_state_is_deterministic_across_evidence_order() -> None:
    one = observed("f-1", "foundation", attempts=3, correct=2)
    two = observed("t-1", "target", attempts=4, correct=3)
    first = learner_state(one, two)
    second = learner_state(two, one)
    assert first.to_wire() == second.to_wire()


def test_state_receipt_tampering_is_detected() -> None:
    state = learner_state(observed("f-1", "foundation"))
    forged = replace(state, receipt_digest="0" * 64)
    with pytest.raises(EducationContractError, match="integrity"):
        graph().verify_state(forged)


def test_unmet_prerequisite_is_planned_before_target() -> None:
    state = learner_state()
    plan = planner().plan(
        plan_id="plan-1",
        state=state,
        target_objective_id="target",
    )
    assert all(step.objective_id == "foundation" for step in plan.steps)
    assert InstructionKind.PREREQUISITE in {step.kind for step in plan.steps}
    assert InstructionKind.ASSESSMENT in {step.kind for step in plan.steps}


def test_high_uncertainty_forces_diagnostic_step() -> None:
    state = learner_state()
    plan = planner().plan(
        plan_id="plan-1",
        state=state,
        target_objective_id="target",
    )
    assert plan.steps[0].kind is InstructionKind.DIAGNOSTIC


def test_mastered_prerequisite_allows_target_instruction() -> None:
    state = learner_state(observed("f-1", "foundation"))
    plan = planner().plan(
        plan_id="plan-1",
        state=state,
        target_objective_id="target",
    )
    assert all(step.objective_id == "target" for step in plan.steps)
    assert InstructionKind.EXPLANATION in {step.kind for step in plan.steps}


def test_mastered_target_uses_retrieval_not_reteach() -> None:
    state = learner_state(
        observed("f-1", "foundation"),
        observed("t-1", "target"),
    )
    plan = planner().plan(
        plan_id="plan-1",
        state=state,
        target_objective_id="target",
    )
    kinds = {step.kind for step in plan.steps}
    assert InstructionKind.RETRIEVAL_PRACTICE in kinds
    assert InstructionKind.EXPLANATION not in kinds


def test_plan_is_deterministic() -> None:
    state = learner_state(observed("f-1", "foundation"))
    first = planner().plan(
        plan_id="plan-1", state=state, target_objective_id="target"
    )
    second = planner().plan(
        plan_id="plan-1", state=state, target_objective_id="target"
    )
    assert first.to_wire() == second.to_wire()


def test_plan_receipt_tampering_is_detected() -> None:
    plan = plan_with_mastered_foundation()
    forged = replace(plan, receipt_digest="0" * 64)
    with pytest.raises(EducationContractError, match="integrity"):
        planner().verify(forged)


def test_outcome_passes_on_real_learning_gain_and_correction() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(plan.receipt_digest),
    )
    assert verdict.decision is OutcomeDecision.PASS
    assert verdict.reasons == ()


def test_outcome_fails_wrong_evaluation_owner() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(plan.receipt_digest, owner_id="engagement-owner"),
    )
    assert verdict.decision is OutcomeDecision.FAIL
    assert "evaluation-owner-mismatch" in verdict.reasons


def test_outcome_fails_wrong_suite() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(plan.receipt_digest, suite_id="click-suite"),
    )
    assert "evaluation-suite-mismatch" in verdict.reasons


def test_outcome_fails_plan_receipt_mismatch() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome("0" * 64),
    )
    assert "plan-receipt-mismatch" in verdict.reasons


def test_outcome_requires_post_threshold_for_nonmastered_learner() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(
            plan.receipt_digest,
            pre_score=0.6,
            post_score=0.75,
        ),
    )
    assert "post-score-below-threshold" in verdict.reasons


def test_outcome_requires_learning_gain_for_nonmastered_learner() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(
            plan.receipt_digest,
            pre_score=0.75,
            post_score=0.81,
        ),
    )
    assert "learning-gain-below-threshold" in verdict.reasons


def test_high_pre_score_can_pass_by_retention() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(
            plan.receipt_digest,
            pre_score=0.9,
            post_score=0.89,
            initial_misconceptions=0,
            corrected_misconceptions=0,
        ),
    )
    assert verdict.decision is OutcomeDecision.PASS


def test_retention_regression_fails_closed() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(
            plan.receipt_digest,
            pre_score=0.9,
            post_score=0.87,
            initial_misconceptions=0,
            corrected_misconceptions=0,
        ),
    )
    assert "outcome-regression" in verdict.reasons


def test_misconception_correction_is_required_when_present() -> None:
    plan = plan_with_mastered_foundation()
    verdict = OutcomeEvaluator().evaluate(
        plan,
        outcome(
            plan.receipt_digest,
            pre_score=0.6,
            post_score=0.9,
            initial_misconceptions=2,
            corrected_misconceptions=0,
        ),
    )
    assert "misconception-not-corrected" in verdict.reasons


def test_corrected_misconceptions_cannot_exceed_initial() -> None:
    plan = plan_with_mastered_foundation()
    with pytest.raises(EducationContractError, match="cannot exceed"):
        outcome(
            plan.receipt_digest,
            initial_misconceptions=1,
            corrected_misconceptions=2,
        )


def test_engagement_metrics_are_not_part_of_outcome_contract() -> None:
    fields = LearningOutcomeEvaluation.__dataclass_fields__
    forbidden = {"click_count", "dwell_time", "message_count", "session_length"}
    assert forbidden.isdisjoint(fields)


def test_prerequisite_order_is_transitive() -> None:
    deep = LearningObjectiveGraph(
        (
            objective("a"),
            objective("b", prerequisites=("a",)),
            objective("c", prerequisites=("b",)),
        )
    )
    assert deep.prerequisite_order("c") == ("a", "b")
