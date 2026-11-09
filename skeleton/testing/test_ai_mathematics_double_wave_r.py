from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    advection_upwind_periodic,
    centered_l2_discrepancy,
    detailed_balance_report,
    diffusion_explicit_periodic,
    dobrushin_coefficient,
    great_circle_distance,
    latin_hypercube,
    mixing_profile,
    scale_unit_design,
    sphere_exp_map,
    sphere_log_map,
    spherical_interpolate,
    wave_leapfrog_periodic,
)


def test_periodic_pde_schemes_obey_reference_invariants() -> None:
    pulse = (1.0, 0.0, 0.0, 0.0)
    shifted = advection_upwind_periodic(
        pulse,
        velocity=1.0,
        spacing=1.0,
        time_step=1.0,
        steps=1,
    )
    assert shifted.final_state == pytest.approx((0.0, 1.0, 0.0, 0.0))

    constant = (3.0, 3.0, 3.0, 3.0, 3.0)
    diffused = diffusion_explicit_periodic(
        constant,
        diffusivity=0.5,
        spacing=1.0,
        time_step=0.5,
        steps=5,
    )
    assert diffused.final_state == pytest.approx(constant, abs=1e-12)

    wave = wave_leapfrog_periodic(
        constant,
        (0.0,) * len(constant),
        wave_speed=1.0,
        spacing=1.0,
        time_step=0.5,
        steps=4,
    )
    assert wave.final_state == pytest.approx(constant, abs=1e-12)


def test_spherical_log_exp_and_interpolation_are_consistent() -> None:
    x = (1.0, 0.0, 0.0)
    y = (0.0, 1.0, 0.0)
    assert great_circle_distance(x, y) == pytest.approx(math.pi / 2.0)
    tangent = sphere_log_map(x, y)
    assert tangent == pytest.approx((0.0, math.pi / 2.0, 0.0), abs=1e-12)
    restored = sphere_exp_map(x, tangent)
    assert restored == pytest.approx(y, abs=1e-12)
    midpoint = spherical_interpolate(x, y, 0.5)
    root_half = math.sqrt(0.5)
    assert midpoint == pytest.approx((root_half, root_half, 0.0), abs=1e-12)


def test_markov_detailed_balance_and_mixing_profile() -> None:
    transition = ((0.9, 0.1), (0.2, 0.8))
    balance = detailed_balance_report(transition)
    assert balance.stationary == pytest.approx((2.0 / 3.0, 1.0 / 3.0), abs=1e-10)
    assert balance.maximum_flux_residual <= 1e-10
    assert balance.reversible
    assert dobrushin_coefficient(transition) == pytest.approx(0.7)
    with pytest.raises(MathInvariantError, match="positive mass"):
        detailed_balance_report(transition, stationary=(0.0, 0.0))

    mixing = mixing_profile(transition, (1.0, 0.0), steps=20, tolerance=1e-3)
    assert mixing.distances[-1] < mixing.distances[0]
    assert all(
        right <= left + 1e-12
        for left, right in zip(mixing.distances, mixing.distances[1:])
    )
    assert mixing.mixing_step is not None


def test_latin_hypercube_has_one_point_per_stratum_per_dimension() -> None:
    report = latin_hypercube(8, 3, seed=42, centered=True)
    assert report.minimum_pairwise_distance > 0.0
    assert report.centered_l2_discrepancy == pytest.approx(
        centered_l2_discrepancy(report.points)
    )
    for axis in range(3):
        strata = sorted(int(point[axis] * 8) for point in report.points)
        assert strata == list(range(8))

    scaled = scale_unit_design(report.points, ((-1.0, 1.0), (10.0, 20.0), (100.0, 200.0)))
    assert all(-1.0 <= point[0] <= 1.0 for point in scaled)
    assert all(10.0 <= point[1] <= 20.0 for point in scaled)
    assert all(100.0 <= point[2] <= 200.0 for point in scaled)
