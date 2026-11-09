from __future__ import annotations

import pytest

from skeleton.jeeves.historical_autoregression import AutoRegressiveSelectionPolicy
from skeleton.jeeves.historical_ensemble import (
    FittedForecastEnsemble,
    ForecastEnsemblePolicy,
    HistoricalEnsembleError,
    HistoricalForecastEnsembler,
    summarize_forecast_ensemble,
)
from skeleton.jeeves.historical_forecasting import (
    ForecastObservation,
    ForecastSelectionPolicy,
    HistoricalSeries,
)


def _series(values: list[float] | tuple[float, ...], *, series_id: str = "ensemble-fixture") -> HistoricalSeries:
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
        "minimum_training_points": 8,
        "minimum_origins": 3,
        "alpha_grid": (0.4, 0.8),
        "beta_grid": (0.2, 0.5),
        "damping_grid": (0.9, 0.98),
        "complexity_weight": 0.0005,
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


def _oscillating_values(count: int) -> list[float]:
    values = [1.0, 0.0]
    while len(values) < count:
        values.append(-values[-2])
    return values


def _trend_oscillation(count: int) -> list[float]:
    pattern = (2.0, -2.0, 2.0, -2.0)
    return [0.35 * index + pattern[index % len(pattern)] for index in range(count)]


def test_policy_sorts_and_deduplicates_weight_grid() -> None:
    policy = ForecastEnsemblePolicy(baseline_weight_grid=(1.0, 0.5, 0.0, 0.5))
    assert policy.baseline_weight_grid == (0.0, 0.5, 1.0)


def test_policy_rejects_empty_weight_grid() -> None:
    with pytest.raises(HistoricalEnsembleError) as exc:
        ForecastEnsemblePolicy(baseline_weight_grid=())
    assert exc.value.context["reason"] == "empty_weight_grid"


def test_policy_rejects_weight_outside_unit_interval() -> None:
    with pytest.raises(HistoricalEnsembleError) as exc:
        ForecastEnsemblePolicy(baseline_weight_grid=(-0.1, 0.5))
    assert exc.value.context["reason"] == "out_of_range"


def test_policy_rejects_negative_improvement_margin() -> None:
    with pytest.raises(HistoricalEnsembleError) as exc:
        ForecastEnsemblePolicy(minimum_objective_improvement=-0.01)
    assert exc.value.context["reason"] == "invalid_non_negative"


def test_policy_rejects_non_boolean_interior_flag() -> None:
    with pytest.raises(HistoricalEnsembleError) as exc:
        ForecastEnsemblePolicy(require_interior_weight=1)  # type: ignore[arg-type]
    assert exc.value.context["reason"] == "invalid_interior_flag"


def test_no_compatible_ar_champion_returns_constituent_only_report() -> None:
    series = _series([float(index) for index in range(24)])
    ensembler = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(minimum_training_points=4),
        autoregression_policy=_ar_policy(orders=(8,), ridge_grid=(1e-6,)),
    )
    report = ensembler.run(series)
    assert report.candidates == ()
    assert report.ensemble_champion is None
    assert report.ensemble_selected is False
    assert report.selected_family == report.advanced_report.family


def test_candidate_count_matches_weight_grid_when_ar_available() -> None:
    series = _series(_oscillating_values(36))
    weights = (0.0, 0.25, 0.5, 0.75, 1.0)
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(
            orders=(2,),
            ridge_grid=(1e-8,),
            include_intercept=False,
        ),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=weights,
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
    ).run(series)
    assert len(report.candidates) == len(weights)
    assert report.ensemble_champion is not None


def test_candidate_weights_are_convex() -> None:
    series = _series(_oscillating_values(36))
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(
            orders=(2,), ridge_grid=(1e-8,), include_intercept=False
        ),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.0, 0.5, 1.0),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
    ).run(series)
    for candidate in report.candidates:
        assert 0.0 <= candidate.baseline_weight <= 1.0
        assert 0.0 <= candidate.autoregression_weight <= 1.0
        assert candidate.baseline_weight + candidate.autoregression_weight == pytest.approx(1.0)


def test_boundary_weight_does_not_masquerade_as_ensemble_by_default() -> None:
    series = _series(_oscillating_values(36))
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(
            orders=(2,), ridge_grid=(1e-8,), include_intercept=False
        ),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.0,),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
            require_interior_weight=True,
        ),
    ).run(series)
    assert report.ensemble_champion is not None
    assert report.ensemble_champion.baseline_weight == 0.0
    assert report.ensemble_selected is False
    assert report.selected_family == report.advanced_report.family


def test_explicit_boundary_policy_can_select_boundary_candidate() -> None:
    series = _series(_oscillating_values(36))
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(
            orders=(2,), ridge_grid=(1e-8,), include_intercept=False
        ),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.0,),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
            require_interior_weight=False,
        ),
    ).run(series)
    assert report.ensemble_selected is True
    assert report.selected_family == "ensemble"


def test_large_improvement_margin_holds_ensemble() -> None:
    series = _series(_trend_oscillation(48))
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.25, 0.5, 0.75),
            minimum_objective_improvement=100.0,
            ensemble_complexity_penalty=0.0,
        ),
    ).run(series)
    assert report.ensemble_selected is False
    assert report.selected_family == report.advanced_report.family


def test_ensemble_complexity_penalty_is_applied() -> None:
    series = _series(_trend_oscillation(48))
    no_penalty = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.5,),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
    ).run(series)
    penalized = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.5,),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.25,
        ),
    ).run(series)
    assert no_penalty.ensemble_champion is not None
    assert penalized.ensemble_champion is not None
    assert penalized.ensemble_champion.objective == pytest.approx(
        no_penalty.ensemble_champion.objective + 0.25
    )


def test_constituent_disagreement_is_non_negative() -> None:
    series = _series(_trend_oscillation(48))
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.5,),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
    ).run(series)
    assert report.ensemble_champion is not None
    assert report.ensemble_champion.constituent_disagreement >= 0.0


def test_report_is_deterministic() -> None:
    series = _series(_trend_oscillation(48))
    ensembler = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.25, 0.5, 0.75),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
    )
    left = ensembler.run(series)
    right = ensembler.run(series)
    assert left.report_fingerprint == right.report_fingerprint
    assert [item.evaluation_fingerprint for item in left.candidates] == [
        item.evaluation_fingerprint for item in right.candidates
    ]


def test_candidate_origin_count_is_common_across_weights() -> None:
    series = _series(_trend_oscillation(40))
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.25, 0.5, 0.75),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
    ).run(series)
    assert report.candidates
    counts = {candidate.origin_count for candidate in report.candidates}
    assert len(counts) == 1


def test_fit_selected_returns_single_model_when_ensemble_not_selected() -> None:
    series = _series(_trend_oscillation(40))
    ensembler = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.5,),
            minimum_objective_improvement=100.0,
            ensemble_complexity_penalty=0.0,
        ),
    )
    fitted, report = ensembler.fit_selected(series)
    assert report.ensemble_selected is False
    assert not isinstance(fitted, FittedForecastEnsemble)


def test_fit_selected_can_materialize_explicit_boundary_ensemble() -> None:
    series = _series(_oscillating_values(36))
    ensembler = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(
            orders=(2,), ridge_grid=(1e-8,), include_intercept=False
        ),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.0,),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
            require_interior_weight=False,
        ),
    )
    fitted, report = ensembler.fit_selected(series)
    assert report.ensemble_selected is True
    assert isinstance(fitted, FittedForecastEnsemble)
    assert fitted.baseline_weight == 0.0
    assert fitted.autoregression_weight == 1.0
    assert fitted.source_report_fingerprint == report.report_fingerprint


def test_fitted_ensemble_forecast_is_convex_combination() -> None:
    series = _series(_oscillating_values(36))
    ensembler = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(
            orders=(2,), ridge_grid=(1e-8,), include_intercept=False
        ),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.5,),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
            require_interior_weight=False,
        ),
    )
    # Materialize constituents from the report regardless of whether the 0.5
    # blend clears the improvement gate.
    report = ensembler.run(series)
    assert report.ensemble_champion is not None
    champion = report.ensemble_champion
    advanced = report.advanced_report
    baseline_eval = advanced.baseline_report.champion
    assert advanced.autoregressive_champion is not None
    from skeleton.jeeves.historical_autoregression import AutoRegressiveForecaster
    from skeleton.jeeves.historical_forecasting import HistoricalForecaster

    baseline_fit = HistoricalForecaster.fit(series, baseline_eval.method, baseline_eval.parameters)
    ar_fit = AutoRegressiveForecaster.fit(series, advanced.autoregressive_champion.parameters)
    fitted = FittedForecastEnsemble(
        baseline_fit=baseline_fit,
        autoregression_fit=ar_fit,
        baseline_weight=champion.baseline_weight,
        autoregression_weight=champion.autoregression_weight,
        source_report_fingerprint=report.report_fingerprint,
    )
    combined = fitted.forecast(3)
    baseline = baseline_fit.forecast(3)
    ar = ar_fit.forecast(3)
    expected = tuple(
        champion.baseline_weight * base.predicted + champion.autoregression_weight * ar_value
        for base, ar_value in zip(baseline, ar, strict=True)
    )
    assert combined == pytest.approx(expected)


def test_summary_exposes_selection_evidence() -> None:
    series = _series(_trend_oscillation(40))
    report = HistoricalForecastEnsembler(
        forecast_policy=_forecast_policy(),
        autoregression_policy=_ar_policy(),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.25, 0.5, 0.75),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
    ).run(series)
    summary = summarize_forecast_ensemble(report)
    assert summary["selected_family"] == report.selected_family
    assert summary["ensemble_selected"] == report.ensemble_selected
    assert summary["selected_objective"] == report.selected_objective
    assert summary["candidate_count"] == len(report.candidates)
    assert summary["advanced_report_fingerprint"] == report.advanced_report.report_fingerprint
    assert summary["report_fingerprint"] == report.report_fingerprint