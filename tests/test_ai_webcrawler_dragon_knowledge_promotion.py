"""Regression tests for fail-closed knowledge promotion."""
import pytest

from skeleton.ai.webcrawler.dragon_knowledge_promotion import (
    PromotionPolicy, assess_promotion,
)
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass


def readings():
    return tuple(EvidencePass(
        f"source-{group}", "revision", f"pass-{i}", "mechanic",
        True, 1.0, 1.0, f"independent-{group}",
        f"frame-{i}", "observed mechanic",
    ) for group in range(3) for i in range(1, 4))


def test_promotion_fails_without_analysis_chain():
    decision = assess_promotion(
        "mechanic", readings(), (), (), authorized=True,
    )
    assert not decision.eligible
    assert any("chain" in reason for reason in decision.reasons)


def test_promotion_fails_without_independent_sources():
    single = tuple(x for x in readings() if x.source_id == "source-0")
    decision = assess_promotion(
        "mechanic", single, (), (), authorized=True,
        policy=PromotionPolicy(require_full_analysis=False),
    )
    assert not decision.eligible
    assert any("independent" in reason for reason in decision.reasons)


def test_promotion_fails_without_evidence():
    decision = assess_promotion(
        "mechanic", (), (), (), authorized=True,
        policy=PromotionPolicy(require_full_analysis=False),
    )
    assert not decision.eligible


def test_promotion_rejects_cross_claim_evidence():
    with pytest.raises(ValueError, match="cross-claim"):
        assess_promotion(
            "different", readings(), (), (), authorized=True,
        )


def test_promotion_requires_authorization():
    with pytest.raises(PermissionError):
        assess_promotion(
            "mechanic", readings(), (), (), authorized=False,
        )


def test_promotion_is_deterministic():
    a = assess_promotion(
        "mechanic", readings(), (), (), authorized=True,
    )
    b = assess_promotion(
        "mechanic", readings(), (), (), authorized=True,
    )
    assert a == b


def test_default_promotion_never_labels_heuristic_as_calibrated():
    decision = assess_promotion(
        "mechanic", readings(), (), (), authorized=True,
        policy=PromotionPolicy(require_full_analysis=False),
    )
    assert not decision.eligible
    assert decision.probability_semantics == "heuristic_logistic_score"
    assert decision.calibration_artifact_fingerprint is None
    assert any("calibrated probability" in x for x in decision.reasons)


def test_legacy_uncalibrated_mode_retains_heuristic_semantics():
    decision = assess_promotion(
        "mechanic", readings(), (), (), authorized=True,
        policy=PromotionPolicy(
            require_full_analysis=False,
            require_empirical_calibration=False,
        ),
    )
    assert decision.probability_semantics == "heuristic_logistic_score"
    assert decision.calibration_artifact_fingerprint is None
