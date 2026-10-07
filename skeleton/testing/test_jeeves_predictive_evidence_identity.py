from __future__ import annotations

from types import SimpleNamespace

from skeleton.jeeves.historical_forecasting import ForecastObservation, HistoricalSeries
from skeleton.jeeves.predictive_engine import PredictivePoint, PredictiveResult
from skeleton.jeeves.predictive_evidence import PredictiveEvidenceBridge
from skeleton.learning.evidence import LearningEvidenceStore


NOW = 9_000.0


def _series() -> HistoricalSeries:
    return HistoricalSeries(
        series_id="identity-fixture",
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=10.0 + float(index))
            for index in range(8)
        ),
    )


def _result(series: HistoricalSeries) -> PredictiveResult:
    return PredictiveResult(
        selected_family="baseline",
        selected_label="last_value",
        selected_objective=0.1,
        points=(
            PredictivePoint(horizon=1, predicted=18.0, lower=17.0, upper=19.0),
            PredictivePoint(horizon=2, predicted=18.5, lower=17.0, upper=20.0),
        ),
        ensemble_report=None,  # type: ignore[arg-type]
        conformal_band=SimpleNamespace(coverage=0.8),  # type: ignore[arg-type]
        conformal_status="calibrated",
        regime_report=None,
        regime_status="stable",
        training_fingerprint=series.fingerprint,
        policy_fingerprint="policy-fingerprint",
        result_fingerprint="result-fingerprint-shared-across-subjects",
    )


def test_same_predictive_result_for_different_subjects_has_distinct_analysis_identity() -> None:
    series = _series()
    result = _result(series)
    bridge = PredictiveEvidenceBridge()

    left = bridge.build(
        series=series,
        result=result,
        subject_id="subject:left",
        observed_at=NOW,
        clock_version=1,
    )
    right = bridge.build(
        series=series,
        result=result,
        subject_id="subject:right",
        observed_at=NOW,
        clock_version=1,
    )

    assert left.observation.observation_id != right.observation.observation_id
    assert left.source_feature.feature_id != right.source_feature.feature_id
    assert {item.hypothesis_id for item in left.hypotheses}.isdisjoint(
        {item.hypothesis_id for item in right.hypotheses}
    )
    assert {item.prediction_id for item in left.predictions}.isdisjoint(
        {item.prediction_id for item in right.predictions}
    )
    assert {item.channel for item in left.predictions}.isdisjoint(
        {item.channel for item in right.predictions}
    )
    assert left.bundle_fingerprint != right.bundle_fingerprint


def test_each_horizon_has_distinct_hypothesis_and_calibration_channel() -> None:
    series = _series()
    bundle = PredictiveEvidenceBridge().build(
        series=series,
        result=_result(series),
        subject_id="subject:horizons",
        observed_at=NOW,
        clock_version=1,
    )

    assert len(bundle.hypotheses) == 2
    assert len({item.hypothesis_id for item in bundle.hypotheses}) == 2
    assert len({item.channel for item in bundle.predictions}) == 2
    assert [item.hypothesis_id for item in bundle.predictions] == [
        item.hypothesis_id for item in bundle.hypotheses
    ]


def test_cross_subject_bundles_persist_into_one_global_store_without_id_collision() -> None:
    series = _series()
    result = _result(series)
    bridge = PredictiveEvidenceBridge()
    store = LearningEvidenceStore(
        clock=lambda: NOW,
        clock_version=1,
        max_age_seconds=100.0,
    )

    left = bridge.build(
        series=series,
        result=result,
        subject_id="subject:left",
        observed_at=NOW,
        clock_version=1,
    )
    right = bridge.build(
        series=series,
        result=result,
        subject_id="subject:right",
        observed_at=NOW,
        clock_version=1,
    )

    left_updates = bridge.persist(store, left)
    right_updates = bridge.persist(store, right)

    assert len(left_updates) == 2 + 2 * len(left.predictions)
    assert len(right_updates) == 2 + 2 * len(right.predictions)
    assert len(store.observations()) == 2
    assert len(store.features()) == 2
    assert len(store.hypotheses()) == 4
    assert len(store.predictions()) == 4


def test_same_context_and_result_remain_deterministic() -> None:
    series = _series()
    result = _result(series)
    bridge = PredictiveEvidenceBridge()

    first = bridge.build(
        series=series,
        result=result,
        subject_id="subject:stable",
        observed_at=NOW,
        clock_version=1,
    )
    second = bridge.build(
        series=series,
        result=result,
        subject_id="subject:stable",
        observed_at=NOW,
        clock_version=1,
    )

    assert first == second
    assert first.bundle_fingerprint == second.bundle_fingerprint


def test_same_subject_new_observation_context_gets_new_analysis_namespace() -> None:
    series = _series()
    result = _result(series)
    bridge = PredictiveEvidenceBridge()

    earlier = bridge.build(
        series=series,
        result=result,
        subject_id="subject:stable",
        observed_at=NOW,
        clock_version=1,
    )
    later = bridge.build(
        series=series,
        result=result,
        subject_id="subject:stable",
        observed_at=NOW + 1.0,
        clock_version=1,
    )

    assert earlier.observation.observation_id != later.observation.observation_id
    assert {item.hypothesis_id for item in earlier.hypotheses}.isdisjoint(
        {item.hypothesis_id for item in later.hypotheses}
    )
    assert {item.prediction_id for item in earlier.predictions}.isdisjoint(
        {item.prediction_id for item in later.predictions}
    )
    assert {item.channel for item in earlier.predictions}.isdisjoint(
        {item.channel for item in later.predictions}
    )
