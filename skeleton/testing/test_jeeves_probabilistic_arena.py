from __future__ import annotations

import math

import pytest

from skeleton.jeeves.probabilistic_arena import (
    ArenaCandidate,
    PredictiveArenaConfig,
    evaluate_predictive_arena,
    newey_west_mean_test,
    regime_forecast_crps,
)
from skeleton.jeeves.probabilistic_regimes import RegimeHMMConfig, fit_regime_hmm
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _regime_series(count: int = 100) -> tuple[float, ...]:
    level = 100.0
    values = [level]
    for index in range(count - 1):
        block = (index // 18) % 3
        drift = (-1.1, 0.0, 1.2)[block]
        level += drift + 0.08 * math.sin(index * 0.7)
        values.append(level)
    return tuple(values)


def _smooth_trend(count: int = 100) -> tuple[float, ...]:
    return tuple(20.0 + 0.45 * index + 0.03 * math.sin(index) for index in range(count))


def test_newey_west_zero_differences_are_unresolved() -> None:
    result = newey_west_mean_test((0.0,) * 20, lags=2)
    assert result.mean_difference == pytest.approx(0.0)
    assert result.standard_error == pytest.approx(0.0)
    assert result.z_score == pytest.approx(0.0)
    assert result.two_sided_p_value == pytest.approx(1.0)


def test_newey_west_clear_positive_gain_resolves() -> None:
    values = tuple(0.5 + 0.01 * math.sin(index) for index in range(60))
    result = newey_west_mean_test(values, lags=3)
    assert result.mean_difference > 0.0
    assert result.z_score > 0.0
    assert result.two_sided_p_value < 0.05


def test_newey_west_rejects_invalid_sample_or_lag() -> None:
    with pytest.raises(StateSpaceError):
        newey_west_mean_test((1.0,), lags=0)
    with pytest.raises(StateSpaceError):
        newey_west_mean_test((1.0, 2.0), lags=2)
    with pytest.raises(StateSpaceError):
        newey_west_mean_test((1.0, 2.0), lags=-1)


def test_arena_uses_identical_forward_targets() -> None:
    report = evaluate_predictive_arena(
        _regime_series(75),
        config=PredictiveArenaConfig(
            min_train_size=30,
            step=5,
            min_folds=3,
            max_p_value=1.0,
            max_relative_mae_regression=100.0,
            min_log_score_gain=-100.0,
        ),
        hmm_config=RegimeHMMConfig(states=3, max_iterations=15),
    )
    expected_targets = tuple(range(30, 75, 5))
    assert tuple(fold.target_index for fold in report.folds) == expected_targets
    assert report.baseline.folds == len(expected_targets)
    assert report.challenger.folds == len(expected_targets)


def test_arena_report_is_deterministic() -> None:
    config = PredictiveArenaConfig(
        min_train_size=28,
        step=6,
        min_folds=2,
        max_p_value=1.0,
        max_relative_mae_regression=100.0,
        min_log_score_gain=-100.0,
    )
    hmm = RegimeHMMConfig(states=2, max_iterations=12)
    left = evaluate_predictive_arena(_regime_series(70), config=config, hmm_config=hmm)
    right = evaluate_predictive_arena(_regime_series(70), config=config, hmm_config=hmm)
    assert left == right
    assert left.fingerprint == right.fingerprint


def test_permissive_arena_gate_can_accept_challenger() -> None:
    report = evaluate_predictive_arena(
        _regime_series(70),
        config=PredictiveArenaConfig(
            min_train_size=28,
            step=7,
            min_folds=1,
            min_log_score_gain=-1e9,
            max_p_value=1.0,
            max_relative_mae_regression=1e9,
        ),
        hmm_config=RegimeHMMConfig(states=2, max_iterations=10),
    )
    assert report.decision.accepted
    assert report.selected is ArenaCandidate.REGIME_HMM
    assert report.decision.reasons == ("regime_complexity_earned",)


def test_impossible_log_score_gate_rejects_challenger() -> None:
    report = evaluate_predictive_arena(
        _smooth_trend(70),
        config=PredictiveArenaConfig(
            min_train_size=28,
            step=7,
            min_folds=1,
            min_log_score_gain=1e9,
            max_p_value=1.0,
            max_relative_mae_regression=1e9,
        ),
        hmm_config=RegimeHMMConfig(states=2, max_iterations=10),
    )
    assert not report.decision.accepted
    assert report.selected is ArenaCandidate.STRUCTURAL_BAYES
    assert "insufficient_log_score_gain" in report.decision.reasons


def test_fold_floor_rejects_thin_arena_evidence() -> None:
    report = evaluate_predictive_arena(
        _regime_series(70),
        config=PredictiveArenaConfig(
            min_train_size=28,
            step=7,
            min_folds=100,
            min_log_score_gain=-1e9,
            max_p_value=1.0,
            max_relative_mae_regression=1e9,
        ),
        hmm_config=RegimeHMMConfig(states=2, max_iterations=8),
    )
    assert not report.decision.accepted
    assert "insufficient_common_folds" in report.decision.reasons


def test_arena_rejects_fold_grid_mismatch() -> None:
    from skeleton.jeeves.probabilistic_ensemble import BayesianEnsembleConfig

    with pytest.raises(StateSpaceError):
        evaluate_predictive_arena(
            _regime_series(60),
            config=PredictiveArenaConfig(min_train_size=24, step=4),
            ensemble_config=BayesianEnsembleConfig(min_train_size=20, step=4),
            hmm_config=RegimeHMMConfig(states=2, max_iterations=5),
        )


def test_regime_one_step_crps_is_nonnegative() -> None:
    fit = fit_regime_hmm(
        _regime_series(65),
        config=RegimeHMMConfig(states=3, max_iterations=15),
    )
    forecast = fit.forecast(1)
    assert regime_forecast_crps(forecast, forecast.mean) >= 0.0


def test_regime_crps_rejects_multi_step_moment_forecast() -> None:
    fit = fit_regime_hmm(
        _regime_series(65),
        config=RegimeHMMConfig(states=3, max_iterations=10),
    )
    with pytest.raises(StateSpaceError):
        regime_forecast_crps(fit.forecast(3), fit.observations[-1])


def test_arena_metrics_are_finite() -> None:
    report = evaluate_predictive_arena(
        _regime_series(70),
        config=PredictiveArenaConfig(
            min_train_size=30,
            step=8,
            min_folds=1,
            min_log_score_gain=-100.0,
            max_p_value=1.0,
            max_relative_mae_regression=100.0,
        ),
        hmm_config=RegimeHMMConfig(states=2, max_iterations=10),
    )
    for metrics in (report.baseline, report.challenger):
        assert math.isfinite(metrics.mean_log_score)
        assert math.isfinite(metrics.mae)
        assert math.isfinite(metrics.rmse)
        assert metrics.mae >= 0.0
        assert metrics.rmse >= 0.0
    assert math.isfinite(report.decision.log_score_gain)
    assert 0.0 <= report.decision.comparison.two_sided_p_value <= 1.0


def test_invalid_arena_configuration_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        PredictiveArenaConfig(min_train_size=5)
    with pytest.raises(StateSpaceError):
        PredictiveArenaConfig(step=0)
    with pytest.raises(StateSpaceError):
        PredictiveArenaConfig(min_folds=0)
    with pytest.raises(StateSpaceError):
        PredictiveArenaConfig(max_p_value=1.1)
    with pytest.raises(StateSpaceError):
        PredictiveArenaConfig(max_relative_mae_regression=-0.1)
    with pytest.raises(StateSpaceError):
        PredictiveArenaConfig(hac_lags=-1)
