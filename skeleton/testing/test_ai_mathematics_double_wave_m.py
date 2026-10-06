from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    fit_chebyshev_series,
    hyperdual_exp,
    hyperdual_sin,
    hyperdual_second_derivative,
    legendre_p,
    probabilists_hermite,
    solve_continuous_lyapunov,
    solve_sylvester,
    symmetric_matrix_exp,
    symmetric_matrix_inverse_sqrt,
    symmetric_matrix_log,
    symmetric_matrix_sqrt,
    value_gradient_hessian,
)


def test_sylvester_solves_known_diagonal_system() -> None:
    left = ((1.0, 0.0), (0.0, 2.0))
    right = ((3.0, 0.0), (0.0, 4.0))
    expected = ((1.0, 2.0), (3.0, 4.0))
    target = tuple(
        tuple((left[i][i] + right[j][j]) * expected[i][j] for j in range(2))
        for i in range(2)
    )
    report = solve_sylvester(left, right, target)
    for actual, row in zip(report.solution, expected):
        assert actual == pytest.approx(row, abs=1e-12)
    assert report.residual_linf <= 1e-12


def test_continuous_lyapunov_has_symmetric_solution() -> None:
    matrix = ((-1.0, 0.0), (0.0, -2.0))
    forcing = ((2.0, 0.0), (0.0, 8.0))
    report = solve_continuous_lyapunov(matrix, forcing)
    assert report.solution[0] == pytest.approx((1.0, 0.0), abs=1e-12)
    assert report.solution[1] == pytest.approx((0.0, 2.0), abs=1e-12)
    assert report.residual_linf <= 1e-12
    assert report.symmetry_linf <= 1e-12


def test_symmetric_matrix_functions_match_diagonal_closed_forms() -> None:
    matrix = ((4.0, 0.0), (0.0, 9.0))
    root = symmetric_matrix_sqrt(matrix)
    assert root.value[0] == pytest.approx((2.0, 0.0), abs=1e-12)
    assert root.value[1] == pytest.approx((0.0, 3.0), abs=1e-12)

    inverse_root = symmetric_matrix_inverse_sqrt(matrix)
    assert inverse_root.value[0] == pytest.approx((0.5, 0.0), abs=1e-12)
    assert inverse_root.value[1] == pytest.approx((0.0, 1.0 / 3.0), abs=1e-12)

    logarithm = symmetric_matrix_log(matrix)
    assert logarithm.value[0][0] == pytest.approx(math.log(4.0))
    exponential = symmetric_matrix_exp(logarithm.value)
    assert exponential.value[0] == pytest.approx(matrix[0], abs=1e-11)
    assert exponential.value[1] == pytest.approx(matrix[1], abs=1e-11)


def test_hyperdual_second_derivative_matches_closed_form() -> None:
    value = 0.7
    result = hyperdual_second_derivative(
        lambda x: hyperdual_sin(x) * hyperdual_exp(x),
        value,
    )
    expected = 2.0 * math.cos(value) * math.exp(value)
    assert result == pytest.approx(expected, abs=1e-12)


def test_hyperdual_value_gradient_hessian_multivariate() -> None:
    def function(point):
        x, y = point
        return x * x * y + hyperdual_sin(y)

    report = value_gradient_hessian(function, (2.0, 0.5))
    assert report.value == pytest.approx(2.0 + math.sin(0.5))
    assert report.gradient == pytest.approx((2.0, 4.0 + math.cos(0.5)), abs=1e-12)
    assert report.hessian[0] == pytest.approx((1.0, 4.0), abs=1e-12)
    assert report.hessian[1] == pytest.approx((4.0, -math.sin(0.5)), abs=1e-12)
    assert report.symmetry_linf <= 1e-12


def test_orthogonal_polynomial_recurrences_and_chebyshev_fit() -> None:
    assert legendre_p(3, 0.25) == pytest.approx(0.5 * (5.0 * 0.25**3 - 3.0 * 0.25))
    assert probabilists_hermite(4, 2.0) == pytest.approx(2.0**4 - 6.0 * 2.0**2 + 3.0)

    series = fit_chebyshev_series(lambda x: x**3 - 2.0 * x + 1.0, 3, lower=-2.0, upper=3.0)
    for point in (-2.0, -0.5, 0.0, 1.75, 3.0):
        assert series.evaluate(point) == pytest.approx(point**3 - 2.0 * point + 1.0, abs=1e-11)
