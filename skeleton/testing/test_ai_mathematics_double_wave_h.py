from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    chi_square_goodness_of_fit,
    group_l2_shrinkage,
    isotonic_regression,
    local_polynomial_smooth,
    project_l1_ball,
    project_l2_ball,
    project_linf_ball,
    proximal_elastic_net,
    savitzky_golay_derivative,
    savitzky_golay_smooth,
    soft_threshold_vector,
    two_sample_ks,
)


def test_weighted_isotonic_regression_pools_violations() -> None:
    report = isotonic_regression((3.0, 1.0, 2.0, 5.0), weights=(1.0, 1.0, 2.0, 1.0))
    assert report.fitted == pytest.approx((1.75, 1.75, 1.75, 5.0))
    assert all(left <= right for left, right in zip(report.fitted, report.fitted[1:]))
    assert len(report.blocks) == 2
    assert report.weighted_squared_error == pytest.approx(2.75)


def test_decreasing_isotonic_preserves_requested_order() -> None:
    report = isotonic_regression((1.0, 3.0, 2.0, 0.0), increasing=False)
    assert all(left >= right for left, right in zip(report.fitted, report.fitted[1:]))


def test_proximal_and_norm_ball_operators_obey_constraints() -> None:
    values = (3.0, -4.0, 1.0)
    assert soft_threshold_vector(values, 1.0) == pytest.approx((2.0, -3.0, 0.0))
    l2 = project_l2_ball(values, 2.0)
    assert math.sqrt(sum(value * value for value in l2)) == pytest.approx(2.0)
    linf = project_linf_ball(values, 2.0)
    assert max(abs(value) for value in linf) <= 2.0

    l1 = project_l1_ball(values, 3.0)
    assert sum(abs(value) for value in l1) == pytest.approx(3.0)
    elastic = proximal_elastic_net(values, step_size=0.5, l1_weight=1.0, l2_weight=2.0)
    assert elastic == pytest.approx((1.25, -1.75, 0.25))
    group = group_l2_shrinkage((3.0, 4.0), 2.0)
    assert group == pytest.approx((1.8, 2.4))


def test_ks_identical_samples_have_zero_statistic() -> None:
    sample = (0.0, 1.0, 2.0, 3.0)
    report = two_sample_ks(sample, sample)
    assert report.statistic == pytest.approx(0.0)
    assert report.asymptotic_p_value == pytest.approx(1.0)


def test_ks_separated_samples_detect_large_shift() -> None:
    report = two_sample_ks((0.0, 0.1, 0.2, 0.3), (10.0, 10.1, 10.2, 10.3))
    assert report.statistic == pytest.approx(1.0)
    assert 0.0 <= report.asymptotic_p_value < 0.05


def test_chi_square_goodness_of_fit_reference_cases() -> None:
    fair = chi_square_goodness_of_fit((25.0, 25.0, 25.0, 25.0), (1.0, 1.0, 1.0, 1.0))
    assert fair.statistic == pytest.approx(0.0)
    assert fair.p_value == pytest.approx(1.0)

    biased = chi_square_goodness_of_fit((70.0, 10.0, 10.0, 10.0), (1.0, 1.0, 1.0, 1.0))
    assert biased.statistic > 50.0
    assert 0.0 <= biased.p_value < 1e-8


def test_local_polynomial_smoothing_recovers_quadratic_and_derivative() -> None:
    xs = tuple(float(index) for index in range(9))
    values = tuple(2.0 + 3.0 * x + 0.5 * x * x for x in xs)
    smooth = savitzky_golay_smooth(values, window=5, degree=2)
    derivative = savitzky_golay_derivative(values, window=5, degree=2, spacing=1.0)
    assert smooth == pytest.approx(values, abs=1e-10)
    assert derivative == pytest.approx(tuple(3.0 + x for x in xs), abs=1e-10)

    report = local_polynomial_smooth(values, window=5, degree=2, derivative_order=2)
    assert report.values == pytest.approx((1.0,) * len(values), abs=1e-10)
