from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_modes import HistoricalModeError, HistoricalSeries
from skeleton.jeeves.probabilistic_state_space import (
    BayesianRegimeMixture,
    GaussianForecast,
    LocalLinearTrendFilter,
    MixtureForecast,
    ProbabilisticEvaluationConfig,
    RegimeMixtureConfig,
    StateSpaceConfig,
    default_regime_specs,
    evaluate_probabilistic_state_space,
    gaussian_crps,
    persistence_distribution,
)


def _trend(length: int = 72) -> tuple[float, ...]:
    return tuple(10.0 + 0.7 * index + 0.15 * ((index % 5) - 2) for index in range(length))


def _regime_series(length: int = 96) -> tuple[float, ...]:
    values: list[float] = []
    for index in range(length):
        if index < length // 3:
            value = 20.0 + 0.08 * ((index % 4) - 1.5)
        elif index < 2 * length // 3:
            value = 20.0 + 0.55 * (index - length // 3) + 0.12 * ((index % 3) - 1)
        else:
            base = 20.0 + 0.55 * (length // 3)
            value = base + 1.8 * ((index % 6) - 2.5)
        values.append(value)
    return tuple(values)


def test_gaussian_forecast_interval_and_scores_are_well_formed() -> None:
    forecast = GaussianForecast(mean=3.0, variance=4.0, horizon=2, model="test")
    lower, upper = forecast.interval(0.90)
    assert lower < forecast.mean < upper
    assert forecast.cdf(lower) == pytest.approx(0.05, abs=1e-10)
    assert forecast.cdf(upper) == pytest.approx(0.95, abs=1e-10)
    assert forecast.crps(3.0) >= 0.0
    assert math.isfinite(forecast.nll(3.0))


def test_gaussian_crps_is_minimized_near_observation() -> None:
    centered = gaussian_crps(5.0, 1.0, 5.0)
    displaced = gaussian_crps(8.0, 1.0, 5.0)
    assert centered < displaced


def test_local_linear_filter_tracks_clean_trend() -> None:
    values = tuple(2.0 + 1.25 * index for index in range(40))
    model = LocalLinearTrendFilter.fit(
        values,
        config=StateSpaceConfig(adaptive_rate=0.0),
    )
    forecast = model.forecast(3)
    expected = values[-1] + 3 * 1.25
    assert forecast.mean == pytest.approx(expected, abs=0.35)
    assert forecast.variance > 0.0
    snapshot = model.snapshot()
    assert snapshot.p00 >= 0.0
    assert snapshot.p11 >= 0.0


def test_robust_filter_clips_extreme_single_shock() -> None:
    model = LocalLinearTrendFilter.fit(
        (0.0, 1.0, 2.0, 3.0, 4.0),
        config=StateSpaceConfig(robust_clip_sigma=1.0, adaptive_rate=0.0),
    )
    before = model.snapshot()
    model.update(10_000.0)
    after = model.snapshot()
    assert after.clipped_updates == before.clipped_updates + 1
    assert after.level < 10_000.0
    assert math.isfinite(after.level)
    assert math.isfinite(after.trend)


def test_filter_variance_adaptation_is_causal() -> None:
    model = LocalLinearTrendFilter.fit((1.0, 1.1, 0.9, 1.0))
    before = model.forecast(1)
    model.update(8.0)
    after = model.forecast(1)
    assert after.variance != before.variance
    assert after.variance > 0.0


def test_mixture_weights_are_normalized_after_updates() -> None:
    model = BayesianRegimeMixture.fit(_regime_series(60))
    weights = model.component_weights()
    assert len(weights) == 4
    assert sum(weight for _, weight in weights) == pytest.approx(1.0, abs=1e-12)
    assert all(weight > 0.0 for _, weight in weights)


def test_mixture_forecast_quantiles_match_mixture_cdf() -> None:
    model = BayesianRegimeMixture.fit(_trend(50))
    forecast = model.forecast(2)
    assert isinstance(forecast, MixtureForecast)
    q10 = forecast.quantile(0.10)
    q50 = forecast.quantile(0.50)
    q90 = forecast.quantile(0.90)
    assert q10 < q50 < q90
    assert forecast.cdf(q10) == pytest.approx(0.10, abs=1e-7)
    assert forecast.cdf(q50) == pytest.approx(0.50, abs=1e-7)
    assert forecast.cdf(q90) == pytest.approx(0.90, abs=1e-7)


def test_mixture_distribution_reports_diversity() -> None:
    model = BayesianRegimeMixture.fit(_regime_series(72))
    forecast = model.forecast()
    assert 1.0 <= forecast.effective_components <= len(forecast.components)
    assert forecast.weight_entropy >= 0.0
    assert forecast.variance > 0.0
    assert forecast.crps(_regime_series(73)[-1]) >= 0.0


def test_mixture_update_scores_before_assimilating_target() -> None:
    history = _trend(36)
    model = BayesianRegimeMixture.fit(history)
    expected = model.forecast(1)
    returned = model.update(history[-1] + 0.75)
    assert returned.mean == pytest.approx(expected.mean)
    assert returned.variance == pytest.approx(expected.variance)
    assert model.observations == len(history) + 1


def test_mixture_forgetting_and_temperature_validate() -> None:
    with pytest.raises(HistoricalModeError):
        RegimeMixtureConfig(forgetting=1.0)
    with pytest.raises(HistoricalModeError):
        RegimeMixtureConfig(evidence_temperature=0.0)


def test_state_space_configuration_rejects_invalid_covariance_bounds() -> None:
    with pytest.raises(HistoricalModeError):
        StateSpaceConfig(minimum_variance=2.0, maximum_variance=1.0)
    with pytest.raises(HistoricalModeError):
        StateSpaceConfig(robust_clip_sigma=0.5)
    with pytest.raises(HistoricalModeError):
        StateSpaceConfig(adaptive_rate=1.1)


def test_persistence_distribution_has_robust_positive_variance() -> None:
    forecast = persistence_distribution((4.0, 4.0, 4.0, 4.0), horizon=3)
    assert forecast.mean == 4.0
    assert forecast.variance > 0.0
    assert math.isfinite(forecast.nll(4.0))


def test_probabilistic_walk_forward_has_strict_temporal_boundary() -> None:
    series = HistoricalSeries.from_values(_trend(58), label="trend")
    report = evaluate_probabilistic_state_space(
        series,
        config=ProbabilisticEvaluationConfig(
            min_train_size=20,
            min_folds=8,
            max_mean_calibration_error=1.0,
        ),
    )
    assert report.folds
    assert all(fold.target_index > fold.train_end for fold in report.folds)
    assert all(fold.target_index == fold.train_end + 1 for fold in report.folds)
    assert report.candidate_metrics.folds == len(report.folds)


def test_future_suffix_cannot_change_earlier_fold_predictions() -> None:
    common = list(_trend(48))
    left = HistoricalSeries.from_values(common + [50.0 + index for index in range(12)], label="same")
    right = HistoricalSeries.from_values(common + [5000.0 - 20.0 * index for index in range(12)], label="same")
    config = ProbabilisticEvaluationConfig(
        min_train_size=20,
        min_folds=4,
        max_mean_calibration_error=1.0,
    )
    left_report = evaluate_probabilistic_state_space(left, config=config)
    right_report = evaluate_probabilistic_state_space(right, config=config)
    left_early = [fold for fold in left_report.folds if fold.target_index < len(common)]
    right_early = [fold for fold in right_report.folds if fold.target_index < len(common)]
    assert len(left_early) == len(right_early)
    for a, b in zip(left_early, right_early):
        assert a.target_index == b.target_index
        assert a.candidate_mean == pytest.approx(b.candidate_mean, abs=1e-12)
        assert a.candidate_variance == pytest.approx(b.candidate_variance, abs=1e-12)
        assert tuple(name for name, _ in a.regime_weights) == tuple(name for name, _ in b.regime_weights)
        for (_, a_weight), (_, b_weight) in zip(a.regime_weights, b.regime_weights):
            assert a_weight == pytest.approx(b_weight, abs=1e-12)


def test_each_fold_exposes_normalized_regime_weights() -> None:
    series = HistoricalSeries.from_values(_regime_series(64), label="regimes")
    report = evaluate_probabilistic_state_space(
        series,
        config=ProbabilisticEvaluationConfig(
            min_train_size=24,
            min_folds=6,
            max_mean_calibration_error=1.0,
        ),
    )
    for fold in report.folds:
        assert sum(weight for _, weight in fold.regime_weights) == pytest.approx(1.0, abs=1e-12)
        assert len(fold.regime_weights) == len(default_regime_specs())


def test_evaluation_fingerprint_is_deterministic() -> None:
    series = HistoricalSeries.from_values(_trend(54), label="fingerprint")
    config = ProbabilisticEvaluationConfig(
        min_train_size=22,
        min_folds=5,
        max_mean_calibration_error=1.0,
    )
    first = evaluate_probabilistic_state_space(series, config=config)
    second = evaluate_probabilistic_state_space(series, config=config)
    assert first.fingerprint == second.fingerprint
    assert first.as_payload() == second.as_payload()


def test_fingerprint_changes_when_history_changes() -> None:
    values = list(_trend(54))
    first = HistoricalSeries.from_values(values, label="fingerprint")
    values[30] += 0.25
    second = HistoricalSeries.from_values(values, label="fingerprint")
    config = ProbabilisticEvaluationConfig(
        min_train_size=22,
        min_folds=5,
        max_mean_calibration_error=1.0,
    )
    assert evaluate_probabilistic_state_space(first, config=config).fingerprint != evaluate_probabilistic_state_space(second, config=config).fingerprint


def test_multi_horizon_evaluation_preserves_exact_target_gap() -> None:
    series = HistoricalSeries.from_values(_trend(70), label="h3")
    report = evaluate_probabilistic_state_space(
        series,
        config=ProbabilisticEvaluationConfig(
            min_train_size=24,
            horizon=3,
            step=2,
            min_folds=5,
            max_mean_calibration_error=1.0,
        ),
    )
    assert all(fold.target_index == fold.train_end + 3 for fold in report.folds)


def test_interval_levels_must_be_ordered_and_strict() -> None:
    with pytest.raises(HistoricalModeError):
        ProbabilisticEvaluationConfig(interval_levels=(0.9, 0.8))
    with pytest.raises(HistoricalModeError):
        ProbabilisticEvaluationConfig(interval_levels=(0.8, 0.8))
    with pytest.raises(HistoricalModeError):
        ProbabilisticEvaluationConfig(interval_levels=(1.0,))


def test_report_contains_proper_scoring_and_calibration_metrics() -> None:
    report = evaluate_probabilistic_state_space(
        HistoricalSeries.from_values(_regime_series(70), label="metrics"),
        config=ProbabilisticEvaluationConfig(
            min_train_size=24,
            min_folds=8,
            max_mean_calibration_error=1.0,
        ),
    )
    metrics = report.candidate_metrics
    assert math.isfinite(metrics.mean_nll)
    assert metrics.mean_crps >= 0.0
    assert metrics.mean_predictive_std > 0.0
    assert len(metrics.coverage) == 4
    assert 0.0 <= metrics.mean_calibration_error <= 1.0


def test_empty_and_short_inputs_fail_closed() -> None:
    with pytest.raises(HistoricalModeError):
        BayesianRegimeMixture.fit(())
    with pytest.raises(HistoricalModeError):
        LocalLinearTrendFilter.fit(())
    with pytest.raises(HistoricalModeError):
        evaluate_probabilistic_state_space(
            HistoricalSeries.from_values((1.0, 2.0, 3.0)),
            config=ProbabilisticEvaluationConfig(min_train_size=3),
        )
