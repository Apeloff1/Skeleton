from __future__ import annotations

from skeleton.ai.runtime.deferred.research_evaluation import EvalCase, EvalOutcome, EvaluationHarness
from skeleton.ai.runtime.deferred.research_evaluation_assurance import evaluate_agent


A = "a" * 64
B = "b" * 64
C = "c" * 64


def harness() -> EvaluationHarness:
    return EvaluationHarness(
        (
            EvalCase("task-1", A, B),
            EvalCase("task-2", B, C),
        )
    )


def test_agent_eval_requires_complete_trajectory_evidence() -> None:
    evidence = evaluate_agent(
        harness(),
        (
            EvalOutcome("task-1", A, 0.9, trajectory_digest=A),
            EvalOutcome("task-2", B, 0.8, trajectory_digest=B),
        ),
        agent_digest=C,
        minimum_score=0.75,
    )
    assert evidence.passed is True
    assert evidence.trajectory_coverage == 1.0
    assert evidence.production_authority is False


def test_agent_eval_exposes_missing_trajectory_and_low_score() -> None:
    evidence = evaluate_agent(
        harness(),
        (
            EvalOutcome("task-1", A, 0.4, trajectory_digest=A),
            EvalOutcome("task-2", B, 0.5),
        ),
        agent_digest=C,
        minimum_score=0.75,
    )
    assert evidence.passed is False
    assert evidence.blockers == (
        "mean-score-below-policy",
        "trajectory-evidence-incomplete",
    )
