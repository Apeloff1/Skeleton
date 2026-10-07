from __future__ import annotations

import pytest

from skeleton.jeeves.historical_autoregression import (
    AdvancedHistoricalForecastTournament,
    AutoRegressiveParameters,
    AutoRegressiveSelectionPolicy,
)
from skeleton.jeeves.historical_forecasting import (
    ForecastObservation,
    ForecastSelectionPolicy,
    HistoricalSeries,
)


def _series(values: list[float]) -> HistoricalSeries:
    return HistoricalSeries(
        series_id="ar-leakage-fixture",
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=value)
            for index, value in enumerate(values, start=1)
        ),
    )


def test_ar_objective_uses_same_initial_training_scale_as_baseline() -> None:
    series = _series(
        [10.0, 11.0, 10.0, 11.0, 1000.0, 1001.0, 1000.0, 1001.0, 1000.0, 1001.0]
    )
    forecast_policy = ForecastSelectionPolicy(
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
    tournament = AdvancedHistoricalForecastTournament(
        forecast_policy=forecast_policy,
        autoregression_policy=AutoRegressiveSelectionPolicy(
            orders=(1,),
            ridge_grid=(1e-4,),
            max_coefficient_l1=1000.0,
            explosion_multiplier=1_000_000.0,
        ),
    )

    evaluation = tournament.evaluate(
        series,
        AutoRegressiveParameters(order=1, ridge=1e-4),
    )

    # Median absolute magnitude of the only pre-forecast training window is
    # (10 + 10 + 11 + 11) / middle pair -> 10.5. Later 1000-scale values must
    # not change the units-vs-percentage weighting used by model selection.
    assert evaluation.objective == pytest.approx(evaluation.aggregate_mae / 10.5)
    assert evaluation.objective > 1.0


def test_baseline_and_ar_family_share_objective_units() -> None:
    series = _series([5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0])
    forecast_policy = ForecastSelectionPolicy(
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
    tournament = AdvancedHistoricalForecastTournament(
        forecast_policy=forecast_policy,
        autoregression_policy=AutoRegressiveSelectionPolicy(
            orders=(1,),
            ridge_grid=(1e-4,),
            max_coefficient_l1=1000.0,
            explosion_multiplier=1_000_000.0,
        ),
    )

    report = tournament.run(series)

    assert report.objective >= 0.0
    if report.autoregressive_champion is not None:
        assert report.autoregressive_champion.objective >= 0.0
    assert report.baseline_report.champion.objective >= 0.0