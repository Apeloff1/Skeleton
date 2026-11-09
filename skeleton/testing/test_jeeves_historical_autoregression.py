from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_autoregression import (
    AdvancedHistoricalForecastTournament,
    AutoRegressiveForecaster,
    AutoRegressiveParameters,
    AutoRegressiveSelectionPolicy,
    HistoricalAutoregressionError,
    summarize_advanced_forecast,
)
from skeleton.jeeves.historical_forecasting import (
    ForecastObservation,
    ForecastSelectionPolicy,
    HistoricalSeries,
)


def _series(values: list[float] | tuple[float, ...], *, series_id: str = "ar-fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values, start=1)
        ),
    )


def _forecast_policy(**overrides: object) -> ForecastSelectionPolicy:
    values: dict[str, object] = {
        "horizons": (1, 2),
        "minimum_training_points": 6,
        "minimum_origins": 3,
        "alpha_grid": (0.4, 0.8),
        "beta_grid": (0.2, 0.5),
        "damping_grid": (0.9, 0.98),
    }
    values.update(overrides)
    return ForecastSelectionPolicy(**values)  # type: ignore[arg-type]


def _ar_policy(**overrides: object) -> AutoRegressiveSelectionPolicy:
    values: dict[str, object] = {
        "orders": (1, 2, 3),
        "ridge_grid": (1e-8, 1e-5),
        "include_intercept": True,
    }
    values.update(overrides)
    return AutoRegressiveSelectionPolicy(**values)  # type: ignore[arg-type]


def _ar1_values(count: int, *, start: float = 0.0, intercept: float = 1.0, coefficient: float = 0.5) -> list[float]:
    values = [start]
    for _ in range(count - 1):
        values.append(intercept + coefficient * values[-1])
    return values


def _oscillating_values(count: int) -> list[float]:
    values = [1.0, 0.0]
    while len(values) < count:
        values.append(-values[-2])
    return values


def test_parameters_validate_order() -> None:
    with pytest.raises(HistoricalAutoregressionError) as exc:
        AutoRegressiveParameters(order=0)
    assert exc.value.context["reason"] == "invalid_order"


def test_parameters_validate_ridge() -> None:
    with pytest.raises(HistoricalAutoregressionError) as exc:
        AutoRegressiveParameters(order=1, ridge=-1.0)
    assert exc.value.context["reason"] == "invalid_non_negative"


def test_parameters_reject_non_boolean_intercept_flag() -> None:
    with pytest.raises(HistoricalAutoregressionError) as exc:
        AutoRegressiveParameters(order=1, include_intercept=1)  # type: ignore[arg-type]
    assert exc.value.context["reason"] == "invalid_intercept_flag"


def test_ar1_recovers_affine_recurrence() -> None:
    series = _series(_ar1_values(30, intercept=1.25, coefficient=0.6))
    fitted = AutoRegressiveForecaster.fit(
        series,
        AutoRegressiveParameters(order=1, ridge=1e-10, include_intercept=True),
    )
    assert fitted.intercept == pytest.approx(1.25, abs=1e-5)
    assert fitted.coefficients[0] == pytest.approx(0.6, abs=1e-5)
    expected = 1.25 + 0.6 * series.values[-1]
    assert fitted.forecast(1)[0] == pytest.approx(expected, abs=1e-5)


def test_ar2_recovers_oscillating_recurrence_without_intercept() -> None:
    series = _series(_oscillating_values(40))
    fitted = AutoRegressiveForecaster.fit(
        series,
        AutoRegressiveParameters(order=2, ridge=1e-8, include_intercept=False),
    )
    assert fitted.coefficients[0] == pytest.approx(0.0, abs=1e-5)
    assert fitted.coefficients[1] == pytest.approx(-1.0, abs=1e-5)
    assert fitted.forecast(4) == pytest.approx(tuple(_oscillating_values(44)[-4:]), abs=1e-4)


def test_recursive_forecast_matches_known_ar1_path() -> None:
    series = _series(_ar1_values(25, intercept=2.0, coefficient=0.25))
    fitted = AutoRegressiveForecaster.fit(
        series,
        AutoRegressiveParameters(order=1, ridge=1e-10),
    )
    predicted = fitted.forecast(5)
    expected: list[float] = []
    value = series.values[-1]
    for _ in range(5):
        value = 2.0 + 0.25 * value
        expected.append(value)
    assert predicted == pytest.approx(expected, abs=1e-5)


def test_fit_requires_order_plus_two_points() -> None:
    with pytest.raises(HistoricalAutoregressionError) as exc:
        AutoRegressiveForecaster.fit(
            _series([1.0, 2.0, 3.0]),
            AutoRegressiveParameters(order=2),
        )
    assert exc.value.context["reason"] == "insufficient_points"


def test_zero_ridge_can_fail_closed_on_singular_constant_design() -> None:
    with pytest.raises(HistoricalAutoregressionError) as exc:
        AutoRegressiveForecaster.fit(
            _series([5.0] * 12),
            AutoRegressiveParameters(order=2, ridge=0.0, include_intercept=True),
        )
    assert exc.value.context["reason"] == "singular_system"


def test_positive_ridge_stabilizes_constant_design() -> None:
    fitted = AutoRegressiveForecaster.fit(
        _series([5.0] * 12),
        AutoRegressiveParameters(order=2, ridge=1e-3, include_intercept=True),
    )
    assert all(math.isfinite(value) for value in fitted.coefficients)
    assert math.isfinite(fitted.intercept)
    assert all(math.isfinite(value) for value in fitted.forecast(10))


def test_fit_retains_exact_training_fingerprint() -> None:
    series = _series(_ar1_values(20))
    fitted = AutoRegressiveForecaster.fit(series, AutoRegressiveParameters(order=1))
    assert fitted.training_fingerprint == series.fingerprint
    assert fitted.training_points == len(series.observations)


def test_coefficient_l1_is_reported() -> None:
    series = _series(_oscillating_values(30))
    fitted = AutoRegressiveForecaster.fit(
        series,
        AutoRegressiveParameters(order=2, ridge=1e-6, include_intercept=False),
    )
    assert fitted.coefficient_l1 == pytest.approx(1.0, abs=1e-4)


def test_selection_policy_sorts_and_deduplicates_orders() -> None:
    policy = AutoRegressiveSelectionPolicy(orders=(3, 1, 3, 2), ridge_grid=(1e-4, 1e-6, 1e-4))
    assert policy.orders == (1, 2, 3)
    assert policy.ridge_grid == (1e-6, 1e-4)


def test_selection_policy_rejects_empty_orders() -> None:
    with pytest.raises(HistoricalAutoregressionError) as exc:
        AutoRegressiveSelectionPolicy(orders=())
    assert exc.value.context["reason"] == "empty_orders"


def test_selection_policy_rejects_empty_ridge_grid() -> None:
    with pytest.raises(HistoricalAutoregressionError) as exc:
        AutoRegressiveSelectionPolicy(ridge_grid=())
    assert exc.value.context["reason"] == "empty_ridge_grid"


def test_selection_policy_rejects_invalid_stability_bounds() -> None:
    with pytest.raises(HistoricalAutoregressionError):
        AutoRegressiveSelectionPolicy(max_coefficient_l1=0.0)
    with pytest.raises(HistoricalAutoregressionError):
        AutoRegressiveSelectionPolicy(explosion_multiplier=0.0)


def test_ar_evaluation_uses_same_rolling_origin_count_as_baseline_policy() -> None:
    series = _series(_ar1_values(16))
    tournament = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(horizons=(1, 2), minimum_training_points=6),
        autoregression_policy=_ar_policy(orders=(1,), ridge_grid=(1e-6,)),
    )
    evaluation = tournament.evaluate(series, AutoRegressiveParameters(order=1, ridge=1e-6))
    assert evaluation.origin_count == 9
    assert all(metric.sample_count == 9 for metric in evaluation.horizons)


def test_ar1_evaluation_has_tiny_error_on_exact_process() -> None:
    series = _series(_ar1_values(30, intercept=1.0, coefficient=0.7))
    tournament = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(orders=(1,), ridge_grid=(1e-10,)),
    )
    evaluation = tournament.evaluate(
        series,
        AutoRegressiveParameters(order=1, ridge=1e-10),
    )
    assert evaluation.aggregate_mae < 1e-5
    assert evaluation.aggregate_rmse < 1e-5


def test_oscillating_ar2_process_beats_baseline_family() -> None:
    series = _series(_oscillating_values(40))
    report = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(
            horizons=(1, 2, 3),
            minimum_training_points=8,
            complexity_weight=0.0001,
        ),
        autoregression_policy=_ar_policy(
            orders=(1, 2, 3),
            ridge_grid=(1e-8,),
            include_intercept=False,
        ),
    ).run(series)
    assert report.family == "autoregression"
    assert report.autoregressive_champion is not None
    assert report.autoregressive_champion.parameters.order == 2
    assert report.objective < report.baseline_report.champion.objective


def test_constant_process_keeps_simpler_baseline() -> None:
    series = _series([9.0] * 30)
    report = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(orders=(1, 2), ridge_grid=(1e-4,)),
    ).run(series)
    assert report.family == "baseline"
    assert report.baseline_report.champion.objective == pytest.approx(0.0)


def test_orders_incompatible_with_common_origin_are_skipped() -> None:
    series = _series(_ar1_values(20))
    report = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(minimum_training_points=4),
        autoregression_policy=_ar_policy(orders=(8,), ridge_grid=(1e-6,)),
    ).run(series)
    assert report.autoregressive_candidates == ()
    assert report.autoregressive_champion is None
    assert report.family == "baseline"


def test_coefficient_stability_gate_can_reject_all_ar_candidates() -> None:
    series = _series(_oscillating_values(30))
    report = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(minimum_training_points=8),
        autoregression_policy=_ar_policy(
            orders=(2,),
            ridge_grid=(1e-8,),
            include_intercept=False,
            max_coefficient_l1=0.01,
        ),
    ).run(series)
    assert report.autoregressive_candidates == ()
    assert report.family == "baseline"


def test_advanced_report_is_deterministic() -> None:
    series = _series(_ar1_values(28, intercept=0.5, coefficient=0.8))
    tournament = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
    )
    left = tournament.run(series)
    right = tournament.run(series)
    assert left.report_fingerprint == right.report_fingerprint
    assert left.method_label == right.method_label


def test_fit_champion_returns_selected_family_model() -> None:
    series = _series(_oscillating_values(36))
    tournament = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(minimum_training_points=8, complexity_weight=0.0001),
        autoregression_policy=_ar_policy(
            orders=(2,),
            ridge_grid=(1e-8,),
            include_intercept=False,
        ),
    )
    fitted, report = tournament.fit_champion(series)
    assert report.family == "autoregression"
    assert fitted.parameters.order == 2
    assert fitted.training_fingerprint == series.fingerprint


def test_summary_exposes_baseline_and_ar_evidence() -> None:
    series = _series(_oscillating_values(36))
    report = AdvancedHistoricalForecastTournament(
        forecast_policy=_forecast_policy(minimum_training_points=8, complexity_weight=0.0001),
        autoregression_policy=_ar_policy(
            orders=(2,),
            ridge_grid=(1e-8,),
            include_intercept=False,
        ),
    ).run(series)
    summary = summarize_advanced_forecast(report)
    assert summary["family"] == report.family
    assert summary["method"] == report.method_label
    assert summary["objective"] == report.objective
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["baseline"]["report_fingerprint"] == report.baseline_report.report_fingerprint
    assert summary["autoregressive_candidate_count"] == len(report.autoregressive_candidates)