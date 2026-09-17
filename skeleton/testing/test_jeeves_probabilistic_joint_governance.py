from __future__ import annotations

import math
from dataclasses import replace

import pytest

from skeleton.jeeves.probabilistic_calibration import (
    CalibrationConfig,
    DistributionObservation,
    calibrate_distributions,
)
from skeleton.jeeves.probabilistic_conformal import ConformalConfig
from skeleton.jeeves.probabilistic_conformal_stratified import (
    StratifiedConformalConfig,
    StratifiedForecastObservation,
    evaluate_stratified_conformal,
)
from skeleton.jeeves.probabilistic_contracts import (
    ProbabilisticPromotionGate,
    evaluate_probabilistic_promotion,
    validate_probabilistic_promotion_decision,
)
from skeleton.jeeves.probabilistic_ensemble import (
    BayesianEnsembleConfig,
    OnlineBayesianEnsemble,
)
from skeleton.jeeves.probabilistic_governance import (
    ConformalGovernanceGate,
    evaluate_conformal_governance,
    validate_conformal_governance_decision,
)
from skeleton.jeeves.probabilistic_joint_governance import (
    JointProbabilisticGovernanceGate,
    evaluate_joint_probabilistic_governance,
    validate_joint_probabilistic_governance_decision,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _trend(count: int = 90) -> tuple[float, ...]:
    return tuple(
        50.0 + 0.25 * index + 0.05 * math.sin(index)
        for index in range(count)
    )


def _child_decisions(*, point_min_folds: int = 1, conformal_min_steps: int = 1):
    ensemble = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=15, step=2),
    ).evaluate(_trend())
    calibration = calibrate_distributions(
        tuple(
            DistributionObservation(
                forecast=step.predictive,
                actual=step.actual,
                target_index=step.target_index,
            )
            for step in ensemble.steps
        ),
        config=CalibrationConfig(levels=(0.5, 0.8, 0.9, 0.95)),
    )
    point = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=point_min_folds,
            min_calibration_score=0.0,
            max_coverage_gap=1.0,
            max_drift_events_per_100=100.0,
            min_effective_model_count=1.0,
        ),
    )

    conformal_report = evaluate_stratified_conformal(
        tuple(
            StratifiedForecastObservation(
                target_index=step.target_index,
                actual=step.actual,
                predictive=step.predictive,
            )
            for step in ensemble.steps
        ),
        config=StratifiedConformalConfig(
            conformal=ConformalConfig(
                alpha=0.20,
                min_calibration=4,
                calibration_window=32,
                adaptive_rate=0.0,
                min_alpha=0.05,
                max_alpha=0.45,
            ),
            condition_on_regime=False,
        ),
    )
    uncertainty = evaluate_conformal_governance(
        conformal_report,
        gate=ConformalGovernanceGate(
            min_scored_steps=conformal_min_steps,
            max_absolute_coverage_gap=1.0,
            max_bucket_coverage_gap=1.0,
            max_fallback_rate=1.0,
            max_unevidenced_step_rate=1.0,
            min_evidenced_buckets=0,
            min_bucket_uses=1,
        ),
    )
    return point, uncertainty


def test_child_decisions_are_independently_self_verifying() -> None:
    point, uncertainty = _child_decisions()

    validate_probabilistic_promotion_decision(point)
    validate_conformal_governance_decision(uncertainty)
    assert len(point.ensemble_fingerprint) == 64
    assert len(point.calibration_fingerprint) == 64
    assert len(point.gate_fingerprint) == 64
    assert len(uncertainty.report_fingerprint) == 64
    assert len(uncertainty.gate_fingerprint) == 64


def test_joint_gate_requires_both_evidence_planes_by_default() -> None:
    point, uncertainty = _child_decisions()

    decision = evaluate_joint_probabilistic_governance(point, uncertainty)

    assert point.eligible
    assert uncertainty.eligible
    assert decision.eligible
    assert decision.reasons == ("joint_probabilistic_evidence_gate_passed",)
    assert decision.probabilistic_decision_fingerprint == point.fingerprint
    assert decision.conformal_decision_fingerprint == uncertainty.fingerprint
    assert 0.5 <= decision.uncertainty_step_ratio <= 1.5
    validate_joint_probabilistic_governance_decision(decision)


def test_point_forecast_failure_vetoes_joint_eligibility() -> None:
    point, uncertainty = _child_decisions(point_min_folds=10_000)

    decision = evaluate_joint_probabilistic_governance(point, uncertainty)

    assert not point.eligible
    assert uncertainty.eligible
    assert not decision.eligible
    assert "probabilistic_evidence_plane_ineligible" in decision.reasons


def test_uncertainty_failure_vetoes_joint_eligibility() -> None:
    point, uncertainty = _child_decisions(conformal_min_steps=10_000)

    decision = evaluate_joint_probabilistic_governance(point, uncertainty)

    assert point.eligible
    assert not uncertainty.eligible
    assert not decision.eligible
    assert "conformal_evidence_plane_ineligible" in decision.reasons


def test_uncertainty_sample_cannot_rubber_stamp_larger_backtest() -> None:
    point, uncertainty = _child_decisions()
    gate = JointProbabilisticGovernanceGate(
        min_uncertainty_step_ratio=1.0,
        max_uncertainty_step_ratio=2.0,
    )

    decision = evaluate_joint_probabilistic_governance(
        point,
        uncertainty,
        gate=gate,
    )

    assert uncertainty.scored_steps < point.folds
    assert not decision.eligible
    assert "uncertainty_evidence_ratio_below_gate" in decision.reasons


def test_joint_decision_is_deterministic() -> None:
    point, uncertainty = _child_decisions()

    left = evaluate_joint_probabilistic_governance(point, uncertainty)
    right = evaluate_joint_probabilistic_governance(point, uncertainty)

    assert left == right
    assert left.fingerprint == right.fingerprint


def test_tampered_point_decision_is_rejected_before_composition() -> None:
    point, uncertainty = _child_decisions()
    tampered = replace(point, folds=point.folds + 1)

    with pytest.raises(StateSpaceError):
        validate_probabilistic_promotion_decision(tampered)
    with pytest.raises(StateSpaceError):
        evaluate_joint_probabilistic_governance(tampered, uncertainty)


def test_tampered_conformal_decision_is_rejected_before_composition() -> None:
    point, uncertainty = _child_decisions()
    tampered = replace(
        uncertainty,
        fallback_rate=min(1.0, uncertainty.fallback_rate + 0.1),
    )

    with pytest.raises(StateSpaceError):
        validate_conformal_governance_decision(tampered)
    with pytest.raises(StateSpaceError):
        evaluate_joint_probabilistic_governance(point, tampered)


def test_tampered_joint_decision_is_rejected() -> None:
    point, uncertainty = _child_decisions()
    decision = evaluate_joint_probabilistic_governance(point, uncertainty)
    tampered = replace(
        decision,
        uncertainty_step_ratio=decision.uncertainty_step_ratio + 0.1,
    )

    with pytest.raises(StateSpaceError):
        validate_joint_probabilistic_governance_decision(tampered)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"require_probabilistic_eligible": 1},
        {"require_conformal_eligible": 1},
        {"min_uncertainty_step_ratio": 0.0},
        {"max_uncertainty_step_ratio": 0.0},
        {
            "min_uncertainty_step_ratio": 2.0,
            "max_uncertainty_step_ratio": 1.0,
        },
    ],
)
def test_invalid_joint_gate_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(StateSpaceError):
        JointProbabilisticGovernanceGate(**kwargs)
