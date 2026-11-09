from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_autoregression import AutoRegressiveSelectionPolicy
from skeleton.jeeves.historical_conformal import ConformalPolicy
from skeleton.jeeves.historical_ensemble import ForecastEnsemblePolicy
from skeleton.jeeves.historical_forecasting import ForecastObservation, ForecastSelectionPolicy, HistoricalSeries
from skeleton.jeeves.historical_regimes import RegimeDetectionPolicy
from skeleton.jeeves.historical_seasonal import SeasonalSelectionPolicy
from skeleton.jeeves.predictive_engine import PredictiveEnginePolicy
from skeleton.jeeves.predictive_seasonal import (
    SeasonalAwarePredictiveEngine,
    SeasonalPredictiveError,
    SeasonalPromotionPolicy,
    summarize_seasonal_challenge,
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
        conformal=ConformalPolicy(coverage=0.8, minimum_residuals=8),
        regime=RegimeDetectionPolicy(minimum_segment_points=6, max_candidate_splits=64),
    )


def _seasonal_policy(*periods: int) -> SeasonalSelectionPolicy:
    return SeasonalSelectionPolicy(
        periods=periods,
        alpha_grid=(0.3, 0.7),
        beta_grid=(0.2,),
        gamma_grid=(0.2, 0.6),
        damping_grid=(0.9,),
        complexity_weight=0.001,
    )


def test_exact_periodic_signal_promotes_seasonal_route() -> None:
    pattern = [10.0, 25.0, 5.0, 18.0]
    series = _series(pattern * 14, series_id="periodic")
    engine = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(4),
        promotion_policy=SeasonalPromotionPolicy(
            minimum_relative_improvement=0.01,
            max_horizon_normalized_mae_regression=0.0,
        ),
    )

    report = engine.evaluate(series, horizon=6)

    assert report.seasonal_selected
    assert report.final_result.selected_family == "seasonal"
    assert "period=4" in report.final_result.selected_label
    assert report.seasonal_score is not None
    assert report.nonseasonal_score is not None
    assert report.seasonal_score.objective < report.nonseasonal_score.objective
    assert report.horizon_regressions == ()


def test_seasonal_comparison_uses_exact_same_origins_and_horizons() -> None:
    values = [30.0 + 0.2 * index + 5.0 * math.sin(index * math.pi / 2.0) for index in range(60)]
    report = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(4, 6),
    ).evaluate(_series(values, series_id="common"), horizon=3)

    assert report.nonseasonal_score is not None
    assert report.seasonal_score is not None
    assert report.nonseasonal_score.common_origin_start == report.seasonal_score.common_origin_start
    assert report.nonseasonal_score.origin_count == report.seasonal_score.origin_count
    assert [item.horizon for item in report.nonseasonal_score.horizons] == [
        item.horizon for item in report.seasonal_score.horizons
    ]
    assert [item.sample_count for item in report.nonseasonal_score.horizons] == [
        item.sample_count for item in report.seasonal_score.horizons
    ]


def test_strict_improvement_threshold_preserves_nonseasonal_route() -> None:
    values = [50.0 + 0.7 * index for index in range(56)]
    report = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(4),
        promotion_policy=SeasonalPromotionPolicy(minimum_relative_improvement=1.0),
    ).evaluate(_series(values, series_id="trend"), horizon=4)

    assert not report.seasonal_selected
    assert report.final_result == report.nonseasonal_result
    assert "insufficient_improvement" in report.reasons


def test_selected_seasonal_route_recalibrates_intervals_from_seasonal_residuals() -> None:
    pattern = [5.0, 20.0, 8.0, 16.0]
    values = [pattern[index % 4] + (0.4 if index % 7 == 0 else 0.0) for index in range(64)]
    report = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(4),
        promotion_policy=SeasonalPromotionPolicy(minimum_relative_improvement=0.0),
    ).evaluate(_series(values, series_id="intervals"), horizon=5)

    if report.seasonal_selected:
        assert report.final_result.conformal_band is not None
        assert report.final_result.conformal_status == "calibrated"
        for point in report.final_result.points:
            assert point.lower is not None
            assert point.upper is not None
            assert point.lower <= point.predicted <= point.upper


def test_short_history_falls_back_without_fabricating_seasonal_evidence() -> None:
    values = [10.0 + 0.5 * index for index in range(18)]
    report = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(12),
        promotion_policy=SeasonalPromotionPolicy(require_seasonal_evaluation=False),
    ).evaluate(_series(values, series_id="short"), horizon=2)

    assert not report.seasonal_selected
    assert report.seasonal_tournament is None
    assert report.seasonal_score is None
    assert report.nonseasonal_score is None
    assert report.final_result == report.nonseasonal_result
    assert report.reasons


def test_required_seasonal_evaluation_fails_closed_when_history_is_too_short() -> None:
    values = [10.0 + 0.5 * index for index in range(18)]
    engine = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(12),
        promotion_policy=SeasonalPromotionPolicy(require_seasonal_evaluation=True),
    )

    with pytest.raises(SeasonalPredictiveError) as exc:
        engine.evaluate(_series(values, series_id="required"), horizon=2)
    assert exc.value.context["reason"] == "seasonal_required"


def test_seasonal_challenge_is_deterministic() -> None:
    values = [20.0 + 0.1 * index + 4.0 * math.sin(index * math.pi / 2.0) for index in range(60)]
    series = _series(values, series_id="deterministic")
    engine = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(4),
    )

    left = engine.evaluate(series, horizon=3)
    right = engine.evaluate(series, horizon=3)

    assert left == right
    assert left.report_fingerprint == right.report_fingerprint


def test_summary_exposes_challenge_decision_and_common_objectives() -> None:
    values = [12.0, 18.0, 9.0, 15.0] * 14
    report = SeasonalAwarePredictiveEngine(
        engine_policy=_engine_policy(),
        seasonal_policy=_seasonal_policy(4),
        promotion_policy=SeasonalPromotionPolicy(minimum_relative_improvement=0.0),
    ).evaluate(_series(values, series_id="summary"), horizon=3)

    summary = summarize_seasonal_challenge(report)

    assert summary["seasonal_selected"] == report.seasonal_selected
    assert summary["final_family"] == report.final_result.selected_family
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["nonseasonal_objective"] is not None
    assert summary["seasonal_objective"] is not None


def test_promotion_policy_rejects_invalid_values() -> None:
    with pytest.raises(SeasonalPredictiveError):
        SeasonalPromotionPolicy(minimum_relative_improvement=-0.1)
    with pytest.raises(SeasonalPredictiveError):
        SeasonalPromotionPolicy(max_horizon_normalized_mae_regression=1.1)
    with pytest.raises(SeasonalPredictiveError):
        SeasonalPromotionPolicy(require_seasonal_evaluation=1)  # type: ignore[arg-type]
