from __future__ import annotations

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    bspline_basis,
    bspline_curve,
    cholesky_factor_after_rank_one_update,
    cholesky_rank_one_update,
    clamped_uniform_knots,
    curl_z_2d,
    divergence_2d,
    gradient_2d,
    laplacian_2d,
    symmetric_rank_one_update,
    whiten,
)


def test_clamped_bspline_basis_partitions_unity_and_hits_endpoints() -> None:
    knots = clamped_uniform_knots(4, 2)
    start = bspline_basis(knots, 2, 0.0)
    middle = bspline_basis(knots, 2, 0.5)
    end = bspline_basis(knots, 2, 1.0)

    assert start.values == pytest.approx((1.0, 0.0, 0.0, 0.0))
    assert end.values == pytest.approx((0.0, 0.0, 0.0, 1.0))
    assert middle.partition_sum == pytest.approx(1.0, abs=1e-14)
    assert all(value >= 0.0 for value in middle.values)


def test_bspline_curve_respects_convex_combination_and_endpoints() -> None:
    points = ((0.0, 0.0), (1.0, 2.0), (3.0, 2.0), (4.0, 0.0))
    knots = clamped_uniform_knots(len(points), 2)
    assert bspline_curve(points, knots, 2, 0.0) == pytest.approx(points[0])
    assert bspline_curve(points, knots, 2, 1.0) == pytest.approx(points[-1])
    midpoint = bspline_curve(points, knots, 2, 0.5)
    assert 0.0 <= midpoint[0] <= 4.0
    assert 0.0 <= midpoint[1] <= 2.0


def test_whitening_centers_and_standardizes_full_rank_covariance() -> None:
    observations = (
        (1.0, 2.0),
        (2.0, 1.0),
        (3.0, 5.0),
        (4.0, 3.0),
        (5.0, 7.0),
        (6.0, 4.0),
    )
    for mode in ("pca", "zca"):
        report = whiten(observations, mode=mode)
        assert report.covariance_residual_linf <= 1e-9
        assert all(value > 0.0 for value in report.eigenvalues)
        means = tuple(
            sum(row[column] for row in report.transformed) / len(report.transformed)
            for column in range(2)
        )
        assert means == pytest.approx((0.0, 0.0), abs=1e-12)


def test_whitening_rank_deficiency_requires_regularization() -> None:
    observations = ((1.0, 2.0), (2.0, 4.0), (3.0, 6.0), (4.0, 8.0))
    with pytest.raises(MathInvariantError, match="rank deficient"):
        whiten(observations)
    regularized = whiten(observations, regularization=1e-3)
    assert regularized.covariance_residual_linf <= 1e-9


def test_2d_finite_differences_recover_polynomial_vector_calculus() -> None:
    xs = tuple(float(index) for index in range(5))
    ys = tuple(float(index) for index in range(5))
    scalar = tuple(
        tuple(x * x + 3.0 * y * y + 2.0 * x - y for x in xs)
        for y in ys
    )
    gx, gy = gradient_2d(scalar)
    for row, y in enumerate(ys):
        for column, x in enumerate(xs):
            assert gx[row][column] == pytest.approx(2.0 * x + 2.0, abs=1e-12)
            assert gy[row][column] == pytest.approx(6.0 * y - 1.0, abs=1e-12)

    laplacian = laplacian_2d(scalar)
    for row in laplacian:
        assert row == pytest.approx((8.0,) * 5, abs=1e-12)

    field_x = tuple(tuple(x + 2.0 * y for x in xs) for y in ys)
    field_y = tuple(tuple(3.0 * x - y for x in xs) for y in ys)
    divergence = divergence_2d(field_x, field_y)
    curl = curl_z_2d(field_x, field_y)
    for row in divergence:
        assert row == pytest.approx((0.0,) * 5, abs=1e-12)
    for row in curl:
        assert row == pytest.approx((1.0,) * 5, abs=1e-12)


def test_rank_one_and_cholesky_updates_reconstruct_targets() -> None:
    matrix = ((4.0, 1.0), (1.0, 3.0))
    vector = (0.5, -1.0)
    target = symmetric_rank_one_update(matrix, vector, alpha=1.0)
    report = cholesky_factor_after_rank_one_update(matrix, vector, sign=1)
    assert report.reconstruction_linf <= 1e-12
    assert report.minimum_diagonal > 0.0

    # Updating then downdating by the same vector recovers the original factor.
    restored = cholesky_rank_one_update(report.lower, vector, sign=-1)
    assert restored.reconstruction_linf <= 1e-12

    aggressive = (10.0, 0.0)
    with pytest.raises(MathInvariantError, match="destroy positive definiteness"):
        cholesky_factor_after_rank_one_update(matrix, aggressive, sign=-1)
