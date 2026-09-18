from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_autoregression import AutoRegressiveSelectionPolicy
from skeleton.jeeves.historical_conformal import ConformalPolicy
from skeleton.jeeves.historical_ensemble import ForecastEnsemblePolicy
from skeleton.jeeves.historical_forecasting import (
    ForecastObservation,
    ForecastSelectionPolicy,
    HistoricalSeries,
)
from skeleton.jeeves.historical_regimes import RegimeDetectionPolicy
from skeleton.jeeves.predictive_engine import (
    JeevesPredictiveEngine,
    PredictiveEngineError,
    PredictiveEnginePolicy,
    summarize_predictive_result,
)


def _series(values: list[float], *, series_id: str = "fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values)
        ),
    )


def _policy(*, require_conformal: bool = False, require_regime: bool = False) -> PredictiveEnginePolicy:
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
            orders=(1, 2, 3),
            ridge_grid=(1e-6, 1e-3),
            max_coefficient_l1=20.0,
        ),
        ensemble=ForecastEnsemblePolicy(
            baseline_weight_grid=(0.0, 0.25, 0.5, 0.75, 1.0),
            minimum_objective_improvement=0.0,
            ensemble_complexity_penalty=0.0,
            require_interior_weight=True,
        ),
        conformal=ConformalPolicy(
            coverage=0.8,
            minimum_residuals=8,
            horizon_growth_exponent=0.5,
        ),
        regime=RegimeDetectionPolicy(
            minimum_segment_points=6,
            max_candidate_splits=64,
            change_threshold=1.5,
        ),
        require_conformal=require_conformal,
        require_regime_diagnostic=require_regime,
    )


def test_predictive_engine_returns_fingerprinted_multi_horizon_forecast() -> None:
    values = [10.0 + 0.8 * index + math.sin(index / 2.0) for index in range(36)]
    series = _series(values)
    engine = JeevesPredictiveEngine(_policy())

    result = engine.evaluate(series, horizon=5)

    assert result.selected_family in {"baseline", "autoregression", "ensemble"}
    assert len(result.points) == 5
    assert [point.horizon for point in result.points] == [1, 2, 3, 4, 5]
    assert all(math.isfinite(point.predicted) for point in result.points)
    assert result.training_fingerprint == series.fingerprint
    assert result.policy_fingerprint
    assert result.result_fingerprint


def test_predictive_engine_is_deterministic() -> None:
    values = [50.0 + 0.4 * index + 2.0 * math.sin(index / 3.0) for index in range(42)]
    series = _series(values, series_id="deterministic")
    engine = JeevesPredictiveEngine(_policy())

    left = engine.evaluate(series, horizon=4)
    right = engine.evaluate(series, horizon=4)

    assert left == right
    assert left.result_fingerprint == right.result_fingerprint


def test_conformal_intervals_use_held_out_residual_evidence() -> None:
    values = [100.0 + 0.5 * index + (-1.0 if index % 3 == 0 else 1.0) for index in range(45)]
    result = JeevesPredictiveEngine(_policy(require_conformal=True)).evaluate(
        _series(values, series_id="conformal"),
        horizon=6,
    )

    assert result.interval_available
    assert result.conformal_status == "calibrated"
    assert result.conformal_band is not None
    assert result.conformal_band.residual_count >= 8
    for point in result.points:
        assert point.lower is not None
        assert point.upper is not None
        assert point.lower <= point.predicted <= point.upper
    widths = [point.upper - point.lower for point in result.points if point.upper is not None and point.lower is not None]
    assert widths == sorted(widths)


def test_short_history_can_return_point_forecast_without_regime_diagnostic() -> None:
    policy = PredictiveEnginePolicy(
        forecast=ForecastSelectionPolicy(
            horizons=(1,),
            minimum_training_points=5,
            minimum_origins=2,
            alpha_grid=(0.5,),
            beta_grid=(0.3,),
            damping_grid=(0.9,),
        ),
        autoregression=AutoRegressiveSelectionPolicy(orders=(1,), ridge_grid=(1e-6,)),
        ensemble=ForecastEnsemblePolicy(baseline_weight_grid=(0.0, 0.5, 1.0)),
        conformal=ConformalPolicy(coverage=0.8, minimum_residuals=20),
        regime=RegimeDetectionPolicy(minimum_segment_points=8),
    )
    result = JeevesPredictiveEngine(policy).evaluate(
        _series([2.0, 2.2, 2.5, 2.8, 3.0, 3.3, 3.5, 3.8], series_id="short"),
        horizon=2,
    )

    assert not result.interval_available
    assert result.conformal_status == "insufficient_residuals"
    assert result.regime_report is None
    assert result.regime_status == "insufficient_points"
    assert all(point.lower is None and point.upper is None for point in result.points)


def test_required_conformal_calibration_fails_closed_when_evidence_is_thin() -> None:
    policy = PredictiveEnginePolicy(
        forecast=ForecastSelectionPolicy(
            horizons=(1,),
            minimum_training_points=5,
            minimum_origins=2,
            alpha_grid=(0.5,),
            beta_grid=(0.3,),
            damping_grid=(0.9,),
        ),
        autoregression=AutoRegressiveSelectionPolicy(orders=(1,), ridge_grid=(1e-6,)),
        ensemble=ForecastEnsemblePolicy(baseline_weight_grid=(0.0, 0.5, 1.0)),
        conformal=ConformalPolicy(coverage=0.9, minimum_residuals=100),
        regime=RegimeDetectionPolicy(minimum_segment_points=4),
        require_conformal=True,
    )
    engine = JeevesPredictiveEngine(policy)

    with pytest.raises(PredictiveEngineError) as exc:
        engine.evaluate(
            _series([float(index) for index in range(14)], series_id="thin-calibration"),
            horizon=2,
        )
    assert exc.value.context["reason"] == "conformal_required"


def test_required_regime_diagnostic_fails_closed_on_short_series() -> None:
    policy = PredictiveEnginePolicy(
        forecast=ForecastSelectionPolicy(
            horizons=(1,),
            minimum_training_points=5,
            minimum_origins=2,
            alpha_grid=(0.5,),
            beta_grid=(0.3,),
            damping_grid=(0.9,),
        ),
        autoregression=AutoRegressiveSelectionPolicy(orders=(1,), ridge_grid=(1e-6,)),
        ensemble=ForecastEnsemblePolicy(baseline_weight_grid=(0.0, 0.5, 1.0)),
        conformal=ConformalPolicy(coverage=0.8, minimum_residuals=2),
        regime=RegimeDetectionPolicy(minimum_segment_points=8),
        require_regime_diagnostic=True,
    )

    with pytest.raises(PredictiveEngineError) as exc:
        JeevesPredictiveEngine(policy).evaluate(
            _series([float(index) for index in range(10)], series_id="thin-regime"),
            horizon=2,
        )
    assert exc.value.context["reason"] == "regime_required"


def test_recent_level_shift_is_reported_but_does_not_silently_rewrite_training() -> None:
    values = [10.0 + 0.05 * index for index in range(30)] + [35.0 + 0.05 * index for index in range(18)]
    series = _series(values, series_id="shift")
    result = JeevesPredictiveEngine(_policy()).evaluate(series, horizon=3)

    assert result.regime_report is not None
    assert result.regime_report.detected
    assert result.training_fingerprint == series.fingerprint
    assert result.regime_report.series_fingerprint == series.fingerprint


def test_summary_exposes_evidence_state_and_not_only_point_predictions() -> None:
    values = [20.0 + 0.2 * index + math.sin(index) for index in range(40)]
    result = JeevesPredictiveEngine(_policy()).evaluate(_series(values, series_id="summary"), horizon=3)

    summary = summarize_predictive_result(result)

    assert summary["selected_family"] == result.selected_family
    assert summary["selected_label"] == result.selected_label
    assert summary["conformal_status"] == result.conformal_status
    assert summary["regime_status"] == result.regime_status
    assert summary["training_fingerprint"] == result.training_fingerprint
    assert summary["result_fingerprint"] == result.result_fingerprint
    assert len(summary["points"]) == 3


def test_horizon_bounds_fail_closed() -> None:
    series = _series([float(index) for index in range(30)], series_id="bounds")
    engine = JeevesPredictiveEngine(_policy())

    with pytest.raises(PredictiveEngineError):
        engine.evaluate(series, horizon=0)
    with pytest.raises(PredictiveEngineError):
        engine.evaluate(series, horizon=257)
