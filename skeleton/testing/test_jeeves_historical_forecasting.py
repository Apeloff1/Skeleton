from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_forecasting import (
    ForecastMethod,
    ForecastObservation,
    ForecastParameters,
    ForecastSelectionPolicy,
    HistoricalForecaster,
    HistoricalForecastError,
    HistoricalForecastTournament,
    HistoricalSeries,
    series_from_registry,
    summarize_forecast_tournament,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    make_benchmark_provenance,
)


NOW = 5_000_000.0


def _series(values: list[float] | tuple[float, ...], *, series_id: str = "fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values, start=1)
        ),
    )


def _policy(**overrides: object) -> ForecastSelectionPolicy:
    values: dict[str, object] = {
        "horizons": (1, 2),
        "minimum_training_points": 4,
        "minimum_origins": 3,
        "alpha_grid": (0.4, 0.8),
        "beta_grid": (0.2, 0.5),
        "damping_grid": (0.9, 0.98),
    }
    values.update(overrides)
    return ForecastSelectionPolicy(**values)  # type: ignore[arg-type]


def _benchmark() -> BenchmarkDefinition:
    return BenchmarkDefinition(
        benchmark_id="reasoning-history",
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )


def _snapshot(
    snapshot_id: str,
    model: ModelIdentity,
    benchmark: BenchmarkDefinition,
    score: float,
    measured_at: float,
) -> BenchmarkSnapshot:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
        measured_at=measured_at,
        provenance=provenance,
    )


def test_series_requires_strictly_increasing_timestamps() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        HistoricalSeries(
            series_id="bad",
            observations=(
                ForecastObservation(1.0, 1.0),
                ForecastObservation(1.0, 2.0),
            ),
        )
    assert exc.value.context["reason"] == "non_monotonic_time"


def test_series_rejects_empty_history() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        HistoricalSeries(series_id="empty", observations=())
    assert exc.value.context["reason"] == "empty_series"


def test_series_fingerprint_is_deterministic() -> None:
    left = _series([1.0, 2.0, 3.0])
    right = _series([1.0, 2.0, 3.0])
    assert left.fingerprint == right.fingerprint


def test_series_fingerprint_changes_with_observation() -> None:
    left = _series([1.0, 2.0, 3.0])
    right = _series([1.0, 2.0, 3.1])
    assert left.fingerprint != right.fingerprint


def test_prefix_is_exact_and_immutable() -> None:
    series = _series([10.0, 20.0, 30.0, 40.0])
    prefix = series.prefix(2)
    assert prefix.values == (10.0, 20.0)
    assert series.values == (10.0, 20.0, 30.0, 40.0)


def test_prefix_rejects_count_beyond_history() -> None:
    series = _series([1.0, 2.0])
    with pytest.raises(HistoricalForecastError) as exc:
        series.prefix(3)
    assert exc.value.context["reason"] == "prefix_too_large"


def test_last_value_forecast_repeats_latest_observation() -> None:
    fitted = HistoricalForecaster.fit(
        _series([2.0, 3.0, 8.0]),
        ForecastMethod.LAST_VALUE,
    )
    assert [point.predicted for point in fitted.forecast(3)] == [8.0, 8.0, 8.0]


def test_mean_forecast_repeats_historical_mean() -> None:
    fitted = HistoricalForecaster.fit(
        _series([1.0, 2.0, 6.0]),
        ForecastMethod.MEAN,
    )
    assert [point.predicted for point in fitted.forecast(2)] == pytest.approx([3.0, 3.0])


def test_drift_recovers_perfect_linear_series() -> None:
    fitted = HistoricalForecaster.fit(
        _series([5.0, 7.0, 9.0, 11.0]),
        ForecastMethod.DRIFT,
    )
    assert fitted.level == pytest.approx(11.0)
    assert fitted.trend == pytest.approx(2.0)
    assert [point.predicted for point in fitted.forecast(3)] == pytest.approx([13.0, 15.0, 17.0])


def test_trend_model_requires_two_points() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        HistoricalForecaster.fit(_series([4.0]), ForecastMethod.DRIFT)
    assert exc.value.context["reason"] == "insufficient_points"


def test_holt_requires_alpha_and_beta() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        HistoricalForecaster.fit(
            _series([1.0, 2.0, 3.0]),
            ForecastMethod.HOLT,
            ForecastParameters(alpha=0.5),
        )
    assert exc.value.context["reason"] == "missing_smoothing_parameters"


def test_plain_holt_rejects_damping_parameter() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        HistoricalForecaster.fit(
            _series([1.0, 2.0, 3.0]),
            ForecastMethod.HOLT,
            ForecastParameters(alpha=0.5, beta=0.2, damping=0.9),
        )
    assert exc.value.context["reason"] == "unexpected_damping"


def test_damped_holt_requires_damping_parameter() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        HistoricalForecaster.fit(
            _series([1.0, 2.0, 3.0]),
            ForecastMethod.DAMPED_HOLT,
            ForecastParameters(alpha=0.5, beta=0.2),
        )
    assert exc.value.context["reason"] == "missing_damping"


def test_damped_holt_projects_less_trend_than_plain_holt() -> None:
    series = _series([10.0, 12.0, 14.0, 16.0, 18.0])
    holt = HistoricalForecaster.fit(
        series,
        ForecastMethod.HOLT,
        ForecastParameters(alpha=0.8, beta=0.5),
    )
    damped = HistoricalForecaster.fit(
        series,
        ForecastMethod.DAMPED_HOLT,
        ForecastParameters(alpha=0.8, beta=0.5, damping=0.8),
    )
    assert damped.forecast(5)[-1].predicted < holt.forecast(5)[-1].predicted


def test_empirical_interval_contains_point_forecast() -> None:
    fitted = HistoricalForecaster.fit(
        _series([1.0, 2.0, 1.5, 3.0, 2.5, 4.0]),
        ForecastMethod.DRIFT,
    )
    points = fitted.forecast(4, interval_coverage=0.8)
    assert all(point.lower is not None and point.upper is not None for point in points)
    assert all(point.lower <= point.predicted <= point.upper for point in points)  # type: ignore[operator]


def test_empirical_interval_expands_with_horizon() -> None:
    fitted = HistoricalForecaster.fit(
        _series([1.0, 3.0, 2.0, 5.0, 4.0, 7.0]),
        ForecastMethod.DRIFT,
    )
    points = fitted.forecast(4, interval_coverage=0.8)
    widths = [point.upper - point.lower for point in points]  # type: ignore[operator]
    assert widths == sorted(widths)
    assert widths[-1] > widths[0]


def test_invalid_interval_coverage_fails_closed() -> None:
    fitted = HistoricalForecaster.fit(_series([1.0, 2.0]), ForecastMethod.DRIFT)
    with pytest.raises(HistoricalForecastError):
        fitted.forecast(2, interval_coverage=0.0)


def test_policy_sorts_horizons_deterministically() -> None:
    policy = _policy(horizons=(4, 1, 2))
    assert policy.horizons == (1, 2, 4)


def test_policy_rejects_duplicate_horizons() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        _policy(horizons=(1, 1, 2))
    assert exc.value.context["reason"] == "duplicate_horizon"


def test_policy_rejects_mismatched_horizon_weights() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        _policy(horizon_weights=(1.0,))
    assert exc.value.context["reason"] == "horizon_weight_mismatch"


def test_policy_rejects_zero_error_metric_weights() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        _policy(mae_weight=0.0, rmse_weight=0.0, smape_weight=0.0)
    assert exc.value.context["reason"] == "zero_metric_weights"


def test_policy_rejects_empty_smoothing_grid() -> None:
    with pytest.raises(HistoricalForecastError) as exc:
        _policy(alpha_grid=())
    assert exc.value.context["reason"] == "empty_grid"


def test_default_horizon_weights_favor_near_term() -> None:
    policy = _policy(horizons=(1, 2, 4))
    weights = policy.normalized_horizon_weights
    assert weights[0] > weights[1] > weights[2]
    assert sum(weights) == pytest.approx(1.0)


def test_rolling_evaluation_counts_expanding_origins() -> None:
    series = _series([float(index) for index in range(12)])
    tournament = HistoricalForecastTournament(_policy(horizons=(1, 2), minimum_training_points=4))
    evaluation = tournament.evaluate(series, ForecastMethod.DRIFT, ForecastParameters())
    assert evaluation.origin_count == 7
    assert all(item.sample_count == 7 for item in evaluation.horizons)


def test_perfect_linear_series_gives_zero_drift_error() -> None:
    series = _series([3.0 + 2.0 * index for index in range(14)])
    tournament = HistoricalForecastTournament(_policy(horizons=(1, 2, 3), minimum_training_points=4))
    evaluation = tournament.evaluate(series, ForecastMethod.DRIFT, ForecastParameters())
    assert evaluation.aggregate_mae == pytest.approx(0.0)
    assert evaluation.aggregate_rmse == pytest.approx(0.0)
    assert evaluation.aggregate_smape == pytest.approx(0.0)


def test_linear_history_selects_drift_over_static_baselines() -> None:
    series = _series([10.0 + 1.5 * index for index in range(18)])
    report = HistoricalForecastTournament(_policy()).run(series)
    assert report.champion.method is ForecastMethod.DRIFT


def test_constant_history_selects_simplest_zero_error_model() -> None:
    series = _series([7.0] * 18)
    report = HistoricalForecastTournament(_policy()).run(series)
    assert report.champion.objective == pytest.approx(0.0)
    assert report.champion.method is ForecastMethod.LAST_VALUE


def test_tournament_report_is_deterministic() -> None:
    series = _series([1.0, 2.0, 2.5, 4.0, 4.5, 5.0, 7.0, 6.5, 8.0, 9.0, 9.5, 11.0])
    tournament = HistoricalForecastTournament(_policy())
    left = tournament.run(series)
    right = tournament.run(series)
    assert left.report_fingerprint == right.report_fingerprint
    assert [item.evaluation_fingerprint for item in left.candidates] == [
        item.evaluation_fingerprint for item in right.candidates
    ]


def test_short_series_is_rejected_before_tournament() -> None:
    series = _series([1.0, 2.0, 3.0, 4.0, 5.0])
    with pytest.raises(HistoricalForecastError) as exc:
        HistoricalForecastTournament(_policy()).run(series)
    assert exc.value.context["reason"] == "insufficient_backtest_history"


def test_fit_champion_refits_on_complete_series() -> None:
    series = _series([2.0 + index for index in range(16)])
    fitted, report = HistoricalForecastTournament(_policy()).fit_champion(series)
    assert fitted.method is report.champion.method
    assert fitted.training_points == len(series.observations)
    assert fitted.training_fingerprint == series.fingerprint


def test_summary_exposes_error_and_fingerprints() -> None:
    series = _series([5.0 + index for index in range(16)])
    report = HistoricalForecastTournament(_policy()).run(series)
    summary = summarize_forecast_tournament(report)
    assert summary["champion"]["method"] == report.champion.method.value
    assert summary["champion"]["percent_error"] == report.champion.percent_error
    assert summary["candidate_count"] == len(report.candidates)
    assert summary["series_fingerprint"] == series.fingerprint
    assert summary["report_fingerprint"] == report.report_fingerprint


def test_series_from_registry_uses_exact_model_and_benchmark_revision() -> None:
    model = ModelIdentity("provider", "model", "r1")
    other_model = ModelIdentity("provider", "model", "r2")
    benchmark = _benchmark()
    other_benchmark = BenchmarkDefinition(
        benchmark_id=benchmark.benchmark_id,
        revision="v2",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("a", model, benchmark, 60.0, NOW - 300.0))
    registry.ingest(_snapshot("b", model, benchmark, 80.0, NOW - 200.0))
    registry.ingest(_snapshot("wrong-model", other_model, benchmark, 99.0, NOW - 150.0))
    registry.ingest(_snapshot("wrong-revision", model, other_benchmark, 100.0, NOW - 100.0))

    series = series_from_registry(registry, model=model, benchmark=benchmark)

    assert series.values == pytest.approx((0.6, 0.8))
    assert series.timestamps == pytest.approx((NOW - 300.0, NOW - 200.0))


def test_series_from_registry_rejects_missing_exact_evidence() -> None:
    model = ModelIdentity("provider", "model", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    with pytest.raises(HistoricalForecastError) as exc:
        series_from_registry(registry, model=model, benchmark=_benchmark())
    assert exc.value.context["reason"] == "no_series_evidence"


def test_registry_series_fingerprint_changes_when_history_grows() -> None:
    model = ModelIdentity("provider", "model", "r1")
    benchmark = _benchmark()
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("a", model, benchmark, 50.0, NOW - 300.0))
    before = series_from_registry(registry, model=model, benchmark=benchmark).fingerprint
    registry.ingest(_snapshot("b", model, benchmark, 55.0, NOW - 200.0))
    after = series_from_registry(registry, model=model, benchmark=benchmark).fingerprint
    assert before != after


def test_smape_is_bounded_for_nonzero_series() -> None:
    series = _series([1.0, 5.0, 2.0, 8.0, 3.0, 13.0, 5.0, 21.0, 8.0, 34.0])
    evaluation = HistoricalForecastTournament(_policy()).evaluate(
        series,
        ForecastMethod.LAST_VALUE,
        ForecastParameters(),
    )
    assert 0.0 <= evaluation.aggregate_smape <= 2.0


def test_forecast_parameters_reject_nan() -> None:
    with pytest.raises(HistoricalForecastError):
        ForecastParameters(alpha=math.nan)


def test_forecast_parameters_reject_zero_smoothing() -> None:
    with pytest.raises(HistoricalForecastError):
        ForecastParameters(alpha=0.0)


def test_forecast_horizon_limit_is_enforced() -> None:
    fitted = HistoricalForecaster.fit(_series([1.0, 2.0]), ForecastMethod.DRIFT)
    with pytest.raises(HistoricalForecastError) as exc:
        fitted.forecast(257)
    assert exc.value.context["reason"] == "too_large"