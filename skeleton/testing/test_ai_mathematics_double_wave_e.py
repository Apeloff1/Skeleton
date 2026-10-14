from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    conditional_entropy_y_given_x,
    explicit_diffusion_stable_step,
    first_derivative_grid,
    gauss_legendre_integrate,
    gauss_legendre_rule,
    gini_impurity,
    least_norm_solve,
    mutual_information,
    pseudoinverse,
    renyi_entropy,
    second_derivative_grid,
    singular_value_decomposition,
    solve_poisson_dirichlet_1d,
    tsallis_entropy,
    variation_of_information,
)


def test_svd_reconstructs_rectangular_matrix_and_pseudoinverse_identity() -> None:
    matrix = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0))
    report = singular_value_decomposition(matrix)
    assert report.rank == 2
    assert report.reconstruction_linf <= 1e-9
    assert report.condition_number is not None and report.condition_number > 1.0

    pinv = pseudoinverse(matrix)
    assert pinv.rank == 2
    assert pinv.projection_residual_linf <= 1e-9


def test_least_norm_solve_handles_underdetermined_system() -> None:
    matrix = ((1.0, 0.0, 1.0), (0.0, 1.0, 1.0))
    solution = least_norm_solve(matrix, (1.0, 1.0))
    assert solution == pytest.approx((1.0 / 3.0, 1.0 / 3.0, 2.0 / 3.0), abs=1e-9)


def test_gauss_legendre_integrates_polynomial_exactly_at_expected_degree() -> None:
    rule = gauss_legendre_rule(4)
    assert sum(rule.weights) == pytest.approx(2.0, abs=1e-14)
    report = gauss_legendre_integrate(lambda x: x**7 - 2.0 * x**4 + 3.0, -1.0, 1.0, order=4)
    expected = -4.0 / 5.0 + 6.0
    assert report.estimate == pytest.approx(expected, abs=1e-13)
    assert report.evaluations == 4


def test_finite_difference_grid_derivatives_recover_quadratics() -> None:
    h = 0.1
    xs = tuple(index * h for index in range(8))
    values = tuple(x * x + 2.0 * x + 1.0 for x in xs)
    first = first_derivative_grid(values, h)
    second = second_derivative_grid(values, h)
    assert first == pytest.approx(tuple(2.0 * x + 2.0 for x in xs), abs=1e-12)
    assert second == pytest.approx((2.0,) * len(xs), abs=1e-11)


def test_poisson_dirichlet_solution_has_small_discrete_residual() -> None:
    # -u'' = 2 with u(0)=u(1)=0 => u=x(1-x).
    interior = 9
    h = 1.0 / (interior + 1)
    report = solve_poisson_dirichlet_1d((2.0,) * interior, h)
    expected = tuple((index * h) * (1.0 - index * h) for index in range(interior + 2))
    assert report.solution == pytest.approx(expected, abs=1e-12)
    assert report.residual_linf <= 1e-12
    assert explicit_diffusion_stable_step(h, 1.0) == pytest.approx(h * h / 2.0)


def test_generalized_entropy_and_joint_information_reference_cases() -> None:
    p = (0.5, 0.5)
    assert renyi_entropy(p, 2.0) == pytest.approx(math.log(2.0))
    assert tsallis_entropy(p, 2.0) == pytest.approx(0.5)
    assert gini_impurity(p) == pytest.approx(0.5)

    independent = ((0.25, 0.25), (0.25, 0.25))
    assert mutual_information(independent) == pytest.approx(0.0, abs=1e-15)
    assert conditional_entropy_y_given_x(independent) == pytest.approx(math.log(2.0))
    assert variation_of_information(independent) == pytest.approx(2.0 * math.log(2.0))

    identical = ((0.5, 0.0), (0.0, 0.5))
    assert mutual_information(identical) == pytest.approx(math.log(2.0))
    assert variation_of_information(identical) == pytest.approx(0.0, abs=1e-15)
