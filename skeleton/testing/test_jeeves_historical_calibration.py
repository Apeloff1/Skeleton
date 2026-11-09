from __future__ import annotations

import pytest

from skeleton.jeeves.historical_calibration import (
    CalibrationPoint,
    HistoricalCalibrationError,
    HistoricalScoreCalibrator,
    summarize_calibration,
)


def test_calibration_point_exposes_signed_error() -> None:
    point = CalibrationPoint("f1", predicted_score=0.9, realized_score=0.7)
    assert point.error == pytest.approx(-0.2)
    assert point.absolute_error == pytest.approx(0.2)


def test_fit_reports_bias_mae_rmse_and_max_error() -> None:
    report = HistoricalScoreCalibrator.fit(
        [
            CalibrationPoint("f1", 0.8, 0.7),
            CalibrationPoint("f2", 0.6, 0.7),
        ],
        bins=5,
    )
    assert report.mean_bias == pytest.approx(0.0)
    assert report.mean_absolute_error == pytest.approx(0.1)
    assert report.root_mean_squared_error == pytest.approx(0.1)
    assert report.max_absolute_error == pytest.approx(0.1)
    assert report.sample_count == 2


def test_affine_fit_recovers_simple_linear_relationship() -> None:
    report = HistoricalScoreCalibrator.fit(
        [
            CalibrationPoint("f1", 0.2, 0.3),
            CalibrationPoint("f2", 0.4, 0.5),
            CalibrationPoint("f3", 0.6, 0.7),
            CalibrationPoint("f4", 0.8, 0.9),
        ]
    )
    assert report.slope == pytest.approx(1.0)
    assert report.intercept == pytest.approx(0.1)
    assert report.r_squared == pytest.approx(1.0)
    assert report.model.calibrate(0.5) == pytest.approx(0.6)


def test_calibration_clips_predictions_to_unit_interval() -> None:
    report = HistoricalScoreCalibrator.fit(
        [
            CalibrationPoint("f1", 0.2, 0.5),
            CalibrationPoint("f2", 0.4, 0.9),
        ]
    )
    assert report.model.calibrate(1.0) == pytest.approx(1.0)
    assert report.model.calibrate(0.0) >= 0.0


def test_constant_predictions_fall_back_to_bias_only_model() -> None:
    report = HistoricalScoreCalibrator.fit(
        [
            CalibrationPoint("f1", 0.5, 0.6),
            CalibrationPoint("f2", 0.5, 0.8),
        ]
    )
    assert report.slope == pytest.approx(1.0)
    assert report.intercept == pytest.approx(0.2)
    assert report.model.calibrate(0.5) == pytest.approx(0.7)


def test_single_point_fit_preserves_order_with_observed_bias() -> None:
    report = HistoricalScoreCalibrator.fit([CalibrationPoint("f1", 0.8, 0.7)])
    assert report.slope == pytest.approx(1.0)
    assert report.intercept == pytest.approx(-0.1)
    assert report.model.calibrate(0.9) == pytest.approx(0.8)


def test_bins_group_points_by_predicted_score() -> None:
    report = HistoricalScoreCalibrator.fit(
        [
            CalibrationPoint("low-a", 0.1, 0.2),
            CalibrationPoint("low-b", 0.15, 0.25),
            CalibrationPoint("high", 0.9, 0.8),
        ],
        bins=2,
    )
    assert len(report.bins) == 2
    assert report.bins[0].count == 2
    assert report.bins[1].count == 1
    assert report.bins[0].gap == pytest.approx(0.1)
    assert report.bins[1].gap == pytest.approx(-0.1)


def test_duplicate_fold_ids_are_rejected() -> None:
    with pytest.raises(HistoricalCalibrationError) as exc:
        HistoricalScoreCalibrator.fit(
            [
                CalibrationPoint("same", 0.5, 0.5),
                CalibrationPoint("same", 0.6, 0.6),
            ]
        )
    assert exc.value.context["reason"] == "duplicate_fold_id"


def test_empty_calibration_is_rejected() -> None:
    with pytest.raises(HistoricalCalibrationError) as exc:
        HistoricalScoreCalibrator.fit([])
    assert exc.value.context["reason"] == "empty_calibration"


def test_invalid_score_is_rejected() -> None:
    with pytest.raises(HistoricalCalibrationError):
        CalibrationPoint("bad", 1.1, 0.5)


def test_report_fingerprint_is_deterministic() -> None:
    points = [
        CalibrationPoint("f1", 0.2, 0.3),
        CalibrationPoint("f2", 0.8, 0.7),
    ]
    first = HistoricalScoreCalibrator.fit(points, bins=4)
    second = HistoricalScoreCalibrator.fit(points, bins=4)
    assert first.report_fingerprint == second.report_fingerprint


def test_summary_exposes_fit_and_bins() -> None:
    report = HistoricalScoreCalibrator.fit(
        [
            CalibrationPoint("f1", 0.25, 0.30),
            CalibrationPoint("f2", 0.75, 0.70),
        ],
        bins=4,
    )
    summary = summarize_calibration(report)
    assert summary["sample_count"] == 2
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["bins"]