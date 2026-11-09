"""Regression tests for Jeeves' bidirectional historical-mode laboratory."""

from __future__ import annotations

import math

import pytest

from skeleton.jeeves.bidirectional_modes import (
    BidirectionalConfig,
    BidirectionalModeLab,
    TemporalDirection,
    reverse_series,
)
from skeleton.jeeves.historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)


def _series(values, *, timestamps=None, label="fixture") -> HistoricalSeries:
    return HistoricalSeries.from_values(values, timestamps=timestamps, label=label)


def _lab(**overrides) -> BidirectionalModeLab:
    values = {
        "min_train_size": 8,
        "rolling_window": 4,
        "seasonal_period": 4,
        "momentum_window": 3,
        "reversion_window": 6,
        "ensemble_history": 5,
        "ensemble_top_k": 3,
    }
    values.update(overrides)
    return BidirectionalModeLab(
        config=WalkForwardConfig(**values),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=0.75, max_direction_rank=4),
    )


def test_reverse_series_reverses_values_exactly() -> None:
    reversed_series = reverse_series(_series([1, 2, 3, 4], label="x"))
    assert reversed_series.values == (4.0, 3.0, 2.0, 1.0)
    assert reversed_series.label == "x::backward"


def test_reverse_series_mirrors_irregular_timestamps_monotonically() -> None:
    reversed_series = reverse_series(
        _series([10, 20, 30, 40], timestamps=[100, 101, 105, 112])
    )
    assert reversed_series.timestamps == (100.0, 107.0, 111.0, 112.0)
    assert all(
        right > left
        for left, right in zip(reversed_series.timestamps, reversed_series.timestamps[1:])
    )


def test_reverse_series_is_value_and_clock_involution() -> None:
    original = _series([10, 20, 30, 40], timestamps=[100, 101, 105, 112])
    restored = reverse_series(reverse_series(original))
    assert restored.values == original.values
    assert restored.timestamps == original.timestamps


def test_backward_direction_is_a_real_walk_forward_over_reversed_history() -> None:
    directional = _lab().evaluate_direction(_series(range(1, 31)), TemporalDirection.BACKWARD)
    for mode_report in directional.report.reports:
        for fold in mode_report.folds:
            assert fold.target_index > fold.train_end
            assert fold.target_index - fold.train_end == 1


def test_backward_first_folds_ignore_unseen_original_prefix() -> None:
    common_tail = list(range(10, 40))
    first = _lab().evaluate_direction(
        _series([-999, -888, -777] + common_tail), TemporalDirection.BACKWARD
    )
    second = _lab().evaluate_direction(
        _series([9999, 8888, 7777] + common_tail), TemporalDirection.BACKWARD
    )
    first_folds = first.report.by_mode(HistoricalMode.LINEAR_TREND).folds
    second_folds = second.report.by_mode(HistoricalMode.LINEAR_TREND).folds
    for left, right in zip(first_folds[:20], second_folds[:20]):
        assert left.predicted == pytest.approx(right.predicted)
        assert left.actual == pytest.approx(right.actual)
        assert left.train_end == right.train_end
        assert left.target_index == right.target_index


def test_forward_and_backward_reports_have_identical_mode_sets() -> None:
    report = _lab().evaluate(_series(range(1, 35)))
    forward_modes = {mode_report.mode for mode_report in report.forward.report.reports}
    backward_modes = {mode_report.mode for mode_report in report.backward.report.reports}
    assert forward_modes == backward_modes
    assert set(report.consensus_ranking) == forward_modes


def test_linear_process_survives_bidirectional_gate() -> None:
    report = _lab().evaluate(_series([3 + 2 * index for index in range(40)]))
    assert report.decision.accepted is True
    assert report.selected_mode is not HistoricalMode.PERSISTENCE
    assert report.decision.forward_relative_mae_improvement > 0.9
    assert report.decision.backward_relative_mae_improvement > 0.9
    assert report.decision.mae_asymmetry == pytest.approx(0.0, abs=1e-10)
    assert "bidirectional_gate_passed" in report.decision.reasons


def test_flat_process_falls_back_to_persistence() -> None:
    report = _lab().evaluate(_series([7] * 40))
    assert report.decision.accepted is False
    assert report.selected_mode is HistoricalMode.PERSISTENCE
    assert "baseline_already_best" in report.decision.reasons


def test_bidirectional_gate_applies_minimum_folds_to_both_directions() -> None:
    lab = BidirectionalModeLab(
        config=WalkForwardConfig(min_train_size=8),
        gate=SelectionGate(min_folds=40, min_relative_improvement=0.0),
    )
    report = lab.evaluate(_series([2 * index for index in range(24)]))
    assert report.decision.accepted is False
    assert "forward_insufficient_folds" in report.decision.reasons
    assert "backward_insufficient_folds" in report.decision.reasons


def test_consensus_candidate_must_rank_well_in_each_direction() -> None:
    lab = BidirectionalModeLab(
        config=WalkForwardConfig(min_train_size=8, seasonal_period=4),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.0),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=10.0, max_direction_rank=1),
    )
    report = lab.evaluate(_series([0, 1, 4, 2, 8, 3, 10, 2, 12, 1] * 5))
    if report.decision.forward_rank > 1:
        assert "weak_forward_rank" in report.decision.reasons
    if report.decision.backward_rank > 1:
        assert "weak_backward_rank" in report.decision.reasons
    assert report.decision.accepted is (
        report.decision.candidate is not HistoricalMode.PERSISTENCE
        and report.decision.forward_rank == 1
        and report.decision.backward_rank == 1
        and not any(
            reason
            for reason in report.decision.reasons
            if reason != "bidirectional_gate_passed"
        )
    )


def test_bidirectional_report_is_deterministic() -> None:
    series = _series([1, 4, 2, 7, 3, 9, 5, 12] * 5, label="stable")
    first = _lab().evaluate(series)
    second = _lab().evaluate(series)
    assert first.fingerprint == second.fingerprint
    assert first.consensus_ranking == second.consensus_ranking
    assert first.decision == second.decision


def test_bidirectional_fingerprint_changes_when_history_changes() -> None:
    values = list(range(40))
    first = _lab().evaluate(_series(values, label="stable"))
    values[0] = -1000
    second = _lab().evaluate(_series(values, label="stable"))
    assert first.fingerprint != second.fingerprint


def test_payload_contains_both_directional_errors() -> None:
    report = _lab().evaluate(_series(range(40), label="payload"))
    payload = report.as_payload()
    assert payload["selected_mode"] == report.selected_mode.value
    assert isinstance(payload["bidirectional_accepted"], bool)
    assert math.isfinite(payload["forward_mae"])
    assert math.isfinite(payload["backward_mae"])
    assert math.isfinite(payload["mae_asymmetry"])
    assert isinstance(payload["fingerprint"], str)


def test_invalid_negative_asymmetry_gate_is_rejected() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        BidirectionalConfig(max_mae_asymmetry=-0.1)
    assert caught.value.context["reason"] == "invalid_bidirectional_gate"


def test_invalid_zero_direction_rank_gate_is_rejected() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        BidirectionalConfig(max_direction_rank=0)
    assert caught.value.context["reason"] == "invalid_bidirectional_gate"
