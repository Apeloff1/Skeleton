from __future__ import annotations

import math
from dataclasses import replace

import pytest

from skeleton.jeeves.probabilistic_calibration import (
    CalibrationConfig,
    DistributionObservation,
    calibrate_distributions,
    calibration_observation_fingerprint,
    validate_calibration_report,
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
    return tuple(
        25.0 + 0.22 * index + 0.04 * math.sin(index * 0.8)
        for index in range(count)
    )


def _ensemble():
    return OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=15, step=2),
    ).evaluate(_trend())


def _observations(ensemble):
    return tuple(
        DistributionObservation(
            forecast=step.predictive,
            actual=step.actual,
            target_index=step.target_index,
        )
        for step in ensemble.steps
    )


def _permissive_gate() -> ProbabilisticPromotionGate:
    return ProbabilisticPromotionGate(
        min_folds=1,
        min_calibration_score=0.0,
        max_coverage_gap=1.0,
        max_drift_events_per_100=100.0,
        min_effective_model_count=1.0,
    )


def test_calibration_report_retains_exact_target_and_observation_provenance() -> None:
    ensemble = _ensemble()
    observations = _observations(ensemble)

    report = calibrate_distributions(observations)

    assert report.target_pairs == tuple(
        (step.target_index, step.actual) for step in ensemble.steps
    )
    assert report.observation_fingerprint == calibration_observation_fingerprint(
        observations
    )
    assert len(report.target_fingerprint) == 64
    assert len(report.observation_fingerprint) == 64
    assert len(report.pits) == report.observations
    validate_calibration_report(report)


def test_calibration_report_rejects_target_ledger_tampering() -> None:
    report = calibrate_distributions(_observations(_ensemble()))
    first_index, first_actual = report.target_pairs[0]
    tampered = replace(
        report,
        target_pairs=((first_index, first_actual + 1.0),) + report.target_pairs[1:],
    )

    with pytest.raises(StateSpaceError) as error:
        validate_calibration_report(tampered)

    assert error.value.context["reason"] == "calibration_report_identity_mismatch"


def test_calibration_report_rejects_pit_sequence_tampering() -> None:
    report = calibrate_distributions(_observations(_ensemble()))
    replacement = min(1.0, report.pits[0] + 0.1)
    tampered = replace(report, pits=(replacement,) + report.pits[1:])

    with pytest.raises(StateSpaceError):
        validate_calibration_report(tampered)


def test_exact_ensemble_calibration_identity_is_accepted() -> None:
    ensemble = _ensemble()
    calibration = calibrate_distributions(_observations(ensemble))

    decision = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=_permissive_gate(),
    )

    assert decision.eligible
    assert decision.calibration_target_fingerprint == calibration.target_fingerprint
    assert (
        decision.evidence_observation_fingerprint
        == calibration.observation_fingerprint
    )


def test_equal_count_but_shifted_target_ids_are_rejected() -> None:
    ensemble = _ensemble()
    shifted = tuple(
        DistributionObservation(
            forecast=step.predictive,
            actual=step.actual,
            target_index=step.target_index + 1000,
        )
        for step in ensemble.steps
    )
    calibration = calibrate_distributions(shifted)

    with pytest.raises(StateSpaceError) as error:
        evaluate_probabilistic_promotion(
            ensemble,
            calibration,
            gate=_permissive_gate(),
        )

    assert error.value.context["reason"] == "promotion_target_identity_mismatch"


def test_equal_targets_but_altered_predictive_geometry_is_rejected() -> None:
    ensemble = _ensemble()
    observations = list(_observations(ensemble))
    source = observations[0].forecast
    component = source.components[0]
    shifted_forecast = replace(
        component.forecast,
        mean=component.forecast.mean + 0.5,
    )
    shifted_component = replace(component, forecast=shifted_forecast)
    altered_mixture = replace(
        source,
        components=(shifted_component,) + source.components[1:],
    )
    observations[0] = replace(observations[0], forecast=altered_mixture)
    calibration = calibrate_distributions(tuple(observations))

    with pytest.raises(StateSpaceError) as error:
        evaluate_probabilistic_promotion(
            ensemble,
            calibration,
            gate=_permissive_gate(),
        )

    assert error.value.context["reason"] == "promotion_forecast_identity_mismatch"


def test_calibration_config_is_bound_into_report_identity() -> None:
    observations = _observations(_ensemble())
    left = calibrate_distributions(
        observations,
        config=CalibrationConfig(levels=(0.8, 0.95)),
    )
    right = calibrate_distributions(
        observations,
        config=CalibrationConfig(levels=(0.7, 0.9)),
    )

    assert left.target_fingerprint == right.target_fingerprint
    assert left.observation_fingerprint == right.observation_fingerprint
    assert left.fingerprint != right.fingerprint
