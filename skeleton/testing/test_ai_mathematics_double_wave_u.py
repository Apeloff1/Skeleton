from __future__ import annotations

import pytest

from skeleton.ai.mathematics import (
    burgers_finite_volume,
    linear_advection_finite_volume,
    solve_box_quadratic_active_set,
    solve_equality_constrained_qp,
)


def test_equality_qp_satisfies_kkt_system() -> None:
    hessian = ((2.0, 0.0), (0.0, 2.0))
    linear = (-2.0, -4.0)
    report = solve_equality_constrained_qp(
        hessian,
        linear,
        ((1.0, 1.0),),
        (2.0,),
    )
    assert report.solution == pytest.approx((0.5, 1.5), abs=1e-12)
    assert report.primal_residual_linf <= 1e-12
    assert report.stationarity_residual_linf <= 1e-12


def test_box_qp_active_set_finds_boundary_solution() -> None:
    report = solve_box_quadratic_active_set(
        ((2.0, 0.0), (0.0, 2.0)),
        (-6.0, 4.0),
        (0.0, -1.0),
        (2.0, 3.0),
    )
    assert report.converged
    assert report.solution == pytest.approx((2.0, -1.0), abs=1e-12)
    assert report.active_upper == (0,)
    assert report.active_lower == (1,)
    assert report.projected_gradient_linf <= 1e-10


def test_linear_advection_finite_volume_is_exact_shift_at_unit_cfl() -> None:
    state = (1.0, 0.0, 0.0, 0.0)
    report = linear_advection_finite_volume(
        state,
        velocity=1.0,
        spacing=1.0,
        time_step=1.0,
        steps=1,
    )
    assert report.final_state == pytest.approx((0.0, 1.0, 0.0, 0.0))
    assert report.mass_drift == pytest.approx(0.0, abs=1e-14)
    assert report.maximum_cfl == pytest.approx(1.0)


def test_burgers_rusanov_preserves_periodic_mass() -> None:
    report = burgers_finite_volume(
        (0.2, 0.4, 0.8, 0.3, -0.1),
        spacing=1.0,
        time_step=0.25,
        steps=8,
    )
    assert report.mass_drift == pytest.approx(0.0, abs=1e-12)
    assert report.maximum_cfl <= 1.0
