"""One fixed timestep for wind, foliage/fabric drag, and droplet mass.

Any sub-step failure restores the previous state. Droplet volume is advanced
only by ``advance_liquid``. The particle is advanced by ``integrate_air_motion``
in air sampled by ``airflow_at`` / ``sample_atmosphere``, with the thermal
column taken from ``evolve_microclimate``. Horizontal drag is an equal-and-
opposite impulse between the particle and the wind slab.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from skeleton.jeeves.game_frontier_advanced_physics import (
    AeroProfile,
    RigidBody,
    TractionSurface,
    airflow_at,
    integrate_air_motion,
)
from skeleton.jeeves.game_frontier_ecosystem import (
    AirConditions,
    LiquidGrid,
    advance_liquid,
    sample_atmosphere,
)
from skeleton.jeeves.game_frontier_motion import Weather
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_weather_physics import Microclimate, evolve_microclimate
from skeleton.simulation.physics.gameplay import GamePhysicsProfile

from skeleton.frontier_weather.contracts import (
    AUTHORITATIVE_DT_S,
    COUPLED_MOMENTUM_EPSILON,
    DROPLET_MASS_EPSILON_KG,
    LIQUID_FLOW_RATE,
    SCHEME,
    WATER_DENSITY_KG_M3,
    WeatherPhysicsError,
    canonical_json,
)
from skeleton.frontier_weather.wind import (
    WindField,
    cell_mass_kg,
    field_kinetic_energy,
    field_momentum,
    step_turbulence,
)

_FAULTS = frozenset({"after_wind", "after_thermal", "after_particle", "after_liquid"})


def bilinear_weights(
    x_m: float, y_m: float, cell_size_m: float, nx: int, ny: int
) -> tuple[tuple[int, int, float], ...]:
    """Periodic bilinear weights on cell centers ``(i+0.5)*dx``. Normalized to 1."""
    gx = (x_m / cell_size_m - 0.5) % nx
    gy = (y_m / cell_size_m - 0.5) % ny
    i0 = int(math.floor(gx))
    j0 = int(math.floor(gy))
    tx = gx - i0
    ty = gy - j0
    raw = (
        (i0 % nx, j0 % ny, (1.0 - tx) * (1.0 - ty)),
        ((i0 + 1) % nx, j0 % ny, tx * (1.0 - ty)),
        (i0 % nx, (j0 + 1) % ny, (1.0 - tx) * ty),
        ((i0 + 1) % nx, (j0 + 1) % ny, tx * ty),
    )
    total = raw[0][2] + raw[1][2] + raw[2][2] + raw[3][2]
    if total <= 0.0 or not math.isfinite(total):
        raise WeatherPhysicsError("wind sample weights vanished")
    return tuple((i, j, weight / total) for i, j, weight in raw)


def _sample_wind(field: WindField, x_m: float, y_m: float) -> tuple[float, float]:
    spec = field.spec
    weights = bilinear_weights(x_m, y_m, spec.cell_size_m, spec.nx, spec.ny)
    u_value = 0.0
    v_value = 0.0
    for i, j, weight in weights:
        u_value += weight * field.velocity_u[j][i]
        v_value += weight * field.velocity_v[j][i]
    return u_value, v_value


def _apply_horizontal_impulse(
    field: WindField, x_m: float, y_m: float, impulse_x: float, impulse_y: float
) -> WindField:
    spec = field.spec
    cell_mass = cell_mass_kg(spec)
    weights = bilinear_weights(x_m, y_m, spec.cell_size_m, spec.nx, spec.ny)
    rows_u = [list(row) for row in field.velocity_u]
    rows_v = [list(row) for row in field.velocity_v]
    for i, j, weight in weights:
        rows_u[j][i] += weight * impulse_x / cell_mass
        rows_v[j][i] += weight * impulse_y / cell_mass
    updated = replace(
        field,
        velocity_u=tuple(tuple(row) for row in rows_u),
        velocity_v=tuple(tuple(row) for row in rows_v),
    )
    return updated


@dataclass(frozen=True)
class DragParticle:
    """Foliage, fabric, and entrained debris treated as one drag body."""

    role: str
    mass_kg: float
    position: Vec3
    velocity: Vec3
    drag_coefficient: float
    area_m2: float
    radius_m: float

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or not self.role or len(self.role) > 128:
            raise WeatherPhysicsError("drag particle role required")
        if type(self.mass_kg) not in (int, float) or not math.isfinite(self.mass_kg):
            raise WeatherPhysicsError("particle mass must be finite")
        if not 0.001 <= float(self.mass_kg) <= 1_000_000:
            raise WeatherPhysicsError("particle mass outside the air integrator envelope")
        if not isinstance(self.position, Vec3) or not isinstance(self.velocity, Vec3):
            raise WeatherPhysicsError("particle kinematics must be Vec3")


@dataclass(frozen=True)
class MarathonState:
    wind: WindField
    particle: DragParticle
    droplets: LiquidGrid
    air: AirConditions
    weather: Weather
    microclimate: Microclimate
    traction: TractionSurface
    step_index: int
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.wind, WindField):
            raise WeatherPhysicsError("marathon state requires a wind field")
        if not isinstance(self.particle, DragParticle):
            raise WeatherPhysicsError("marathon state requires a drag particle")
        if not isinstance(self.droplets, LiquidGrid):
            raise WeatherPhysicsError("marathon state requires a liquid grid")
        if not isinstance(self.air, AirConditions):
            raise WeatherPhysicsError("marathon state requires air")
        if not isinstance(self.weather, Weather):
            raise WeatherPhysicsError("marathon state requires weather")
        if not isinstance(self.microclimate, Microclimate):
            raise WeatherPhysicsError("marathon state requires a microclimate")
        if not isinstance(self.traction, TractionSurface):
            raise WeatherPhysicsError("marathon state requires traction")
        if type(self.step_index) is not int or self.step_index < 0:
            raise WeatherPhysicsError("step index must be a non-negative integer")
        if type(self.seed) is not int or self.seed < 0 or self.seed >= 2**63:
            raise WeatherPhysicsError("seed must be a fixed non-negative integer")


@dataclass(frozen=True)
class StepReceipt:
    authoritative_dt_s: float
    step_index: int
    seed: int
    scheme: str
    air_density_kg_m3: float
    kinetic_energy_j: float
    particle_kinetic_energy_j: float
    droplet_mass_kg: float
    droplet_mass_residual_kg: float
    droplet_mass_epsilon_kg: float
    coupled_momentum_residual_x: float
    coupled_momentum_residual_y: float
    coupled_momentum_epsilon: float
    thermal_updraft_mps: float
    internal_liquid_flux_m3: float
    canonical: str


class AuthoritativeWeatherClock:
    """Fixed-step clock. ``advance`` never accepts a caller-chosen ``dt``."""

    def __init__(self, state: MarathonState) -> None:
        if not isinstance(state, MarathonState):
            raise WeatherPhysicsError("clock requires marathon weather state")
        self._state = state

    @property
    def state(self) -> MarathonState:
        return self._state

    def advance(self, *, fault: str | None = None) -> StepReceipt:
        if fault is not None and fault not in _FAULTS:
            raise WeatherPhysicsError("unknown substep fault")
        previous = self._state
        try:
            proposed, receipt = self._propose(previous, fault)
        except Exception:
            self._state = previous
            raise
        self._state = proposed
        return receipt

    def _propose(self, state: MarathonState, fault: str | None) -> tuple[MarathonState, StepReceipt]:
        dt = AUTHORITATIVE_DT_S
        wind_step = step_turbulence(state.wind, dt_s=dt)
        if fault == "after_wind":
            raise WeatherPhysicsError("substep failed: after_wind")
        thermal = evolve_microclimate(
            state.microclimate,
            state.weather,
            state.air,
            state.traction,
            delta_s=dt,
            location=state.particle.position,
        )
        if fault == "after_thermal":
            raise WeatherPhysicsError("substep failed: after_thermal")
        sampled_u, sampled_v = _sample_wind(
            wind_step.field, state.particle.position.x, state.particle.position.y
        )
        airflow = airflow_at(
            state.particle.position,
            ambient_wind=Vec3(sampled_u, sampled_v, 0.0),
            air=state.air,
            thermals=(thermal.terrain_updraft,),
            turbulence_seed=state.seed,
            time_s=state.step_index * dt,
            turbulence_amplitude=0.0,
        )
        body = RigidBody(
            state.particle.role,
            state.particle.position,
            state.particle.velocity,
            state.particle.mass_kg,
            state.particle.radius_m,
        )
        profile = AeroProfile(state.particle.drag_coefficient, state.particle.area_m2)
        aero = integrate_air_motion(body, profile, airflow, delta_s=dt)
        if fault == "after_particle":
            raise WeatherPhysicsError("substep failed: after_particle")
        drag_ix = aero.drag_force_n.x * dt
        drag_iy = aero.drag_force_n.y * dt
        gained_x = state.particle.mass_kg * (aero.body.velocity.x - state.particle.velocity.x)
        gained_y = state.particle.mass_kg * (aero.body.velocity.y - state.particle.velocity.y)
        if (
            abs(gained_x - drag_ix) > COUPLED_MOMENTUM_EPSILON
            or abs(gained_y - drag_iy) > COUPLED_MOMENTUM_EPSILON
        ):
            raise WeatherPhysicsError("particle momentum left the drag impulse")
        reacted = _apply_horizontal_impulse(
            wind_step.field,
            state.particle.position.x,
            state.particle.position.y,
            -drag_ix,
            -drag_iy,
        )
        liquid = advance_liquid(
            state.droplets,
            delta_s=dt,
            rain_mm_h=0.0,
            evaporation_mm_h=0.0,
            flow_rate=LIQUID_FLOW_RATE,
        )
        if fault == "after_liquid":
            raise WeatherPhysicsError("substep failed: after_liquid")
        mass_before = state.droplets.volume_m3 * WATER_DENSITY_KG_M3
        mass_after = liquid.grid.volume_m3 * WATER_DENSITY_KG_M3
        accounted = (liquid.rain_added_m3 - liquid.evaporation_removed_m3) * WATER_DENSITY_KG_M3
        mass_gap = mass_after - mass_before - accounted
        mass_residual = liquid.mass_residual_m3 * WATER_DENSITY_KG_M3
        if abs(mass_gap) > DROPLET_MASS_EPSILON_KG or abs(mass_residual) > DROPLET_MASS_EPSILON_KG:
            raise WeatherPhysicsError("droplet mass left the stated epsilon")
        before_x, before_y = field_momentum(state.wind)
        after_x, after_y = field_momentum(reacted)
        particle_before_x = state.particle.mass_kg * state.particle.velocity.x
        particle_before_y = state.particle.mass_kg * state.particle.velocity.y
        particle_after_x = state.particle.mass_kg * aero.body.velocity.x
        particle_after_y = state.particle.mass_kg * aero.body.velocity.y
        residual_x = (
            (after_x + particle_after_x) - (before_x + particle_before_x) - (wind_step.momentum_x - before_x)
        )
        residual_y = (
            (after_y + particle_after_y) - (before_y + particle_before_y) - (wind_step.momentum_y - before_y)
        )
        if abs(residual_x) > COUPLED_MOMENTUM_EPSILON or abs(residual_y) > COUPLED_MOMENTUM_EPSILON:
            raise WeatherPhysicsError("coupled momentum left the stated epsilon")
        new_particle = replace(state.particle, position=aero.body.position, velocity=aero.body.velocity)
        proposed = MarathonState(
            wind=reacted,
            particle=new_particle,
            droplets=liquid.grid,
            air=state.air,
            weather=state.weather,
            microclimate=thermal.state,
            traction=thermal.traction_surface,
            step_index=state.step_index + 1,
            seed=state.seed,
        )
        density = sample_atmosphere(state.air).density_kg_m3
        speed = math.hypot(new_particle.velocity.x, new_particle.velocity.y, new_particle.velocity.z)
        payload = {
            "air_density_kg_m3": density,
            "authoritative_dt_s": dt,
            "coupled_momentum_epsilon": COUPLED_MOMENTUM_EPSILON,
            "coupled_momentum_residual_x": residual_x,
            "coupled_momentum_residual_y": residual_y,
            "droplet_mass_epsilon_kg": DROPLET_MASS_EPSILON_KG,
            "droplet_mass_kg": mass_after,
            "droplet_mass_residual_kg": mass_residual,
            "internal_liquid_flux_m3": liquid.internal_flux_m3,
            "kinetic_energy_j": field_kinetic_energy(reacted),
            "particle_kinetic_energy_j": GamePhysicsProfile.kinetic_energy(new_particle.mass_kg, speed),
            "scheme": SCHEME,
            "seed": state.seed,
            "step_index": proposed.step_index,
            "thermal_updraft_mps": thermal.terrain_updraft.vertical_velocity_mps,
        }
        receipt = StepReceipt(
            authoritative_dt_s=dt,
            step_index=proposed.step_index,
            seed=state.seed,
            scheme=SCHEME,
            air_density_kg_m3=density,
            kinetic_energy_j=payload["kinetic_energy_j"],
            particle_kinetic_energy_j=payload["particle_kinetic_energy_j"],
            droplet_mass_kg=mass_after,
            droplet_mass_residual_kg=mass_residual,
            droplet_mass_epsilon_kg=DROPLET_MASS_EPSILON_KG,
            coupled_momentum_residual_x=residual_x,
            coupled_momentum_residual_y=residual_y,
            coupled_momentum_epsilon=COUPLED_MOMENTUM_EPSILON,
            thermal_updraft_mps=thermal.terrain_updraft.vertical_velocity_mps,
            internal_liquid_flux_m3=liquid.internal_flux_m3,
            canonical=canonical_json(payload),
        )
        return proposed, receipt
