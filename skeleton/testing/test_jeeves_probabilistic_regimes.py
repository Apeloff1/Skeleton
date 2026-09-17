from __future__ import annotations

import math

import pytest

from skeleton.jeeves.probabilistic_regimes import (
    RegimeHMMConfig,
    evaluate_regime_hmm_prequential,
    fit_regime_hmm,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _segmented_series() -> tuple[float, ...]:
    level = 100.0
    values = [level]
    changes = (
        [-1.5 + 0.05 * math.sin(index) for index in range(22)]
        + [0.05 * math.sin(index * 1.7) for index in range(22)]
        + [1.5 + 0.05 * math.sin(index * 0.7) for index in range(22)]
    )
    for change in changes:
        level += change
        values.append(level)
    return tuple(values)


def _two_regime_series() -> tuple[float, ...]:
    level = 10.0
    values = [level]
    for index in range(80):
        change = -0.7 if (index // 20) % 2 == 0 else 0.9
        change += 0.03 * math.sin(index)
        level += change
        values.append(level)
    return tuple(values)


def test_hmm_fit_is_deterministic() -> None:
    config = RegimeHMMConfig(states=3, max_iterations=40)
    left = fit_regime_hmm(_segmented_series(), config=config)
    right = fit_regime_hmm(_segmented_series(), config=config)
    assert left.fingerprint == right.fingerprint
    assert left.model == right.model
    assert left.posteriors == right.posteriors


def test_regime_means_are_deterministically_ordered() -> None:
    fit = fit_regime_hmm(_segmented_series(), config=RegimeHMMConfig(states=3))
    means = [regime.mean_change for regime in fit.model.regimes]
    assert means == sorted(means)
    assert means[0] < -0.5
    assert means[-1] > 0.5


def test_transition_rows_and_initial_probabilities_are_normalized() -> None:
    fit = fit_regime_hmm(_segmented_series())
    assert sum(fit.model.initial) == pytest.approx(1.0)
    assert all(value >= 0.0 for value in fit.model.initial)
    for row in fit.model.transition:
        assert sum(row) == pytest.approx(1.0)
        assert all(value >= 0.0 for value in row)


def test_posterior_probabilities_are_normalized_and_entropy_bounded() -> None:
    fit = fit_regime_hmm(_segmented_series())
    maximum_entropy = math.log(len(fit.model.regimes))
    for posterior in fit.posteriors:
        assert sum(posterior.probabilities) == pytest.approx(1.0)
        assert all(0.0 <= value <= 1.0 for value in posterior.probabilities)
        assert 0.0 <= posterior.entropy <= maximum_entropy + 1e-10
        assert posterior.dominant_state in range(len(fit.model.regimes))


def test_one_step_forecast_is_exact_regime_mixture() -> None:
    fit = fit_regime_hmm(_segmented_series())
    forecast = fit.forecast(1)
    assert len(forecast.components) == len(fit.model.regimes)
    assert sum(component.probability for component in forecast.components) == pytest.approx(1.0)
    assert sum(forecast.state_probabilities) == pytest.approx(1.0)
    assert forecast.variance > 0.0
    assert math.isfinite(forecast.log_density(forecast.mean))


def test_multi_step_forecast_propagates_markov_reward_uncertainty() -> None:
    fit = fit_regime_hmm(_segmented_series())
    one = fit.forecast(1)
    five = fit.forecast(5)
    assert not five.components
    assert five.variance > 0.0
    assert five.variance >= one.variance
    assert sum(five.state_probabilities) == pytest.approx(1.0)
    lower, upper = five.moment_interval()
    assert lower < five.mean < upper


def test_positive_terminal_regime_pushes_forecast_above_last_level() -> None:
    fit = fit_regime_hmm(_segmented_series())
    forecast = fit.forecast(3)
    assert forecast.mean > fit.observations[-1]


def test_sticky_regularization_produces_persistent_transition_structure() -> None:
    fit = fit_regime_hmm(
        _segmented_series(),
        config=RegimeHMMConfig(states=3, sticky_prior=4.0, transition_prior=0.05),
    )
    diagonal = statistics_mean(
        fit.model.transition[state][state]
        for state in range(len(fit.model.regimes))
    )
    off_diagonal = statistics_mean(
        fit.model.transition[source][target]
        for source in range(len(fit.model.regimes))
        for target in range(len(fit.model.regimes))
        if source != target
    )
    assert diagonal > off_diagonal


def test_fit_prefix_is_immune_to_future_tail_mutation() -> None:
    common = list(_two_regime_series()[:55])
    left = tuple(common + [20.0, 21.0, 22.0, 23.0])
    right = tuple(common + [2000.0, -3000.0, 5000.0, -7000.0])
    config = RegimeHMMConfig(states=2, max_iterations=25)
    left_prefix = fit_regime_hmm(left[: len(common)], config=config)
    right_prefix = fit_regime_hmm(right[: len(common)], config=config)
    assert left_prefix.fingerprint == right_prefix.fingerprint
    assert left_prefix.model == right_prefix.model


def test_prequential_score_is_deterministic_and_finite() -> None:
    config = RegimeHMMConfig(states=2, max_iterations=20)
    left = evaluate_regime_hmm_prequential(
        _two_regime_series(),
        min_train_size=30,
        step=10,
        config=config,
    )
    right = evaluate_regime_hmm_prequential(
        _two_regime_series(),
        min_train_size=30,
        step=10,
        config=config,
    )
    assert left == right
    assert left.folds > 0
    assert math.isfinite(left.mean_log_score)
    assert left.mae >= 0.0
    assert left.rmse >= 0.0
    assert left.average_entropy >= 0.0


def test_prequential_configuration_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        evaluate_regime_hmm_prequential(_two_regime_series(), min_train_size=5)
    with pytest.raises(StateSpaceError):
        evaluate_regime_hmm_prequential(_two_regime_series(), step=0)
    with pytest.raises(StateSpaceError):
        evaluate_regime_hmm_prequential(_two_regime_series(), min_train_size=1000)


def test_hmm_config_rejects_invalid_values() -> None:
    with pytest.raises(StateSpaceError):
        RegimeHMMConfig(states=1)
    with pytest.raises(StateSpaceError):
        RegimeHMMConfig(states=9)
    with pytest.raises(StateSpaceError):
        RegimeHMMConfig(max_iterations=0)
    with pytest.raises(StateSpaceError):
        RegimeHMMConfig(tolerance=0.0)
    with pytest.raises(StateSpaceError):
        RegimeHMMConfig(min_variance=0.0)
    with pytest.raises(StateSpaceError):
        RegimeHMMConfig(sticky_prior=-1.0)


def test_too_short_series_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        fit_regime_hmm((1.0, 2.0, 3.0), config=RegimeHMMConfig(states=2))


def test_nonfinite_series_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        fit_regime_hmm((1.0, 2.0, float("nan"), 4.0, 5.0, 6.0))


def test_terminal_posterior_changes_state_forecast_probabilities() -> None:
    fit = fit_regime_hmm(_segmented_series())
    forecast = fit.forecast(1)
    expected = []
    for target in range(len(fit.model.regimes)):
        expected.append(
            sum(
                fit.last_posterior[source] * fit.model.transition[source][target]
                for source in range(len(fit.model.regimes))
            )
        )
    assert forecast.state_probabilities == pytest.approx(tuple(expected))


def statistics_mean(values) -> float:
    collected = tuple(values)
    return sum(collected) / len(collected)
