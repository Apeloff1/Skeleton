from __future__ import annotations

import pytest

from skeleton.jeeves.historical_forecasting import (
    ForecastMethod,
    ForecastObservation,
    ForecastParameters,
    ForecastSelectionPolicy,
    HistoricalForecaster,
    HistoricalForecastTournament,
    HistoricalSeries,
)


def _series(values: list[float], *, series_id: str = "leakage-fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=value)
            for index, value in enumerate(values, start=1)
        ),
    )


def test_objective_scale_uses_only_initial_training_window() -> None:
    # The first four observations are the only values available before the
    # first rolling forecast origin. Later values are intentionally huge: using
    # the full-series median would leak future magnitude and shrink the MAE
    # contribution by two orders of magnitude.
    series = _series([10.0, 10.0, 10.0, 10.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0])
    policy = ForecastSelectionPolicy(
        horizons=(1,),
        minimum_training_points=4,
        minimum_origins=3,
        mae_weight=1.0,
        rmse_weight=0.0,
        smape_weight=0.0,
        complexity_weight=0.0,
        alpha_grid=(0.5,),
        beta_grid=(0.2,),
        damping_grid=(0.9,),
    )
    tournament = HistoricalForecastTournament(policy)

    evaluation = tournament.evaluate(
        series,
        ForecastMethod.LAST_VALUE,
        ForecastParameters(),
    )

    assert evaluation.aggregate_mae > 0.0
    assert evaluation.objective == pytest.approx(evaluation.aggregate_mae / 10.0)
    assert evaluation.objective > 1.0


def test_fit_champion_uses_rolling_origin_residuals_for_intervals() -> None:
    series = _series(
        [10.0, 12.0, 11.0, 15.0, 14.0, 19.0, 17.0, 24.0, 21.0, 29.0, 25.0, 34.0]
    )
    policy = ForecastSelectionPolicy(
        horizons=(1, 2),
        minimum_training_points=4,
        minimum_origins=3,
        alpha_grid=(0.4, 0.8),
        beta_grid=(0.2, 0.5),
        damping_grid=(0.9, 0.98),
    )
    tournament = HistoricalForecastTournament(policy)

    fitted, report = tournament.fit_champion(series)
    in_sample = HistoricalForecaster.fit(
        series,
        report.champion.method,
        report.champion.parameters,
    )

    assert fitted.residuals == report.champion.residuals
    assert fitted.training_fingerprint == series.fingerprint
    assert fitted.training_points == len(series.observations)
    # The calibrated residual source is deliberately not the final in-sample
    # fit residual vector; it comes from historical out-of-sample forecasts.
    assert fitted.residuals != in_sample.residuals


def test_rolling_residual_calibration_produces_finite_intervals() -> None:
    series = _series(
        [2.0, 3.0, 2.5, 5.0, 4.0, 7.5, 6.0, 9.0, 7.0, 11.0, 8.5, 13.0]
    )
    tournament = HistoricalForecastTournament(
        ForecastSelectionPolicy(
            horizons=(1, 2),
            minimum_training_points=4,
            minimum_origins=3,
            alpha_grid=(0.4,),
            beta_grid=(0.2,),
            damping_grid=(0.9,),
        )
    )
    fitted, _ = tournament.fit_champion(series)

    points = fitted.forecast(4, interval_coverage=0.8)

    assert len(points) == 4
    assert all(point.lower is not None and point.upper is not None for point in points)
    assert all(point.lower <= point.predicted <= point.upper for point in points)  # type: ignore[operator]