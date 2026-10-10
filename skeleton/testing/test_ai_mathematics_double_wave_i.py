from __future__ import annotations


import pytest

from skeleton.ai.mathematics import (
    bilinear_gradient,
    bilinear_interpolate,
    empirical_cdf,
    gaussian_kde_density,
    histogram,
    kendall_tau_b,
    polynomial_derivative,
    polynomial_divmod,
    polynomial_evaluate,
    polynomial_integral,
    polynomial_multiply,
    polynomial_roots,
    rank_biserial_correlation,
    rankdata,
    silverman_bandwidth,
    spearman_correlation,
    trilinear_interpolate,
)


def test_rankdata_and_rank_correlations_handle_ties() -> None:
    values = (10.0, 20.0, 20.0, 40.0)
    assert rankdata(values) == pytest.approx((1.0, 2.5, 2.5, 4.0))
    assert spearman_correlation(values, values) == pytest.approx(1.0)
    report = kendall_tau_b((1.0, 2.0, 2.0, 4.0), (1.0, 3.0, 2.0, 4.0))
    assert 0.0 < report.tau_b <= 1.0
    assert report.ties_left_only == 1


def test_rank_biserial_orders_separated_groups() -> None:
    assert rank_biserial_correlation((1.0, 2.0, 10.0, 11.0), (0, 0, 1, 1)) == pytest.approx(1.0)


def test_empirical_cdf_histogram_and_kde_contracts() -> None:
    sample = (0.0, 1.0, 2.0, 3.0)
    cdf = empirical_cdf(sample)
    assert cdf.evaluate(1.5) == pytest.approx(0.5)
    assert cdf.quantile(0.5) == pytest.approx(1.5)

    hist = histogram(sample, bins=2)
    assert hist.counts == (2, 2)
    assert sum(hist.probabilities) == pytest.approx(1.0)
    assert sum(
        density * (hist.edges[index + 1] - hist.edges[index])
        for index, density in enumerate(hist.densities)
    ) == pytest.approx(1.0)

    bandwidth = silverman_bandwidth(sample)
    densities = gaussian_kde_density(sample, (0.0, 1.5, 3.0), bandwidth=bandwidth)
    assert all(value > 0.0 for value in densities)
    assert densities[0] == pytest.approx(densities[-1], rel=1e-12)


def test_polynomial_algebra_and_division() -> None:
    left = (-1.0, 1.0)   # x - 1
    right = (-2.0, 1.0)  # x - 2
    product = polynomial_multiply(left, right)
    assert product == pytest.approx((2.0, -3.0, 1.0))
    quotient, remainder = polynomial_divmod(product, left)
    assert quotient == pytest.approx(right)
    assert remainder == pytest.approx((0.0,))
    assert polynomial_derivative(product) == pytest.approx((-3.0, 2.0))
    assert polynomial_integral((-3.0, 2.0), constant=2.0) == pytest.approx((2.0, -3.0, 1.0))
    assert polynomial_evaluate(product, 2.0).real == pytest.approx(0.0)


def test_polynomial_roots_find_distinct_cubic_roots() -> None:
    # (x-1)(x-2)(x+3) = x^3 - 7x + 6
    report = polynomial_roots((6.0, -7.0, 0.0, 1.0), tolerance=1e-11)
    assert report.converged
    assert report.maximum_residual <= 1e-8
    real_roots = sorted(root.real for root in report.roots)
    assert real_roots == pytest.approx((-3.0, 1.0, 2.0), abs=1e-8)
    assert max(abs(root.imag) for root in report.roots) <= 1e-8


def test_bilinear_interpolation_recovers_affine_surface_and_gradient() -> None:
    xs = (0.0, 2.0)
    ys = (0.0, 4.0)
    values = tuple(tuple(3.0 * x - 2.0 * y + 5.0 for y in ys) for x in xs)
    assert bilinear_interpolate(xs, ys, values, 0.5, 1.5) == pytest.approx(3.5)
    assert bilinear_gradient(xs, ys, values, 0.5, 1.5) == pytest.approx((3.0, -2.0))


def test_trilinear_interpolation_recovers_affine_volume() -> None:
    xs = (0.0, 1.0)
    ys = (0.0, 2.0)
    zs = (0.0, 4.0)
    values = tuple(
        tuple(
            tuple(2.0 * x + 3.0 * y - z + 7.0 for z in zs)
            for y in ys
        )
        for x in xs
    )
    result = trilinear_interpolate(xs, ys, zs, values, 0.25, 0.5, 1.0)
    assert result == pytest.approx(8.0)
