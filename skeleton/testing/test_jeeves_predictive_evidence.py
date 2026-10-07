from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_autoregression import AutoRegressiveSelectionPolicy
from skeleton.jeeves.historical_conformal import ConformalPolicy
from skeleton.jeeves.historical_ensemble import ForecastEnsemblePolicy
from skeleton.jeeves.historical_forecasting import ForecastObservation, ForecastSelectionPolicy, HistoricalSeries
from skeleton.jeeves.historical_regimes import RegimeDetectionPolicy
from skeleton.jeeves.predictive_engine import JeevesPredictiveEngine, PredictiveEnginePolicy
from skeleton.jeeves.predictive_evidence import (
    PredictiveEvidenceBridge,
    PredictiveEvidenceError,
    summarize_predictive_evidence,
)
from skeleton.learning.evidence import LearningEvidenceStore, RecordPlane


NOW = 5_000.0


def _series(values: list[float], *, series_id: str = "fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values)
        ),
    )


def _engine_policy(*, minimum_residuals: int = 6) -> PredictiveEnginePolicy:
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
        conformal=ConformalPolicy(coverage=0.8, minimum_residuals=minimum_residuals),
        regime=RegimeDetectionPolicy(minimum_segment_points=6, max_candidate_splits=64),
    )


def _calibrated_result(series: HistoricalSeries, *, horizon: int = 3):
    return JeevesPredictiveEngine(_engine_policy()).evaluate(series, horizon=horizon)


def test_build_is_side_effect_free_and_predictions_live_on_analysis_plane() -> None:
    series = _series([20.0 + 0.25 * i + math.sin(i / 2.0) for i in range(40)], series_id="evidence")
    result = _calibrated_result(series, horizon=3)
    assert result.conformal_band is not None
    store = LearningEvidenceStore(clock=lambda: NOW, clock_version=1, max_age_seconds=100.0)
    bridge = PredictiveEvidenceBridge()

    bundle = bridge.build(
        series=series,
        result=result,
        subject_id="series:evidence",
        observed_at=NOW,
        clock_version=1,
    )

    assert store.version == 0
    assert store.observations() == ()
    assert store.predictions() == ()
    assert len(bundle.hypotheses) == 3
    assert len(bundle.predictions) == 3
    assert [item.hypothesis_id for item in bundle.predictions] == [
        item.hypothesis_id for item in bundle.hypotheses
    ]

    updates = bridge.persist(store, bundle)

    assert len(updates) == 2 + 2 * len(bundle.predictions)
    assert store.plane_of(bundle.observation.observation_id) is RecordPlane.FACT
    assert store.plane_of(bundle.source_feature.feature_id) is RecordPlane.FACT
    for hypothesis in bundle.hypotheses:
        assert store.plane_of(hypothesis.hypothesis_id) is RecordPlane.ANALYSIS
    for prediction in bundle.predictions:
        assert store.plane_of(prediction.prediction_id) is RecordPlane.ANALYSIS
        assert prediction.confidence == pytest.approx(result.conformal_band.coverage)


def test_same_series_same_ingest_context_reuses_fact_root_across_forecast_horizons() -> None:
    series = _series([30.0 + 0.4 * i + math.sin(i / 3.0) for i in range(42)], series_id="shared-root")
    engine = JeevesPredictiveEngine(_engine_policy())
    bridge = PredictiveEvidenceBridge()
    two = bridge.build(
        series=series,
        result=engine.evaluate(series, horizon=2),
        subject_id="series:shared",
        observed_at=NOW,
        clock_version=1,
    )
    four = bridge.build(
        series=series,
        result=engine.evaluate(series, horizon=4),
        subject_id="series:shared",
        observed_at=NOW,
        clock_version=1,
    )

    assert two.observation == four.observation
    assert two.source_feature == four.source_feature
    assert two.hypothesis != four.hypothesis
    assert len(two.hypotheses) == 2
    assert len(four.hypotheses) == 4
    assert two.predictive_result_fingerprint != four.predictive_result_fingerprint


def test_persist_second_analysis_reuses_existing_identical_fact_root() -> None:
    series = _series([12.0 + 0.2 * i + math.sin(i) for i in range(44)], series_id="reuse")
    engine = JeevesPredictiveEngine(_engine_policy())
    bridge = PredictiveEvidenceBridge()
    store = LearningEvidenceStore(clock=lambda: NOW, clock_version=1, max_age_seconds=100.0)

    first = bridge.build(
        series=series,
        result=engine.evaluate(series, horizon=2),
        subject_id="series:reuse",
        observed_at=NOW,
        clock_version=1,
    )
    second = bridge.build(
        series=series,
        result=engine.evaluate(series, horizon=3),
        subject_id="series:reuse",
        observed_at=NOW,
        clock_version=1,
    )

    first_updates = bridge.persist(store, first)
    second_updates = bridge.persist(store, second)

    assert len(first_updates) == 2 + 2 * len(first.predictions)
    assert len(second_updates) == 2 * len(second.predictions)
    assert len(store.observations()) == 1
    assert len(store.features()) == 1
    assert len(store.hypotheses()) == 5
    assert len(store.predictions()) == 5


def test_different_ingest_context_gets_distinct_fact_root_identity() -> None:
    series = _series([8.0 + 0.1 * i for i in range(40)], series_id="contexts")
    result = _calibrated_result(series, horizon=2)
    bridge = PredictiveEvidenceBridge()

    earlier = bridge.build(
        series=series,
        result=result,
        subject_id="series:contexts",
        observed_at=NOW,
        clock_version=1,
    )
    later = bridge.build(
        series=series,
        result=result,
        subject_id="series:contexts",
        observed_at=NOW + 1.0,
        clock_version=1,
    )

    assert earlier.observation.observation_id != later.observation.observation_id
    assert earlier.source_feature.feature_id != later.source_feature.feature_id
    assert earlier.hypothesis.hypothesis_id != later.hypothesis.hypothesis_id


def test_uncalibrated_prediction_is_not_emitted_as_learning_evidence() -> None:
    series = _series([float(i) for i in range(14)], series_id="uncalibrated")
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
    )
    result = JeevesPredictiveEngine(policy).evaluate(series, horizon=2)
    assert result.conformal_band is None

    with pytest.raises(PredictiveEvidenceError) as exc:
        PredictiveEvidenceBridge().build(
            series=series,
            result=result,
            subject_id="series:uncalibrated",
            observed_at=NOW,
            clock_version=1,
        )
    assert exc.value.context["reason"] == "uncalibrated_prediction"


def test_bundle_rejects_result_from_different_series() -> None:
    left = _series([10.0 + i for i in range(38)], series_id="left")
    right = _series([20.0 + i for i in range(38)], series_id="right")
    result = _calibrated_result(left, horizon=2)

    with pytest.raises(PredictiveEvidenceError) as exc:
        PredictiveEvidenceBridge().build(
            series=right,
            result=result,
            subject_id="series:mismatch",
            observed_at=NOW,
            clock_version=1,
        )
    assert exc.value.context["reason"] == "series_fingerprint_mismatch"


def test_summary_is_stable_and_contains_no_implicit_store_action() -> None:
    series = _series([25.0 + 0.3 * i for i in range(40)], series_id="summary")
    result = _calibrated_result(series, horizon=2)
    bundle = PredictiveEvidenceBridge().build(
        series=series,
        result=result,
        subject_id="series:summary",
        observed_at=NOW,
        clock_version=1,
    )

    summary = summarize_predictive_evidence(bundle)

    assert summary["prediction_count"] == 2
    assert len(summary["hypothesis_ids"]) == 2
    assert summary["hypothesis_id"] == bundle.hypothesis.hypothesis_id
    assert summary["predictive_result_fingerprint"] == result.result_fingerprint
    assert summary["bundle_fingerprint"] == bundle.bundle_fingerprint
