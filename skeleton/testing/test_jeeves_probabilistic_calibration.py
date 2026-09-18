from __future__ import annotations

import math

import pytest

from skeleton.jeeves.probabilistic import (
    BayesianEnsembleConfig,
    CalibrationConfig,
    DistributionObservation,
    GaussianForecast,
    MixtureForecast,
    OnlineBayesianEnsemble,
    StateSpaceError,
    StateSpaceFamily,
    WeightedForecast,
    calibrate_distributions,
    central_interval,
    mixture_cdf,
    mixture_quantile,
    pinball_loss,
)


def _single_gaussian(mean: float, variance: float = 1.0) -> MixtureForecast:
    return MixtureForecast(
        horizon=1,
        components=(
            WeightedForecast(
                family=StateSpaceFamily.LOCAL_LEVEL,
                weight=1.0,
                forecast=GaussianForecast(horizon=1, mean=mean, variance=variance),
            ),
        ),
    )


def _symmetric_mixture() -> MixtureForecast:
    return MixtureForecast(
        horizon=1,
        components=(
            WeightedForecast(
                family=StateSpaceFamily.LOCAL_LEVEL,
                weight=0.5,
                forecast=GaussianForecast(horizon=1, mean=-2.0, variance=1.0),
            ),
            WeightedForecast(
                family=StateSpaceFamily.LOCAL_LINEAR_TREND,
                weight=0.5,
                forecast=GaussianForecast(horizon=1, mean=2.0, variance=1.0),
            ),
        ),
    )


def _trend(count: int = 70) -> tuple[float, ...]:
    return tuple(20.0 + 0.4 * index for index in range(count))


def test_mixture_cdf_is_bounded_and_monotone() -> None:
    forecast = _symmetric_mixture()
    points = [-10.0, -2.0, 0.0, 2.0, 10.0]
    values = [mixture_cdf(forecast, point) for point in points]
    assert all(0.0 <= value <= 1.0 for value in values)
    assert values == sorted(values)
    assert values[0] < 0.01
    assert values[-1] > 0.99


def test_symmetric_mixture_has_half_mass_at_zero() -> None:
    assert mixture_cdf(_symmetric_mixture(), 0.0) == pytest.approx(0.5, abs=1e-12)


def test_mixture_quantile_inverts_cdf() -> None:
    forecast = _symmetric_mixture()
    for probability in (0.05, 0.25, 0.50, 0.75, 0.95):
        quantile = mixture_quantile(forecast, probability)
        assert mixture_cdf(forecast, quantile) == pytest.approx(probability, abs=2e-7)


def test_single_gaussian_median_equals_mean() -> None:
    forecast = _single_gaussian(7.25, variance=4.0)
    assert mixture_quantile(forecast, 0.5) == pytest.approx(7.25, abs=1e-8)


def test_central_interval_is_nested() -> None:
    forecast = _symmetric_mixture()
    lower_50, upper_50 = central_interval(forecast, 0.50)
    lower_95, upper_95 = central_interval(forecast, 0.95)
    assert lower_95 < lower_50 < upper_50 < upper_95


def test_pinball_loss_is_zero_at_exact_quantile_realization() -> None:
    assert pinball_loss(4.0, 4.0, 0.9) == pytest.approx(0.0)


def test_pinball_loss_penalizes_wrong_tail_asymmetrically() -> None:
    high_quantile_underprediction = pinball_loss(10.0, 0.0, 0.9)
    high_quantile_overprediction = pinball_loss(0.0, 10.0, 0.9)
    assert high_quantile_underprediction > high_quantile_overprediction


def test_calibration_config_rejects_invalid_levels() -> None:
    with pytest.raises(StateSpaceError):
        CalibrationConfig(levels=())
    with pytest.raises(StateSpaceError):
        CalibrationConfig(levels=(0.9, 0.9))
    with pytest.raises(StateSpaceError):
        CalibrationConfig(levels=(1.0,))
    with pytest.raises(StateSpaceError):
        CalibrationConfig(pit_bins=1)


def test_calibration_rejects_empty_and_duplicate_targets() -> None:
    with pytest.raises(StateSpaceError):
        calibrate_distributions(())

    forecast = _single_gaussian(0.0)
    observations = (
        DistributionObservation(forecast=forecast, actual=0.0, target_index=2),
        DistributionObservation(forecast=forecast, actual=1.0, target_index=2),
    )
    with pytest.raises(StateSpaceError):
        calibrate_distributions(observations)


def test_calibration_report_is_deterministic() -> None:
    observations = tuple(
        DistributionObservation(
            forecast=_single_gaussian(float(index), variance=2.0),
            actual=float(index) + 0.25 * math.sin(index),
            target_index=index,
        )
        for index in range(1, 41)
    )
    left = calibrate_distributions(observations)
    right = calibrate_distributions(observations)
    assert left.fingerprint == right.fingerprint
    assert left.calibration_score == pytest.approx(right.calibration_score)
    assert left.pit.histogram == right.pit.histogram


def test_pit_histogram_counts_every_observation_once() -> None:
    observations = tuple(
        DistributionObservation(
            forecast=_single_gaussian(0.0, variance=4.0),
            actual=-3.0 + index * 0.15,
            target_index=index,
        )
        for index in range(40)
    )
    report = calibrate_distributions(observations, config=CalibrationConfig(pit_bins=8))
    assert sum(report.pit.histogram) == len(observations)
    assert report.pit.count == len(observations)


def test_well_centered_sequence_scores_better_than_shifted_sequence() -> None:
    centered = tuple(
        DistributionObservation(
            forecast=_single_gaussian(0.0, variance=1.0),
            actual=math.sin(index * 1.7),
            target_index=index,
        )
        for index in range(1, 81)
    )
    shifted = tuple(
        DistributionObservation(
            forecast=_single_gaussian(0.0, variance=1.0),
            actual=4.0 + math.sin(index * 1.7),
            target_index=index,
        )
        for index in range(1, 81)
    )
    centered_report = calibrate_distributions(centered)
    shifted_report = calibrate_distributions(shifted)
    assert centered_report.calibration_score > shifted_report.calibration_score
    assert centered_report.mean_log_score > shifted_report.mean_log_score


def test_shifted_realizations_trigger_directional_calibration_drift() -> None:
    observations = tuple(
        DistributionObservation(
            forecast=_single_gaussian(0.0, variance=1.0),
            actual=5.0,
            target_index=index,
        )
        for index in range(1, 60)
    )
    report = calibrate_distributions(
        observations,
        config=CalibrationConfig(drift_reference=0.05, drift_threshold=2.0),
    )
    assert report.drift_detected
    assert any(event.direction == "high" for event in report.drift_events)


def test_centered_realizations_do_not_require_drift_event() -> None:
    # Alternating symmetric realizations keep centered PIT residual accumulation small.
    observations = tuple(
        DistributionObservation(
            forecast=_single_gaussian(0.0, variance=4.0),
            actual=(-1.0 if index % 2 else 1.0),
            target_index=index,
        )
        for index in range(1, 80)
    )
    report = calibrate_distributions(
        observations,
        config=CalibrationConfig(drift_reference=0.15, drift_threshold=4.0),
    )
    assert not report.drift_detected


def test_coverage_diagnostic_reports_interval_width_and_gap() -> None:
    observations = tuple(
        DistributionObservation(
            forecast=_single_gaussian(0.0, variance=1.0),
            actual=0.0,
            target_index=index,
        )
        for index in range(1, 21)
    )
    report = calibrate_distributions(observations)
    coverage_95 = report.coverage_for(0.95)
    assert coverage_95.empirical == pytest.approx(1.0)
    assert coverage_95.absolute_gap == pytest.approx(0.05)
    assert coverage_95.average_width > 0.0
    assert coverage_95.average_pinball_loss >= 0.0


def test_coverage_level_lookup_fails_closed() -> None:
    observations = (
        DistributionObservation(
            forecast=_single_gaussian(0.0),
            actual=0.0,
            target_index=1,
        ),
    )
    report = calibrate_distributions(observations, config=CalibrationConfig(levels=(0.8,)))
    with pytest.raises(StateSpaceError):
        report.coverage_for(0.95)


def test_ensemble_output_can_flow_directly_into_calibration() -> None:
    ensemble = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=15, step=2),
    )
    report = ensemble.evaluate(_trend(70))
    observations = tuple(
        DistributionObservation(
            forecast=step.predictive,
            actual=step.actual,
            target_index=step.target_index,
        )
        for step in report.steps
    )
    calibration = calibrate_distributions(observations)
    assert calibration.observations == len(report.steps)
    assert math.isfinite(calibration.mean_log_score)
    assert math.isfinite(calibration.mean_crps)
    assert 0.0 <= calibration.calibration_score <= 1.0


def test_future_observations_cannot_change_prior_calibration_prefix() -> None:
    base = tuple(
        DistributionObservation(
            forecast=_single_gaussian(float(index), variance=3.0),
            actual=float(index) + 0.1,
            target_index=index,
        )
        for index in range(1, 21)
    )
    extended = base + tuple(
        DistributionObservation(
            forecast=_single_gaussian(float(index), variance=3.0),
            actual=1000.0,
            target_index=index,
        )
        for index in range(21, 31)
    )
    base_report = calibrate_distributions(base)
    prefix_report = calibrate_distributions(extended[: len(base)])
    assert base_report.fingerprint == prefix_report.fingerprint
    assert base_report.pit == prefix_report.pit
    assert base_report.coverage == prefix_report.coverage


def test_extreme_mixture_quantiles_remain_finite() -> None:
    forecast = MixtureForecast(
        horizon=1,
        components=(
            WeightedForecast(
                family=StateSpaceFamily.LOCAL_LEVEL,
                weight=0.99,
                forecast=GaussianForecast(horizon=1, mean=0.0, variance=1e-6),
            ),
            WeightedForecast(
                family=StateSpaceFamily.ROBUST_LOCAL_LINEAR_TREND,
                weight=0.01,
                forecast=GaussianForecast(horizon=1, mean=1000.0, variance=10000.0),
            ),
        ),
    )
    for probability in (0.0001, 0.01, 0.5, 0.99, 0.9999):
        quantile = mixture_quantile(forecast, probability)
        assert math.isfinite(quantile)


def test_quantile_input_validation_fails_closed() -> None:
    forecast = _single_gaussian(0.0)
    with pytest.raises(StateSpaceError):
        mixture_quantile(forecast, -0.1)
    with pytest.raises(StateSpaceError):
        mixture_quantile(forecast, 1.1)
    with pytest.raises(StateSpaceError):
        mixture_quantile(forecast, 0.5, max_iterations=3)
    with pytest.raises(StateSpaceError):
        central_interval(forecast, 1.0)
