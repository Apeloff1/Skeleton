from __future__ import annotations

import pytest

from skeleton.jeeves.historical_forecasting import ForecastObservation, HistoricalSeries
from skeleton.jeeves.historical_regimes import (
    HistoricalRegimeDetector,
    HistoricalRegimeError,
    RegimeDetectionPolicy,
    summarize_regime_shift,
)


def _series(values: list[float] | tuple[float, ...], *, series_id: str = "regime-fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values, start=1)
        ),
    )


def _policy(**overrides: object) -> RegimeDetectionPolicy:
    values: dict[str, object] = {
        "minimum_segment_points": 6,
        "max_candidate_splits": 128,
        "change_threshold": 0.5,
        "recent_fraction": 0.35,
    }
    values.update(overrides)
    return RegimeDetectionPolicy(**values)  # type: ignore[arg-type]


def test_policy_rejects_segment_size_below_two() -> None:
    with pytest.raises(HistoricalRegimeError) as exc:
        RegimeDetectionPolicy(minimum_segment_points=1)
    assert exc.value.context["reason"] == "invalid_minimum_segment_points"


def test_policy_requires_at_least_one_signal_weight() -> None:
    with pytest.raises(HistoricalRegimeError) as exc:
        RegimeDetectionPolicy(mean_weight=0.0, slope_weight=0.0, variance_weight=0.0)
    assert exc.value.context["reason"] == "zero_signal_weights"


def test_policy_rejects_invalid_recent_fraction() -> None:
    with pytest.raises(HistoricalRegimeError) as exc:
        RegimeDetectionPolicy(recent_fraction=0.0)
    assert exc.value.context["reason"] == "invalid_recent_fraction"


def test_policy_normalizes_signal_weights() -> None:
    policy = RegimeDetectionPolicy(mean_weight=2.0, slope_weight=1.0, variance_weight=1.0)
    weights = policy.normalized_signal_weights
    assert weights == pytest.approx((0.5, 0.25, 0.25))
    assert sum(weights) == pytest.approx(1.0)


def test_detector_requires_two_minimum_segments() -> None:
    detector = HistoricalRegimeDetector(_policy(minimum_segment_points=6))
    with pytest.raises(HistoricalRegimeError) as exc:
        detector.analyze(_series([1.0] * 11))
    assert exc.value.context["reason"] == "insufficient_points"


def test_constant_series_has_no_regime_break() -> None:
    report = HistoricalRegimeDetector(_policy()).analyze(_series([5.0] * 30))
    assert report.detected is False
    assert report.recent is False
    assert report.recommended_training_start == 0
    assert report.best.score == pytest.approx(0.0)


def test_abrupt_mean_shift_is_detected() -> None:
    values = [0.0] * 20 + [10.0] * 20
    report = HistoricalRegimeDetector(
        _policy(mean_weight=1.0, slope_weight=0.0, variance_weight=0.0, change_threshold=0.5)
    ).analyze(_series(values))
    assert report.detected is True
    assert report.best.split_index == 20
    assert report.best.post.mean - report.best.pre.mean == pytest.approx(10.0)
    assert report.best.mean_effect > 0.5


def test_recent_mean_shift_recommends_post_break_training() -> None:
    values = [0.0] * 30 + [10.0] * 12
    detector = HistoricalRegimeDetector(
        _policy(
            mean_weight=1.0,
            slope_weight=0.0,
            variance_weight=0.0,
            change_threshold=0.5,
            recent_fraction=0.35,
        )
    )
    report = detector.analyze(_series(values))
    assert report.detected is True
    assert report.recent is True
    assert report.best.split_index == 30
    assert report.recommended_training_start == 30


def test_old_break_can_be_detected_without_truncation_recommendation() -> None:
    values = [0.0] * 10 + [10.0] * 30
    report = HistoricalRegimeDetector(
        _policy(
            mean_weight=1.0,
            slope_weight=0.0,
            variance_weight=0.0,
            change_threshold=0.5,
            recent_fraction=0.25,
        )
    ).analyze(_series(values))
    assert report.detected is True
    assert report.best.split_index == 10
    assert report.recent is False
    assert report.recommended_training_start == 0


def test_slope_break_is_detected() -> None:
    first = [0.0 for _ in range(20)]
    second = [2.0 * index for index in range(1, 21)]
    report = HistoricalRegimeDetector(
        _policy(mean_weight=0.0, slope_weight=1.0, variance_weight=0.0, change_threshold=0.3)
    ).analyze(_series(first + second))
    assert report.detected is True
    assert report.best.slope_effect > 0.3
    assert report.best.post.slope > report.best.pre.slope


def test_variance_break_is_detected() -> None:
    low = [1.0 if index % 2 == 0 else -1.0 for index in range(20)]
    high = [10.0 if index % 2 == 0 else -10.0 for index in range(20)]
    report = HistoricalRegimeDetector(
        _policy(mean_weight=0.0, slope_weight=0.0, variance_weight=1.0, change_threshold=1.0)
    ).analyze(_series(low + high))
    assert report.detected is True
    assert report.best.variance_effect > 1.0
    assert report.best.post.variance > report.best.pre.variance


def test_high_threshold_can_hold_same_break() -> None:
    values = [0.0] * 20 + [10.0] * 20
    report = HistoricalRegimeDetector(
        _policy(mean_weight=1.0, slope_weight=0.0, variance_weight=0.0, change_threshold=100.0)
    ).analyze(_series(values))
    assert report.detected is False
    assert report.recommended_training_start == 0


def test_candidate_search_respects_bound() -> None:
    values = [float(index % 7) for index in range(120)]
    report = HistoricalRegimeDetector(
        _policy(max_candidate_splits=5)
    ).analyze(_series(values))
    assert report.candidate_count == 5


def test_candidate_search_includes_edge_valid_splits_when_subsampled() -> None:
    values = [0.0] * 90 + [20.0] * 10
    report = HistoricalRegimeDetector(
        _policy(
            minimum_segment_points=6,
            max_candidate_splits=10,
            mean_weight=1.0,
            slope_weight=0.0,
            variance_weight=0.0,
            change_threshold=0.3,
            recent_fraction=0.2,
        )
    ).analyze(_series(values))
    assert report.candidate_count <= 10
    assert report.best.split_index >= 80


def test_report_is_deterministic() -> None:
    series = _series([0.0] * 24 + [7.0] * 12)
    detector = HistoricalRegimeDetector(_policy())
    left = detector.analyze(series)
    right = detector.analyze(series)
    assert left.report_fingerprint == right.report_fingerprint
    assert left.best == right.best


def test_report_fingerprint_changes_with_policy() -> None:
    series = _series([0.0] * 24 + [7.0] * 12)
    left = HistoricalRegimeDetector(_policy(change_threshold=0.4)).analyze(series)
    right = HistoricalRegimeDetector(_policy(change_threshold=0.6)).analyze(series)
    assert left.report_fingerprint != right.report_fingerprint


def test_recommended_series_returns_original_when_no_recent_break() -> None:
    series = _series([3.0] * 30)
    detector = HistoricalRegimeDetector(_policy())
    report = detector.analyze(series)
    assert detector.recommended_series(series, report) is series


def test_recommended_series_truncates_at_recent_break() -> None:
    series = _series([0.0] * 30 + [10.0] * 12)
    detector = HistoricalRegimeDetector(
        _policy(
            mean_weight=1.0,
            slope_weight=0.0,
            variance_weight=0.0,
            change_threshold=0.5,
            recent_fraction=0.35,
        )
    )
    report = detector.analyze(series)
    recommended = detector.recommended_series(series, report)
    assert report.recommended_training_start == 30
    assert recommended.values == tuple([10.0] * 12)
    assert series.values == tuple([0.0] * 30 + [10.0] * 12)


def test_recommended_series_rejects_report_for_other_series() -> None:
    detector = HistoricalRegimeDetector(_policy())
    left = _series([0.0] * 20 + [5.0] * 10, series_id="left")
    right = _series([0.0] * 20 + [6.0] * 10, series_id="right")
    report = detector.analyze(left)
    with pytest.raises(HistoricalRegimeError) as exc:
        detector.recommended_series(right, report)
    assert exc.value.context["reason"] == "series_fingerprint_mismatch"


def test_summary_exposes_break_evidence() -> None:
    series = _series([0.0] * 30 + [10.0] * 12)
    report = HistoricalRegimeDetector(
        _policy(
            mean_weight=1.0,
            slope_weight=0.0,
            variance_weight=0.0,
            change_threshold=0.5,
        )
    ).analyze(series)
    summary = summarize_regime_shift(report)
    assert summary["detected"] == report.detected
    assert summary["recent"] == report.recent
    assert summary["split_index"] == report.best.split_index
    assert summary["mean_effect"] == report.best.mean_effect
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["pre"]["count"] == report.best.pre.count
    assert summary["post"]["count"] == report.best.post.count
