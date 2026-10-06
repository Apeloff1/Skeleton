from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    binomial_coefficient,
    binomial_log_pmf,
    blackman_window,
    bray_curtis_distance,
    canberra_distance,
    chebyshev_distance,
    cross_correlation,
    dice_distance,
    hamming_window,
    hann_window,
    hypergeometric_log_pmf,
    inverse_softplus,
    jaccard_distance,
    linear_detrend,
    log1mexp,
    logaddexp,
    logsubexp,
    manhattan_distance,
    minkowski_distance,
    moving_average,
    moving_rms,
    multinomial_log_pmf,
    pairwise_distance_matrix,
    stable_logit,
    stable_sigmoid,
    stable_softplus,
    weighted_jaccard_distance,
)


def test_combinatorial_counts_and_log_masses_match_closed_forms() -> None:
    assert binomial_coefficient(10, 3) == 120
    assert math.exp(binomial_log_pmf(2, 4, 0.5)) == pytest.approx(6.0 / 16.0)
    assert math.exp(
        hypergeometric_log_pmf(
            2,
            population_successes=5,
            population_failures=5,
            draws=4,
        )
    ) == pytest.approx(100.0 / 210.0)
    assert math.exp(multinomial_log_pmf((1, 1, 1), (1, 1, 1))) == pytest.approx(2.0 / 9.0)


def test_discrete_probability_zero_support_fails_closed() -> None:
    with pytest.raises(MathInvariantError, match="zero support"):
        binomial_log_pmf(1, 3, 0.0)


def test_stable_special_functions_are_inverse_or_log_domain_consistent() -> None:
    for value in (-20.0, -2.0, 0.0, 3.0, 30.0):
        probability = stable_sigmoid(value)
        assert stable_logit(probability) == pytest.approx(value, abs=1e-9)
        softplus = stable_softplus(value)
        assert inverse_softplus(softplus) == pytest.approx(value, abs=1e-9)
    a, b = 1000.0, 999.0
    assert logaddexp(a, b) == pytest.approx(a + math.log1p(math.exp(-1.0)))
    assert logsubexp(a, b) == pytest.approx(a + math.log1p(-math.exp(-1.0)))
    logp = math.log(0.9)
    assert math.exp(log1mexp(logp)) == pytest.approx(0.1)


def test_windows_have_expected_symmetry_and_endpoints() -> None:
    for window in (hann_window(9), hamming_window(9), blackman_window(9)):
        assert window == pytest.approx(tuple(reversed(window)), abs=1e-15)
    assert hann_window(9)[0] == pytest.approx(0.0, abs=1e-15)
    assert hann_window(9)[-1] == pytest.approx(0.0, abs=1e-15)


def test_cross_correlation_finds_known_shift() -> None:
    left = (0.0, 0.0, 1.0, 2.0, 1.0, 0.0)
    right = (1.0, 2.0, 1.0)
    report = cross_correlation(left, right)
    assert report.maximum_lag == 2
    assert report.maximum_value == pytest.approx(6.0)


def test_rolling_signal_math_and_detrending() -> None:
    assert moving_average((1.0, 2.0, 3.0, 4.0), 2) == pytest.approx((1.5, 2.5, 3.5))
    assert moving_rms((3.0, 4.0), 2) == pytest.approx((math.sqrt(12.5),))
    trend = tuple(2.0 + 3.0 * index for index in range(8))
    assert linear_detrend(trend) == pytest.approx((0.0,) * 8, abs=1e-12)


def test_distance_metrics_satisfy_reference_cases() -> None:
    left = (0.0, 1.0, 2.0)
    right = (1.0, 1.0, 4.0)
    assert manhattan_distance(left, right) == pytest.approx(3.0)
    assert minkowski_distance(left, right, order=2.0) == pytest.approx(math.sqrt(5.0))
    assert chebyshev_distance(left, right) == pytest.approx(2.0)
    assert canberra_distance((0.0, 1.0), (0.0, 3.0)) == pytest.approx(0.5)
    assert bray_curtis_distance((1.0, 2.0), (1.0, 4.0)) == pytest.approx(2.0 / 8.0)
    assert jaccard_distance({1, 2}, {2, 3}) == pytest.approx(2.0 / 3.0)
    assert dice_distance({1, 2}, {2, 3}) == pytest.approx(0.5)
    assert weighted_jaccard_distance((1.0, 2.0), (1.0, 4.0)) == pytest.approx(0.4)

    matrix = pairwise_distance_matrix(((0.0, 0.0), (3.0, 4.0)))
    assert matrix[0] == pytest.approx((0.0, 5.0))
    assert matrix[1] == pytest.approx((5.0, 0.0))
