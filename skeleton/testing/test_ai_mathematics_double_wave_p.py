from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    anderson_accelerate,
    apply_diagonal_scaling,
    controllability_gramian,
    controllability_report,
    discretize_zero_order_hold,
    equilibrate_matrix,
    fixed_point_iteration,
    integrate_rectangle_2d,
    observability_gramian,
    observability_report,
    tensor_gauss_legendre_cubature,
)


def test_controllability_observability_and_discretization_reference_cases() -> None:
    system = ((0.0, 1.0), (-2.0, -3.0))
    input_matrix = ((0.0,), (1.0,))
    output_matrix = ((1.0, 0.0),)
    assert controllability_report(system, input_matrix).full_rank
    assert observability_report(system, output_matrix).full_rank

    integrator = ((0.0, 1.0), (0.0, 0.0))
    discrete = discretize_zero_order_hold(integrator, ((0.0,), (1.0,)), 0.1)
    assert discrete.state_matrix[0] == pytest.approx((1.0, 0.1), abs=1e-12)
    assert discrete.state_matrix[1] == pytest.approx((0.0, 1.0), abs=1e-12)
    assert discrete.input_matrix[0] == pytest.approx((0.005,), abs=1e-12)
    assert discrete.input_matrix[1] == pytest.approx((0.1,), abs=1e-12)


def test_controllability_and_observability_gramians_match_diagonal_closed_form() -> None:
    system = ((-1.0, 0.0), (0.0, -2.0))
    identity = ((1.0, 0.0), (0.0, 1.0))
    controllability = controllability_gramian(system, identity)
    observability = observability_gramian(system, identity)
    for report in (controllability, observability):
        assert report.gramian[0] == pytest.approx((0.5, 0.0), abs=1e-12)
        assert report.gramian[1] == pytest.approx((0.0, 0.25), abs=1e-12)
        assert report.residual_linf <= 1e-12
        assert report.positive_definite


def test_matrix_equilibration_reconstructs_scaled_matrix_and_normalizes_support() -> None:
    matrix = ((1e-6, 1.0), (2.0, 1e4))
    report = equilibrate_matrix(matrix, tolerance=1e-7)
    assert report.converged
    reconstructed = apply_diagonal_scaling(matrix, report.left_scale, report.right_scale)
    for actual, expected in zip(report.scaled_matrix, reconstructed):
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)
    assert report.maximum_row_norm_error <= 1e-7
    assert report.maximum_column_norm_error <= 1e-7


def test_anderson_acceleration_converges_at_least_as_well_as_plain_iteration() -> None:
    mapping = lambda point: (math.cos(point[0]),)
    plain = fixed_point_iteration(mapping, (1.0,), tolerance=1e-10, max_iterations=500)
    accelerated = anderson_accelerate(mapping, (1.0,), tolerance=1e-10, max_iterations=100)
    assert plain.converged
    assert accelerated.converged
    assert accelerated.solution[0] == pytest.approx(0.7390851332151607, abs=1e-9)
    assert accelerated.iterations < plain.iterations


def test_tensor_gauss_legendre_cubature_integrates_polynomials_exactly() -> None:
    report = integrate_rectangle_2d(
        lambda x, y: x * x + 3.0 * y,
        (-1.0, 1.0),
        (0.0, 2.0),
        order=3,
    )
    expected = (2.0 / 3.0) * 2.0 + 2.0 * 6.0
    assert report.estimate == pytest.approx(expected, abs=1e-12)

    cube = tensor_gauss_legendre_cubature(
        lambda point: point[0] * point[1] * point[2] + 1.0,
        ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0)),
        order=2,
    )
    assert cube.estimate == pytest.approx(1.125, abs=1e-12)
    assert cube.evaluations == 8
