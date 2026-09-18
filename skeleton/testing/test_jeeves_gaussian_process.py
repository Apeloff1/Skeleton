from __future__ import annotations

import math

import pytest

from skeleton.jeeves.gaussian_process import (
    GaussianProcessConfig,
    GaussianProcessEvaluationConfig,
    GaussianProcessForecaster,
    GaussianProcessSelector,
    KernelKind,
    KernelPortfolioCandidate,
    KernelSpec,
    default_kernel_candidates,
    evaluate_gaussian_process,
)
from skeleton.jeeves.historical_modes import HistoricalModeError, HistoricalSeries


def _smooth(length: int = 48) -> tuple[float, ...]:
    return tuple(0.08 * index + math.sin(index / 4.0) for index in range(length))


def _weekly(length: int = 56) -> tuple[float, ...]:
    pattern = (0.0, 1.5, 2.4, 1.1, -0.8, -1.6, -0.6)
    return tuple(10.0 + 0.03 * index + pattern[index % 7] for index in range(length))


def test_all_kernels_are_symmetric_and_positive_on_diagonal() -> None:
    for kind in KernelKind:
        kernel = KernelSpec(kind, amplitude=1.7, length_scale=3.0, alpha=0.8, period=7.0)
        assert kernel.covariance(2.0, 5.0) == pytest.approx(kernel.covariance(5.0, 2.0))
        assert kernel.covariance(3.0, 3.0) > 0.0


def test_gp_fits_smooth_series_with_positive_predictive_variance() -> None:
    series = HistoricalSeries.from_values(_smooth(), label="smooth")
    model = GaussianProcessForecaster.fit_series(series)
    forecast = model.forecast(1)
    assert math.isfinite(forecast.mean)
    assert forecast.variance > 0.0
    assert math.isfinite(model.log_marginal_likelihood)


def test_gp_retains_bounded_trailing_history() -> None:
    config = GaussianProcessConfig(max_train_points=12)
    model = GaussianProcessForecaster.fit_series(
        HistoricalSeries.from_values(_smooth(40)), config=config
    )
    snapshot = model.snapshot()
    assert snapshot.observations == 40
    assert snapshot.retained_observations == 12
    assert snapshot.effective_jitter >= config.jitter


def test_irregular_timestamps_are_supported() -> None:
    values = _smooth(24)
    timestamps = tuple(float(index * index + index) for index in range(24))
    series = HistoricalSeries.from_values(values, timestamps=timestamps)
    model = GaussianProcessForecaster.fit_series(series)
    forecast = model.predict_at(timestamps[-1] + 50.0, horizon=1)
    assert math.isfinite(forecast.mean)
    assert forecast.variance > 0.0


def test_duplicate_timestamps_fail_closed() -> None:
    with pytest.raises(HistoricalModeError):
        GaussianProcessForecaster((0.0, 1.0, 1.0), (1.0, 2.0, 3.0))


def test_selector_ranking_is_deterministic() -> None:
    series = HistoricalSeries.from_values(_weekly(), label="weekly")
    selector = GaussianProcessSelector()
    first = selector.fit_series(series)
    second = selector.fit_series(series)
    assert first.selected_name == second.selected_name
    assert first.ranking == second.ranking
    assert {item.name for item in first.ranking} == {item.name for item in default_kernel_candidates()}


def test_selector_rejects_duplicate_candidate_names() -> None:
    candidate = KernelPortfolioCandidate(
        "same", (KernelSpec(KernelKind.RBF, length_scale=2.0),)
    )
    with pytest.raises(HistoricalModeError):
        GaussianProcessSelector(candidates=(candidate, candidate))


def test_gp_walk_forward_preserves_temporal_boundary() -> None:
    series = HistoricalSeries.from_values(_smooth(38), label="walk")
    selector = GaussianProcessSelector(
        candidates=(
            KernelPortfolioCandidate(
                "smooth-a", (KernelSpec(KernelKind.RBF, length_scale=5.0),)
            ),
            KernelPortfolioCandidate(
                "smooth-b", (KernelSpec(KernelKind.MATERN32, length_scale=5.0),)
            ),
        ),
        base_config=GaussianProcessConfig(max_train_points=32),
    )
    report = evaluate_gaussian_process(
        series,
        config=GaussianProcessEvaluationConfig(min_train_size=20, min_folds=4),
        selector=selector,
    )
    assert report.folds
    assert all(fold.target_index == fold.train_end + 1 for fold in report.folds)
    assert all(fold.predicted_variance > 0.0 for fold in report.folds)
    assert math.isfinite(report.candidate.mean_crps)
    assert math.isfinite(report.candidate.mean_nll)


def test_future_suffix_cannot_change_earlier_gp_folds() -> None:
    common = list(_smooth(32))
    left = HistoricalSeries.from_values(common + [0.0] * 8, label="same")
    right = HistoricalSeries.from_values(common + [1000.0] * 8, label="same")
    candidates = (
        KernelPortfolioCandidate(
            "rbf", (KernelSpec(KernelKind.RBF, length_scale=5.0),)
        ),
        KernelPortfolioCandidate(
            "matern", (KernelSpec(KernelKind.MATERN32, length_scale=5.0),)
        ),
    )
    selector = GaussianProcessSelector(
        candidates=candidates,
        base_config=GaussianProcessConfig(max_train_points=28),
    )
    config = GaussianProcessEvaluationConfig(min_train_size=18, min_folds=3)
    left_report = evaluate_gaussian_process(left, config=config, selector=selector)
    right_report = evaluate_gaussian_process(right, config=config, selector=selector)
    left_early = [fold for fold in left_report.folds if fold.target_index < len(common)]
    right_early = [fold for fold in right_report.folds if fold.target_index < len(common)]
    for first, second in zip(left_early, right_early):
        assert first.target_index == second.target_index
        assert first.predicted_mean == pytest.approx(second.predicted_mean, abs=1e-12)
        assert first.predicted_variance == pytest.approx(second.predicted_variance, abs=1e-12)
        assert first.selected_portfolio == second.selected_portfolio


def test_multi_horizon_target_geometry_is_exact() -> None:
    selector = GaussianProcessSelector(
        candidates=(
            KernelPortfolioCandidate("a", (KernelSpec(KernelKind.RBF, length_scale=4.0),)),
            KernelPortfolioCandidate("b", (KernelSpec(KernelKind.MATERN32, length_scale=4.0),)),
        ),
        base_config=GaussianProcessConfig(max_train_points=24),
    )
    report = evaluate_gaussian_process(
        HistoricalSeries.from_values(_smooth(40), label="h3"),
        config=GaussianProcessEvaluationConfig(
            min_train_size=20, horizon=3, step=2, min_folds=3
        ),
        selector=selector,
    )
    assert all(fold.target_index == fold.train_end + 3 for fold in report.folds)


def test_report_fingerprint_is_deterministic() -> None:
    selector = GaussianProcessSelector(
        candidates=(
            KernelPortfolioCandidate("a", (KernelSpec(KernelKind.RBF, length_scale=5.0),)),
            KernelPortfolioCandidate("b", (KernelSpec(KernelKind.MATERN32, length_scale=5.0),)),
        )
    )
    series = HistoricalSeries.from_values(_smooth(34), label="fingerprint")
    config = GaussianProcessEvaluationConfig(min_train_size=20, min_folds=3)
    first = evaluate_gaussian_process(series, config=config, selector=selector)
    second = evaluate_gaussian_process(series, config=config, selector=selector)
    assert first.fingerprint == second.fingerprint
    assert first.as_payload() == second.as_payload()


def test_bad_gp_configuration_fails_closed() -> None:
    with pytest.raises(HistoricalModeError):
        GaussianProcessConfig(jitter=1.0, max_jitter=0.1)
    with pytest.raises(HistoricalModeError):
        GaussianProcessConfig(max_train_points=0)
    with pytest.raises(HistoricalModeError):
        KernelSpec(KernelKind.RBF, length_scale=0.0)
