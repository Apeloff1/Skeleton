from __future__ import annotations

from skeleton.ai.runtime.deferred.research_evaluation import EvalCase, EvalOutcome, EvaluationHarness
from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    ModelEvaluationPolicy,
    evaluate_model,
)


A = "a" * 64
B = "b" * 64
C = "c" * 64


def harness() -> EvaluationHarness:
    return EvaluationHarness(
        (
            EvalCase("c1", A, B),
            EvalCase("c2", B, C),
        )
    )


def outcomes(score1: float, score2: float):
    return (
        EvalOutcome("c1", A, score1),
        EvalOutcome("c2", B, score2),
    )


def test_model_eval_binds_quality_policy_and_clean_contamination() -> None:
    evidence = evaluate_model(
        harness(),
        outcomes(0.9, 0.8),
        model_digest=C,
        policy=ModelEvaluationPolicy("policy", 0.8, 0.7),
        contamination_status="clean",
    )
    assert evidence.passed is True
    assert evidence.blockers == ()
    assert evidence.production_authority is False


def test_model_eval_blocks_low_tail_or_contamination() -> None:
    evidence = evaluate_model(
        harness(),
        outcomes(0.95, 0.5),
        model_digest=C,
        policy=ModelEvaluationPolicy("policy", 0.8, 0.7),
        contamination_status="suspected",
    )
    assert evidence.passed is False
    assert evidence.blockers == (
        "contamination-not-clean",
        "minimum-case-score-below-policy",
    )
