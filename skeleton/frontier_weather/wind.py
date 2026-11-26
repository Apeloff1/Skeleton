"""Boundary-layer wind on a fixed periodic grid.

The diagnostic field is a logarithmic profile, a linear terrain speed-up,
and one regularized vortex shed downstream of the ridge crest. Each
turbulence step is forward Euler with central advection and a five-point
Laplacian. Density comes from ``sample_atmosphere``. Cell kinetic energy
uses ``GamePhysicsProfile.kinetic_energy``. This module does not integrate a
free surface; droplet mass stays with ``advance_liquid``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from skeleton.jeeves.game_frontier_ecosystem import AirConditions, sample_atmosphere
from skeleton.simulation.physics.gameplay import GamePhysicsProfile

from skeleton.frontier_weather.contracts import (
    MAX_CFL,
    MAX_EXPLICIT_DT_S,
    SCHEME,
    SPEEDUP_MAX,
    SPEEDUP_MIN,
    VON_KARMAN,
    WeatherPhysicsError,
    require_real,
)


def _unit_direction(direction_x: float, direction_y: float) -> tuple[float, float]:
    scale = math.hypot(direction_x, direction_y)
    if scale <= 0.0 or not math.isfinite(scale):
        raise WeatherPhysicsError("wind direction must be non-zero")
    return direction_x / scale, direction_y / scale


def _shortest_delta(origin: float, target: float, length: float) -> float:
    """Signed distance from target to origin, in ``(-length/2, length/2]``."""
    delta = (origin - target) % length
    if delta > length * 0.5:
        delta -= length
    return delta


def _clamp_speedup(value: float) -> float:
    if value < SPEEDUP_MIN:
        return SPEEDUP_MIN
    if value > SPEEDUP_MAX:
        return SPEEDUP_MAX
    return value


def _first_crest(terrain: tuple[float, ...]) -> int:
    crest = 0
    best = terrain[0]
    for index, height in enumerate(terrain):
        if height > best:
            best = height
            crest = index
    return crest


@dataclass(frozen=True)
class BoundaryLayerSpec:
    """Inputs for one fixed-grid boundary layer. ``seed`` is recorded, not drawn."""

    nx: int
    ny: int
    cell_size_m: float
    viscosity_m2_s: float
    roughness_m: float
    friction_velocity_m_s: float
    z_ref_m: float
    slab_thickness_m: float
    direction_x: float
    direction_y: float
    terrain_m: tuple[float, ...]
    speedup_gain: float
    speedup_length_m: float
    circulation_gain: float
    core_radius_m: float
    shed_distance_m: float
    air: AirConditions
    seed: int = 174329

    def __post_init__(self) -> None:
        if type(self.nx) is not int or type(self.ny) is not int:
            raise WeatherPhysicsError("grid dimensions must be integers")
        if not 3 <= self.nx <= 32 or not 3 <= self.ny <= 32:
            raise WeatherPhysicsError("grid dimensions must be in 3..32")
        require_real(self.cell_size_m, "cell_size_m", lo=0.0, hi=10000.0, inclusive_lo=False)
        require_real(self.viscosity_m2_s, "viscosity_m2_s", lo=0.0, hi=1.0e6)
        require_real(self.roughness_m, "roughness_m", lo=0.0, hi=100.0, inclusive_lo=False)
        require_real(self.friction_velocity_m_s, "friction_velocity_m_s", lo=0.0, hi=50.0)
        require_real(self.z_ref_m, "z_ref_m", lo=0.0, hi=5000.0, inclusive_lo=False)
        require_real(self.slab_thickness_m, "slab_thickness_m", lo=0.0, hi=5000.0, inclusive_lo=False)
        require_real(self.direction_x, "direction_x", lo=-1.0e6, hi=1.0e6)
        require_real(self.direction_y, "direction_y", lo=-1.0e6, hi=1.0e6)
        _unit_direction(self.direction_x, self.direction_y)
        if len(self.terrain_m) != self.nx * self.ny:
            raise WeatherPhysicsError("terrain length must equal nx*ny")
        for height in self.terrain_m:
            require_real(height, "terrain_m", lo=-1000.0, hi=9000.0)
        require_real(self.speedup_gain, "speedup_gain", lo=0.0, hi=5.0)
        require_real(self.speedup_length_m, "speedup_length_m", lo=0.0, hi=1.0e6, inclusive_lo=False)
        require_real(self.circulation_gain, "circulation_gain", lo=-20.0, hi=20.0)
        require_real(self.core_radius_m, "core_radius_m", lo=0.0, hi=1.0e5, inclusive_lo=False)
        require_real(self.shed_distance_m, "shed_distance_m", lo=0.0, hi=1.0e6)
        if not isinstance(self.air, AirConditions):
            raise WeatherPhysicsError("air must be AirConditions")
        if type(self.seed) is not int or self.seed < 0 or self.seed >= 2**63:
            raise WeatherPhysicsError("seed must be a fixed non-negative integer")


@dataclass(frozen=True)
class WindField:
    spec: BoundaryLayerSpec
    velocity_u: tuple[tuple[float, ...], ...]
    velocity_v: tuple[tuple[float, ...], ...]
    vortex_x_m: float
    vortex_y_m: float
    vortex_gamma_m2_s: float
    log_speed_m_s: float
    crest_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.spec, BoundaryLayerSpec):
            raise WeatherPhysicsError("wind field requires a boundary-layer spec")
        nx, ny = self.spec.nx, self.spec.ny
        if len(self.velocity_u) != ny or len(self.velocity_v) != ny:
            raise WeatherPhysicsError("velocity rows must match ny")
        for row_u, row_v in zip(self.velocity_u, self.velocity_v):
            if len(row_u) != nx or len(row_v) != nx:
                raise WeatherPhysicsError("velocity columns must match nx")
            for value in row_u + row_v:
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise WeatherPhysicsError("velocity must be finite")
        for name, value in (
            ("vortex_x_m", self.vortex_x_m),
            ("vortex_y_m", self.vortex_y_m),
            ("vortex_gamma_m2_s", self.vortex_gamma_m2_s),
            ("log_speed_m_s", self.log_speed_m_s),
        ):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise WeatherPhysicsError(f"{name} must be finite")
        if type(self.crest_index) is not int or not 0 <= self.crest_index < nx * ny:
            raise WeatherPhysicsError("crest index out of range")


@dataclass(frozen=True)
class TurbulenceStep:
    field: WindField
    kinetic_energy_j: float
    momentum_x: float
    momentum_y: float
    momentum_residual_x: float
    momentum_residual_y: float
    momentum_residual_rms: float
    dt_s: float
    scheme: str = SCHEME


def cell_mass_kg(spec: BoundaryLayerSpec) -> float:
    """Slab mass of one cell from the existing atmosphere sample."""
    density = sample_atmosphere(spec.air).density_kg_m3
    if not math.isfinite(density) or density <= 0.0:
        raise WeatherPhysicsError("atmosphere density must be positive")
    return density * spec.cell_size_m * spec.cell_size_m * spec.slab_thickness_m


def field_momentum(field: WindField) -> tuple[float, float]:
    mass = cell_mass_kg(field.spec)
    total_u = 0.0
    total_v = 0.0
    for row_u, row_v in zip(field.velocity_u, field.velocity_v):
        for u_value, v_value in zip(row_u, row_v):
            total_u += u_value
            total_v += v_value
    return mass * total_u, mass * total_v


def field_kinetic_energy(field: WindField) -> float:
    """Sum of simulation-physics kinetic energies over the slab cells."""
    mass = cell_mass_kg(field.spec)
    total = 0.0
    for row_u, row_v in zip(field.velocity_u, field.velocity_v):
        for u_value, v_value in zip(row_u, row_v):
            total += GamePhysicsProfile.kinetic_energy(mass, math.hypot(u_value, v_value))
    return total


def build_boundary_layer(spec: BoundaryLayerSpec) -> WindField:
    """Log profile, terrain speed-up, and one vortex shed from the ridge."""
    if not isinstance(spec, BoundaryLayerSpec):
        raise WeatherPhysicsError("boundary-layer spec required")
    # Touch the atmosphere solver up front so a bad air state fails closed.
    cell_mass_kg(spec)
    direction_x, direction_y = _unit_direction(spec.direction_x, spec.direction_y)
    log_speed = (spec.friction_velocity_m_s / VON_KARMAN) * math.log(
        (spec.z_ref_m + spec.roughness_m) / spec.roughness_m
    )
    if not math.isfinite(log_speed) or log_speed < 0.0:
        raise WeatherPhysicsError("logarithmic speed must be finite and non-negative")
    floor = min(spec.terrain_m)
    speedup = tuple(
        _clamp_speedup(1.0 + spec.speedup_gain * (height - floor) / spec.speedup_length_m)
        for height in spec.terrain_m
    )
    crest = _first_crest(spec.terrain_m)
    crest_i = crest % spec.nx
    crest_j = crest // spec.nx
    length_x = spec.nx * spec.cell_size_m
    length_y = spec.ny * spec.cell_size_m
    vortex_x = ((crest_i + 0.5) * spec.cell_size_m + direction_x * spec.shed_distance_m) % length_x
    vortex_y = ((crest_j + 0.5) * spec.cell_size_m + direction_y * spec.shed_distance_m) % length_y
    gamma = spec.circulation_gain * log_speed * speedup[crest] * spec.cell_size_m
    two_pi = 2.0 * math.pi
    core_sq = spec.core_radius_m * spec.core_radius_m
    rows_u: list[tuple[float, ...]] = []
    rows_v: list[tuple[float, ...]] = []
    for j in range(spec.ny):
        row_u: list[float] = []
        row_v: list[float] = []
        for i in range(spec.nx):
            center_x = (i + 0.5) * spec.cell_size_m
            center_y = (j + 0.5) * spec.cell_size_m
            offset_x = _shortest_delta(center_x, vortex_x, length_x)
            offset_y = _shortest_delta(center_y, vortex_y, length_y)
            denom = offset_x * offset_x + offset_y * offset_y + core_sq
            induced_u = -(gamma / two_pi) * offset_y / denom
            induced_v = (gamma / two_pi) * offset_x / denom
            factor = speedup[j * spec.nx + i] * log_speed
            u_value = factor * direction_x + induced_u
            v_value = factor * direction_y + induced_v
            if not math.isfinite(u_value) or not math.isfinite(v_value):
                raise WeatherPhysicsError("boundary-layer velocity became non-finite")
            row_u.append(u_value)
            row_v.append(v_value)
        rows_u.append(tuple(row_u))
        rows_v.append(tuple(row_v))
    return WindField(
        spec=spec,
        velocity_u=tuple(rows_u),
        velocity_v=tuple(rows_v),
        vortex_x_m=vortex_x,
        vortex_y_m=vortex_y,
        vortex_gamma_m2_s=gamma,
        log_speed_m_s=log_speed,
        crest_index=crest,
    )


def step_turbulence(field: WindField, *, dt_s: float) -> TurbulenceStep:
    """One explicit FTCS step. Momentum residual is the discrete force imbalance."""
    if not isinstance(field, WindField):
        raise WeatherPhysicsError("wind field required")
    dt = require_real(dt_s, "dt_s", lo=0.0, hi=MAX_EXPLICIT_DT_S, inclusive_lo=False)
    spec = field.spec
    dx = spec.cell_size_m
    nu = spec.viscosity_m2_s
    nx, ny = spec.nx, spec.ny
    inv_two_dx = 1.0 / (2.0 * dx)
    inv_dx2 = 1.0 / (dx * dx)
    max_speed = 0.0
    for row_u, row_v in zip(field.velocity_u, field.velocity_v):
        for u_value, v_value in zip(row_u, row_v):
            max_speed = max(max_speed, math.hypot(u_value, v_value))
    cfl = dt * max_speed / dx + 4.0 * nu * dt * inv_dx2
    if not math.isfinite(cfl) or cfl > MAX_CFL:
        raise WeatherPhysicsError("turbulence step exceeds the documented CFL bound")
    mass = cell_mass_kg(spec)
    momentum_before_x, momentum_before_y = field_momentum(field)
    next_u = [[0.0] * nx for _ in range(ny)]
    next_v = [[0.0] * nx for _ in range(ny)]
    sum_accel_u = 0.0
    sum_accel_v = 0.0
    residual_sq = 0.0
    for j in range(ny):
        for i in range(nx):
            west = (i - 1) % nx
            east = (i + 1) % nx
            south = (j - 1) % ny
            north = (j + 1) % ny
            u_value = field.velocity_u[j][i]
            v_value = field.velocity_v[j][i]
            dudx = (field.velocity_u[j][east] - field.velocity_u[j][west]) * inv_two_dx
            dudy = (field.velocity_u[north][i] - field.velocity_u[south][i]) * inv_two_dx
            dvdx = (field.velocity_v[j][east] - field.velocity_v[j][west]) * inv_two_dx
            dvdy = (field.velocity_v[north][i] - field.velocity_v[south][i]) * inv_two_dx
            lap_u = (
                field.velocity_u[j][east]
                + field.velocity_u[j][west]
                + field.velocity_u[north][i]
                + field.velocity_u[south][i]
                - 4.0 * u_value
            ) * inv_dx2
            lap_v = (
                field.velocity_v[j][east]
                + field.velocity_v[j][west]
                + field.velocity_v[north][i]
                + field.velocity_v[south][i]
                - 4.0 * v_value
            ) * inv_dx2
            adv_u = u_value * dudx + v_value * dudy
            adv_v = u_value * dvdx + v_value * dvdy
            accel_u = nu * lap_u - adv_u
            accel_v = nu * lap_v - adv_v
            updated_u = u_value + dt * accel_u
            updated_v = v_value + dt * accel_v
            if not math.isfinite(updated_u) or not math.isfinite(updated_v):
                raise WeatherPhysicsError("turbulence step produced a non-finite velocity")
            next_u[j][i] = updated_u
            next_v[j][i] = updated_v
            sum_accel_u += accel_u
            sum_accel_v += accel_v
            residual_u = (updated_u - u_value) / dt - accel_u
            residual_v = (updated_v - v_value) / dt - accel_v
            residual_sq += residual_u * residual_u + residual_v * residual_v
    updated = replace(
        field,
        velocity_u=tuple(tuple(row) for row in next_u),
        velocity_v=tuple(tuple(row) for row in next_v),
    )
    momentum_after_x, momentum_after_y = field_momentum(updated)
    impulse_x = mass * dt * sum_accel_u
    impulse_y = mass * dt * sum_accel_v
    return TurbulenceStep(
        field=updated,
        kinetic_energy_j=field_kinetic_energy(updated),
        momentum_x=momentum_after_x,
        momentum_y=momentum_after_y,
        momentum_residual_x=momentum_after_x - momentum_before_x - impulse_x,
        momentum_residual_y=momentum_after_y - momentum_before_y - impulse_y,
        momentum_residual_rms=math.sqrt(residual_sq / float(nx * ny)),
        dt_s=dt,
    )
