from __future__ import annotations

import math

import pytest

from skeleton.jeeves.probabilistic_calibration import (
    CalibrationConfig,
    DistributionObservation,
    calibrate_distributions,
)
from skeleton.jeeves.probabilistic_contracts import (
    ProbabilisticPromotionGate,
    evaluate_probabilistic_promotion,
)
from skeleton.jeeves.probabilistic_ensemble import (
    BayesianEnsembleConfig,
    OnlineBayesianEnsemble,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _trend(count: int = 90) -> tuple[float, ...]:
    return tuple(50.0 + 0.25 * index + 0.05 * math.sin(index) for index in range(count))


def _evidence(count: int = 90):
    ensemble = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=15, step=2),
    ).evaluate(_trend(count))
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
    return ensemble, calibration


def test_promotion_decision_is_deterministic() -> None:
    ensemble, calibration = _evidence()
    gate = ProbabilisticPromotionGate(
        min_folds=10,
        min_calibration_score=0.0,
        max_coverage_gap=1.0,
        max_drift_events_per_100=100.0,
    )
    left = evaluate_probabilistic_promotion(ensemble, calibration, gate=gate)
    right = evaluate_probabilistic_promotion(ensemble, calibration, gate=gate)
    assert left == right
    assert left.fingerprint == right.fingerprint


def test_permissive_gate_can_mark_valid_evidence_eligible() -> None:
    ensemble, calibration = _evidence()
    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=1,
            min_calibration_score=0.0,
            max_coverage_gap=1.0,
            max_drift_events_per_100=100.0,
            min_effective_model_count=1.0,
        ),
    )
    assert decision.eligible
    assert decision.reasons == ("probabilistic_evidence_gate_passed",)


def test_fold_floor_rejects_thin_evidence() -> None:
    ensemble, calibration = _evidence(45)
    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=1000,
            min_calibration_score=0.0,
            max_coverage_gap=1.0,
            max_drift_events_per_100=100.0,
        ),
    )
    assert not decision.eligible
    assert "insufficient_folds" in decision.reasons


def test_calibration_score_gate_can_veto() -> None:
    ensemble, calibration = _evidence()
    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=1,
            min_calibration_score=1.0,
            max_coverage_gap=1.0,
            max_drift_events_per_100=100.0,
        ),
    )
    if calibration.calibration_score < 1.0:
        assert not decision.eligible
        assert "calibration_score_below_gate" in decision.reasons


def test_worst_coverage_gap_gate_can_veto() -> None:
    ensemble, calibration = _evidence()
    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=1,
            min_calibration_score=0.0,
            max_coverage_gap=0.0,
            max_drift_events_per_100=100.0,
        ),
    )
    if max(item.absolute_gap for item in calibration.coverage) > 0.0:
        assert not decision.eligible
        assert "coverage_gap_above_gate" in decision.reasons


def test_log_score_threshold_can_veto() -> None:
    ensemble, calibration = _evidence()
    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=1,
            min_calibration_score=0.0,
            max_coverage_gap=1.0,
            min_mean_log_score=ensemble.mean_log_score + 1.0,
            max_drift_events_per_100=100.0,
        ),
    )
    assert not decision.eligible
    assert "log_score_below_gate" in decision.reasons


def test_crps_threshold_can_veto() -> None:
    ensemble, calibration = _evidence()
    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=1,
            min_calibration_score=0.0,
            max_coverage_gap=1.0,
            max_mean_crps=max(0.0, ensemble.mean_crps - 1e-9),
            max_drift_events_per_100=100.0,
        ),
    )
    if ensemble.mean_crps > 0.0:
        assert not decision.eligible
        assert "crps_above_gate" in decision.reasons


def test_diversity_gate_can_veto() -> None:
    ensemble, calibration = _evidence()
    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=ProbabilisticPromotionGate(
            min_folds=1,
            min_calibration_score=0.0,
            max_coverage_gap=1.0,
            max_drift_events_per_100=100.0,
            min_effective_model_count=10.0,
        ),
    )
    assert not decision.eligible
    assert "ensemble_diversity_below_gate" in decision.reasons


def test_mismatched_evidence_counts_fail_closed() -> None:
    ensemble, calibration = _evidence()
    shortened = calibrate_distributions(
        tuple(
            DistributionObservation(
                forecast=step.predictive,
                actual=step.actual,
                target_index=step.target_index,
            )
            for step in ensemble.steps[:-1]
        )
    )
    with pytest.raises(StateSpaceError):
        evaluate_probabilistic_promotion(ensemble, shortened)


def test_invalid_gate_configuration_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        ProbabilisticPromotionGate(min_folds=0)
    with pytest.raises(StateSpaceError):
        ProbabilisticPromotionGate(min_calibration_score=1.1)
    with pytest.raises(StateSpaceError):
        ProbabilisticPromotionGate(max_coverage_gap=-0.1)
    with pytest.raises(StateSpaceError):
        ProbabilisticPromotionGate(max_mean_crps=-1.0)
    with pytest.raises(StateSpaceError):
        ProbabilisticPromotionGate(max_drift_events_per_100=-1.0)
    with pytest.raises(StateSpaceError):
        ProbabilisticPromotionGate(min_effective_model_count=0.9)
