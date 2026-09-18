from __future__ import annotations

import pytest

from skeleton.jeeves.historical_autoregression import AutoRegressiveSelectionPolicy
from skeleton.jeeves.historical_ensemble import (
    ForecastEnsemblePolicy,
    HistoricalForecastEnsembler,
)
from skeleton.jeeves.historical_forecasting import (
    ForecastObservation,
    ForecastSelectionPolicy,
    HistoricalSeries,
)


def _series(values: list[float]) -> HistoricalSeries:
    return HistoricalSeries(
        series_id="ensemble-leakage-fixture",
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=value)
            for index, value in enumerate(values, start=1)
        ),
    )


def _ensembler() -> HistoricalForecastEnsembler:
    return HistoricalForecastEnsembler(
        forecast_policy=ForecastSelectionPolicy(
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
        ),
        autoregression_policy=AutoRegressiveSelectionPolicy(
            orders=(1,),
            ridge_grid=(1e-4,),
            max_coefficient_l1=1000.0,
            explosion_multiplier=1_000_000.0,
        ),
        ensemble_policy=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.25, 0.5, 0.75),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
            require_interior_weight=True,
        ),
    )


def test_ensemble_objective_uses_initial_training_scale_only() -> None:
    # Initial median magnitude is 10.5. Large future evaluation values are
    # deliberately present so a full-series normalization leak would shrink the
    # MAE term toward a 1000-scale denominator instead.
    series = _series(
        [10.0, 11.0, 10.0, 11.0, 1000.0, 1001.0, 1000.0, 1001.0, 1000.0, 1001.0]
    )

    report = _ensembler().run(series)

    assert report.candidates
    for candidate in report.candidates:
        assert candidate.objective == pytest.approx(candidate.aggregate_mae / 10.5)


def test_ensemble_and_constituent_objectives_remain_comparable() -> None:
    series = _series([5.0, 7.0, 6.0, 8.0, 10.0, 9.0, 12.0, 11.0, 14.0, 13.0, 16.0])

    report = _ensembler().run(series)

    assert report.best_constituent_objective >= 0.0
    assert report.selected_objective >= 0.0
    assert report.improvement == pytest.approx(
        report.best_constituent_objective
        - (report.ensemble_champion.objective if report.ensemble_champion is not None else report.best_constituent_objective)
    )


def test_later_scale_changes_do_not_change_initial_normalization_contract() -> None:
    low_tail = _series([10.0, 11.0, 10.0, 11.0, 20.0, 21.0, 20.0, 21.0, 20.0, 21.0])
    high_tail = _series([10.0, 11.0, 10.0, 11.0, 2000.0, 2001.0, 2000.0, 2001.0, 2000.0, 2001.0])
    ensembler = _ensembler()

    low = ensembler.run(low_tail)
    high = ensembler.run(high_tail)

    assert low.candidates and high.candidates
    # Both reports are allowed to have very different errors; what is fixed is
    # that objective normalization remains tied to the identical first four
    # observations rather than adapting to the unseen tail magnitude.
    for candidate in low.candidates:
        assert candidate.objective == pytest.approx(candidate.aggregate_mae / 10.5)
    for candidate in high.candidates:
        assert candidate.objective == pytest.approx(candidate.aggregate_mae / 10.5)