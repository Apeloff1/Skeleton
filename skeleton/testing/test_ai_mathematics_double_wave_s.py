from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    euler_maruyama,
    geometric_brownian_moments,
    matrix_exponential_frechet,
    matrix_exponential_relative_condition_proxy,
    milstein_scalar,
)


def test_sde_paths_are_seed_deterministic_and_share_noise() -> None:
    drift = lambda _t, x: 0.2 * x
    diffusion = lambda _t, x: 0.3 * x
    derivative = lambda _t, _x: 0.3
    euler_a = euler_maruyama(
        drift,
        diffusion,
        initial_state=2.0,
        time_step=0.01,
        steps=20,
        seed=7,
    )
    euler_b = euler_maruyama(
        drift,
        diffusion,
        initial_state=2.0,
        time_step=0.01,
        steps=20,
        seed=7,
    )
    milstein = milstein_scalar(
        drift,
        diffusion,
        derivative,
        initial_state=2.0,
        time_step=0.01,
        steps=20,
        seed=7,
    )
    assert euler_a == euler_b
    assert euler_a.brownian_increments == pytest.approx(milstein.brownian_increments)
    assert len(euler_a.states) == 21
    assert all(math.isfinite(value) for value in milstein.states)


def test_gbm_moments_match_closed_form() -> None:
    report = geometric_brownian_moments(2.0, 0.1, 0.3, 1.5)
    expected_mean = 2.0 * math.exp(0.15)
    expected_second = 4.0 * math.exp((0.2 + 0.09) * 1.5)
    assert report.mean == pytest.approx(expected_mean)
    assert report.second_moment == pytest.approx(expected_second)
    assert report.variance == pytest.approx(expected_second - expected_mean**2)


def test_matrix_exponential_frechet_matches_commuting_closed_form() -> None:
    matrix = ((1.0, 0.0), (0.0, 2.0))
    direction = ((3.0, 0.0), (0.0, -4.0))
    report = matrix_exponential_frechet(matrix, direction)
    assert report.exponential[0] == pytest.approx((math.e, 0.0), abs=1e-12)
    assert report.exponential[1] == pytest.approx((0.0, math.exp(2.0)), abs=1e-12)
    assert report.derivative[0] == pytest.approx((3.0 * math.e, 0.0), abs=1e-11)
    assert report.derivative[1] == pytest.approx((0.0, -4.0 * math.exp(2.0)), abs=1e-10)
    assert report.finite_difference_residual_frobenius <= 1e-6


def test_matrix_exponential_condition_proxy_is_finite_nonnegative() -> None:
    value = matrix_exponential_relative_condition_proxy(((0.2, 0.1), (-0.3, 0.4)))
    assert math.isfinite(value)
    assert value >= 0.0
