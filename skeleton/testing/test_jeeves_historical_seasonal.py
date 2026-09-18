from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_forecasting import ForecastObservation, ForecastSelectionPolicy, HistoricalSeries
from skeleton.jeeves.historical_seasonal import (
    HistoricalSeasonalError,
    HistoricalSeasonalForecaster,
    HistoricalSeasonalTournament,
    SeasonalMethod,
    SeasonalParameters,
    SeasonalSelectionPolicy,
    summarize_seasonal_tournament,
)


def _series(values: list[float], *, series_id: str = "seasonal") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values)
        ),
    )


def _forecast_policy() -> ForecastSelectionPolicy:
    return ForecastSelectionPolicy(
        horizons=(1, 2, 4),
        minimum_training_points=8,
        minimum_origins=4,
        alpha_grid=(0.5,),
        beta_grid=(0.3,),
        damping_grid=(0.9,),
    )


def _seasonal_policy() -> SeasonalSelectionPolicy:
    return SeasonalSelectionPolicy(
        periods=(4, 6),
        alpha_grid=(0.3, 0.7),
        beta_grid=(0.2,),
        gamma_grid=(0.2, 0.6),
        damping_grid=(0.9,),
        complexity_weight=0.001,
    )


def test_seasonal_naive_replays_exact_periodic_pattern() -> None:
    values = [1.0, 3.0, 2.0, 5.0] * 5
    series = _series(values, series_id="periodic")

    fitted = HistoricalSeasonalForecaster.fit(
        series,
        SeasonalMethod.SEASONAL_NAIVE,
        SeasonalParameters(period=4),
    )

    assert fitted.forecast(8) == pytest.approx(tuple([1.0, 3.0, 2.0, 5.0] * 2))
    assert max(abs(value) for value in fitted.residuals) == pytest.approx(0.0)


def test_seasonal_naive_phase_remains_correct_when_history_ends_mid_cycle() -> None:
    values = [2.0, 4.0, 8.0, 16.0] * 4 + [2.0]
    fitted = HistoricalSeasonalForecaster.fit(
        _series(values, series_id="mid-cycle"),
        SeasonalMethod.SEASONAL_NAIVE,
        SeasonalParameters(period=4),
    )

    assert fitted.forecast(4) == pytest.approx((4.0, 8.0, 16.0, 2.0))


def test_additive_holt_winters_tracks_trend_plus_additive_seasonality() -> None:
    seasonal = (-3.0, 1.0, 4.0, -2.0)
    values = [50.0 + 0.8 * index + seasonal[index % 4] for index in range(48)]
    series = _series(values, series_id="trend-season")
    fitted = HistoricalSeasonalForecaster.fit(
        series,
        SeasonalMethod.ADDITIVE_HOLT_WINTERS,
        SeasonalParameters(period=4, alpha=0.5, beta=0.2, gamma=0.3),
    )

    predictions = fitted.forecast(4)
    expected = tuple(50.0 + 0.8 * (48 + step) + seasonal[(48 + step) % 4] for step in range(4))

    assert all(math.isfinite(value) for value in predictions)
    assert max(abs(left - right) for left, right in zip(predictions, expected, strict=True)) < 4.0


def test_damped_holt_winters_forecast_is_finite_and_deterministic() -> None:
    values = [20.0 + 0.35 * index + (2.0 if index % 3 == 0 else -1.0) for index in range(42)]
    series = _series(values, series_id="damped")
    parameters = SeasonalParameters(period=3, alpha=0.5, beta=0.2, gamma=0.4, damping=0.9)

    left = HistoricalSeasonalForecaster.fit(
        series,
        SeasonalMethod.DAMPED_ADDITIVE_HOLT_WINTERS,
        parameters,
    )
    right = HistoricalSeasonalForecaster.fit(
        series,
        SeasonalMethod.DAMPED_ADDITIVE_HOLT_WINTERS,
        parameters,
    )

    assert left == right
    assert left.forecast(12) == right.forecast(12)
    assert all(math.isfinite(value) for value in left.forecast(12))


def test_tournament_selects_exact_seasonal_naive_pattern() -> None:
    values = [10.0, 12.0, 7.0, 15.0] * 12
    tournament = HistoricalSeasonalTournament(
        forecast_policy=_forecast_policy(),
        seasonal_policy=SeasonalSelectionPolicy(
            periods=(4,),
            alpha_grid=(0.5,),
            beta_grid=(0.2,),
            gamma_grid=(0.3,),
            damping_grid=(0.9,),
            complexity_weight=0.001,
        ),
    )

    report = tournament.run(_series(values, series_id="champion"))

    assert report.champion.method is SeasonalMethod.SEASONAL_NAIVE
    assert report.champion.parameters.period == 4
    assert report.champion.aggregate_mae == pytest.approx(0.0)
    assert report.champion.objective == pytest.approx(0.001)


def test_every_candidate_uses_exact_same_origin_window() -> None:
    values = [30.0 + 0.1 * index + math.sin(index * math.pi / 2.0) for index in range(60)]
    tournament = HistoricalSeasonalTournament(
        forecast_policy=_forecast_policy(),
        seasonal_policy=_seasonal_policy(),
    )

    report = tournament.run(_series(values, series_id="common-origin"))

    assert report.common_origin_start == 12
    assert {item.common_origin_start for item in report.candidates} == {12}
    assert len({item.origin_count for item in report.candidates}) == 1


def test_future_tail_does_not_rewrite_earlier_rolling_origin_residuals() -> None:
    base_values = [40.0 + 0.2 * index + (3.0 if index % 4 == 0 else -1.0) for index in range(40)]
    extended_values = base_values + [500.0, -300.0, 700.0, -600.0, 900.0, -800.0]
    policy = SeasonalSelectionPolicy(
        periods=(4,),
        alpha_grid=(0.5,),
        beta_grid=(0.2,),
        gamma_grid=(0.3,),
        damping_grid=(0.9,),
    )
    tournament = HistoricalSeasonalTournament(
        forecast_policy=_forecast_policy(),
        seasonal_policy=policy,
    )
    parameters = SeasonalParameters(period=4, alpha=0.5, beta=0.2, gamma=0.3)

    base = tournament.evaluate(
        _series(base_values, series_id="base"),
        SeasonalMethod.ADDITIVE_HOLT_WINTERS,
        parameters,
    )
    extended = tournament.evaluate(
        _series(extended_values, series_id="extended"),
        SeasonalMethod.ADDITIVE_HOLT_WINTERS,
        parameters,
    )

    assert extended.residuals[: len(base.residuals)] == pytest.approx(base.residuals)
    assert extended.origin_count > base.origin_count


def test_fit_champion_refits_on_full_source_series() -> None:
    values = [5.0, 9.0, 7.0, 12.0] * 10
    series = _series(values, series_id="refit")
    tournament = HistoricalSeasonalTournament(
        forecast_policy=_forecast_policy(),
        seasonal_policy=SeasonalSelectionPolicy(
            periods=(4,),
            alpha_grid=(0.5,),
            beta_grid=(0.2,),
            gamma_grid=(0.3,),
            damping_grid=(0.9,),
        ),
    )

    fitted, report = tournament.fit_champion(series)

    assert fitted.training_points == len(values)
    assert fitted.training_fingerprint == series.fingerprint
    assert fitted.method == report.champion.method
    assert fitted.parameters == report.champion.parameters


def test_report_and_summary_are_deterministic() -> None:
    values = [25.0 + math.sin(index * math.pi / 2.0) for index in range(48)]
    series = _series(values, series_id="deterministic")
    tournament = HistoricalSeasonalTournament(
        forecast_policy=_forecast_policy(),
        seasonal_policy=_seasonal_policy(),
    )

    left = tournament.run(series)
    right = tournament.run(series)
    summary = summarize_seasonal_tournament(left)

    assert left == right
    assert left.report_fingerprint == right.report_fingerprint
    assert summary["champion_method"] == left.champion.method.value
    assert summary["common_origin_start"] == left.common_origin_start


def test_seasonal_contracts_fail_closed() -> None:
    with pytest.raises(HistoricalSeasonalError):
        SeasonalParameters(period=1)
    with pytest.raises(HistoricalSeasonalError):
        SeasonalSelectionPolicy(periods=())
    with pytest.raises(HistoricalSeasonalError):
        SeasonalSelectionPolicy(periods=(4,), gamma_grid=(0.0,))

    short = _series([1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0], series_id="short")
    with pytest.raises(HistoricalSeasonalError) as exc:
        HistoricalSeasonalForecaster.fit(
            short,
            SeasonalMethod.SEASONAL_NAIVE,
            SeasonalParameters(period=4),
        )
    assert exc.value.context["reason"] == "insufficient_cycles"
