from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    determinant,
    lu_decompose,
    lu_solve,
    matrix_inverse,
    natural_cubic_spline,
    quaternion_from_axis_angle,
    quaternion_rotate_vector,
    quaternion_slerp,
    quaternion_to_rotation_matrix,
    sinkhorn_transport,
    wasserstein_distance_1d,
)


def test_lu_factorization_solve_inverse_and_determinant() -> None:
    matrix = ((2.0, 1.0, 1.0), (4.0, -6.0, 0.0), (-2.0, 7.0, 2.0))
    report = lu_decompose(matrix)
    assert report.reconstruction_linf <= 1e-12
    solution = lu_solve(matrix, (5.0, -2.0, 9.0))
    reconstructed = tuple(sum(row[j] * solution[j] for j in range(3)) for row in matrix)
    assert reconstructed == pytest.approx((5.0, -2.0, 9.0), abs=1e-12)
    assert determinant(matrix) == pytest.approx(-16.0)
    inverse = matrix_inverse(matrix)
    assert inverse.residual_linf <= 1e-12


def test_lu_rejects_singular_matrix() -> None:
    with pytest.raises(MathInvariantError, match="singular"):
        lu_decompose(((1.0, 2.0), (2.0, 4.0)))


def test_natural_cubic_spline_interpolates_and_has_natural_boundaries() -> None:
    spline = natural_cubic_spline((0.0, 1.0, 2.0, 3.0), (0.0, 1.0, 0.0, 1.0))
    for x, y in zip(spline.knots, (0.0, 1.0, 0.0, 1.0)):
        assert spline.evaluate(x) == pytest.approx(y, abs=1e-12)
    assert spline.second_derivative(0.0) == pytest.approx(0.0, abs=1e-12)
    assert spline.second_derivative(3.0) == pytest.approx(0.0, abs=1e-12)
    assert spline.integral(0.0, 3.0) == pytest.approx(1.5, abs=1e-12)


def test_weighted_wasserstein_distance_known_cases() -> None:
    assert wasserstein_distance_1d((0.0,), (3.0,)) == pytest.approx(3.0)
    assert wasserstein_distance_1d((0.0, 2.0), (1.0, 3.0)) == pytest.approx(1.0)
    weighted = wasserstein_distance_1d(
        (0.0, 10.0),
        (0.0, 10.0),
        left_weights=(0.9, 0.1),
        right_weights=(0.1, 0.9),
    )
    assert weighted == pytest.approx(8.0)


def test_sinkhorn_plan_matches_marginals() -> None:
    report = sinkhorn_transport(
        ((0.0, 1.0), (1.0, 0.0)),
        (0.5, 0.5),
        (0.25, 0.75),
        regularization=0.5,
        tolerance=1e-10,
    )
    assert report.converged
    assert report.marginal_residual_linf <= 1e-10
    assert sum(report.plan[0]) == pytest.approx(0.5, abs=1e-10)
    assert sum(row[0] for row in report.plan) == pytest.approx(0.25, abs=1e-10)


def test_quaternion_rotation_slerp_and_matrix_agree() -> None:
    quarter_turn = quaternion_from_axis_angle((0.0, 0.0, 1.0), math.pi / 2.0)
    rotated = quaternion_rotate_vector(quarter_turn, (1.0, 0.0, 0.0))
    assert rotated == pytest.approx((0.0, 1.0, 0.0), abs=1e-12)

    identity = quaternion_from_axis_angle((0.0, 0.0, 1.0), 0.0)
    halfway = quaternion_slerp(identity, quarter_turn, 0.5)
    half_rotated = quaternion_rotate_vector(halfway, (1.0, 0.0, 0.0))
    root_half = math.sqrt(0.5)
    assert half_rotated == pytest.approx((root_half, root_half, 0.0), abs=1e-12)

    matrix = quaternion_to_rotation_matrix(quarter_turn)
    matrix_rotated = tuple(sum(matrix[i][j] * (1.0, 0.0, 0.0)[j] for j in range(3)) for i in range(3))
    assert matrix_rotated == pytest.approx(rotated, abs=1e-12)
