from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    arnoldi_iteration,
    frobenius_norm,
    gmres,
    identity_matrix,
    kronecker_product,
    matrix_exponential,
    matrix_power,
    matrix_trace,
    slogdet,
    solve_tridiagonal,
    tridiagonal_matvec,
)


def test_arnoldi_basis_is_orthonormal_and_hessenberg_dimensioned() -> None:
    matrix = (
        (4.0, 1.0, 0.0),
        (1.0, 3.0, 1.0),
        (0.0, 1.0, 2.0),
    )
    report = arnoldi_iteration(matrix, (1.0, 2.0, -1.0), steps=3)
    assert report.orthogonality_linf <= 1e-12
    assert 1 <= report.steps <= 3
    assert len(report.hessenberg[0]) == report.steps


def test_gmres_solves_nonsymmetric_system() -> None:
    matrix = (
        (4.0, 1.0, 0.0),
        (-2.0, 3.0, 1.0),
        (0.0, 1.0, 2.0),
    )
    rhs = (1.0, 2.0, 3.0)
    report = gmres(matrix, rhs, relative_tolerance=1e-12)
    assert report.converged
    reconstructed = tuple(
        sum(row[j] * report.solution[j] for j in range(3))
        for row in matrix
    )
    assert reconstructed == pytest.approx(rhs, abs=1e-10)
    assert report.residual_l2 <= 1e-10


def test_tridiagonal_solver_and_matvec_agree() -> None:
    lower = (-1.0, -1.0, -1.0)
    diagonal = (4.0, 4.0, 4.0, 4.0)
    upper = (-1.0, -1.0, -1.0)
    expected = (1.0, 2.0, 3.0, 4.0)
    rhs = tridiagonal_matvec(lower, diagonal, upper, expected)
    report = solve_tridiagonal(lower, diagonal, upper, rhs)
    assert report.solution == pytest.approx(expected, abs=1e-12)
    assert report.residual_linf <= 1e-12
    assert report.minimum_effective_pivot > 0.0


def test_matrix_algebra_reference_operations() -> None:
    identity = identity_matrix(2)
    matrix = ((2.0, 1.0), (0.0, 3.0))
    assert matrix_trace(matrix) == pytest.approx(5.0)
    assert frobenius_norm(matrix) == pytest.approx(math.sqrt(14.0))
    assert matrix_power(matrix, 0) == identity
    powered = matrix_power(matrix, 2)
    assert powered[0] == pytest.approx((4.0, 5.0))
    assert powered[1] == pytest.approx((0.0, 9.0))

    kron = kronecker_product(((1.0, 2.0),), ((3.0,), (4.0,)))
    assert kron[0] == pytest.approx((3.0, 6.0))
    assert kron[1] == pytest.approx((4.0, 8.0))

    determinant = slogdet(matrix)
    assert determinant.sign == 1
    assert determinant.log_abs_determinant == pytest.approx(math.log(6.0))


def test_matrix_exponential_matches_diagonal_closed_form_and_nilpotent_case() -> None:
    diagonal = matrix_exponential(((1.0, 0.0), (0.0, -2.0)))
    assert diagonal.converged
    assert diagonal.value[0] == pytest.approx((math.e, 0.0), abs=1e-12)
    assert diagonal.value[1] == pytest.approx((0.0, math.exp(-2.0)), abs=1e-12)

    # exp([[0,1],[0,0]]) = I + A because A^2=0.
    nilpotent = matrix_exponential(((0.0, 1.0), (0.0, 0.0)))
    assert nilpotent.value[0] == pytest.approx((1.0, 1.0), abs=1e-12)
    assert nilpotent.value[1] == pytest.approx((0.0, 1.0), abs=1e-12)
