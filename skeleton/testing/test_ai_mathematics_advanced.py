from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    bhattacharyya_distance,
    cholesky_decompose,
    discrete_frechet_distance,
    dynamic_time_warping,
    finite_difference_hessian,
    fisher_rao_distance,
    gram_matrix,
    hellinger_distance,
    least_squares,
    levenshtein_distance,
    mahalanobis_distance,
    maximum_mean_discrepancy_squared,
    normalized_levenshtein_distance,
    qr_decompose,
    rbf_kernel,
    solve_cholesky,
    total_variation_distance,
)


def test_cholesky_reconstructs_spd_matrix_and_solves() -> None:
    matrix = (
        (4.0, 1.0, 1.0),
        (1.0, 3.0, 0.5),
        (1.0, 0.5, 2.0),
    )
    report = cholesky_decompose(matrix)
    assert report.reconstruction_linf <= 1e-12
    assert report.minimum_diagonal > 0.0
    solution = solve_cholesky(matrix, (1.0, 2.0, 3.0))
    reconstructed = tuple(
        sum(row[j] * solution[j] for j in range(3))
        for row in matrix
    )
    assert reconstructed == pytest.approx((1.0, 2.0, 3.0), abs=1e-12)


def test_qr_and_least_squares_expose_factorization_evidence() -> None:
    matrix = (
        (1.0, 1.0),
        (1.0, 2.0),
        (1.0, 3.0),
        (1.0, 4.0),
    )
    qr = qr_decompose(matrix)
    assert qr.reconstruction_linf <= 1e-12
    assert qr.orthogonality_linf <= 1e-12

    result = least_squares(matrix, (6.0, 5.0, 7.0, 10.0))
    assert result.rank == 2
    assert result.solution == pytest.approx((3.5, 1.4), abs=1e-12)
    assert result.normal_equation_residual_linf <= 1e-12


def test_rank_deficient_qr_and_non_spd_cholesky_fail_closed() -> None:
    with pytest.raises(MathInvariantError, match="rank deficient"):
        qr_decompose(((1.0, 2.0), (2.0, 4.0), (3.0, 6.0)))
    with pytest.raises(MathInvariantError, match="positive definite"):
        cholesky_decompose(((1.0, 2.0), (2.0, 1.0)))


def test_finite_difference_hessian_recovers_quadratic() -> None:
    def objective(point):
        x, y = point
        return 3.0 * x * x + 2.0 * x * y + 5.0 * y * y + 7.0 * x - 4.0 * y

    point = (1.25, -0.75)
    report = finite_difference_hessian(objective, point, relative_step=1e-4)
    expected_gradient = (
        6.0 * point[0] + 2.0 * point[1] + 7.0,
        2.0 * point[0] + 10.0 * point[1] - 4.0,
    )
    assert report.gradient == pytest.approx(expected_gradient, rel=1e-8, abs=1e-8)
    assert report.hessian[0] == pytest.approx((6.0, 2.0), rel=1e-7, abs=1e-7)
    assert report.hessian[1] == pytest.approx((2.0, 10.0), rel=1e-7, abs=1e-7)
    assert report.symmetry_linf == pytest.approx(0.0)


def test_rbf_gram_is_symmetric_and_mmd_detects_shift() -> None:
    samples = ((0.0,), (1.0,), (2.0,))
    gram = gram_matrix(samples, lambda a, b: rbf_kernel(a, b, gamma=0.5))
    for i in range(3):
        assert gram[i][i] == pytest.approx(1.0)
        for j in range(3):
            assert gram[i][j] == pytest.approx(gram[j][i])

    same = maximum_mean_discrepancy_squared(
        samples,
        samples,
        lambda a, b: rbf_kernel(a, b, gamma=0.5),
        unbiased=False,
    )
    shifted = maximum_mean_discrepancy_squared(
        samples,
        ((5.0,), (6.0,), (7.0,)),
        lambda a, b: rbf_kernel(a, b, gamma=0.5),
        unbiased=False,
    )
    assert same == pytest.approx(0.0, abs=1e-15)
    assert shifted > 0.5


def test_information_geometry_invariants_and_mahalanobis() -> None:
    p = (0.5, 0.25, 0.25)
    q = (0.25, 0.5, 0.25)
    assert total_variation_distance(p, p) == pytest.approx(0.0)
    assert hellinger_distance(p, p) == pytest.approx(0.0)
    assert fisher_rao_distance(p, p) == pytest.approx(0.0)
    assert bhattacharyya_distance(p, q) > 0.0

    covariance = ((4.0, 0.0), (0.0, 9.0))
    distance = mahalanobis_distance((0.0, 0.0), (2.0, 3.0), covariance)
    assert distance == pytest.approx(math.sqrt(2.0))


def test_sequence_metrics_capture_edit_alignment_and_trajectory_geometry() -> None:
    assert levenshtein_distance("kitten", "sitting") == 3
    assert normalized_levenshtein_distance("abc", "abc") == pytest.approx(0.0)

    report = dynamic_time_warping((1.0, 2.0, 3.0), (1.0, 1.5, 2.5, 3.0))
    assert report.distance >= 0.0
    assert report.path[0] == (0, 0)
    assert report.path[-1] == (2, 3)
    assert report.path_length == len(report.path)

    frechet = discrete_frechet_distance(
        ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0)),
        ((0.0, 0.0), (1.0, 1.0), (2.0, 0.0)),
    )
    assert frechet == pytest.approx(1.0)
