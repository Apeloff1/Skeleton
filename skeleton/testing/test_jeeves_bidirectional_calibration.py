"""Regression tests for Jeeves cross-direction calibration."""

from __future__ import annotations

import math

import pytest

from skeleton.jeeves.bidirectional_calibration import (
    CalibratedBidirectionalModeLab,
    CrossDirectionConfig,
)
from skeleton.jeeves.bidirectional_modes import BidirectionalConfig
from skeleton.jeeves.historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)


def _series(values, *, label="fixture", timestamps=None) -> HistoricalSeries:
    return HistoricalSeries.from_values(values, label=label, timestamps=timestamps)


def _lab(*, calibration=None, **config_overrides) -> CalibratedBidirectionalModeLab:
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
    return CalibratedBidirectionalModeLab(
        config=WalkForwardConfig(**values),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=0.75, max_direction_rank=4),
        calibration=calibration or CrossDirectionConfig(),
    )


def test_linear_process_survives_cross_direction_calibration() -> None:
    report = _lab().evaluate(_series([3 + 2 * index for index in range(40)]))
    assert report.base.decision.accepted is True
    assert report.decision.accepted is True
    assert report.selected_mode is not HistoricalMode.PERSISTENCE
    assert "cross_direction_calibration_passed" in report.decision.reasons


def test_flat_process_remains_fail_closed_after_calibration() -> None:
    report = _lab().evaluate(_series([7] * 40))
    assert report.base.decision.accepted is False
    assert report.decision.accepted is False
    assert report.selected_mode is HistoricalMode.PERSISTENCE
    assert "base_bidirectional_gate_rejected" in report.decision.reasons


def test_rank_agreement_is_bounded() -> None:
    report = _lab().evaluate(_series([1, 4, 2, 7, 3, 9, 5, 12] * 6))
    agreement = report.ranking_agreement
    assert -1.0 <= agreement.spearman_rank_correlation <= 1.0
    assert 0.0 <= agreement.top_k_overlap <= 1.0
    assert agreement.mean_absolute_rank_gap >= 0.0
    assert agreement.common_modes == len(report.diagnostics)


def test_top_k_is_clamped_to_number_of_common_modes() -> None:
    lab = CalibratedBidirectionalModeLab(
        config=WalkForwardConfig(min_train_size=8),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.0),
        calibration=CrossDirectionConfig(top_k=999, min_rank_correlation=-1.0),
        modes=(HistoricalMode.LINEAR_TREND,),
    )
    report = lab.evaluate(_series(range(40)))
    assert report.ranking_agreement.top_k == report.ranking_agreement.common_modes


def test_every_consensus_mode_gets_diagnostics() -> None:
    report = _lab().evaluate(_series(range(40)))
    assert tuple(item.mode for item in report.diagnostics) == report.base.consensus_ranking


def test_candidate_diagnostics_match_base_candidate() -> None:
    report = _lab().evaluate(_series([index * 1.5 for index in range(40)]))
    assert report.decision.candidate_diagnostics.mode is report.base.decision.candidate
    assert report.decision.candidate is report.base.decision.candidate


def test_same_target_pairing_is_nonempty_for_dense_walk_forward() -> None:
    report = _lab().evaluate(_series(range(40)))
    diagnostic = report.by_mode(HistoricalMode.PERSISTENCE)
    assert diagnostic.paired_targets == 24
    assert diagnostic.paired_mean_absolute_error_gap is not None
    assert diagnostic.paired_error_asymmetry is not None


def test_same_target_pair_count_respects_multi_step_horizon() -> None:
    report = _lab(horizon=3).evaluate(_series(range(40)))
    diagnostic = report.by_mode(HistoricalMode.PERSISTENCE)
    assert diagnostic.paired_targets == 20


def test_linear_trend_has_symmetric_tail_error_on_exact_line() -> None:
    report = _lab().evaluate(_series([5 + 4 * index for index in range(40)]))
    diagnostic = report.by_mode(HistoricalMode.LINEAR_TREND)
    assert diagnostic.p90_error_asymmetry == pytest.approx(0.0, abs=1e-10)
    assert diagnostic.median_error_asymmetry == pytest.approx(0.0, abs=1e-10)


def test_mode_rank_gap_matches_directional_rank_difference() -> None:
    report = _lab().evaluate(_series([0, 2, 1, 4, 3, 8, 5, 10] * 6))
    for diagnostic in report.diagnostics:
        assert diagnostic.rank_gap == abs(
            diagnostic.forward_rank - diagnostic.backward_rank
        )


def test_directional_accuracy_gap_is_bounded_when_present() -> None:
    report = _lab().evaluate(_series([0, 2, 1, 4, 3, 8, 5, 10] * 6))
    for diagnostic in report.diagnostics:
        if diagnostic.directional_accuracy_gap is not None:
            assert 0.0 <= diagnostic.directional_accuracy_gap <= 1.0


def test_paired_error_correlation_is_bounded_when_defined() -> None:
    report = _lab().evaluate(_series([0, 2, 1, 4, 3, 8, 5, 10] * 6))
    for diagnostic in report.diagnostics:
        if diagnostic.paired_absolute_error_correlation is not None:
            assert -1.0 <= diagnostic.paired_absolute_error_correlation <= 1.0


def test_report_is_deterministic() -> None:
    series = _series([1, 4, 2, 7, 3, 9, 5, 12] * 6, label="stable")
    first = _lab().evaluate(series)
    second = _lab().evaluate(series)
    assert first.fingerprint == second.fingerprint
    assert first.ranking_agreement == second.ranking_agreement
    assert first.diagnostics == second.diagnostics
    assert first.decision == second.decision


def test_fingerprint_changes_when_history_changes() -> None:
    values = list(range(40))
    first = _lab().evaluate(_series(values, label="stable"))
    values[20] += 100
    second = _lab().evaluate(_series(values, label="stable"))
    assert first.fingerprint != second.fingerprint


def test_irregular_timestamps_do_not_break_calibration_geometry() -> None:
    values = list(range(40))
    timestamps = []
    cursor = 100.0
    for index in range(40):
        cursor += 1.0 + (index % 4)
        timestamps.append(cursor)
    report = _lab().evaluate(_series(values, timestamps=timestamps))
    assert report.ranking_agreement.common_modes == len(report.diagnostics)
    assert report.by_mode(HistoricalMode.PERSISTENCE).paired_targets == 24


def test_payload_is_evidence_friendly() -> None:
    report = _lab().evaluate(_series(range(40), label="payload"))
    payload = report.as_payload()
    assert payload["selected_mode"] == report.selected_mode.value
    assert isinstance(payload["calibration_accepted"], bool)
    assert isinstance(payload["base_bidirectional_accepted"], bool)
    assert math.isfinite(payload["rank_correlation"])
    assert math.isfinite(payload["top_k_overlap"])
    paired = payload["candidate_paired_error_asymmetry"]
    assert paired is None or math.isfinite(paired)
    assert isinstance(payload["fingerprint"], str)


def test_unknown_diagnostic_mode_is_rejected() -> None:
    lab = CalibratedBidirectionalModeLab(
        config=WalkForwardConfig(min_train_size=8),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.0),
        modes=(HistoricalMode.LINEAR_TREND,),
    )
    report = lab.evaluate(_series(range(40)))
    with pytest.raises(HistoricalModeError) as caught:
        report.by_mode(HistoricalMode.AR1)
    assert caught.value.context["reason"] == "unknown_mode"


def test_strict_rank_gate_is_reflected_when_violated() -> None:
    calibration = CrossDirectionConfig(
        min_rank_correlation=-1.0,
        min_top_k_overlap=0.0,
        max_candidate_rank_gap=0,
        max_normalized_score_gap=100.0,
        max_p90_error_asymmetry=100.0,
        max_bias_ratio_asymmetry=100.0,
        max_directional_accuracy_gap=1.0,
        min_paired_targets=0,
        max_paired_error_asymmetry=100.0,
    )
    report = _lab(calibration=calibration).evaluate(
        _series([0, 3, 1, 6, 2, 12, 5, 7, 20, 4] * 5)
    )
    candidate = report.decision.candidate_diagnostics
    if candidate.rank_gap > 0:
        assert "candidate_rank_instability" in report.decision.reasons
        assert report.decision.accepted is False


def test_strict_global_rank_gate_is_reflected_when_violated() -> None:
    calibration = CrossDirectionConfig(
        min_rank_correlation=1.0,
        min_top_k_overlap=0.0,
        max_candidate_rank_gap=99,
        max_normalized_score_gap=100.0,
        max_p90_error_asymmetry=100.0,
        max_bias_ratio_asymmetry=100.0,
        max_directional_accuracy_gap=1.0,
        min_paired_targets=0,
        max_paired_error_asymmetry=100.0,
    )
    report = _lab(calibration=calibration).evaluate(
        _series([0, 3, 1, 6, 2, 12, 5, 7, 20, 4] * 5)
    )
    if report.ranking_agreement.spearman_rank_correlation < 1.0:
        assert "weak_global_rank_agreement" in report.decision.reasons
        assert report.decision.accepted is False


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"top_k": 0}, "top_k"),
        ({"min_rank_correlation": 1.1}, "min_rank_correlation"),
        ({"min_top_k_overlap": -0.1}, "min_top_k_overlap"),
        ({"max_candidate_rank_gap": -1}, "max_candidate_rank_gap"),
        ({"max_normalized_score_gap": -0.1}, "max_normalized_score_gap"),
        ({"max_p90_error_asymmetry": -0.1}, "max_p90_error_asymmetry"),
        ({"max_bias_ratio_asymmetry": -0.1}, "max_bias_ratio_asymmetry"),
        ({"max_directional_accuracy_gap": 1.1}, "max_directional_accuracy_gap"),
        ({"min_paired_targets": -1}, "min_paired_targets"),
        ({"max_paired_error_asymmetry": -0.1}, "max_paired_error_asymmetry"),
    ],
)
def test_invalid_cross_direction_gate_is_rejected(kwargs: dict, field: str) -> None:
    with pytest.raises(HistoricalModeError) as caught:
        CrossDirectionConfig(**kwargs)
    assert caught.value.context["reason"] == "invalid_cross_direction_gate"
    assert caught.value.context["field"] == field
