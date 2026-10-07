"""Regression tests for Jeeves multi-horizon historical consistency."""

from __future__ import annotations

import pytest

from skeleton.jeeves.bidirectional_calibration import CrossDirectionConfig
from skeleton.jeeves.bidirectional_modes import BidirectionalConfig
from skeleton.jeeves.historical_horizons import HorizonGridConfig, MultiHorizonModeLab
from skeleton.jeeves.historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)
from skeleton.jeeves.historical_robustness import TemporalJackknifeConfig
from skeleton.jeeves.historical_uncertainty import ConformalConfig


def _series(values=None, *, label="multi-horizon") -> HistoricalSeries:
    data = values if values is not None else [4 + 2 * index for index in range(64)]
    return HistoricalSeries.from_values(data, label=label)


def _lab(*, horizons=None) -> MultiHorizonModeLab:
    return MultiHorizonModeLab(
        config=WalkForwardConfig(
            min_train_size=8,
            rolling_window=4,
            seasonal_period=4,
            momentum_window=3,
            reversion_window=6,
            ensemble_history=5,
            ensemble_top_k=2,
        ),
        gate=SelectionGate(min_folds=8, min_relative_improvement=0.02),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=0.75, max_direction_rank=2),
        calibration=CrossDirectionConfig(
            top_k=2,
            min_rank_correlation=-1.0,
            min_top_k_overlap=0.0,
            max_candidate_rank_gap=2,
            max_normalized_score_gap=100.0,
            max_p90_error_asymmetry=100.0,
            max_bias_ratio_asymmetry=100.0,
            max_directional_accuracy_gap=1.0,
            min_paired_targets=0,
            max_paired_error_asymmetry=100.0,
        ),
        jackknife=TemporalJackknifeConfig(
            trim_fraction=0.10,
            max_trim=5,
            min_views=3,
            min_acceptance_rate=0.75,
            min_candidate_support_rate=0.75,
            max_candidate_mae_spread=1.0,
        ),
        conformal=ConformalConfig(
            min_calibration_folds=6,
            calibration_window=24,
            min_empirical_coverage=0.0,
            max_direction_coverage_gap=1.0,
            max_direction_width_asymmetry=100.0,
        ),
        horizons=horizons
        or HorizonGridConfig(
            horizons=(1, 2, 3),
            min_horizons=3,
            min_acceptance_rate=1.0,
            min_candidate_support_rate=1.0,
            max_candidate_mae_spread=1.0,
            max_coverage_spread=1.0,
        ),
        modes=(HistoricalMode.LINEAR_TREND,),
    )


def _permissive_short_lab(horizons: HorizonGridConfig) -> MultiHorizonModeLab:
    return MultiHorizonModeLab(
        config=WalkForwardConfig(min_train_size=8),
        gate=SelectionGate(min_folds=1, min_relative_improvement=0.0),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=100.0, max_direction_rank=2),
        calibration=CrossDirectionConfig(
            top_k=2,
            min_rank_correlation=-1.0,
            min_top_k_overlap=0.0,
            max_candidate_rank_gap=99,
            max_normalized_score_gap=100.0,
            max_p90_error_asymmetry=100.0,
            max_bias_ratio_asymmetry=100.0,
            max_directional_accuracy_gap=1.0,
            min_paired_targets=0,
            max_paired_error_asymmetry=100.0,
        ),
        jackknife=TemporalJackknifeConfig(
            trim_fraction=0.10,
            max_trim=1,
            min_views=1,
            min_acceptance_rate=0.0,
            min_candidate_support_rate=0.0,
            max_candidate_mae_spread=100.0,
        ),
        conformal=ConformalConfig(
            min_calibration_folds=1,
            calibration_window=None,
            min_empirical_coverage=0.0,
            max_direction_coverage_gap=1.0,
            max_direction_width_asymmetry=100.0,
        ),
        horizons=horizons,
        modes=(HistoricalMode.LINEAR_TREND,),
    )


def test_exact_linear_process_survives_all_configured_horizons() -> None:
    report = _lab().evaluate(_series())
    assert report.decision.accepted is True
    assert report.selected_mode is HistoricalMode.LINEAR_TREND
    assert tuple(item.horizon for item in report.evaluations) == (1, 2, 3)
    assert report.decision.accepted_horizons == 3
    assert report.decision.candidate_supported_horizons == 3
    assert report.decision.acceptance_rate == pytest.approx(1.0)
    assert report.decision.candidate_support_rate == pytest.approx(1.0)
    assert "multi_horizon_gate_passed" in report.decision.reasons


def test_flat_process_stays_fail_closed_on_persistence() -> None:
    report = _lab().evaluate(_series([9] * 64))
    assert report.decision.accepted is False
    assert report.selected_mode is HistoricalMode.PERSISTENCE
    assert "anchor_horizon_rejected" in report.decision.reasons


def test_smallest_evaluated_horizon_is_anchor() -> None:
    report = _lab(
        horizons=HorizonGridConfig(
            horizons=(2, 4, 6),
            min_horizons=3,
            min_acceptance_rate=0.0,
            min_candidate_support_rate=0.0,
            max_candidate_mae_spread=100.0,
            max_coverage_spread=1.0,
        )
    ).evaluate(_series())
    assert report.decision.anchor_horizon == 2
    assert report.evaluations[0].horizon == 2


def test_each_horizon_uses_its_own_walk_forward_distance() -> None:
    report = _lab().evaluate(_series())
    for evaluation in report.evaluations:
        forward = evaluation.report.robustness.full.base.forward.report
        folds = forward.by_mode(HistoricalMode.LINEAR_TREND).folds
        assert folds
        assert all(
            fold.target_index - fold.train_end == evaluation.horizon for fold in folds
        )


def test_short_history_skips_unevaluable_horizons_and_fails_coverage_gate() -> None:
    grid = HorizonGridConfig(
        horizons=(1, 2, 3, 5),
        min_horizons=3,
        min_acceptance_rate=0.0,
        min_candidate_support_rate=0.0,
        max_candidate_mae_spread=100.0,
        max_coverage_spread=1.0,
    )
    report = _permissive_short_lab(grid).evaluate(_series(list(range(10))))
    assert tuple(item.horizon for item in report.evaluations) == (1, 2)
    assert report.decision.evaluated_horizons == 2
    assert report.decision.accepted is False
    assert "insufficient_horizon_coverage" in report.decision.reasons


def test_series_too_short_for_every_horizon_is_rejected() -> None:
    grid = HorizonGridConfig(horizons=(1, 2, 3), min_horizons=1)
    with pytest.raises(HistoricalModeError) as caught:
        _permissive_short_lab(grid).evaluate(_series(list(range(8))))
    assert caught.value.context["reason"] == "insufficient_history"


def test_candidate_mae_spread_is_zero_for_exact_linear_process() -> None:
    report = _lab().evaluate(_series())
    assert report.decision.candidate_mae_spread == pytest.approx(0.0, abs=1e-10)


def test_empirical_coverage_spread_is_bounded() -> None:
    report = _lab().evaluate(_series())
    assert report.decision.empirical_coverage_spread is not None
    assert 0.0 <= report.decision.empirical_coverage_spread <= 1.0


def test_report_is_deterministic() -> None:
    series = _series(label="stable")
    first = _lab().evaluate(series)
    second = _lab().evaluate(series)
    assert first.fingerprint == second.fingerprint
    assert first.decision == second.decision
    assert first.evaluations == second.evaluations


def test_fingerprint_changes_when_history_changes() -> None:
    values = [4 + 2 * index for index in range(64)]
    first = _lab().evaluate(_series(values, label="stable"))
    values[30] += 7
    second = _lab().evaluate(_series(values, label="stable"))
    assert first.fingerprint != second.fingerprint


def test_payload_contains_multi_horizon_summary() -> None:
    report = _lab().evaluate(_series())
    payload = report.as_payload()
    assert payload["selected_mode"] == report.selected_mode.value
    assert isinstance(payload["multi_horizon_accepted"], bool)
    assert payload["anchor_horizon"] == 1
    assert payload["evaluated_horizons"] == 3
    assert isinstance(payload["fingerprint"], str)


def test_by_horizon_rejects_unknown_horizon() -> None:
    report = _lab().evaluate(_series())
    with pytest.raises(HistoricalModeError) as caught:
        report.by_horizon(99)
    assert caught.value.context["reason"] == "unknown_horizon"


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"horizons": ()}, "horizons"),
        ({"horizons": (1, 1, 2)}, "horizons"),
        ({"horizons": (2, 1, 3)}, "horizons"),
        ({"horizons": (0, 1, 2)}, "horizon"),
        ({"min_horizons": 0}, "min_horizons"),
        ({"horizons": (1, 2), "min_horizons": 3}, "min_horizons"),
        ({"min_acceptance_rate": -0.1}, "min_acceptance_rate"),
        ({"min_candidate_support_rate": 1.1}, "min_candidate_support_rate"),
        ({"max_candidate_mae_spread": -0.1}, "max_candidate_mae_spread"),
        ({"max_coverage_spread": 1.1}, "max_coverage_spread"),
    ],
)
def test_invalid_horizon_grid_is_rejected(kwargs: dict, field: str) -> None:
    with pytest.raises(HistoricalModeError) as caught:
        HorizonGridConfig(**kwargs)
    assert caught.value.context["reason"] == "invalid_horizon_grid"
    assert caught.value.context["field"] == field
