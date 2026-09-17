"""Evidence-plane regressions for Jeeves conformal uncertainty reports."""

from __future__ import annotations

import pytest

from skeleton.jeeves.historical_evidence import (
    build_historical_evidence,
    build_uncertainty_evidence,
)
from skeleton.jeeves.historical_modes import HistoricalSeries, SelectionGate, WalkForwardConfig
from skeleton.jeeves.historical_uncertainty import ConformalConfig, HistoricalUncertaintyModeLab
from skeleton.jeeves.historical_robustness import TemporalJackknifeConfig
from skeleton.learning import LearningEvidenceStore

NOW = 1_000.0
SUBJECT = "uncertainty-evidence"


def _series() -> HistoricalSeries:
    return HistoricalSeries.from_values(
        [5 + 3 * index for index in range(50)],
        label="uncertainty-evidence-series",
    )


def _report(series: HistoricalSeries):
    lab = HistoricalUncertaintyModeLab(
        config=WalkForwardConfig(
            min_train_size=8,
            rolling_window=4,
            seasonal_period=4,
            momentum_window=3,
            reversion_window=6,
        ),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
        jackknife=TemporalJackknifeConfig(
            trim_fraction=0.10,
            max_trim=5,
            min_views=3,
            min_acceptance_rate=0.75,
            min_candidate_support_rate=0.75,
            max_candidate_mae_spread=1.0,
        ),
        conformal=ConformalConfig(min_calibration_folds=8),
    )
    return lab.evaluate(series)


def test_uncertainty_evidence_reuses_same_series_fact_root() -> None:
    series = _series()
    report = _report(series)
    uncertainty = build_uncertainty_evidence(report, series, subject_id=SUBJECT)
    calibrated = build_historical_evidence(
        report.robustness.full,
        series,
        subject_id=SUBJECT,
    )
    assert uncertainty.observation == calibrated.observation
    assert uncertainty.series_fingerprint == calibrated.series_fingerprint
    assert uncertainty.report_fingerprint == report.fingerprint
    assert uncertainty.report_fingerprint != calibrated.report_fingerprint


def test_uncertainty_metrics_remain_on_derived_feature_plane() -> None:
    series = _series()
    report = _report(series)
    bundle = build_uncertainty_evidence(report, series, subject_id=SUBJECT)
    assert "uncertainty_accepted" not in bundle.observation.payload
    assert "uncertainty_fingerprint" not in bundle.observation.payload
    assert bundle.feature_by_name("uncertainty_accepted").value is report.decision.accepted
    assert bundle.feature_by_name("uncertainty_fingerprint").value == report.fingerprint
    assert bundle.feature_by_name("uncertainty_nominal_coverage").value == pytest.approx(0.8)


def test_uncertainty_bundle_contains_base_calibration_and_interval_features() -> None:
    series = _series()
    report = _report(series)
    bundle = build_uncertainty_evidence(report, series, subject_id=SUBJECT)
    assert bundle.feature_by_name("calibration_fingerprint").value == report.robustness.full.fingerprint
    assert bundle.feature_by_name("robustness_fingerprint").value == report.robustness.fingerprint
    assert bundle.feature_by_name("uncertainty_forward_calibrated_folds").value > 0
    assert bundle.feature_by_name("uncertainty_backward_calibrated_folds").value > 0


def test_uncertainty_bundle_can_be_explicitly_persisted() -> None:
    series = _series()
    report = _report(series)
    bundle = build_uncertainty_evidence(
        report,
        series,
        subject_id=SUBJECT,
        observed_at=NOW,
        clock_version=1,
    )
    store = LearningEvidenceStore(
        clock=lambda: NOW,
        clock_version=1,
        max_age_seconds=60.0,
        max_history=128,
    )
    store.record_observation(bundle.observation)
    for feature in bundle.features:
        store.record_feature(feature)
    assert bundle.observation.observation_id in store.facts()
    assert all(feature.feature_id in store.facts() for feature in bundle.features)


def test_building_uncertainty_bundle_has_no_implicit_store_side_effect() -> None:
    series = _series()
    report = _report(series)
    store = LearningEvidenceStore(clock=lambda: NOW, clock_version=1)
    before = store.facts()
    bundle = build_uncertainty_evidence(report, series, subject_id=SUBJECT)
    assert bundle.features
    assert store.facts() == before
