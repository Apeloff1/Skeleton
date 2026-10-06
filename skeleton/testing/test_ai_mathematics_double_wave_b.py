from __future__ import annotations

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    absorbing_probability,
    bootstrap,
    expected_hitting_times,
    huber_location,
    jackknife,
    minimum_cost_assignment,
    modified_z_scores,
    propagate_distribution,
    robust_scale_mad,
    transition_power,
    trimmed_mean,
    winsorized_mean,
)


def test_robust_location_resists_single_extreme_outlier() -> None:
    values = (9.8, 10.0, 10.1, 10.2, 1000.0)
    assert trimmed_mean(values, proportion=0.2) == pytest.approx((10.0 + 10.1 + 10.2) / 3.0)
    assert winsorized_mean(values, proportion=0.2) < 11.0
    report = huber_location(values)
    assert report.converged
    assert 9.5 < report.location < 11.0
    assert robust_scale_mad(values) > 0.0


def test_modified_z_scores_flag_extreme_observation() -> None:
    scores = modified_z_scores((1.0, 1.1, 0.9, 1.05, 100.0))
    assert max(abs(value) for value in scores[:-1]) < 2.0
    assert abs(scores[-1]) > 100.0
    with pytest.raises(MathInvariantError, match="MAD is zero"):
        modified_z_scores((1.0, 1.0, 1.0, 2.0, 1.0))


def test_jackknife_mean_has_expected_bias_and_standard_error() -> None:
    report = jackknife((1.0, 2.0, 3.0, 4.0), lambda sample: sum(sample) / len(sample))
    assert report.estimate == pytest.approx(2.5)
    assert report.bias_estimate == pytest.approx(0.0, abs=1e-15)
    assert report.bias_corrected_estimate == pytest.approx(2.5)
    assert report.standard_error > 0.0


def test_bootstrap_is_seed_reproducible_and_interval_contains_mean() -> None:
    statistic = lambda sample: sum(sample) / len(sample)
    left = bootstrap((1.0, 2.0, 3.0, 4.0, 5.0), statistic, replicates=500, seed=123)
    right = bootstrap((1.0, 2.0, 3.0, 4.0, 5.0), statistic, replicates=500, seed=123)
    assert left.replicates == right.replicates
    assert left.confidence_interval[0] <= left.estimate <= left.confidence_interval[1]
    assert left.standard_error > 0.0


def test_markov_propagation_and_transition_power_agree() -> None:
    transition = ((0.75, 0.25), (0.1, 0.9))
    initial = (1.0, 0.0)
    direct = propagate_distribution(initial, transition, steps=5)
    powered = transition_power(transition, 5)
    via_power = (
        initial[0] * powered[0][0] + initial[1] * powered[1][0],
        initial[0] * powered[0][1] + initial[1] * powered[1][1],
    )
    assert direct == pytest.approx(via_power, abs=1e-12)
    assert sum(direct) == pytest.approx(1.0, abs=1e-15)


def test_hitting_times_and_absorption_probabilities_are_exact_on_small_chain() -> None:
    transition = (
        (0.5, 0.5, 0.0),
        (0.0, 0.5, 0.5),
        (0.0, 0.0, 1.0),
    )
    hitting = expected_hitting_times(transition, (2,))
    assert hitting.expected_steps == pytest.approx((4.0, 2.0, 0.0), abs=1e-12)
    assert hitting.residual_linf <= 1e-12
    probabilities = absorbing_probability(transition, 2, absorbing_states=(2,))
    assert probabilities == pytest.approx((1.0, 1.0, 1.0), abs=1e-12)


def test_minimum_cost_assignment_handles_square_and_rectangular_cases() -> None:
    square = minimum_cost_assignment(
        (
            (4.0, 1.0, 3.0),
            (2.0, 0.0, 5.0),
            (3.0, 2.0, 2.0),
        )
    )
    assert square.total_cost == pytest.approx(5.0)
    assert len(square.pairs) == 3

    rectangular = minimum_cost_assignment(
        (
            (10.0, 2.0, 9.0),
            (7.0, 5.0, 6.0),
        )
    )
    assert len(rectangular.pairs) == 2
    assert rectangular.total_cost == pytest.approx(8.0)
    assert len({column for _, column in rectangular.pairs}) == 2


def test_absorption_requires_declared_states_to_be_actually_absorbing() -> None:
    with pytest.raises(MathInvariantError, match="absorbing transition row"):
        absorbing_probability(
            ((0.5, 0.5), (0.0, 1.0)),
            0,
            absorbing_states=(0,),
        )
