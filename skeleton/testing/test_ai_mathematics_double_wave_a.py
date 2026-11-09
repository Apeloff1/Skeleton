from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    bfgs,
    check_gradient,
    damped_newton,
    finite_difference_jacobian,
    principal_components,
    richardson_derivative,
    symmetric_eigensystem,
    adaptive_rk45,
)


def test_full_symmetric_eigensystem_reconstructs_matrix() -> None:
    matrix = (
        (4.0, 1.0, 1.0),
        (1.0, 3.0, 0.0),
        (1.0, 0.0, 2.0),
    )
    report = symmetric_eigensystem(matrix)
    assert report.converged
    assert report.orthogonality_linf <= 1e-10
    assert report.reconstruction_linf <= 1e-10
    assert report.eigenvalues == tuple(sorted(report.eigenvalues, reverse=True))


def test_pca_finds_single_line_component_and_reconstructs() -> None:
    observations = tuple((x, 2.0 * x + 1.0) for x in (-2.0, -1.0, 0.0, 1.0, 2.0))
    report = principal_components(observations, components=1)
    assert report.explained_variance_ratio[0] == pytest.approx(1.0, abs=1e-12)
    assert report.reconstruction_linf <= 1e-10


def test_richardson_derivative_improves_central_difference() -> None:
    report = richardson_derivative(math.sin, 0.7, step=1e-2)
    expected = math.cos(0.7)
    assert report.derivative == pytest.approx(expected, abs=1e-9)
    assert abs(report.derivative - expected) <= abs(report.coarse_estimate - expected)


def test_finite_difference_jacobian_recovers_vector_map() -> None:
    report = finite_difference_jacobian(
        lambda point: (point[0] * point[1], point[0] ** 2 + math.sin(point[1])),
        (2.0, 0.5),
    )
    assert report.jacobian[0] == pytest.approx((0.5, 2.0), abs=1e-6)
    assert report.jacobian[1] == pytest.approx((4.0, math.cos(0.5)), abs=1e-6)


def test_gradient_check_distinguishes_correct_and_wrong_gradient() -> None:
    function = lambda point: (point[0] - 3.0) ** 2 + 2.0 * (point[1] + 1.0) ** 2
    point = (1.5, -0.25)
    correct = (2.0 * (point[0] - 3.0), 4.0 * (point[1] + 1.0))
    report = check_gradient(function, point, correct)
    assert report.passed
    wrong = check_gradient(function, point, (correct[0] + 0.1, correct[1]))
    assert not wrong.passed


def test_damped_newton_and_bfgs_converge_on_strict_convex_quadratic() -> None:
    function = lambda point: (point[0] - 4.0) ** 2 + 3.0 * (point[1] + 2.0) ** 2
    gradient = lambda point: (2.0 * (point[0] - 4.0), 6.0 * (point[1] + 2.0))
    hessian = lambda _point: ((2.0, 0.0), (0.0, 6.0))

    newton = damped_newton(function, (20.0, 10.0), gradient=gradient, hessian=hessian)
    assert newton.converged
    assert newton.point == pytest.approx((4.0, -2.0), abs=1e-8)

    quasi = bfgs(function, (20.0, 10.0), gradient=gradient)
    assert quasi.converged
    assert quasi.point == pytest.approx((4.0, -2.0), abs=1e-6)


def test_adaptive_rk45_tracks_exponential_with_fewer_than_fixed_microsteps() -> None:
    report = adaptive_rk45(
        lambda _time, state: state,
        0.0,
        1.0,
        (1.0,),
        initial_step=0.05,
        absolute_tolerance=1e-10,
        relative_tolerance=1e-9,
    )
    assert report.converged
    assert report.points[-1].time == pytest.approx(1.0)
    assert report.points[-1].state[0] == pytest.approx(math.e, rel=2e-9)
    assert report.accepted_steps < 100
    assert report.function_evaluations == 7 * (report.accepted_steps + report.rejected_steps)
