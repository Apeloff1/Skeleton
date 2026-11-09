from __future__ import annotations

from decimal import Decimal
import hashlib

import pytest

from skeleton.ai.runtime.autonomous_engineering.improvement import (
    EvaluationVector,
    ImprovementCandidate,
    ImprovementError,
    PromotionPolicy,
    evaluate_improvement,
)


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _candidate():
    return ImprovementCandidate(
        candidate_id="candidate-1",
        author_id="builder",
        champion_model_digest=_sha("champion"),
        challenger_model_digest=_sha("challenger"),
        experiment_scope="isolated-lab",
        experiment_isolated=True,
        change_digest=_sha("change"),
        evidence_refs=("experiment:1",),
    )


def _eval(model, *, quality, safety, robustness, cost, suite="suite-v1", samples=100):
    return EvaluationVector(
        model_digest=_sha(model),
        evaluation_suite_digest=_sha(suite),
        sample_count=samples,
        quality=Decimal(quality),
        safety=Decimal(safety),
        robustness=Decimal(robustness),
        cost=Decimal(cost),
        evidence_refs=(f"eval:{model}",),
    )


def _policy():
    return PromotionPolicy(
        policy_id="policy-1",
        min_samples=100,
        min_quality_delta=Decimal("0.02"),
        min_safety=Decimal("0.95"),
        min_robustness=Decimal("0.90"),
        max_cost_ratio=Decimal("1.10"),
        max_canary_fraction=Decimal("0.10"),
    )


def test_independent_challenger_can_only_be_approved_for_canary() -> None:
    decision=evaluate_improvement(
        _candidate(),
        champion=_eval("champion",quality="0.80",safety="0.96",robustness="0.91",cost="1.0"),
        challenger=_eval("challenger",quality="0.84",safety="0.97",robustness="0.92",cost="1.05"),
        policy=_policy(),
        promoter_id="independent-verifier",
        canary_fraction=Decimal("0.05"),
        rollback_ref="rollback:champion-v1",
        promotion_evidence_refs=("promotion:review",),
    )
    assert decision.approved_for_canary is True
    assert decision.reason_codes == ("all_predeclared_gates_passed",)
    assert decision.canary_fraction == Decimal("0.050000")
    assert decision.rollback_ref == "rollback:champion-v1"


def test_self_promotion_is_rejected() -> None:
    with pytest.raises(ImprovementError,match="cannot independently promote"):
        evaluate_improvement(
            _candidate(),
            champion=_eval("champion",quality="0.8",safety="0.96",robustness="0.91",cost="1"),
            challenger=_eval("challenger",quality="0.9",safety="0.97",robustness="0.92",cost="1"),
            policy=_policy(),
            promoter_id="builder",
            canary_fraction="0.05",
            rollback_ref="rollback:v1",
            promotion_evidence_refs=("promotion:review",),
        )


def test_evaluation_suite_mismatch_blocks_benchmark_gaming() -> None:
    with pytest.raises(ImprovementError,match="identical predeclared"):
        evaluate_improvement(
            _candidate(),
            champion=_eval("champion",quality="0.8",safety="0.96",robustness="0.91",cost="1",suite="suite-a"),
            challenger=_eval("challenger",quality="0.99",safety="0.99",robustness="0.99",cost="0.5",suite="suite-b"),
            policy=_policy(),
            promoter_id="verifier",
            canary_fraction="0.05",
            rollback_ref="rollback:v1",
            promotion_evidence_refs=("promotion:review",),
        )


def test_safety_regression_blocks_even_when_quality_improves() -> None:
    decision=evaluate_improvement(
        _candidate(),
        champion=_eval("champion",quality="0.80",safety="0.99",robustness="0.91",cost="1"),
        challenger=_eval("challenger",quality="0.95",safety="0.96",robustness="0.92",cost="1"),
        policy=_policy(),
        promoter_id="verifier",
        canary_fraction="0.05",
        rollback_ref="rollback:v1",
        promotion_evidence_refs=("promotion:review",),
    )
    assert decision.approved_for_canary is False
    assert "safety_regression" in decision.reason_codes


def test_cost_regression_blocks_cheap_quality_gaming_inverse() -> None:
    decision=evaluate_improvement(
        _candidate(),
        champion=_eval("champion",quality="0.80",safety="0.96",robustness="0.91",cost="1"),
        challenger=_eval("challenger",quality="0.90",safety="0.97",robustness="0.92",cost="2"),
        policy=_policy(),
        promoter_id="verifier",
        canary_fraction="0.05",
        rollback_ref="rollback:v1",
        promotion_evidence_refs=("promotion:review",),
    )
    assert decision.approved_for_canary is False
    assert "cost_ratio_exceeded" in decision.reason_codes


def test_canary_cannot_exceed_predeclared_policy() -> None:
    with pytest.raises(ImprovementError,match="canary fraction"):
        evaluate_improvement(
            _candidate(),
            champion=_eval("champion",quality="0.80",safety="0.96",robustness="0.91",cost="1"),
            challenger=_eval("challenger",quality="0.90",safety="0.97",robustness="0.92",cost="1"),
            policy=_policy(),
            promoter_id="verifier",
            canary_fraction="0.5",
            rollback_ref="rollback:v1",
            promotion_evidence_refs=("promotion:review",),
        )


def test_nonisolated_candidate_is_rejected_at_construction() -> None:
    with pytest.raises(ImprovementError,match="isolated"):
        ImprovementCandidate(
            candidate_id="candidate-bad",
            author_id="builder",
            champion_model_digest=_sha("champion"),
            challenger_model_digest=_sha("challenger"),
            experiment_scope="production",
            experiment_isolated=False,
            change_digest=_sha("change"),
            evidence_refs=("experiment:bad",),
        )
