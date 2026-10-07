"""Regression tests for Jeeves leakage-safe historical uncertainty bands."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalModeLab,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)
from skeleton.jeeves.historical_uncertainty import (
    ConformalConfig,
    HistoricalUncertaintyModeLab,
    build_sequential_intervals,
    conformal_radius,
)
from skeleton.jeeves.historical_robustness import TemporalJackknifeConfig


def _series(values=None, *, label="uncertainty") -> HistoricalSeries:
    data = values if values is not None else [5 + 3 * index for index in range(50)]
    return HistoricalSeries.from_values(data, label=label)


def _historical_lab(**overrides) -> HistoricalModeLab:
    values = {
        "min_train_size": 8,
        "rolling_window": 4,
        "seasonal_period": 4,
        "momentum_window": 3,
        "reversion_window": 6,
    }
    values.update(overrides)
    return HistoricalModeLab(config=WalkForwardConfig(**values))


def _lab(*, conformal=None) -> HistoricalUncertaintyModeLab:
    return HistoricalUncertaintyModeLab(
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
        conformal=conformal or ConformalConfig(),
    )


def test_conformal_radius_uses_conservative_finite_sample_rank() -> None:
    errors = [1, 2, 3, 4, 5, 6, 7, 8]
    # ceil((8+1) * .8) = 8, therefore the largest observed residual.
    assert conformal_radius(errors, 0.20) == 8.0


def test_conformal_radius_rejects_empty_residuals() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        conformal_radius([], 0.20)
    assert caught.value.context["reason"] == "insufficient_calibration"


def test_conformal_radius_rejects_negative_or_nonfinite_residual() -> None:
    for bad in (-1.0, float("inf"), float("nan")):
        with pytest.raises(HistoricalModeError):
            conformal_radius([0.0, bad], 0.20)


def test_first_interval_uses_exactly_minimum_prior_folds() -> None:
    report = _historical_lab().evaluate(_series(range(40))).by_mode(HistoricalMode.PERSISTENCE)
    uncertainty = build_sequential_intervals(
        report,
        ConformalConfig(min_calibration_folds=8, calibration_window=32),
    )
    assert uncertainty.intervals[0].calibration_count == 8
    assert uncertainty.intervals[0].target_index == report.folds[8].target_index


def test_current_target_cannot_change_its_own_interval_geometry() -> None:
    report = _historical_lab().evaluate(_series(range(40))).by_mode(HistoricalMode.PERSISTENCE)
    config = ConformalConfig(min_calibration_folds=8)
    original = build_sequential_intervals(report, config)

    folds = list(report.folds)
    target_fold = folds[10]
    changed_actual = target_fold.actual + 10_000.0
    error = target_fold.predicted - changed_actual
    folds[10] = replace(
        target_fold,
        actual=changed_actual,
        absolute_error=abs(error),
        squared_error=error * error,
    )
    changed_report = replace(report, folds=tuple(folds))
    changed = build_sequential_intervals(changed_report, config)

    left = original.intervals[2]  # source fold index 10 after eight-fold warmup
    right = changed.intervals[2]
    assert left.target_index == right.target_index
    assert left.lower == pytest.approx(right.lower)
    assert left.upper == pytest.approx(right.upper)
    assert left.radius == pytest.approx(right.radius)
    assert left.covered != right.covered


def test_changed_target_only_affects_later_calibration() -> None:
    report = _historical_lab().evaluate(_series(range(40))).by_mode(HistoricalMode.PERSISTENCE)
    config = ConformalConfig(min_calibration_folds=8, calibration_window=None)
    original = build_sequential_intervals(report, config)

    folds = list(report.folds)
    target_fold = folds[10]
    changed_actual = target_fold.actual + 10_000.0
    error = target_fold.predicted - changed_actual
    folds[10] = replace(
        target_fold,
        actual=changed_actual,
        absolute_error=abs(error),
        squared_error=error * error,
    )
    changed = build_sequential_intervals(replace(report, folds=tuple(folds)), config)

    assert original.intervals[2].radius == pytest.approx(changed.intervals[2].radius)
    assert changed.intervals[3].radius >= original.intervals[3].radius


def test_calibration_window_caps_residual_history() -> None:
    report = _historical_lab().evaluate(_series(range(60))).by_mode(HistoricalMode.PERSISTENCE)
    config = ConformalConfig(min_calibration_folds=4, calibration_window=6)
    uncertainty = build_sequential_intervals(report, config)
    assert max(interval.calibration_count for interval in uncertainty.intervals) == 6


def test_exact_linear_candidate_has_zero_width_full_coverage() -> None:
    report = _historical_lab().evaluate(_series()).by_mode(HistoricalMode.LINEAR_TREND)
    uncertainty = build_sequential_intervals(report, ConformalConfig(min_calibration_folds=8))
    assert uncertainty.empirical_coverage == pytest.approx(1.0)
    assert uncertainty.average_width == pytest.approx(0.0, abs=1e-10)
    assert all(interval.radius == pytest.approx(0.0, abs=1e-10) for interval in uncertainty.intervals)


def test_interval_geometry_is_symmetric_around_point_prediction() -> None:
    report = _historical_lab().evaluate(_series([0, 2, 1, 5, 2, 8] * 10)).by_mode(
        HistoricalMode.PERSISTENCE
    )
    uncertainty = build_sequential_intervals(report, ConformalConfig(min_calibration_folds=6))
    for interval in uncertainty.intervals:
        assert interval.predicted - interval.lower == pytest.approx(interval.radius)
        assert interval.upper - interval.predicted == pytest.approx(interval.radius)
        assert interval.width == pytest.approx(2.0 * interval.radius)


def test_future_tail_cannot_change_earlier_interval_geometry() -> None:
    common = list(range(1, 35))
    first = _historical_lab().evaluate(_series(common + [35, 36, 37])).by_mode(
        HistoricalMode.LINEAR_TREND
    )
    second = _historical_lab().evaluate(_series(common + [3500, -900, 7000])).by_mode(
        HistoricalMode.LINEAR_TREND
    )
    config = ConformalConfig(min_calibration_folds=8)
    left = build_sequential_intervals(first, config)
    right = build_sequential_intervals(second, config)
    for a, b in zip(left.intervals[:-3], right.intervals[:-3]):
        assert a.target_index == b.target_index
        assert a.lower == pytest.approx(b.lower)
        assert a.upper == pytest.approx(b.upper)
        assert a.radius == pytest.approx(b.radius)


def test_directional_report_counts_calibrated_folds_after_warmup() -> None:
    report = _historical_lab().evaluate(_series(range(40))).by_mode(HistoricalMode.PERSISTENCE)
    config = ConformalConfig(min_calibration_folds=8)
    uncertainty = build_sequential_intervals(report, config)
    assert uncertainty.source_folds == len(report.folds)
    assert uncertainty.calibrated_folds == len(report.folds) - 8


def test_full_uncertainty_lab_accepts_exact_linear_process() -> None:
    report = _lab().evaluate(_series())
    assert report.robustness.decision.accepted is True
    assert report.decision.accepted is True
    assert report.selected_mode is not HistoricalMode.PERSISTENCE
    assert report.forward.empirical_coverage == pytest.approx(1.0)
    assert report.backward.empirical_coverage == pytest.approx(1.0)
    assert report.decision.coverage_gap == pytest.approx(0.0)
    assert report.decision.width_asymmetry == pytest.approx(0.0)
    assert "conformal_uncertainty_gate_passed" in report.decision.reasons


def test_flat_process_stays_on_persistence() -> None:
    report = _lab().evaluate(_series([7] * 50))
    assert report.decision.accepted is False
    assert report.selected_mode is HistoricalMode.PERSISTENCE
    assert "robustness_gate_rejected" in report.decision.reasons


def test_uncertainty_report_is_deterministic() -> None:
    series = _series([1, 4, 2, 7, 3, 9, 5, 12] * 7, label="stable")
    first = _lab().evaluate(series)
    second = _lab().evaluate(series)
    assert first.fingerprint == second.fingerprint
    assert first.forward == second.forward
    assert first.backward == second.backward
    assert first.decision == second.decision


def test_payload_contains_finite_or_nullable_uncertainty_summary() -> None:
    report = _lab().evaluate(_series())
    payload = report.as_payload()
    assert payload["selected_mode"] == report.selected_mode.value
    assert isinstance(payload["uncertainty_accepted"], bool)
    assert payload["nominal_coverage"] == pytest.approx(0.8)
    assert payload["forward_coverage"] is not None
    assert payload["backward_coverage"] is not None
    assert isinstance(payload["fingerprint"], str)


def test_too_large_warmup_yields_explicit_insufficient_calibration_reasons() -> None:
    conformal = ConformalConfig(
        min_calibration_folds=100,
        calibration_window=None,
        min_empirical_coverage=0.0,
    )
    report = _lab(conformal=conformal).evaluate(_series())
    assert report.decision.accepted is False
    assert report.forward.empirical_coverage is None
    assert report.backward.empirical_coverage is None
    assert "insufficient_forward_calibration" in report.decision.reasons
    assert "insufficient_backward_calibration" in report.decision.reasons


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"alpha": 0.0}, "alpha"),
        ({"alpha": 1.0}, "alpha"),
        ({"min_calibration_folds": 0}, "min_calibration_folds"),
        ({"calibration_window": 0}, "calibration_window"),
        ({"min_empirical_coverage": -0.1}, "min_empirical_coverage"),
        ({"max_direction_coverage_gap": 1.1}, "max_direction_coverage_gap"),
        ({"max_direction_width_asymmetry": -0.1}, "max_direction_width_asymmetry"),
    ],
)
def test_invalid_conformal_config_is_rejected(kwargs: dict, field: str) -> None:
    with pytest.raises(HistoricalModeError) as caught:
        ConformalConfig(**kwargs)
    assert caught.value.context["reason"] == "invalid_conformal_config"
    assert caught.value.context["field"] == field


def test_calibration_window_cannot_be_smaller_than_warmup() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        ConformalConfig(min_calibration_folds=8, calibration_window=4)
    assert caught.value.context["reason"] == "invalid_conformal_config"
    assert caught.value.context["field"] == "calibration_window"
