from __future__ import annotations

import math

import pytest

from skeleton.jeeves.bayesian_regime_shift import (
    BayesianRegimeShiftDetector,
    NormalInverseGamma,
    RegimeShiftConfig,
    StudentTPredictive,
    detect_regime_shifts,
)
from skeleton.jeeves.historical_modes import HistoricalModeError, HistoricalSeries


def _stable_then_shift() -> tuple[float, ...]:
    first = [10.0 + 0.05 * ((index % 5) - 2) for index in range(40)]
    second = [30.0 + 0.05 * ((index % 5) - 2) for index in range(40)]
    return tuple(first + second)


def test_conjugate_update_moves_mean_toward_observation() -> None:
    prior = NormalInverseGamma(mean=0.0, kappa=1.0, alpha=2.0, beta=2.0)
    posterior = prior.updated(10.0)
    assert 0.0 < posterior.mean < 10.0
    assert posterior.kappa == 2.0
    assert posterior.alpha == 2.5
    assert posterior.beta > prior.beta


def test_student_t_predictive_is_symmetric() -> None:
    predictive = StudentTPredictive(5.0, 3.0, 2.0)
    assert predictive.logpdf(1.0) == pytest.approx(predictive.logpdf(5.0))
    assert predictive.variance > 0.0


def test_detector_posterior_is_normalized() -> None:
    detector = BayesianRegimeShiftDetector.fit((1.0, 1.1, 0.9, 1.0, 1.05))
    posterior = detector.posterior()
    assert posterior
    assert sum(item.probability for item in posterior) == pytest.approx(1.0, abs=1e-12)
    assert all(item.probability > 0.0 for item in posterior)


def test_change_probability_responds_to_evidence_not_only_hazard() -> None:
    config = RegimeShiftConfig(
        hazard_probability=0.02,
        prior_mean=10.0,
        prior_kappa=0.2,
        prior_alpha=2.0,
        prior_beta=2.0,
    )
    detector = BayesianRegimeShiftDetector.fit(
        tuple(10.0 + 0.02 * ((index % 3) - 1) for index in range(30)),
        config=config,
    )
    normal_probability = detector.update(10.01)
    shock_probability = detector.update(30.0)
    assert normal_probability != pytest.approx(config.hazard_probability)
    assert shock_probability > normal_probability


def test_abrupt_level_shift_resets_modal_run_length() -> None:
    config = RegimeShiftConfig(
        hazard_probability=0.02,
        prior_mean=10.0,
        prior_kappa=0.1,
        prior_alpha=2.0,
        prior_beta=4.0,
        event_threshold=0.10,
    )
    detector = BayesianRegimeShiftDetector.fit(
        tuple(10.0 + 0.03 * ((index % 4) - 1.5) for index in range(35)),
        config=config,
    )
    before = detector.forecast()
    detector.update(30.0)
    after = detector.forecast()
    assert before.modal_run_length > 20
    assert after.change_probability > config.hazard_probability
    assert after.modal_run_length < before.modal_run_length


def test_detector_hypothesis_budget_is_bounded() -> None:
    config = RegimeShiftConfig(max_hypotheses=8)
    detector = BayesianRegimeShiftDetector.fit(
        tuple(0.2 * index + ((index % 7) - 3) for index in range(100)),
        config=config,
    )
    assert len(detector.posterior()) <= 8
    assert sum(item.probability for item in detector.posterior()) == pytest.approx(1.0, abs=1e-12)


def test_forecast_exposes_uncertainty_and_run_length_diagnostics() -> None:
    detector = BayesianRegimeShiftDetector.fit(tuple(float(index) for index in range(20)))
    forecast = detector.forecast()
    assert math.isfinite(forecast.mean)
    assert forecast.variance > 0.0
    assert 0.0 <= forecast.change_probability <= 1.0
    assert forecast.modal_run_length >= 1
    assert forecast.expected_run_length >= 1.0
    assert forecast.entropy >= 0.0
    assert forecast.effective_hypotheses >= 1.0


def test_report_is_deterministic_and_covers_every_observation() -> None:
    series = HistoricalSeries.from_values(_stable_then_shift(), label="shift")
    config = RegimeShiftConfig(
        prior_mean=10.0,
        prior_kappa=0.1,
        prior_beta=4.0,
        event_threshold=0.10,
    )
    first = detect_regime_shifts(series, config=config)
    second = detect_regime_shifts(series, config=config)
    assert first.fingerprint == second.fingerprint
    assert len(first.observations) == len(series.values)
    assert first.as_payload() == second.as_payload()


def test_future_suffix_cannot_change_earlier_posteriors() -> None:
    common = tuple(5.0 + 0.02 * ((index % 4) - 1.5) for index in range(35))
    left = HistoricalSeries.from_values(common + tuple(5.0 for _ in range(12)), label="same")
    right = HistoricalSeries.from_values(common + tuple(100.0 for _ in range(12)), label="same")
    config = RegimeShiftConfig(prior_mean=5.0, prior_kappa=0.1)
    left_report = detect_regime_shifts(left, config=config)
    right_report = detect_regime_shifts(right, config=config)
    for a, b in zip(left_report.observations[: len(common)], right_report.observations[: len(common)]):
        assert a.index == b.index
        assert a.change_probability == pytest.approx(b.change_probability, abs=1e-12)
        assert a.modal_run_length == b.modal_run_length
        assert a.expected_run_length == pytest.approx(b.expected_run_length, abs=1e-12)


def test_shift_report_surfaces_event_near_structural_break() -> None:
    series = HistoricalSeries.from_values(_stable_then_shift(), label="break")
    config = RegimeShiftConfig(
        prior_mean=10.0,
        prior_kappa=0.1,
        prior_alpha=2.0,
        prior_beta=4.0,
        event_threshold=0.10,
        min_event_separation=2,
    )
    report = detect_regime_shifts(series, config=config)
    assert report.events
    assert any(38 <= event.index <= 44 for event in report.events)


def test_bad_configurations_fail_closed() -> None:
    with pytest.raises(HistoricalModeError):
        RegimeShiftConfig(hazard_probability=0.0)
    with pytest.raises(HistoricalModeError):
        RegimeShiftConfig(hazard_probability=1.0)
    with pytest.raises(HistoricalModeError):
        RegimeShiftConfig(max_hypotheses=0)
    with pytest.raises(HistoricalModeError):
        RegimeShiftConfig(event_threshold=1.0)
    with pytest.raises(HistoricalModeError):
        RegimeShiftConfig(probability_floor=2.0)


def test_empty_fit_fails_closed() -> None:
    with pytest.raises(HistoricalModeError):
        BayesianRegimeShiftDetector.fit(())
