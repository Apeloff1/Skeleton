from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_autoregression import AutoRegressiveSelectionPolicy
from skeleton.jeeves.historical_conformal import ConformalPolicy
from skeleton.jeeves.historical_ensemble import ForecastEnsemblePolicy
from skeleton.jeeves.historical_forecasting import ForecastObservation, ForecastSelectionPolicy, HistoricalSeries
from skeleton.jeeves.historical_regimes import RegimeDetectionPolicy
from skeleton.jeeves.predictive_engine import PredictiveEnginePolicy
from skeleton.jeeves.predictive_regime_routing import (
    PredictiveRegimeRoutingError,
    RegimeAwarePredictiveRouter,
    RegimeRoutePolicy,
    summarize_regime_route,
)


def _series(values: list[float], *, series_id: str = "fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values)
        ),
    )


def _engine_policy() -> PredictiveEnginePolicy:
    return PredictiveEnginePolicy(
        forecast=ForecastSelectionPolicy(
            horizons=(1, 2),
            minimum_training_points=8,
            minimum_origins=4,
            alpha_grid=(0.3, 0.7),
            beta_grid=(0.2, 0.5),
            damping_grid=(0.9, 0.98),
        ),
        autoregression=AutoRegressiveSelectionPolicy(
            orders=(1, 2),
            ridge_grid=(1e-6, 1e-3),
        ),
        ensemble=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.0, 0.25, 0.5, 0.75, 1.0),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
        ),
        conformal=ConformalPolicy(coverage=0.8, minimum_residuals=6),
        regime=RegimeDetectionPolicy(
            minimum_segment_points=6,
            max_candidate_splits=64,
            change_threshold=1.2,
            recent_fraction=0.5,
        ),
    )


def test_stable_history_keeps_full_route() -> None:
    values = [20.0 + 0.35 * index + 0.2 * math.sin(index / 2.0) for index in range(52)]
    router = RegimeAwarePredictiveRouter(
        engine_policy=_engine_policy(),
        route_policy=RegimeRoutePolicy(validation_points=6, minimum_post_break_points=12),
    )

    report = router.evaluate(_series(values, series_id="stable"), horizon=4)

    assert report.selected_route in {"full_history", "post_break"}
    assert report.full_history_score.sample_count == 6
    assert report.final_result.points
    assert report.selection_training_fingerprint
    assert report.validation_fingerprint
    assert report.report_fingerprint


def test_break_detection_uses_only_pre_validation_history() -> None:
    prefix = [10.0 + 0.05 * index for index in range(28)] + [40.0 + 0.1 * index for index in range(18)]
    left = _series(prefix + [42.0, 42.1, 42.2, 42.3, 42.4, 42.5], series_id="left")
    right = _series(prefix + [400.0, -200.0, 800.0, -500.0, 1000.0, -900.0], series_id="right")
    router = RegimeAwarePredictiveRouter(
        engine_policy=_engine_policy(),
        route_policy=RegimeRoutePolicy(
            validation_points=6,
            minimum_post_break_points=10,
            minimum_relative_improvement=0.0,
        ),
    )

    left_report = router.evaluate(left, horizon=3)
    right_report = router.evaluate(right, horizon=3)

    assert left_report.selection_training_fingerprint != right_report.selection_training_fingerprint
    # The series ids differ, so fingerprints differ even with equal pre-validation
    # values. The actual changepoint decision itself must be unaffected by the
    # held-out tail.
    assert (left_report.regime_report is None) == (right_report.regime_report is None)
    if left_report.regime_report is not None and right_report.regime_report is not None:
        assert left_report.regime_report.best.split_index == right_report.regime_report.best.split_index
        assert left_report.regime_report.detected == right_report.regime_report.detected
        assert left_report.regime_report.recent == right_report.regime_report.recent
    assert left_report.validation_fingerprint != right_report.validation_fingerprint


def test_strong_recent_break_produces_post_break_candidate_on_same_holdout() -> None:
    old = [5.0 + 0.05 * index for index in range(30)]
    new = [80.0 + 0.6 * index for index in range(24)]
    router = RegimeAwarePredictiveRouter(
        engine_policy=_engine_policy(),
        route_policy=RegimeRoutePolicy(
            validation_points=6,
            minimum_post_break_points=12,
            minimum_relative_improvement=0.0,
        ),
    )

    report = router.evaluate(_series(old + new, series_id="break"), horizon=3)

    assert report.regime_report is not None
    assert report.regime_report.detected
    assert report.post_break_score is not None
    assert report.post_break_score.sample_count == report.full_history_score.sample_count == 6
    assert report.post_break_score.training_start > 0
    if report.post_break_selected:
        assert report.relative_improvement >= -1e-12
        assert report.selected_training_start == report.post_break_score.training_start


def test_positive_improvement_threshold_can_preserve_full_history() -> None:
    values = [15.0 + 0.2 * index for index in range(30)] + [25.0 + 0.22 * index for index in range(24)]
    router = RegimeAwarePredictiveRouter(
        engine_policy=_engine_policy(),
        route_policy=RegimeRoutePolicy(
            validation_points=6,
            minimum_post_break_points=10,
            minimum_relative_improvement=1.0,
        ),
    )

    report = router.evaluate(_series(values, series_id="strict"), horizon=2)

    assert report.selected_route == "full_history"
    assert report.selected_training_start == 0


def test_route_report_is_deterministic() -> None:
    values = [12.0 + 0.15 * index + math.sin(index / 3.0) for index in range(56)]
    series = _series(values, series_id="deterministic")
    router = RegimeAwarePredictiveRouter(
        engine_policy=_engine_policy(),
        route_policy=RegimeRoutePolicy(validation_points=5, minimum_post_break_points=10),
    )

    left = router.evaluate(series, horizon=3)
    right = router.evaluate(series, horizon=3)

    assert left == right
    assert left.report_fingerprint == right.report_fingerprint


def test_summary_exposes_common_holdout_scores_and_final_route() -> None:
    values = [10.0 + 0.1 * index for index in range(28)] + [35.0 + 0.3 * index for index in range(26)]
    report = RegimeAwarePredictiveRouter(
        engine_policy=_engine_policy(),
        route_policy=RegimeRoutePolicy(validation_points=6, minimum_post_break_points=10),
    ).evaluate(_series(values, series_id="summary"), horizon=3)

    summary = summarize_regime_route(report)

    assert summary["selected_route"] == report.selected_route
    assert summary["full_history"]["sample_count"] == 6
    assert summary["validation_fingerprint"] == report.validation_fingerprint
    assert summary["report_fingerprint"] == report.report_fingerprint


def test_route_policy_and_short_series_fail_closed() -> None:
    with pytest.raises(PredictiveRegimeRoutingError):
        RegimeRoutePolicy(validation_points=0)
    with pytest.raises(PredictiveRegimeRoutingError):
        RegimeRoutePolicy(minimum_post_break_points=2)
    with pytest.raises(PredictiveRegimeRoutingError):
        RegimeRoutePolicy(minimum_relative_improvement=1.1)

    router = RegimeAwarePredictiveRouter(
        engine_policy=_engine_policy(),
        route_policy=RegimeRoutePolicy(validation_points=6),
    )
    with pytest.raises(PredictiveRegimeRoutingError) as exc:
        router.evaluate(_series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], series_id="too-short"), horizon=2)
    assert exc.value.context["reason"] == "insufficient_points_for_validation"
