"""Regressions for Jeeves' offline historical-mode laboratory."""

from __future__ import annotations

import math

import pytest

from skeleton.jeeves.historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalModeLab,
    HistoricalSeries,
    Regime,
    SelectionGate,
    WalkForwardConfig,
    classify_regime,
)


def _series(values, *, label="fixture") -> HistoricalSeries:
    return HistoricalSeries.from_values(values, label=label)


def _lab(**config_overrides) -> HistoricalModeLab:
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
    return HistoricalModeLab(config=WalkForwardConfig(**values))


def test_empty_series_is_rejected() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        HistoricalSeries(values=())
    assert caught.value.context["reason"] == "empty_series"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_series_values_are_rejected(bad: float) -> None:
    with pytest.raises(HistoricalModeError) as caught:
        _series([1.0, bad, 2.0])
    assert caught.value.context["reason"] == "invalid_number"


def test_bool_is_not_accepted_as_numeric_history() -> None:
    with pytest.raises(HistoricalModeError):
        _series([1.0, True, 2.0])


def test_timestamp_length_mismatch_is_rejected() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        HistoricalSeries.from_values([1, 2, 3], timestamps=[1, 2])
    assert caught.value.context["reason"] == "length_mismatch"


def test_timestamps_must_be_strictly_increasing() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        HistoricalSeries.from_values([1, 2, 3], timestamps=[1, 1, 2])
    assert caught.value.context["reason"] == "non_monotonic_time"


def test_prefix_preserves_temporal_alignment() -> None:
    series = HistoricalSeries.from_values([10, 20, 30], timestamps=[100, 200, 300], label="x")
    prefix = series.prefix(2)
    assert prefix.values == (10.0, 20.0)
    assert prefix.timestamps == (100.0, 200.0)
    assert prefix.label == "x"


def test_custom_mode_set_always_gets_persistence_baseline() -> None:
    lab = HistoricalModeLab(modes=(HistoricalMode.LINEAR_TREND,))
    assert lab.modes == (HistoricalMode.PERSISTENCE, HistoricalMode.LINEAR_TREND)


def test_duplicate_modes_fail_closed() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        HistoricalModeLab(modes=(HistoricalMode.PERSISTENCE, HistoricalMode.PERSISTENCE))
    assert caught.value.context["reason"] == "duplicate_mode"


def test_adaptive_ensemble_cannot_be_supplied_as_base_mode() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        HistoricalModeLab(modes=(HistoricalMode.ADAPTIVE_ENSEMBLE,))
    assert caught.value.context["reason"] == "invalid_mode"


def test_linear_trend_forecast_is_exact_on_linear_history() -> None:
    forecast = _lab().forecast(_series([1, 3, 5, 7, 9]), HistoricalMode.LINEAR_TREND)
    assert forecast.predicted == pytest.approx(11.0)


def test_drift_forecast_respects_horizon() -> None:
    forecast = _lab(horizon=3).forecast(_series([2, 4, 6, 8]), HistoricalMode.DRIFT)
    assert forecast.predicted == pytest.approx(14.0)
    assert forecast.horizon == 3


def test_seasonal_naive_reuses_same_phase() -> None:
    lab = _lab(seasonal_period=4)
    forecast = lab.forecast(_series([1, 2, 3, 4, 1, 2, 3, 4]), HistoricalMode.SEASONAL_NAIVE)
    assert forecast.predicted == pytest.approx(1.0)


def test_ewma_forecast_is_bounded_by_observed_range() -> None:
    forecast = _lab().forecast(_series([1, 10, 2, 9, 3]), HistoricalMode.EWMA)
    assert 1.0 <= forecast.predicted <= 10.0


def test_ar1_constant_series_stays_constant() -> None:
    forecast = _lab().forecast(_series([5, 5, 5, 5]), HistoricalMode.AR1)
    assert forecast.predicted == pytest.approx(5.0)


def test_quiet_regime_is_detected() -> None:
    assert classify_regime([10, 10, 10, 10, 10]).regime is Regime.QUIET


def test_uptrend_regime_is_detected() -> None:
    assert classify_regime([10, 11, 12, 13, 14, 15]).regime is Regime.TRENDING_UP


def test_downtrend_regime_is_detected() -> None:
    assert classify_regime([20, 18, 16, 14, 12, 10]).regime is Regime.TRENDING_DOWN


def test_volatile_regime_is_detected_before_trend() -> None:
    profile = classify_regime([1, 10, -3, 12, -6, 15, -8])
    assert profile.regime is Regime.VOLATILE


def test_short_history_regime_is_insufficient() -> None:
    assert classify_regime([1, 2]).regime is Regime.INSUFFICIENT


def test_walk_forward_boundaries_never_overlap_target() -> None:
    report = _lab().evaluate(_series(range(1, 25)))
    for mode_report in report.reports:
        for fold in mode_report.folds:
            assert fold.target_index > fold.train_end


def test_walk_forward_uses_expected_number_of_folds() -> None:
    report = _lab(min_train_size=8, horizon=1, step=1).evaluate(_series(range(20)))
    assert report.by_mode(HistoricalMode.PERSISTENCE).metrics.folds == 12


def test_multi_step_walk_forward_targets_correct_horizon() -> None:
    report = _lab(min_train_size=8, horizon=3).evaluate(_series(range(25)))
    folds = report.by_mode(HistoricalMode.PERSISTENCE).folds
    assert all(fold.target_index - fold.train_end == 3 for fold in folds)


def test_future_tail_cannot_change_earlier_fold_predictions() -> None:
    common = list(range(1, 25))
    first = _lab().evaluate(_series(common + [25, 26, 27]))
    second = _lab().evaluate(_series(common + [2500, -900, 7000]))
    first_folds = first.by_mode(HistoricalMode.LINEAR_TREND).folds
    second_folds = second.by_mode(HistoricalMode.LINEAR_TREND).folds
    for left, right in zip(first_folds[:16], second_folds[:16]):
        assert left.predicted == pytest.approx(right.predicted)
        assert left.actual == pytest.approx(right.actual)
        assert left.train_end == right.train_end
        assert left.target_index == right.target_index


def test_adaptive_ensemble_is_always_in_report() -> None:
    report = _lab().evaluate(_series(range(1, 25)))
    assert report.by_mode(HistoricalMode.ADAPTIVE_ENSEMBLE).metrics.folds > 0


def test_adaptive_ensemble_current_target_cannot_change_its_own_prediction() -> None:
    values = [
        1,
        4,
        2,
        7,
        3,
        9,
        5,
        12,
        8,
        14,
        9,
        16,
        11,
        18,
        12,
        21,
        13,
        23,
        15,
        25,
        16,
        27,
        18,
        30,
        19,
        31,
        21,
        34,
        22,
        36,
        24,
        39,
    ]
    target_index = 20
    changed = list(values)
    changed[target_index] += 10_000

    original = _lab().evaluate(_series(values)).by_mode(HistoricalMode.ADAPTIVE_ENSEMBLE)
    mutated = _lab().evaluate(_series(changed)).by_mode(HistoricalMode.ADAPTIVE_ENSEMBLE)
    original_fold = next(fold for fold in original.folds if fold.target_index == target_index)
    mutated_fold = next(fold for fold in mutated.folds if fold.target_index == target_index)

    assert original_fold.train_end == mutated_fold.train_end
    assert original_fold.regime is mutated_fold.regime
    assert original_fold.predicted == pytest.approx(mutated_fold.predicted)
    assert original_fold.actual != mutated_fold.actual


def test_perfect_linear_history_promotes_a_non_persistence_mode() -> None:
    lab = HistoricalModeLab(
        config=WalkForwardConfig(min_train_size=8, rolling_window=4, seasonal_period=4),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
    )
    report = lab.evaluate(_series([2 * index + 3 for index in range(30)]))
    assert report.promotion.accepted is True
    assert report.selected_mode is not HistoricalMode.PERSISTENCE
    assert "historical_gate_passed" in report.promotion.reasons
    assert report.promotion.relative_mae_improvement > 0.9


def test_flat_history_does_not_promote_when_persistence_is_perfect() -> None:
    report = _lab().evaluate(_series([7] * 30))
    assert report.selected_mode is HistoricalMode.PERSISTENCE
    assert report.promotion.accepted is False


def test_min_fold_gate_blocks_tiny_backtest() -> None:
    lab = HistoricalModeLab(
        config=WalkForwardConfig(min_train_size=8),
        gate=SelectionGate(min_folds=20, min_relative_improvement=0.0),
    )
    report = lab.evaluate(_series([index * 2 for index in range(18)]))
    assert report.promotion.accepted is False
    assert "insufficient_folds" in report.promotion.reasons


def test_short_series_cannot_be_evaluated() -> None:
    with pytest.raises(HistoricalModeError) as caught:
        _lab(min_train_size=8).evaluate(_series(range(8)))
    assert caught.value.context["reason"] == "insufficient_history"


def test_metrics_are_finite_for_zero_crossing_series() -> None:
    report = _lab().evaluate(_series([0, 1, 0, -1] * 8))
    for mode_report in report.reports:
        metrics = mode_report.metrics
        assert math.isfinite(metrics.mae)
        assert math.isfinite(metrics.rmse)
        assert math.isfinite(metrics.smape)
        assert math.isfinite(metrics.bias)


def test_regime_metrics_partition_folds() -> None:
    report = _lab().evaluate(_series([1, 2, 3, 4, 5, 10, 0, 12, -2, 13, 3, 4, 5, 6, 7, 8, 9, 10]))
    mode_report = report.by_mode(HistoricalMode.PERSISTENCE)
    assert sum(metrics.folds for _, metrics in mode_report.regime_metrics) == mode_report.metrics.folds


def test_report_fingerprint_is_deterministic() -> None:
    series = _series([index * 1.5 for index in range(30)], label="stable")
    first = _lab().evaluate(series)
    second = _lab().evaluate(series)
    assert first.fingerprint == second.fingerprint


def test_report_fingerprint_changes_when_history_changes() -> None:
    first = _lab().evaluate(_series(range(30), label="stable"))
    changed = list(range(30))
    changed[-1] = 99
    second = _lab().evaluate(_series(changed, label="stable"))
    assert first.fingerprint != second.fingerprint


def test_payload_is_small_and_evidence_friendly() -> None:
    report = _lab().evaluate(_series(range(30), label="payload-fixture"))
    payload = report.as_payload()
    assert payload["series_label"] == "payload-fixture"
    assert payload["selected_mode"] == report.selected_mode.value
    assert isinstance(payload["promotion_accepted"], bool)
    assert isinstance(payload["fingerprint"], str)


def test_unknown_report_mode_is_rejected() -> None:
    lab = HistoricalModeLab(modes=(HistoricalMode.PERSISTENCE, HistoricalMode.LINEAR_TREND))
    report = lab.evaluate(_series(range(30)))
    with pytest.raises(HistoricalModeError) as caught:
        report.by_mode(HistoricalMode.AR1)
    assert caught.value.context["reason"] == "unknown_mode"


def test_invalid_config_rejects_zero_horizon() -> None:
    with pytest.raises(HistoricalModeError):
        WalkForwardConfig(horizon=0)


def test_invalid_config_rejects_zero_ewma_alpha() -> None:
    with pytest.raises(HistoricalModeError):
        WalkForwardConfig(ewma_alpha=0.0)


def test_invalid_gate_rejects_worst_error_ratio_below_one() -> None:
    with pytest.raises(HistoricalModeError):
        SelectionGate(max_relative_worst_error=0.99)


def test_forecast_metadata_is_deterministically_sorted() -> None:
    forecast = _lab().forecast(_series([1, 2, 3, 4, 5]), HistoricalMode.AR1)
    assert forecast.metadata == tuple(sorted(forecast.metadata))
