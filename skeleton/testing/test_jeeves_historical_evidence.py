"""Tests for Jeeves calibrated historical evidence construction."""

from __future__ import annotations

import json

import pytest

from skeleton.jeeves.bidirectional_calibration import (
    CalibratedBidirectionalModeLab,
    CrossDirectionConfig,
)
from skeleton.jeeves.historical_evidence import (
    build_historical_evidence,
    bundle_manifest,
)
from skeleton.jeeves.historical_modes import (
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)
from skeleton.learning import LearningEvidenceError, LearningEvidenceStore

NOW = 1_790_000_000.0
SUBJECT = "jeeves-historical-fixture"


def _series(values=None, *, label="evidence-series", timestamps=None) -> HistoricalSeries:
    data = values if values is not None else [3 + 2 * index for index in range(40)]
    return HistoricalSeries.from_values(data, label=label, timestamps=timestamps)


def _report(series: HistoricalSeries, *, calibration=None):
    lab = CalibratedBidirectionalModeLab(
        config=WalkForwardConfig(
            min_train_size=8,
            rolling_window=4,
            seasonal_period=4,
            momentum_window=3,
            reversion_window=6,
        ),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
        calibration=calibration,
    )
    return lab.evaluate(series)


def _build(report, series, **kwargs):
    return build_historical_evidence(
        report,
        series,
        subject_id=SUBJECT,
        observed_at=NOW,
        **kwargs,
    )


def test_bridge_requires_explicit_observation_time() -> None:
    series = _series()
    with pytest.raises(LearningEvidenceError) as caught:
        build_historical_evidence(_report(series), series, subject_id=SUBJECT)
    assert caught.value.context == {
        "reason": "missing_observed_at",
        "field": "observed_at",
    }


def test_bridge_builds_one_fact_root_and_derived_features() -> None:
    series = _series()
    report = _report(series)
    bundle = _build(report, series)
    assert bundle.observation.subject_id == SUBJECT
    assert bundle.observation.payload["sample_count"] == 40
    assert bundle.observation.payload["series_label"] == series.label
    assert "report_fingerprint" not in bundle.observation.payload
    assert len(bundle.features) >= 15
    assert all(feature.observation_ids == (bundle.observation.observation_id,) for feature in bundle.features)


def test_bridge_is_deterministic_for_same_report_and_series() -> None:
    series = _series()
    report = _report(series)
    first = _build(report, series)
    second = _build(report, series)
    assert first == second
    assert bundle_manifest(first) == bundle_manifest(second)


def test_series_fingerprint_changes_when_input_changes() -> None:
    first_series = _series()
    second_values = list(first_series.values)
    second_values[20] += 1
    second_series = _series(second_values)
    first = _build(_report(first_series), first_series)
    second = _build(_report(second_series), second_series)
    assert first.series_fingerprint != second.series_fingerprint
    assert first.observation.observation_id != second.observation.observation_id


def test_fact_root_is_invariant_to_analysis_configuration() -> None:
    series = _series()
    first_report = _report(series)
    second_report = _report(
        series,
        calibration=CrossDirectionConfig(
            top_k=2,
            min_rank_correlation=-1.0,
            min_top_k_overlap=0.0,
        ),
    )
    first = _build(first_report, series)
    second = _build(second_report, series)
    assert first.observation == second.observation
    assert first.series_fingerprint == second.series_fingerprint
    assert first.report_fingerprint != second.report_fingerprint
    assert first.feature_by_name("calibration_fingerprint").value != second.feature_by_name(
        "calibration_fingerprint"
    ).value


def test_timestamp_fingerprint_is_present_when_clock_exists() -> None:
    timestamps = [100.0 + index * index + index for index in range(40)]
    series = _series(timestamps=timestamps)
    bundle = _build(_report(series), series)
    assert bundle.observation.payload["has_timestamps"] is True
    assert "timestamp_fingerprint" in bundle.observation.payload
    assert bundle.observation.payload["first_timestamp"] == timestamps[0]
    assert bundle.observation.payload["last_timestamp"] == timestamps[-1]


def test_feature_lookup_exposes_calibration_measurements() -> None:
    series = _series()
    report = _report(series)
    bundle = _build(report, series)
    assert bundle.feature_by_name("selected_mode").value == report.selected_mode.value
    assert bundle.feature_by_name("calibration_fingerprint").value == report.fingerprint
    assert bundle.feature_by_name("rank_correlation").value == pytest.approx(
        report.ranking_agreement.spearman_rank_correlation
    )


def test_unknown_feature_lookup_fails_closed() -> None:
    series = _series()
    bundle = _build(_report(series), series)
    with pytest.raises(LearningEvidenceError) as caught:
        bundle.feature_by_name("does-not-exist")
    assert caught.value.context["reason"] == "unknown_record"


def test_bundle_can_be_explicitly_recorded_into_learning_evidence_store() -> None:
    series = _series()
    bundle = _build(_report(series), series, clock_version=1)
    store = LearningEvidenceStore(
        clock=lambda: NOW,
        clock_version=1,
        max_age_seconds=60.0,
        max_history=64,
    )
    store.record_observation(bundle.observation)
    for feature in bundle.features:
        store.record_feature(feature)
    facts = store.facts()
    assert bundle.observation.observation_id in facts
    assert all(feature.feature_id in facts for feature in bundle.features)


def test_bridge_itself_does_not_require_or_mutate_a_store() -> None:
    series = _series()
    store = LearningEvidenceStore(clock=lambda: NOW, clock_version=1)
    before = store.facts()
    bundle = _build(_report(series), series)
    assert bundle.features
    assert store.facts() == before


def test_report_series_label_mismatch_is_rejected() -> None:
    original = _series(label="original")
    report = _report(original)
    different = _series(label="different")
    with pytest.raises(HistoricalModeError) as caught:
        build_historical_evidence(report, different, subject_id=SUBJECT, observed_at=NOW)
    assert caught.value.context["reason"] == "report_series_mismatch"


def test_blocked_live_model_source_kind_is_rejected_by_evidence_contract() -> None:
    series = _series()
    report = _report(series)
    with pytest.raises(LearningEvidenceError) as caught:
        build_historical_evidence(
            report,
            series,
            subject_id=SUBJECT,
            observed_at=NOW,
            source_kind="live-model",
        )
    assert caught.value.context["reason"] == "blocked_source"


def test_manifest_contains_only_identifiers_and_fingerprints() -> None:
    series = _series()
    bundle = _build(_report(series), series)
    manifest = json.loads(bundle_manifest(bundle))
    assert set(manifest) == {
        "observation_id",
        "feature_count",
        "report_fingerprint",
        "series_fingerprint",
    }
    assert "values" not in manifest
    assert manifest["feature_count"] == len(bundle.features)


def test_report_fingerprint_stays_on_derived_feature_plane() -> None:
    series = _series()
    report = _report(series)
    bundle = _build(report, series)
    assert bundle.report_fingerprint == report.fingerprint
    assert "report_fingerprint" not in bundle.observation.payload
    assert bundle.feature_by_name("calibration_fingerprint").value == report.fingerprint
