from __future__ import annotations

import math

import pytest

from skeleton.jeeves.probabilistic_bayes import (
    BayesianTrendConfig,
    evaluate_bayesian_trend,
    fit_bayesian_trend,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _trend(count: int = 80, slope: float = 0.6) -> tuple[float, ...]:
    return tuple(5.0 + slope * index + 0.08 * math.sin(index * 0.9) for index in range(count))


def _noisy(count: int = 80) -> tuple[float, ...]:
    return tuple(10.0 + 0.2 * index + 2.0 * math.sin(index * 1.7) for index in range(count))


def test_bayesian_trend_fit_is_deterministic() -> None:
    left = fit_bayesian_trend(_trend())
    right = fit_bayesian_trend(_trend())
    assert left == right
    assert left.fingerprint == right.fingerprint


def test_posterior_slope_recovers_clean_linear_trend() -> None:
    fit = fit_bayesian_trend(_trend(100, slope=0.75))
    assert fit.slope_mean == pytest.approx(0.75, abs=0.03)
    assert fit.slope_standard_deviation > 0.0


def test_more_data_contracts_slope_uncertainty() -> None:
    short = fit_bayesian_trend(_trend(20))
    long = fit_bayesian_trend(_trend(100))
    assert long.slope_standard_deviation < short.slope_standard_deviation


def test_predictive_uncertainty_expands_with_extrapolation_horizon() -> None:
    fit = fit_bayesian_trend(_trend(60))
    one = fit.forecast(1)
    ten = fit.forecast(10)
    assert ten.mean > one.mean
    assert ten.parameter_variance > one.parameter_variance
    assert ten.variance > one.variance
    assert ten.uncertainty_fraction_from_parameters > one.uncertainty_fraction_from_parameters


def test_student_t_log_density_prefers_nearby_realization() -> None:
    forecast = fit_bayesian_trend(_trend(60)).forecast(1)
    assert forecast.log_density(forecast.mean) > forecast.log_density(forecast.mean + 20.0)


def test_student_t_forecast_has_finite_variance_and_interval() -> None:
    forecast = fit_bayesian_trend(_trend(60)).forecast(4)
    assert forecast.degrees_of_freedom > 2.0
    assert forecast.variance > 0.0
    assert math.isfinite(forecast.variance)
    lower, upper = forecast.moment_interval()
    assert lower < forecast.mean < upper


def test_noise_increases_expected_observation_variance() -> None:
    smooth = fit_bayesian_trend(_trend(80))
    noisy = fit_bayesian_trend(_noisy(80))
    assert noisy.expected_observation_variance > smooth.expected_observation_variance


def test_rolling_window_tracks_absolute_time_for_forecast() -> None:
    values = _trend(100, slope=0.5)
    fit = fit_bayesian_trend(values, config=BayesianTrendConfig(window=25))
    assert fit.sample_count == 25
    assert fit.source_start_index == 75
    forecast = fit.forecast(1)
    assert forecast.mean == pytest.approx(5.0 + 0.5 * 100, abs=0.25)


def test_prequential_evaluation_is_deterministic() -> None:
    left = evaluate_bayesian_trend(_trend(70), min_train_size=20, step=5)
    right = evaluate_bayesian_trend(_trend(70), min_train_size=20, step=5)
    assert left == right
    assert left.fingerprint == right.fingerprint
    assert left.folds


def test_prequential_metrics_are_finite() -> None:
    report = evaluate_bayesian_trend(_noisy(70), min_train_size=20, step=5)
    assert math.isfinite(report.mean_log_score)
    assert report.mae >= 0.0
    assert report.rmse >= 0.0
    assert 0.0 <= report.average_parameter_uncertainty_fraction <= 1.0


def test_future_tail_mutation_cannot_change_prefix_fit() -> None:
    prefix = list(_trend(45))
    left = tuple(prefix + [40.0, 41.0, 42.0])
    right = tuple(prefix + [10000.0, -8000.0, 5000.0])
    left_fit = fit_bayesian_trend(left[: len(prefix)])
    right_fit = fit_bayesian_trend(right[: len(prefix)])
    assert left_fit == right_fit


def test_configuration_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        BayesianTrendConfig(prior_intercept_precision=0.0)
    with pytest.raises(StateSpaceError):
        BayesianTrendConfig(prior_slope_precision=0.0)
    with pytest.raises(StateSpaceError):
        BayesianTrendConfig(alpha=1.0)
    with pytest.raises(StateSpaceError):
        BayesianTrendConfig(beta=0.0)
    with pytest.raises(StateSpaceError):
        BayesianTrendConfig(window=2)


def test_too_short_or_nonfinite_series_fail_closed() -> None:
    with pytest.raises(StateSpaceError):
        fit_bayesian_trend((1.0, 2.0))
    with pytest.raises(StateSpaceError):
        fit_bayesian_trend((1.0, 2.0, float("inf")))


def test_evaluation_config_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        evaluate_bayesian_trend(_trend(20), min_train_size=2)
    with pytest.raises(StateSpaceError):
        evaluate_bayesian_trend(_trend(20), step=0)
    with pytest.raises(StateSpaceError):
        evaluate_bayesian_trend(_trend(20), min_train_size=20)
