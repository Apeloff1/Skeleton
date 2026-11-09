from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.observability.forecasting import (
    ForecastMetric,
    ForecastModelKind,
    ForecastObservation,
    ForecastPolicy,
    ForecastSeries,
    ForecastingError,
    backtest_forecast,
)


def _ref(index: int) -> EvidenceRef:
    return EvidenceRef(
        source=f"fixture://forecast/{index}",
        digest=f"{index % 10}" * 64,
        category="forecast_observation",
    )


def _series(
    metric: ForecastMetric,
    values: list[float],
    *,
    interval_s: float = 60.0,
) -> ForecastSeries:
    return ForecastSeries(
        series_id=f"{metric.value}-series",
        metric=metric,
        unit=(
            "requests"
            if metric is ForecastMetric.DEMAND
            else "workers"
            if metric is ForecastMetric.CAPACITY
            else "usd"
        ),
        interval_s=interval_s,
        observations=tuple(
            ForecastObservation(
                observed_at=1_800_000_000.0 + i * interval_s,
                value=value,
                evidence_refs=(_ref(i + 1),),
            )
            for i, value in enumerate(values)
        ),
    )


def _policy(**overrides: object) -> ForecastPolicy:
    values: dict[str, object] = {
        "policy_id": "dist-06-test",
        "version": 1,
        "model_kind": ForecastModelKind.LINEAR_TREND,
        "training_window": 4,
        "min_backtest_points": 4,
        "horizon_steps": 3,
        "max_mape": 0.05,
        "max_absolute_error": 1.0,
        "anomaly_relative_error": 0.10,
        "high_anomaly_relative_error": 0.25,
        "critical_anomaly_relative_error": 0.50,
    }
    values.update(overrides)
    return ForecastPolicy(**values)


@pytest.mark.parametrize(
    ("metric", "values"),
    (
        (ForecastMetric.DEMAND, [100, 110, 120, 130, 140, 150, 160, 170]),
        (ForecastMetric.CAPACITY, [2, 3, 4, 5, 6, 7, 8, 9]),
        (ForecastMetric.COST, [1, 2, 3, 4, 5, 6, 7, 8]),
    ),
)
def test_linear_trend_backtest_is_exact_and_reproducible(
    metric: ForecastMetric,
    values: list[float],
) -> None:
    series = _series(metric, values)
    policy = _policy()

    first = backtest_forecast(series=series, policy=policy)
    second = backtest_forecast(series=series, policy=policy)

    assert first.accepted is True
    assert first.reasons == ()
    assert first.mape == pytest.approx(0.0)
    assert first.mean_absolute_error == pytest.approx(0.0)
    assert first.max_absolute_error == pytest.approx(0.0)
    assert first.decision_digest == second.decision_digest
    assert first.forecast[0].step == 1
    assert first.forecast[0].expected_at == pytest.approx(
        series.observations[-1].observed_at + series.interval_s
    )


def test_backtest_accuracy_threshold_is_promotion_blocking() -> None:
    series = _series(
        ForecastMetric.DEMAND,
        [10, 20, 10, 20, 10, 20, 10, 20],
    )
    policy = _policy(
        model_kind=ForecastModelKind.TRAILING_MEAN,
        max_mape=0.01,
        max_absolute_error=1.0,
    )

    decision = backtest_forecast(series=series, policy=policy)

    assert decision.accepted is False
    assert "mape-exceeds-policy" in decision.reasons
    assert "absolute-error-exceeds-policy" in decision.reasons


def test_insufficient_history_fails_closed() -> None:
    series = _series(
        ForecastMetric.COST,
        [1.0, 2.0, 3.0, 4.0],
    )
    with pytest.raises(
        ForecastingError,
        match="enough history",
    ):
        backtest_forecast(series=series, policy=_policy())


def test_series_cadence_drift_is_rejected() -> None:
    observations = (
        ForecastObservation(
            observed_at=100.0,
            value=1.0,
            evidence_refs=(_ref(1),),
        ),
        ForecastObservation(
            observed_at=161.0,
            value=2.0,
            evidence_refs=(_ref(2),),
        ),
    )
    with pytest.raises(
        ForecastingError,
        match="cadence",
    ):
        ForecastSeries(
            series_id="bad-cadence",
            metric=ForecastMetric.COST,
            unit="usd",
            observations=observations,
            interval_s=60.0,
        )


def test_series_identity_changes_when_evidence_changes() -> None:
    series = _series(
        ForecastMetric.COST,
        [1, 2, 3, 4, 5, 6, 7, 8],
    )
    changed = replace(
        series,
        observations=(
            *series.observations[:-1],
            replace(
                series.observations[-1],
                evidence_refs=(
                    EvidenceRef(
                        source="fixture://changed",
                        digest="f" * 64,
                        category="forecast_observation",
                    ),
                ),
            ),
        ),
    )

    assert series.series_digest != changed.series_digest
