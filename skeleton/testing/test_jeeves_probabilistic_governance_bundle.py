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
from skeleton.jeeves.probabilistic_contracts import ProbabilisticPromotionGate
from skeleton.jeeves.probabilistic_ensemble import (
    BayesianEnsembleConfig,
    OnlineBayesianEnsemble,
)
from skeleton.jeeves.probabilistic_governance import ConformalGovernanceGate
from skeleton.jeeves.probabilistic_governance_bundle import (
    ProbabilisticGovernanceBundleGate,
    evaluate_probabilistic_governance_bundle,
    validate_probabilistic_governance_bundle,
)
from skeleton.jeeves.probabilistic_joint_governance import (
    JointProbabilisticGovernanceGate,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _trend(count: int = 90) -> tuple[float, ...]:
    return tuple(
        30.0 + 0.18 * index + 0.04 * math.sin(index * 0.7)
        for index in range(count)
    )


def _sources(*, conformal_slice: slice | None = None, index_offset: int = 0, actual_delta: float = 0.0):
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
    source_steps = ensemble.steps if conformal_slice is None else ensemble.steps[conformal_slice]
    conformal_report = evaluate_stratified_conformal(
        tuple(
            StratifiedForecastObservation(
                target_index=step.target_index + index_offset,
                actual=step.actual + actual_delta,
                predictive=step.predictive,
            )
            for step in source_steps
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
    return ensemble, calibration, conformal_report


def _point_gate() -> ProbabilisticPromotionGate:
    return ProbabilisticPromotionGate(
        min_folds=1,
        min_calibration_score=0.0,
        max_coverage_gap=1.0,
        max_drift_events_per_100=100.0,
        min_effective_model_count=1.0,
    )


def _conformal_gate() -> ConformalGovernanceGate:
    return ConformalGovernanceGate(
        min_scored_steps=1,
        max_absolute_coverage_gap=1.0,
        max_bucket_coverage_gap=1.0,
        max_horizon_coverage_gap=1.0,
        max_fallback_rate=1.0,
        max_unevidenced_step_rate=1.0,
        max_unevidenced_horizon_step_rate=1.0,
        min_evidenced_buckets=0,
        min_bucket_uses=1,
        min_evidenced_horizons=1,
        min_horizon_steps=1,
    )


def test_aligned_bundle_is_eligible_and_self_verifying() -> None:
    ensemble, calibration, conformal_report = _sources()

    bundle = evaluate_probabilistic_governance_bundle(
        ensemble,
        calibration,
        conformal_report,
        probabilistic_gate=_point_gate(),
        conformal_gate=_conformal_gate(),
    )

    assert bundle.eligible
    assert bundle.reasons == ("probabilistic_governance_bundle_passed",)
    assert bundle.aligned_targets == bundle.conformal_targets
    assert bundle.aligned_targets < bundle.ensemble_targets
    assert bundle.aligned_target_indices == tuple(
        step.interval.target_index for step in conformal_report.steps
    )
    assert bundle.joint.eligible
    validate_probabilistic_governance_bundle(bundle)


def test_bundle_is_deterministic() -> None:
    ensemble, calibration, conformal_report = _sources()
    kwargs = {
        "probabilistic_gate": _point_gate(),
        "conformal_gate": _conformal_gate(),
    }

    left = evaluate_probabilistic_governance_bundle(
        ensemble,
        calibration,
        conformal_report,
        **kwargs,
    )
    right = evaluate_probabilistic_governance_bundle(
        ensemble,
        calibration,
        conformal_report,
        **kwargs,
    )

    assert left == right
    assert left.fingerprint == right.fingerprint


def test_unknown_conformal_target_fails_closed() -> None:
    ensemble, calibration, conformal_report = _sources(index_offset=1000)

    with pytest.raises(StateSpaceError) as error:
        evaluate_probabilistic_governance_bundle(
            ensemble,
            calibration,
            conformal_report,
            probabilistic_gate=_point_gate(),
            conformal_gate=_conformal_gate(),
            joint_gate=JointProbabilisticGovernanceGate(
                min_uncertainty_step_ratio=0.01,
                max_uncertainty_step_ratio=2.0,
            ),
        )

    assert error.value.context["reason"] == "governance_target_alignment_mismatch"


def test_same_target_with_different_realization_fails_closed() -> None:
    ensemble, calibration, conformal_report = _sources(actual_delta=0.01)

    with pytest.raises(StateSpaceError) as error:
        evaluate_probabilistic_governance_bundle(
            ensemble,
            calibration,
            conformal_report,
            probabilistic_gate=_point_gate(),
            conformal_gate=_conformal_gate(),
        )

    assert error.value.context["reason"] == "governance_target_alignment_mismatch"


def test_small_but_valid_aligned_subset_cannot_rubber_stamp_full_backtest() -> None:
    ensemble, calibration, conformal_report = _sources(conformal_slice=slice(-10, None))

    bundle = evaluate_probabilistic_governance_bundle(
        ensemble,
        calibration,
        conformal_report,
        probabilistic_gate=_point_gate(),
        conformal_gate=_conformal_gate(),
        joint_gate=JointProbabilisticGovernanceGate(
            min_uncertainty_step_ratio=0.01,
            max_uncertainty_step_ratio=2.0,
        ),
        bundle_gate=ProbabilisticGovernanceBundleGate(
            min_aligned_target_ratio=0.50,
        ),
    )

    assert bundle.joint.eligible
    assert bundle.aligned_target_ratio < 0.50
    assert not bundle.eligible
    assert "aligned_target_ratio_below_gate" in bundle.reasons


def test_bundle_retains_distinct_target_custody_fingerprints() -> None:
    ensemble, calibration, conformal_report = _sources()
    bundle = evaluate_probabilistic_governance_bundle(
        ensemble,
        calibration,
        conformal_report,
        probabilistic_gate=_point_gate(),
        conformal_gate=_conformal_gate(),
    )

    assert len(bundle.ensemble_target_fingerprint) == 64
    assert len(bundle.conformal_target_fingerprint) == 64
    assert bundle.ensemble_target_fingerprint != bundle.conformal_target_fingerprint


def test_tampered_bundle_is_rejected() -> None:
    ensemble, calibration, conformal_report = _sources()
    bundle = evaluate_probabilistic_governance_bundle(
        ensemble,
        calibration,
        conformal_report,
        probabilistic_gate=_point_gate(),
        conformal_gate=_conformal_gate(),
    )
    tampered = replace(
        bundle,
        aligned_target_ratio=bundle.aligned_target_ratio + 0.01,
    )

    with pytest.raises(StateSpaceError):
        validate_probabilistic_governance_bundle(tampered)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_aligned_target_ratio": 0.0},
        {"min_aligned_target_ratio": 1.1},
        {"max_actual_delta": -1e-9},
        {"max_actual_delta": float("nan")},
    ],
)
def test_invalid_bundle_gate_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(StateSpaceError):
        ProbabilisticGovernanceBundleGate(**kwargs)
