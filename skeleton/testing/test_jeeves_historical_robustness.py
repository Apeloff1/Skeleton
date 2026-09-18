"""Regression tests for Jeeves temporal jackknife robustness validation."""

from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)
from skeleton.jeeves.historical_robustness import (
    TemporalJackknifeConfig,
    TemporalJackknifeModeLab,
    TemporalViewKind,
)


def _series(values=None, *, label="jackknife", timestamps=None) -> HistoricalSeries:
    data = values if values is not None else [5 + 3 * index for index in range(40)]
    return HistoricalSeries.from_values(data, label=label, timestamps=timestamps)


def _lab(*, jackknife=None, **config_overrides) -> TemporalJackknifeModeLab:
    values = {
        "min_train_size": 8,
        "rolling_window": 4,
        "seasonal_period": 4,
        "momentum_window": 3,
        "reversion_window": 6,
        "ensemble_history": 5,
        "ensemble_top_k": 3,
    }
    values.update(config_overrides)
    return TemporalJackknifeModeLab(
        config=WalkForwardConfig(**values),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
        jackknife=jackknife or TemporalJackknifeConfig(),
    )


def test_exact_linear_process_survives_all_default_temporal_views() -> None:
    report = _lab().evaluate(_series())
    assert report.decision.accepted is True
    assert report.selected_mode is not HistoricalMode.PERSISTENCE
    assert report.decision.total_views == 4
    assert report.decision.accepted_views == 4
    assert report.decision.candidate_supported_views == 4
    assert report.decision.candidate_mae_spread == pytest.approx(0.0, abs=1e-10)
    assert "temporal_jackknife_passed" in report.decision.reasons


def test_flat_process_remains_fail_closed() -> None:
    report = _lab().evaluate(_series([7] * 40))
    assert report.decision.accepted is False
    assert report.selected_mode is HistoricalMode.PERSISTENCE
    assert "full_calibration_rejected" in report.decision.reasons


def test_default_view_geometry_uses_deterministic_ten_percent_trim() -> None:
    report = _lab().evaluate(_series())
    geometry = {view.kind: (view.start, view.stop) for view in report.views}
    assert geometry == {
        TemporalViewKind.FULL: (0, 40),
        TemporalViewKind.TRIM_LEFT: (4, 40),
        TemporalViewKind.TRIM_RIGHT: (0, 36),
        TemporalViewKind.TRIM_BOTH: (4, 36),
    }


def test_max_trim_caps_large_fraction() -> None:
    jackknife = TemporalJackknifeConfig(trim_fraction=0.4, max_trim=3)
    report = _lab(jackknife=jackknife).evaluate(_series())
    geometry = {view.kind: (view.start, view.stop) for view in report.views}
    assert geometry[TemporalViewKind.TRIM_LEFT] == (3, 40)
    assert geometry[TemporalViewKind.TRIM_RIGHT] == (0, 37)
    assert geometry[TemporalViewKind.TRIM_BOTH] == (3, 37)


def test_full_view_preserves_original_series_label() -> None:
    series = _series(label="original-label")
    report = _lab().evaluate(series)
    assert report.full.base.forward.report.series_label == "original-label"


def test_trimmed_views_have_explicit_distinct_labels() -> None:
    report = _lab().evaluate(_series(label="root"))
    for view in report.views:
        label = view.report.base.forward.report.series_label
        if view.kind is TemporalViewKind.FULL:
            assert label == "root"
        else:
            assert label == f"root::jackknife-{view.kind.value}"


def test_irregular_timestamps_are_sliced_without_retiming() -> None:
    timestamps = []
    cursor = 100.0
    for index in range(40):
        cursor += 1 + (index % 5)
        timestamps.append(cursor)
    report = _lab().evaluate(_series(timestamps=timestamps))
    left = report.by_view(TemporalViewKind.TRIM_LEFT)
    assert left.start == 4
    assert left.report.base.forward.report.series_label.endswith("trim_left")
    assert left.sample_count == 36


def test_acceptance_and_support_rates_are_bounded() -> None:
    report = _lab().evaluate(_series([0, 3, 1, 6, 2, 12, 5, 7, 20, 4] * 5))
    assert 0.0 <= report.decision.acceptance_rate <= 1.0
    assert 0.0 <= report.decision.candidate_support_rate <= 1.0
    assert report.decision.candidate_supported_views <= report.decision.accepted_views


def test_candidate_mae_spread_is_finite() -> None:
    report = _lab().evaluate(_series([0, 3, 1, 6, 2, 12, 5, 7, 20, 4] * 5))
    assert math.isfinite(report.decision.candidate_mae_spread)
    assert report.decision.candidate_mae_spread >= 0.0


def test_report_is_deterministic() -> None:
    series = _series([1, 4, 2, 7, 3, 9, 5, 12] * 6, label="stable")
    first = _lab().evaluate(series)
    second = _lab().evaluate(series)
    assert first.fingerprint == second.fingerprint
    assert first.views == second.views
    assert first.decision == second.decision


def test_fingerprint_changes_when_history_changes() -> None:
    values = list(range(40))
    first = _lab().evaluate(_series(values, label="stable"))
    values[20] += 50
    second = _lab().evaluate(_series(values, label="stable"))
    assert first.fingerprint != second.fingerprint


def test_shorter_valid_history_can_fail_minimum_view_count_without_crashing() -> None:
    jackknife = TemporalJackknifeConfig(
        trim_fraction=0.4,
        max_trim=4,
        min_views=3,
        min_acceptance_rate=0.0,
        min_candidate_support_rate=0.0,
        max_candidate_mae_spread=100.0,
    )
    lab = TemporalJackknifeModeLab(
        config=WalkForwardConfig(min_train_size=8),
        gate=SelectionGate(min_folds=1, min_relative_improvement=0.0),
        jackknife=jackknife,
    )
    report = lab.evaluate(_series(list(range(12))))
    assert report.decision.total_views < 3
    assert report.decision.accepted is False
    assert "insufficient_temporal_views" in report.decision.reasons


def test_series_too_short_even_for_full_view_is_rejected() -> None:
    lab = TemporalJackknifeModeLab(config=WalkForwardConfig(min_train_size=8))
    with pytest.raises(HistoricalModeError) as caught:
        lab.evaluate(_series(list(range(8))))
    assert caught.value.context["reason"] == "insufficient_history"


def test_payload_contains_robustness_summary() -> None:
    report = _lab().evaluate(_series())
    payload = report.as_payload()
    assert payload["selected_mode"] == report.selected_mode.value
    assert isinstance(payload["jackknife_accepted"], bool)
    assert payload["total_views"] == len(report.views)
    assert 0.0 <= payload["acceptance_rate"] <= 1.0
    assert isinstance(payload["fingerprint"], str)


def test_unknown_view_lookup_is_rejected_when_view_was_not_constructed() -> None:
    jackknife = TemporalJackknifeConfig(
        trim_fraction=0.4,
        max_trim=4,
        min_views=1,
        min_acceptance_rate=0.0,
        min_candidate_support_rate=0.0,
        max_candidate_mae_spread=100.0,
    )
    lab = TemporalJackknifeModeLab(
        config=WalkForwardConfig(min_train_size=8),
        gate=SelectionGate(min_folds=1, min_relative_improvement=0.0),
        jackknife=jackknife,
    )
    report = lab.evaluate(_series(list(range(12))))
    with pytest.raises(HistoricalModeError) as caught:
        report.by_view(TemporalViewKind.TRIM_BOTH)
    assert caught.value.context["reason"] == "unknown_temporal_view"


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"trim_fraction": 0.0}, "trim_fraction"),
        ({"trim_fraction": 0.5}, "trim_fraction"),
        ({"max_trim": 0}, "max_trim"),
        ({"min_views": 0}, "min_views"),
        ({"min_views": 5}, "min_views"),
        ({"min_acceptance_rate": -0.1}, "min_acceptance_rate"),
        ({"min_candidate_support_rate": 1.1}, "min_candidate_support_rate"),
        ({"max_candidate_mae_spread": -0.1}, "max_candidate_mae_spread"),
    ],
)
def test_invalid_jackknife_gate_is_rejected(kwargs: dict, field: str) -> None:
    with pytest.raises(HistoricalModeError) as caught:
        TemporalJackknifeConfig(**kwargs)
    assert caught.value.context["reason"] == "invalid_jackknife_gate"
    assert caught.value.context["field"] == field
