from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    circulant,
    condition_number,
    dct2,
    dct_ii,
    dct_iv,
    diagonal_dominance_margins,
    gauss_seidel_solve,
    gershgorin_discs,
    inverse_dct2,
    inverse_dct_ii,
    is_strictly_diagonally_dominant,
    jacobi_solve,
    linear_backward_error,
    matrix_infinity_norm,
    matrix_one_norm,
    sor_solve,
    toeplitz,
)


def test_stationary_solvers_converge_on_strictly_diagonally_dominant_system() -> None:
    matrix = (
        (10.0, -1.0, 2.0),
        (-1.0, 11.0, -1.0),
        (2.0, -1.0, 10.0),
    )
    expected = (1.0, 2.0, -1.0)
    rhs = tuple(sum(row[j] * expected[j] for j in range(3)) for row in matrix)

    jacobi = jacobi_solve(matrix, rhs, relative_tolerance=1e-12)
    gs = gauss_seidel_solve(matrix, rhs, relative_tolerance=1e-12)
    sor = sor_solve(matrix, rhs, omega=1.1, relative_tolerance=1e-12)

    for report in (jacobi, gs, sor):
        assert report.converged
        assert report.solution == pytest.approx(expected, abs=1e-10)
        assert report.residual_l2 <= 1e-10


def test_matrix_conditioning_and_backward_error_known_cases() -> None:
    diagonal = ((2.0, 0.0), (0.0, 5.0))
    assert matrix_one_norm(diagonal) == pytest.approx(5.0)
    assert matrix_infinity_norm(diagonal) == pytest.approx(5.0)
    report = condition_number(diagonal, norm="1")
    assert report.condition_number == pytest.approx(2.5)
    assert report.inverse_residual_linf <= 1e-15

    backward = linear_backward_error(diagonal, (3.0, -2.0), (6.0, -10.0))
    assert backward.residual_linf == pytest.approx(0.0)
    assert backward.relative_backward_error == pytest.approx(0.0)


def test_toeplitz_circulant_and_gershgorin_contracts() -> None:
    matrix = toeplitz((1.0, 2.0, 3.0), (1.0, 4.0, 5.0))
    assert matrix[0] == pytest.approx((1.0, 4.0, 5.0))
    assert matrix[1] == pytest.approx((2.0, 1.0, 4.0))
    assert matrix[2] == pytest.approx((3.0, 2.0, 1.0))

    circ = circulant((1.0, 2.0, 3.0))
    assert circ[0] == pytest.approx((1.0, 2.0, 3.0))
    assert circ[1] == pytest.approx((3.0, 1.0, 2.0))

    dominant = ((5.0, 1.0, 1.0), (0.5, 4.0, 0.5), (1.0, 1.0, 6.0))
    margins = diagonal_dominance_margins(dominant)
    assert all(value > 0.0 for value in margins)
    assert is_strictly_diagonally_dominant(dominant)
    discs = gershgorin_discs(dominant)
    assert discs[0].center == pytest.approx(5.0)
    assert discs[0].radius == pytest.approx(2.0)


def test_dct_ii_and_dct_iv_are_orthonormal_round_trips() -> None:
    values = (1.0, 2.0, -1.0, 4.0, 0.5, -2.0)
    transformed = dct_ii(values)
    restored = inverse_dct_ii(transformed)
    assert restored == pytest.approx(values, abs=1e-12)
    assert sum(value * value for value in transformed) == pytest.approx(
        sum(value * value for value in values),
        abs=1e-12,
    )

    fourth = dct_iv(values)
    fourth_roundtrip = dct_iv(fourth)
    assert fourth_roundtrip == pytest.approx(values, abs=1e-12)


def test_separable_2d_dct_round_trip() -> None:
    matrix = (
        (1.0, 2.0, 3.0),
        (4.0, -1.0, 2.0),
        (0.5, 3.0, -2.0),
        (1.5, 0.0, 4.0),
    )
    transformed = dct2(matrix)
    restored = inverse_dct2(transformed)
    for expected, actual in zip(matrix, restored):
        assert actual == pytest.approx(expected, abs=1e-12)
