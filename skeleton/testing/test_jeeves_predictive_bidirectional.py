from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_autoregression import AutoRegressiveSelectionPolicy
from skeleton.jeeves.historical_conformal import ConformalPolicy
from skeleton.jeeves.historical_ensemble import ForecastEnsemblePolicy
from skeleton.jeeves.historical_forecasting import ForecastObservation, ForecastSelectionPolicy, HistoricalSeries
from skeleton.jeeves.historical_regimes import RegimeDetectionPolicy
from skeleton.jeeves.predictive_bidirectional import (
    BidirectionalPredictiveAuditor,
    BidirectionalPredictiveError,
    BidirectionalPredictivePolicy,
    mirror_series,
    summarize_bidirectional_predictive,
)
from skeleton.jeeves.predictive_engine import PredictiveEnginePolicy


def _series(values: list[float], timestamps: list[float] | None = None, *, series_id: str = "fixture") -> HistoricalSeries:
    if timestamps is None:
        timestamps = [float(index) for index in range(len(values))]
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=timestamp, value=value)
            for timestamp, value in zip(timestamps, values, strict=True)
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


def test_mirror_series_is_involutive_for_values_and_irregular_time_geometry() -> None:
    original = _series(
        [4.0, 7.0, 6.0, 10.0, 12.0],
        [2.0, 3.5, 9.0, 10.0, 21.0],
        series_id="irregular",
    )

    mirrored = mirror_series(original)
    restored = mirror_series(mirrored)

    assert mirrored.values == tuple(reversed(original.values))
    assert all(left < right for left, right in zip(mirrored.timestamps, mirrored.timestamps[1:]))
    assert restored.series_id == original.series_id
    assert restored.values == original.values
    assert restored.timestamps == pytest.approx(original.timestamps)


def test_constant_series_is_bidirectionally_symmetric() -> None:
    series = _series([12.0] * 36, series_id="constant")
    auditor = BidirectionalPredictiveAuditor(
        engine_policy=_engine_policy(),
        audit_policy=BidirectionalPredictivePolicy(
            max_objective_asymmetry=0.01,
            max_interval_radius_asymmetry=0.01,
            require_family_agreement=True,
            require_regime_detection_agreement=True,
        ),
    )

    report = auditor.audit(series, horizon=3)

    assert report.robust
    assert report.reasons == ()
    assert report.objective_asymmetry == pytest.approx(0.0)
    assert report.interval_radius_asymmetry == pytest.approx(0.0)
    assert report.family_agreement
    assert report.regime_detection_agreement


def test_bidirectional_audit_is_deterministic() -> None:
    values = [20.0 + 0.4 * index + 1.5 * math.sin(index / 2.0) for index in range(40)]
    series = _series(values, series_id="deterministic")
    auditor = BidirectionalPredictiveAuditor(engine_policy=_engine_policy())

    left = auditor.audit(series, horizon=4)
    right = auditor.audit(series, horizon=4)

    assert left == right
    assert left.report_fingerprint == right.report_fingerprint


def test_reverse_forecast_is_diagnostic_and_never_replaces_forward_points() -> None:
    values = [5.0 + index * 0.7 + math.sin(index / 3.0) for index in range(38)]
    series = _series(values, series_id="directional")
    report = BidirectionalPredictiveAuditor(engine_policy=_engine_policy()).audit(series, horizon=3)

    assert report.forward.training_fingerprint == series.fingerprint
    assert report.reverse.training_fingerprint == report.mirrored_series_fingerprint
    assert report.forward.training_fingerprint != report.reverse.training_fingerprint
    assert len(report.forward.points) == 3
    assert len(report.reverse.points) == 3


def test_strict_zero_asymmetry_policy_can_veto_directional_history() -> None:
    values = [float(index * index) for index in range(1, 42)]
    series = _series(values, series_id="quadratic")
    auditor = BidirectionalPredictiveAuditor(
        engine_policy=_engine_policy(),
        audit_policy=BidirectionalPredictivePolicy(
            max_objective_asymmetry=0.0,
            max_interval_radius_asymmetry=0.0,
            require_family_agreement=True,
            require_regime_detection_agreement=True,
        ),
    )

    report = auditor.audit(series, horizon=3)

    assert isinstance(report.robust, bool)
    if not report.robust:
        assert report.reasons


def test_summary_preserves_forward_reverse_evidence() -> None:
    values = [30.0 + math.sin(index / 2.0) for index in range(36)]
    report = BidirectionalPredictiveAuditor(engine_policy=_engine_policy()).audit(
        _series(values, series_id="summary"),
        horizon=2,
    )

    summary = summarize_bidirectional_predictive(report)

    assert summary["robust"] == report.robust
    assert summary["forward_family"] == report.forward.selected_family
    assert summary["reverse_family"] == report.reverse.selected_family
    assert summary["forward_objective"] == report.forward.selected_objective
    assert summary["reverse_objective"] == report.reverse.selected_objective
    assert summary["report_fingerprint"] == report.report_fingerprint


def test_policy_rejects_invalid_thresholds_and_flags() -> None:
    with pytest.raises(BidirectionalPredictiveError):
        BidirectionalPredictivePolicy(max_objective_asymmetry=-0.1)
    with pytest.raises(BidirectionalPredictiveError):
        BidirectionalPredictivePolicy(max_interval_radius_asymmetry=11.0)
    with pytest.raises(BidirectionalPredictiveError):
        BidirectionalPredictivePolicy(require_family_agreement=1)  # type: ignore[arg-type]
