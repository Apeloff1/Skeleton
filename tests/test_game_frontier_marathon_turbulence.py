"""Independent finite-difference checks for the marathon weather slice.

The reference below reimplements the documented log profile, terrain
speed-up, shed vortex, and FTCS step. It does not call the package stepper.
"""

from __future__ import annotations

import inspect
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from skeleton.frontier_weather import (
    AUTHORITATIVE_DT_S,
    COUPLED_MOMENTUM_EPSILON,
    DROPLET_MASS_EPSILON_KG,
    ENERGY_DRIFT_BOUND,
    FIXED_SEED,
    MIN_HORIZON_STEPS,
    VON_KARMAN,
    WATER_DENSITY_KG_M3,
    AuthoritativeWeatherClock,
    EnergyDriftError,
    WeatherPhysicsError,
    build_boundary_layer,
    canonical_json,
    enforce_energy_drift,
    field_kinetic_energy,
    map_weather_to_surface,
    reference_boundary_spec,
    reference_marathon_state,
    step_turbulence,
)
from skeleton.frontier_weather.contracts import LIQUID_FLOW_RATE
from skeleton.jeeves.game_frontier_ecosystem import (
    AirConditions,
    advance_liquid,
    sample_atmosphere,
)
from skeleton.jeeves.game_frontier_motion import Weather
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_weather_physics import Microclimate, evolve_microclimate
from skeleton.jeeves.game_frontier_advanced_physics import TractionSurface


def _direction(spec):
    scale = math.hypot(spec.direction_x, spec.direction_y)
    return spec.direction_x / scale, spec.direction_y / scale


def _shortest(origin, target, length):
    delta = (origin - target) % length
    if delta > length * 0.5:
        delta -= length
    return delta


def _clamp_speedup(value):
    if value < 0.25:
        return 0.25
    if value > 4.0:
        return 4.0
    return value


def _crest(terrain):
    crest = 0
    best = terrain[0]
    for index, height in enumerate(terrain):
        if height > best:
            best = height
            crest = index
    return crest


def independent_initial(spec):
    """Finite-difference / analytic reference for the diagnostic wind field."""
    direction_x, direction_y = _direction(spec)
    log_speed = (spec.friction_velocity_m_s / 0.41) * math.log(
        (spec.z_ref_m + spec.roughness_m) / spec.roughness_m
    )
    floor = min(spec.terrain_m)
    speedup = [
        _clamp_speedup(1.0 + spec.speedup_gain * (height - floor) / spec.speedup_length_m)
        for height in spec.terrain_m
    ]
    crest = _crest(spec.terrain_m)
    crest_i = crest % spec.nx
    crest_j = crest // spec.nx
    length_x = spec.nx * spec.cell_size_m
    length_y = spec.ny * spec.cell_size_m
    vortex_x = ((crest_i + 0.5) * spec.cell_size_m + direction_x * spec.shed_distance_m) % length_x
    vortex_y = ((crest_j + 0.5) * spec.cell_size_m + direction_y * spec.shed_distance_m) % length_y
    gamma = spec.circulation_gain * log_speed * speedup[crest] * spec.cell_size_m
    two_pi = 2.0 * math.pi
    core_sq = spec.core_radius_m * spec.core_radius_m
    rows_u = []
    rows_v = []
    for j in range(spec.ny):
        row_u = []
        row_v = []
        for i in range(spec.nx):
            center_x = (i + 0.5) * spec.cell_size_m
            center_y = (j + 0.5) * spec.cell_size_m
            offset_x = _shortest(center_x, vortex_x, length_x)
            offset_y = _shortest(center_y, vortex_y, length_y)
            denom = offset_x * offset_x + offset_y * offset_y + core_sq
            induced_u = -(gamma / two_pi) * offset_y / denom
            induced_v = (gamma / two_pi) * offset_x / denom
            factor = speedup[j * spec.nx + i] * log_speed
            row_u.append(factor * direction_x + induced_u)
            row_v.append(factor * direction_y + induced_v)
        rows_u.append(row_u)
        rows_v.append(row_v)
    return (
        rows_u,
        rows_v,
        {
            "log_speed": log_speed,
            "gamma": gamma,
            "vortex_x": vortex_x,
            "vortex_y": vortex_y,
            "crest": crest,
        },
    )


def independent_step(rows_u, rows_v, spec, dt):
    """Periodic central-difference FTCS step and its momentum residual."""
    dx = spec.cell_size_m
    nu = spec.viscosity_m2_s
    nx, ny = spec.nx, spec.ny
    inv_two_dx = 1.0 / (2.0 * dx)
    inv_dx2 = 1.0 / (dx * dx)
    density = sample_atmosphere(spec.air).density_kg_m3
    mass = density * dx * dx * spec.slab_thickness_m
    next_u = [[0.0] * nx for _ in range(ny)]
    next_v = [[0.0] * nx for _ in range(ny)]
    sum_u = 0.0
    sum_v = 0.0
    sum_u2 = 0.0
    sum_v2 = 0.0
    sum_accel_u = 0.0
    sum_accel_v = 0.0
    residual_sq = 0.0
    for j in range(ny):
        for i in range(nx):
            west = (i - 1) % nx
            east = (i + 1) % nx
            south = (j - 1) % ny
            north = (j + 1) % ny
            u_value = rows_u[j][i]
            v_value = rows_v[j][i]
            dudx = (rows_u[j][east] - rows_u[j][west]) * inv_two_dx
            dudy = (rows_u[north][i] - rows_u[south][i]) * inv_two_dx
            dvdx = (rows_v[j][east] - rows_v[j][west]) * inv_two_dx
            dvdy = (rows_v[north][i] - rows_v[south][i]) * inv_two_dx
            lap_u = (
                rows_u[j][east] + rows_u[j][west] + rows_u[north][i] + rows_u[south][i] - 4.0 * u_value
            ) * inv_dx2
            lap_v = (
                rows_v[j][east] + rows_v[j][west] + rows_v[north][i] + rows_v[south][i] - 4.0 * v_value
            ) * inv_dx2
            adv_u = u_value * dudx + v_value * dudy
            adv_v = u_value * dvdx + v_value * dvdy
            accel_u = nu * lap_u - adv_u
            accel_v = nu * lap_v - adv_v
            updated_u = u_value + dt * accel_u
            updated_v = v_value + dt * accel_v
            next_u[j][i] = updated_u
            next_v[j][i] = updated_v
            sum_u += u_value
            sum_v += v_value
            sum_u2 += updated_u
            sum_v2 += updated_v
            sum_accel_u += accel_u
            sum_accel_v += accel_v
            residual_u = (updated_u - u_value) / dt - accel_u
            residual_v = (updated_v - v_value) / dt - accel_v
            residual_sq += residual_u * residual_u + residual_v * residual_v
    momentum_before_x = mass * sum_u
    momentum_before_y = mass * sum_v
    momentum_after_x = mass * sum_u2
    momentum_after_y = mass * sum_v2
    residual_x = momentum_after_x - momentum_before_x - mass * dt * sum_accel_u
    residual_y = momentum_after_y - momentum_before_y - mass * dt * sum_accel_v
    rms = math.sqrt(residual_sq / float(nx * ny))
    return next_u, next_v, residual_x, residual_y, rms, momentum_after_x, momentum_after_y


def _kinetic(rows_u, rows_v, spec):
    density = sample_atmosphere(spec.air).density_kg_m3
    mass = density * spec.cell_size_m * spec.cell_size_m * spec.slab_thickness_m
    total = 0.0
    for row_u, row_v in zip(rows_u, rows_v):
        for u_value, v_value in zip(row_u, row_v):
            total += 0.5 * mass * (u_value * u_value + v_value * v_value)
    return total


def _rows(field):
    return [list(row) for row in field.velocity_u], [list(row) for row in field.velocity_v]


def _assert_velocity(field, rows_u, rows_v):
    for row_u, row_v, ref_u, ref_v in zip(field.velocity_u, field.velocity_v, rows_u, rows_v):
        for u_value, v_value, expect_u, expect_v in zip(row_u, row_v, ref_u, ref_v):
            assert u_value == pytest.approx(expect_u, abs=1e-12, rel=1e-12)
            assert v_value == pytest.approx(expect_v, abs=1e-12, rel=1e-12)


def test_rejects_nan_negative_viscosity_and_nonpositive_cell_size():
    spec = reference_boundary_spec()
    with pytest.raises(WeatherPhysicsError):
        build_boundary_layer(replace(spec, viscosity_m2_s=float("nan")))
    with pytest.raises(WeatherPhysicsError):
        build_boundary_layer(replace(spec, viscosity_m2_s=-0.2))
    with pytest.raises(WeatherPhysicsError):
        build_boundary_layer(replace(spec, cell_size_m=0.0))
    with pytest.raises(WeatherPhysicsError):
        build_boundary_layer(replace(spec, cell_size_m=-4.0))
    field = build_boundary_layer(spec)
    with pytest.raises(WeatherPhysicsError):
        step_turbulence(field, dt_s=float("nan"))
    with pytest.raises(WeatherPhysicsError):
        step_turbulence(field, dt_s=0.0)


def test_log_profile_speedup_and_shed_vortex_against_reference():
    assert VON_KARMAN == 0.41
    spec = reference_boundary_spec()
    flat = replace(
        spec,
        terrain_m=tuple(0.0 for _ in range(spec.nx * spec.ny)),
        circulation_gain=0.0,
        shed_distance_m=0.0,
    )
    field = build_boundary_layer(flat)
    rows_u, rows_v, meta = independent_initial(flat)
    _assert_velocity(field, rows_u, rows_v)
    assert field.log_speed_m_s == pytest.approx(meta["log_speed"], rel=1e-12)
    for row_u, row_v in zip(field.velocity_u, field.velocity_v):
        for u_value, v_value in zip(row_u, row_v):
            assert u_value == pytest.approx(meta["log_speed"], rel=1e-12)
            assert v_value == pytest.approx(0.0, abs=1e-12)

    ridge = replace(spec, circulation_gain=0.0)
    ridge_field = build_boundary_layer(ridge)
    crest = ridge_field.crest_index
    crest_i = crest % ridge.nx
    crest_j = crest // ridge.nx
    crest_speed = math.hypot(
        ridge_field.velocity_u[crest_j][crest_i], ridge_field.velocity_v[crest_j][crest_i]
    )
    edge_speed = math.hypot(ridge_field.velocity_u[0][0], ridge_field.velocity_v[0][0])
    assert crest_speed > edge_speed

    spinning = replace(
        spec,
        terrain_m=tuple(0.0 for _ in range(spec.nx * spec.ny)),
        circulation_gain=0.8,
        shed_distance_m=0.0,
    )
    vortex = build_boundary_layer(spinning)
    ref_u, ref_v, vortex_meta = independent_initial(spinning)
    _assert_velocity(vortex, ref_u, ref_v)
    assert vortex.velocity_v[0][1] > 0.0
    assert vortex.velocity_v[0][spinning.nx - 1] < 0.0
    assert vortex.vortex_gamma_m2_s == pytest.approx(vortex_meta["gamma"], rel=1e-12)

    shed = build_boundary_layer(spec)
    shed_meta = independent_initial(spec)[2]
    assert shed.vortex_x_m == pytest.approx(shed_meta["vortex_x"], abs=1e-12)
    assert shed.vortex_y_m == pytest.approx(shed_meta["vortex_y"], abs=1e-12)
    crest_x = (shed.crest_index % spec.nx + 0.5) * spec.cell_size_m
    assert shed.vortex_x_m > crest_x
    assert shed.vortex_gamma_m2_s > 0.0


def test_kinetic_energy_and_momentum_residual_match_finite_difference():
    spec = reference_boundary_spec()
    field = build_boundary_layer(spec)
    rows_u, rows_v, _meta = independent_initial(spec)
    _assert_velocity(field, rows_u, rows_v)
    initial_reference = _kinetic(rows_u, rows_v, spec)
    initial_solver = field_kinetic_energy(field)
    assert initial_solver == pytest.approx(initial_reference, rel=1e-12)

    stepped = step_turbulence(field, dt_s=AUTHORITATIVE_DT_S)
    ref_u, ref_v, res_x, res_y, rms, mom_x, mom_y = independent_step(rows_u, rows_v, spec, AUTHORITATIVE_DT_S)
    _assert_velocity(stepped.field, ref_u, ref_v)
    assert stepped.kinetic_energy_j == pytest.approx(_kinetic(ref_u, ref_v, spec), rel=1e-12)
    assert stepped.momentum_residual_x == pytest.approx(res_x, abs=1e-8)
    assert stepped.momentum_residual_y == pytest.approx(res_y, abs=1e-8)
    assert stepped.momentum_residual_rms == pytest.approx(rms, abs=1e-12)
    assert abs(stepped.momentum_residual_x) < 1e-6
    assert abs(res_x) < 1e-6
    assert abs(res_y) < 1e-6
    assert stepped.momentum_x == pytest.approx(mom_x, rel=1e-12, abs=1e-8)
    assert stepped.momentum_y == pytest.approx(mom_y, rel=1e-12, abs=1e-8)
    assert stepped.dt_s == AUTHORITATIVE_DT_S


def test_authoritative_step_holds_mass_and_coupled_momentum():
    clock = AuthoritativeWeatherClock(reference_marathon_state())
    before = clock.state
    signature = inspect.signature(AuthoritativeWeatherClock.advance)
    assert "dt" not in signature.parameters
    assert "delta_s" not in signature.parameters
    direct_liquid = advance_liquid(
        before.droplets,
        delta_s=AUTHORITATIVE_DT_S,
        rain_mm_h=0.0,
        evaporation_mm_h=0.0,
        flow_rate=LIQUID_FLOW_RATE,
    )
    direct_thermal = evolve_microclimate(
        before.microclimate,
        before.weather,
        before.air,
        before.traction,
        delta_s=AUTHORITATIVE_DT_S,
        location=before.particle.position,
    )
    receipt = clock.advance()
    after = clock.state
    assert after.droplets == direct_liquid.grid
    assert direct_liquid.internal_flux_m3 > 0.0
    mass_gap = abs(after.droplets.volume_m3 - before.droplets.volume_m3) * WATER_DENSITY_KG_M3
    assert mass_gap <= DROPLET_MASS_EPSILON_KG
    assert abs(receipt.droplet_mass_residual_kg) <= receipt.droplet_mass_epsilon_kg
    assert receipt.droplet_mass_epsilon_kg == DROPLET_MASS_EPSILON_KG
    assert receipt.internal_liquid_flux_m3 == direct_liquid.internal_flux_m3
    assert receipt.thermal_updraft_mps == direct_thermal.terrain_updraft.vertical_velocity_mps
    assert receipt.air_density_kg_m3 == sample_atmosphere(before.air).density_kg_m3
    assert receipt.authoritative_dt_s == AUTHORITATIVE_DT_S
    assert receipt.seed == FIXED_SEED
    assert after.step_index == 1
    assert after.particle.velocity.x > 0.0

    rows_u, rows_v = _rows(before.wind)
    ref_u, ref_v, _rx, _ry, _rms, pde_x, pde_y = independent_step(
        rows_u, rows_v, before.wind.spec, AUTHORITATIVE_DT_S
    )
    del ref_u, ref_v
    density = sample_atmosphere(before.wind.spec.air).density_kg_m3
    mass = density * before.wind.spec.cell_size_m**2 * before.wind.spec.slab_thickness_m
    wind_after_u = 0.0
    wind_after_v = 0.0
    for row_u, row_v in zip(after.wind.velocity_u, after.wind.velocity_v):
        wind_after_u += sum(row_u)
        wind_after_v += sum(row_v)
    residual_x = (
        mass * wind_after_u
        - pde_x
        + after.particle.mass_kg * (after.particle.velocity.x - before.particle.velocity.x)
    )
    residual_y = (
        mass * wind_after_v
        - pde_y
        + after.particle.mass_kg * (after.particle.velocity.y - before.particle.velocity.y)
    )
    assert abs(residual_x) <= COUPLED_MOMENTUM_EPSILON
    assert abs(residual_y) <= COUPLED_MOMENTUM_EPSILON
    assert abs(receipt.coupled_momentum_residual_x) <= receipt.coupled_momentum_epsilon
    assert abs(receipt.coupled_momentum_residual_y) <= receipt.coupled_momentum_epsilon
    again = clock.advance()
    assert again.authoritative_dt_s == AUTHORITATIVE_DT_S
    assert again.step_index == 2
    parsed = json.loads(receipt.canonical)
    assert receipt.canonical == canonical_json(parsed)
    assert " " not in receipt.canonical
    assert "\n" not in receipt.canonical


def test_substep_failure_restores_previous_state():
    clock = AuthoritativeWeatherClock(reference_marathon_state())
    before = clock.state
    for fault in ("after_wind", "after_thermal", "after_particle", "after_liquid"):
        with pytest.raises(WeatherPhysicsError):
            clock.advance(fault=fault)
        assert clock.state is before
    with pytest.raises(WeatherPhysicsError):
        clock.advance(fault="not-a-substep")
    assert clock.state is before
    clock.advance()
    assert clock.state.step_index == 1
    assert clock.state is not before


def test_surface_map_is_pure_and_repeatable():
    clock = AuthoritativeWeatherClock(reference_marathon_state())
    state = clock.state
    world = {"canonical_world": "untouched", "friction": 0.0}
    world_snapshot = dict(world)
    micro = state.microclimate
    traction = state.traction
    first = map_weather_to_surface(state.weather, state.air, micro, traction)
    second = map_weather_to_surface(state.weather, state.air, micro, traction)
    assert first == second
    assert clock.state is state
    assert state.microclimate is micro
    assert state.traction is traction
    assert world == world_snapshot
    assert micro.soil_water_fraction == 0.1

    air = AirConditions()
    base = Microclimate(
        terrain_temperature_c=8.0,
        soil_water_fraction=0.1,
        ground_ice_fraction=0.0,
        loose_sediment_fraction=0.1,
        surface_roughness=0.6,
        vegetation_cover=0.3,
    )
    grip = TractionSurface(Vec3(0.0, 0.0, 1.0), 1.0, 0.75)
    rainy = Weather(Vec3(4.0, 0.0, 0.0), 10.0, precipitation_mm_h=800.0, sunlight=0.1)
    dry = Weather(Vec3(1.0, 0.0, 0.0), 18.0, precipitation_mm_h=0.0, sunlight=1.0)
    wet_surface = map_weather_to_surface(rainy, air, base, grip)
    dry_surface = map_weather_to_surface(dry, air, base, grip)
    assert wet_surface == map_weather_to_surface(rainy, air, base, grip)
    assert wet_surface.friction < dry_surface.friction
    assert wet_surface.damage_rate_per_s > dry_surface.damage_rate_per_s
    assert wet_surface.surface_temperature_c != dry_surface.surface_temperature_c
    assert base.terrain_temperature_c == 8.0
    assert grip.wetness == 0.0
    assert wet_surface.authority.startswith("derived_surface_response")


def test_long_horizon_energy_drift_against_reference():
    spec = reference_boundary_spec()
    field = build_boundary_layer(spec)
    rows_u, rows_v, _meta = independent_initial(spec)
    solver_series = []
    reference_series = []
    for _ in range(MIN_HORIZON_STEPS):
        field = step_turbulence(field, dt_s=AUTHORITATIVE_DT_S).field
        rows_u, rows_v, _rx, _ry, _rms, _mx, _my = independent_step(rows_u, rows_v, spec, AUTHORITATIVE_DT_S)
        solver_u, solver_v = _rows(field)
        solver_series.append(_kinetic(solver_u, solver_v, spec))
        reference_series.append(_kinetic(rows_u, rows_v, spec))
    assert len(solver_series) >= 120
    receipt = enforce_energy_drift(solver_series, reference_series, seed=FIXED_SEED)
    assert receipt.steps == MIN_HORIZON_STEPS
    assert receipt.bound == ENERGY_DRIFT_BOUND
    assert receipt.max_relative_drift <= ENERGY_DRIFT_BOUND
    assert receipt.seed == FIXED_SEED
    parsed = json.loads(receipt.canonical)
    assert parsed["passed"] is True
    assert parsed["seed"] == FIXED_SEED
    assert parsed["steps"] >= 120
    assert " " not in receipt.canonical

    with pytest.raises(EnergyDriftError):
        enforce_energy_drift(solver_series[:119], reference_series[:119], seed=FIXED_SEED)
    drifted = [value + 1.0 for value in reference_series]
    with pytest.raises(EnergyDriftError, match="documented bound"):
        enforce_energy_drift(solver_series, drifted, seed=FIXED_SEED)


def test_canonical_json_rejects_nan_and_repeat_runs_share_the_seed():
    payload = {"b": 1, "a": 0.05}
    text = canonical_json(payload)
    assert text == '{"a":0.05,"b":1}'
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})
    first = build_boundary_layer(reference_boundary_spec())
    second = build_boundary_layer(reference_boundary_spec())
    assert first.velocity_u == second.velocity_u
    assert first.velocity_v == second.velocity_v
    assert first.spec.seed == FIXED_SEED
    left = AuthoritativeWeatherClock(reference_marathon_state()).advance()
    right = AuthoritativeWeatherClock(reference_marathon_state()).advance()
    assert left.canonical == right.canonical
    assert json.loads(left.canonical)["seed"] == FIXED_SEED


def test_package_sources_do_not_use_a_wall_clock_or_rng():
    root = Path(__file__).resolve().parents[1] / "skeleton" / "frontier_weather"
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py")))
    assert "NotImplemented" not in text
    assert "import random" not in text
    assert "time.time" not in text
    assert "datetime" not in text


def test_thermal_plume_changes_the_foliage_particle():
    neutral = reference_marathon_state()
    hot_micro = Microclimate(
        terrain_temperature_c=42.0,
        soil_water_fraction=0.1,
        ground_ice_fraction=0.0,
        loose_sediment_fraction=0.1,
        surface_roughness=0.2,
        vegetation_cover=0.1,
        ground_heat_flux_w_m2=850.0,
    )
    hot = replace(neutral, microclimate=hot_micro)
    cold_clock = AuthoritativeWeatherClock(neutral)
    cold_receipt = cold_clock.advance()
    hot_clock = AuthoritativeWeatherClock(hot)
    hot_receipt = hot_clock.advance()
    assert hot_receipt.thermal_updraft_mps > 0.0
    assert hot_receipt.thermal_updraft_mps != cold_receipt.thermal_updraft_mps
    assert hot_clock.state.particle.velocity.z != cold_clock.state.particle.velocity.z
    assert hot_clock.state.particle.role == "foliage_fabric"
