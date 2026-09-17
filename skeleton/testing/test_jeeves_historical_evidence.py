"""Tests for Jeeves calibrated historical evidence construction."""

from __future__ import annotations

import json

import pytest

from skeleton.jeeves.bidirectional_calibration import CalibratedBidirectionalModeLab
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

NOW = 1_000.0
SUBJECT = "jeeves-historical-fixture"


def _series(values=None, *, label="evidence-series", timestamps=None) -> HistoricalSeries:
    data = values if values is not None else [3 + 2 * index for index in range(40)]
    return HistoricalSeries.from_values(data, label=label, timestamps=timestamps)


def _report(series: HistoricalSeries):
    lab = CalibratedBidirectionalModeLab(
        config=WalkForwardConfig(
            min_train_size=8,
            rolling_window=4,
            seasonal_period=4,
            momentum_window=3,
            reversion_window=6,
        ),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
    )
    return lab.evaluate(series)


def test_bridge_builds_one_fact_root_and_derived_features() -> None:
    series = _series()
    report = _report(series)
    bundle = build_historical_evidence(report, series, subject_id=SUBJECT)
    assert bundle.observation.subject_id == SUBJECT
    assert bundle.observation.payload["sample_count"] == 40
    assert bundle.observation.payload["series_label"] == series.label
    assert len(bundle.features) >= 15
    assert all(feature.observation_ids == (bundle.observation.observation_id,) for feature in bundle.features)


def test_bridge_is_deterministic_for_same_report_and_series() -> None:
    series = _series()
    report = _report(series)
    first = build_historical_evidence(report, series, subject_id=SUBJECT)
    second = build_historical_evidence(report, series, subject_id=SUBJECT)
    assert first == second
    assert bundle_manifest(first) == bundle_manifest(second)


def test_series_fingerprint_changes_when_input_changes() -> None:
    first_series = _series()
    second_values = list(first_series.values)
    second_values[20] += 1
    second_series = _series(second_values)
    first = build_historical_evidence(_report(first_series), first_series, subject_id=SUBJECT)
    second = build_historical_evidence(_report(second_series), second_series, subject_id=SUBJECT)
    assert first.series_fingerprint != second.series_fingerprint
    assert first.observation.observation_id != second.observation.observation_id


def test_timestamp_fingerprint_is_present_when_clock_exists() -> None:
    timestamps = [100.0 + index * index + index for index in range(40)]
    series = _series(timestamps=timestamps)
    bundle = build_historical_evidence(_report(series), series, subject_id=SUBJECT)
    assert bundle.observation.payload["has_timestamps"] is True
    assert "timestamp_fingerprint" in bundle.observation.payload
    assert bundle.observation.payload["first_timestamp"] == timestamps[0]
    assert bundle.observation.payload["last_timestamp"] == timestamps[-1]


def test_feature_lookup_exposes_calibration_measurements() -> None:
    series = _series()
    report = _report(series)
    bundle = build_historical_evidence(report, series, subject_id=SUBJECT)
    assert bundle.feature_by_name("selected_mode").value == report.selected_mode.value
    assert bundle.feature_by_name("calibration_fingerprint").value == report.fingerprint
    assert bundle.feature_by_name("rank_correlation").value == pytest.approx(
        report.ranking_agreement.spearman_rank_correlation
    )


def test_unknown_feature_lookup_fails_closed() -> None:
    series = _series()
    bundle = build_historical_evidence(_report(series), series, subject_id=SUBJECT)
    with pytest.raises(LearningEvidenceError) as caught:
        bundle.feature_by_name("does-not-exist")
    assert caught.value.context["reason"] == "unknown_record"


def test_bundle_can_be_explicitly_recorded_into_learning_evidence_store() -> None:
    series = _series()
    bundle = build_historical_evidence(
        _report(series),
        series,
        subject_id=SUBJECT,
        observed_at=NOW,
        clock_version=1,
    )
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
    bundle = build_historical_evidence(_report(series), series, subject_id=SUBJECT)
    assert bundle.features
    assert store.facts() == before


def test_report_series_label_mismatch_is_rejected() -> None:
    original = _series(label="original")
    report = _report(original)
    different = _series(label="different")
    with pytest.raises(HistoricalModeError) as caught:
        build_historical_evidence(report, different, subject_id=SUBJECT)
    assert caught.value.context["reason"] == "report_series_mismatch"


def test_blocked_live_model_source_kind_is_rejected_by_evidence_contract() -> None:
    series = _series()
    report = _report(series)
    with pytest.raises(LearningEvidenceError) as caught:
        build_historical_evidence(
            report,
            series,
            subject_id=SUBJECT,
            source_kind="live-model",
        )
    assert caught.value.context["reason"] == "blocked_source"


def test_manifest_contains_only_identifiers_and_fingerprints() -> None:
    series = _series()
    bundle = build_historical_evidence(_report(series), series, subject_id=SUBJECT)
    manifest = json.loads(bundle_manifest(bundle))
    assert set(manifest) == {
        "observation_id",
        "feature_count",
        "report_fingerprint",
        "series_fingerprint",
    }
    assert "values" not in manifest
    assert manifest["feature_count"] == len(bundle.features)


def test_report_fingerprint_is_carried_through_fact_and_feature_planes() -> None:
    series = _series()
    report = _report(series)
    bundle = build_historical_evidence(report, series, subject_id=SUBJECT)
    assert bundle.report_fingerprint == report.fingerprint
    assert bundle.observation.payload["report_fingerprint"] == report.fingerprint
    assert bundle.feature_by_name("calibration_fingerprint").value == report.fingerprint
