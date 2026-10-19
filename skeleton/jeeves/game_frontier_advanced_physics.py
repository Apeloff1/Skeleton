"""Reference game physics: terminal velocity, wakes, updrafts, climbing and impulses.

This supplements Jeeves' existing deterministic physics owners without changing
authoritative game state. SI units: metres, kilograms, seconds, newtons.
Contact impulse solver supports moving bodies, infinite-mass terrain, friction,
spin, restitution and penetration correction. Atmospheric models share the
existing frontier weather sampling. No CFD, FEM, or native engine parity claim.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math

from .game_frontier_production import Vec3
from .game_frontier_ecosystem import AirConditions, sample_atmosphere

G0 = 9.80665
ZERO = Vec3(0, 0, 0)


class AdvancedPhysicsError(ValueError):
    pass


def finite(x: float, name: str, lo: float = -1e8, hi: float = 1e8) -> float:
    if type(x) not in (int, float) or not math.isfinite(x) or not lo <= x <= hi:
        raise AdvancedPhysicsError(f"{name} must be finite between {lo} and {hi}")
    return float(x)


def vecnorm(v: Vec3) -> float:
    return math.sqrt(v.dot(v))


def unit(v: Vec3) -> Vec3:
    n = vecnorm(v)
    if n < 1e-10:
        raise AdvancedPhysicsError("direction vector cannot be zero")
    return v.scaled(1 / n)


def clamp(x: float, lo: float = 0., hi: float = 1.) -> float:
    return max(lo, min(hi, x))


def kinetic_energy(body: "RigidBody") -> float:
    return .5 * body.mass_kg * body.velocity.dot(body.velocity) + (
        .5 * body.inertia_kg_m2 * body.angular_velocity.dot(body.angular_velocity)
    )


@dataclass(frozen=True)
class RigidBody:
    body_id: str
    position: Vec3
    velocity: Vec3
    mass_kg: float
    radius_m: float
    restitution: float = .15
    friction: float = .6
    angular_velocity: Vec3 = ZERO

    def __post_init__(self) -> None:
        if not self.body_id or len(self.body_id) > 128:
            raise AdvancedPhysicsError("body id required")
        finite(self.mass_kg, "mass", .001, 1000000)
        finite(self.radius_m, "radius", .001, 1000)
        finite(self.restitution, "restitution", 0, 1)
        finite(self.friction, "friction", 0, 3)
        if vecnorm(self.velocity) > 10000 or vecnorm(self.angular_velocity) > 10000:
            raise AdvancedPhysicsError("body speed bound exceeded")

    @property
    def inertia_kg_m2(self) -> float:
        return .4 * self.mass_kg * self.radius_m ** 2


@dataclass(frozen=True)
class WakeSource:
    source_id: str
    center: Vec3
    radius_m: float
    strength: float
    length_m: float

    def __post_init__(self) -> None:
        if not self.source_id or len(self.source_id) > 128:
            raise AdvancedPhysicsError("wake source id required")
        finite(self.radius_m, "wake radius", .01, 1000)
        finite(self.strength, "wake strength", 0, .95)
        finite(self.length_m, "wake length", .01, 10000)


@dataclass(frozen=True)
class UpdraftColumn:
    center: Vec3
    radius_m: float
    vertical_velocity_mps: float
    height_m: float

    def __post_init__(self) -> None:
        finite(self.radius_m, "updraft radius", .1, 10000)
        finite(self.vertical_velocity_mps, "updraft speed", -100, 100)
        finite(self.height_m, "updraft height", .1, 100000)


@dataclass(frozen=True)
class Airflow:
    wind: Vec3
    air_density_kg_m3: float
    wake_drag_multiplier: float
    updraft_mps: float
    turbulence: Vec3
    altitude_m: float

    def __post_init__(self) -> None:
        finite(self.air_density_kg_m3, "density", .01, 10)
        finite(self.wake_drag_multiplier, "wake drag", .01, 1)
        finite(self.updraft_mps, "updraft", -100, 100)


def airflow_at(
    position: Vec3, *,
    ambient_wind: Vec3,
    air: AirConditions,
    wakes: tuple[WakeSource, ...] = (),
    thermals: tuple[UpdraftColumn, ...] = (),
    turbulence_seed: int = 0,
    time_s: float = 0.,
    turbulence_amplitude: float = 0.,
) -> Airflow:
    """Wake shielding is downwind, not spherical; thermals attenuate in XYZ.

    Deterministic lattice-independent gust sample, no stochastic global state.
    Wake reduces the effective aerodynamic coefficient and wind at the
    sheltered object; it does NOT increase energy or guarantee safety.
    """
    if len(wakes) > 128 or len(thermals) > 128:
        raise AdvancedPhysicsError("airflow field budget exceeded")
    if type(turbulence_seed) is not int or not 0 <= turbulence_seed < 2**63:
        raise AdvancedPhysicsError("turbulence seed invalid")
    t = finite(time_s, "time_s", 0, 1e9)
    amplitude = finite(turbulence_amplitude, "turbulence amplitude", 0, 50)
    altitude = finite(air.altitude_m + position.z, "absolute altitude", -500, 11000)
    local_air = replace(air, altitude_m=altitude)
    density = sample_atmosphere(local_air).density_kg_m3
    wind_speed = vecnorm(ambient_wind)
    direction = unit(ambient_wind) if wind_speed > 1e-9 else ZERO
    wake_factor = 1.
    for wake in wakes:
        displacement = position - wake.center
        downstream = displacement.dot(direction)
        if downstream <= 0 or downstream >= wake.length_m:
            continue
        radial = vecnorm(displacement - direction.scaled(downstream))
        width = wake.radius_m * (1 + downstream / wake.length_m)
        if radial >= width:
            continue
        local = wake.strength * (1 - downstream / wake.length_m) * (
            1 - (radial / width) ** 2)
        wake_factor *= (1 - local)
    wake_factor = clamp(wake_factor, .05, 1.)
    thermal_velocity = 0.
    for column in thermals:
        displacement = position - column.center
        radial2 = displacement.x**2 + displacement.y**2
        relative_height = displacement.z
        if 0 <= relative_height <= column.height_m:
            thermal_velocity += column.vertical_velocity_mps * math.exp(
                -radial2 / (2 * column.radius_m**2)) * (
                    1 - relative_height / column.height_m)
    thermal_velocity = finite(thermal_velocity, "cumulative thermal", -100, 100)
    # Position/time/seed-deterministic continuous wave gust, bounded by amplitude.
    seed_phase = (turbulence_seed % 1009) * .0137
    gust = Vec3(
        math.sin(position.x*.083 + t*.37 + seed_phase),
        math.cos(position.y*.071 - t*.29 + seed_phase),
        math.sin(position.z*.041 + t*.43 + seed_phase),
    ).scaled(amplitude / math.sqrt(3))
    local_wind = ambient_wind.scaled(wake_factor) + gust + Vec3(0, 0, thermal_velocity)
    return Airflow(local_wind, density, wake_factor, thermal_velocity, gust, altitude)


@dataclass(frozen=True)
class AeroProfile:
    drag_coefficient: float
    projected_area_m2: float
    lift_coefficient: float = 0.
    lift_area_m2: float = 0.
    max_acceleration_mps2: float = 150.

    def __post_init__(self) -> None:
        finite(self.drag_coefficient, "drag coefficient", .001, 5)
        finite(self.projected_area_m2, "projected area", .001, 10000)
        finite(self.lift_coefficient, "lift coefficient", -5, 5)
        finite(self.lift_area_m2, "lift area", 0, 10000)
        finite(self.max_acceleration_mps2, "acceleration ceiling", .1, 1000)


@dataclass(frozen=True)
class AerodynamicStep:
    body: RigidBody
    relative_air_speed_mps: float
    drag_force_n: Vec3
    lift_force_n: Vec3
    gravitational_force_n: Vec3
    terminal_speed_mps: float
    wake_multiplier: float
    updraft_mps: float
    mechanical_energy_j: float
    drag_dissipation_j: float
    authority: str = "candidate_reference_air_motion_not_engine_executed"


def terminal_velocity(mass_kg: float, density_kg_m3: float, drag_coefficient: float,
                      area_m2: float, *, gravity_mps2: float = G0) -> float:
    """Ideal stationary-air vertical terminal speed (no lift)."""
    m = finite(mass_kg, "mass", .001, 1e6)
    rho = finite(density_kg_m3, "air density", .001, 10)
    cd = finite(drag_coefficient, "Cd", .001, 10)
    area = finite(area_m2, "area", .001, 10000)
    g = finite(gravity_mps2, "gravity", 0, 100)
    return math.sqrt(2 * m * g / (rho * cd * area))


def integrate_air_motion(
    body: RigidBody, profile: AeroProfile, airflow: Airflow, *,
    delta_s: float, gravity_mps2: float = G0,
) -> AerodynamicStep:
    dt = finite(delta_s, "air step", 0, .1)
    g = finite(gravity_mps2, "gravity", 0, 100)
    relative = body.velocity - airflow.wind
    speed = vecnorm(relative)
    drag = relative.scaled(
        -.5 * airflow.air_density_kg_m3 * profile.drag_coefficient
        * profile.projected_area_m2 * speed * airflow.wake_drag_multiplier
    )
    # Simplified vertical lift response to relative horizontal slipstream.
    horizontal = math.hypot(relative.x, relative.y)
    lift = Vec3(0, 0, .5 * airflow.air_density_kg_m3
                * horizontal**2 * profile.lift_coefficient * profile.lift_area_m2)
    gravity = Vec3(0, 0, -body.mass_kg * g)
    acceleration = (drag + lift + gravity).scaled(1 / body.mass_kg)
    amount = vecnorm(acceleration)
    if amount > profile.max_acceleration_mps2:
        acceleration = acceleration.scaled(profile.max_acceleration_mps2 / amount)
    velocity = body.velocity + acceleration.scaled(dt)
    position = body.position + (body.velocity + velocity).scaled(.5 * dt)
    new_body = replace(body, position=position, velocity=velocity)
    effective_cd = profile.drag_coefficient * airflow.wake_drag_multiplier
    tv = terminal_velocity(body.mass_kg, airflow.air_density_kg_m3,
                           effective_cd, profile.projected_area_m2,
                           gravity_mps2=g)
    # Aerodynamic drag always dissipates relative flow energy; wind can
    # exchange kinetic energy with the body, so no claim of total decline.
    dissipated = max(0., -drag.dot(relative) * dt)
    return AerodynamicStep(new_body, speed, drag, lift, gravity, tv,
                           airflow.wake_drag_multiplier, airflow.updraft_mps,
                           kinetic_energy(new_body) + new_body.mass_kg * g * position.z,
                           dissipated)


@dataclass(frozen=True)
class TractionSurface:
    normal: Vec3
    friction_static: float
    friction_dynamic: float
    rock_roughness: float = .5
    wetness: float = 0.
    ice_fraction: float = 0.
    loose_gravel: float = 0.
    foothold_quality: float = 0.
    temperature_c: float = 15.
    deformation: float = 0.

    def __post_init__(self) -> None:
        if abs(vecnorm(self.normal) - 1) > .0001:
            raise AdvancedPhysicsError("traction surface normal must be unit")
        for key in ("friction_static", "friction_dynamic"):
            finite(getattr(self, key), key, 0, 3)
        for key in ("rock_roughness", "wetness", "ice_fraction",
                    "loose_gravel", "foothold_quality", "deformation"):
            finite(getattr(self, key), key, 0, 1)
        finite(self.temperature_c, "temperature", -120, 120)


@dataclass(frozen=True)
class Climber:
    mass_kg: float
    strength_n: float
    grip_skill: float
    boot_traction: float
    stamina: float
    load_kg: float = 0.
    limb_reach_m: float = 1.
    ropes_assist_n: float = 0.

    def __post_init__(self) -> None:
        finite(self.mass_kg, "climber mass", .1, 500)
        finite(self.strength_n, "strength", 0, 10000)
        finite(self.load_kg, "cargo", 0, 500)
        finite(self.ropes_assist_n, "rope force", 0, 10000)
        finite(self.limb_reach_m, "reach", .1, 4)
        for key in ("grip_skill", "boot_traction", "stamina"):
            finite(getattr(self, key), key, 0, 1)


@dataclass(frozen=True)
class TractionDecision:
    effective_static_friction: float
    max_slope_degrees: float
    slope_degrees: float
    required_uphill_force_n: float
    available_climbing_force_n: float
    slip_risk: float
    climbing_possible: bool
    recommended_gait: str
    recommended_speed_scale: float
    exposure_risk: float


def evaluate_climbing(
    surface: TractionSurface, climber: Climber, *,
    wind: Vec3 = ZERO, motion_mps: float = 0.,
    gravity_mps2: float = G0,
) -> TractionDecision:
    """Evaluate slope, climbing grips, carried mass and environmental load.

    Friction alone never magically permits vertical walls; footholds plus
    character strength/rope assist are required.
    """
    speed = finite(motion_mps, "motion", 0, 100)
    g = finite(gravity_mps2, "gravity", 0, 100)
    mass = climber.mass_kg + climber.load_kg
    up = Vec3(0, 0, 1)
    slope = math.degrees(math.acos(clamp(surface.normal.dot(up), -1, 1)))
    friction_factor = (
        (1 - .5 * surface.wetness)
        * (1 - .85 * surface.ice_fraction)
        * (1 - .45 * surface.loose_gravel)
        * (1 - .25 * surface.deformation)
    )
    mu = surface.friction_static * friction_factor * (
        .45 + .55 * climber.boot_traction)
    mu = max(0, mu)
    radians = math.radians(slope)
    normal_force = mass * g * max(0., math.cos(radians))
    gravity_slope = mass * g * math.sin(radians)
    wind_load = max(0., vecnorm(wind)) ** 2 * .25
    demand = gravity_slope + wind_load + mass * speed**2 * .01
    static_support = mu * normal_force
    handhold_support = (climber.strength_n * climber.stamina
                        * climber.grip_skill * surface.foothold_quality
                        + climber.ropes_assist_n)
    available = static_support + handhold_support
    deficit = max(0., demand - available)
    risk = clamp(deficit / max(1., demand) + surface.ice_fraction * .25
                 + surface.wetness * .1)
    possible = available >= demand and (slope < 85 or
                surface.foothold_quality > 0 or climber.ropes_assist_n > 0)
    gait = ("slide" if not possible and slope > 12 else
            "climb" if slope > 45 else
            "scramble" if slope > 20 else
            "careful_walk" if risk > .15 else "walk")
    scale = clamp((1 - .65 * risk) * (1 - min(.7, slope / 200)), .05, 1)
    exposure = clamp(risk + wind_load / max(1, mass * g) * .25)
    return TractionDecision(mu, math.degrees(math.atan(mu)), slope,
                            demand, available, risk, possible, gait, scale, exposure)


@dataclass(frozen=True)
class CollisionContact:
    point: Vec3
    normal_a_to_b: Vec3
    penetration_m: float
    surface_friction: float = .7
    surface_restitution: float = .2

    def __post_init__(self):
        if abs(vecnorm(self.normal_a_to_b) - 1) > 1e-4:
            raise AdvancedPhysicsError("contact normal must be unit")
        finite(self.penetration_m, "penetration", 0, 100)
        finite(self.surface_friction, "surface friction", 0, 3)
        finite(self.surface_restitution, "surface restitution", 0, 1)


@dataclass(frozen=True)
class CollisionResolution:
    body_a: RigidBody
    body_b: RigidBody | None
    normal_impulse_ns: float
    friction_impulse_ns: float
    energy_before_j: float
    energy_after_j: float
    energy_dissipated_j: float
    separation_m: float
    damage_a: float
    damage_b: float
    momentum_residual_ns: float
    authority: str = "candidate_reference_contact_not_engine_executed"


def resolve_contact(
    a: RigidBody, b: RigidBody | None, contact: CollisionContact,
    *, damage_threshold_j: float = 100.,
    damage_scale: float = .0001,
) -> CollisionResolution:
    """Sequential rigid sphere contact impulse with finite/infinite mass.

    Normal points from A toward B, including a static B surface. Contact
    velocities include angular spin. Dynamic/dynamic linear impulse conserves
    momentum; dissipated collision energy is measured, not guessed.
    """
    threshold = finite(damage_threshold_j, "damage threshold", 0, 1e9)
    scale = finite(damage_scale, "damage scale", 0, 1)
    if b is not None and a.body_id == b.body_id:
        raise AdvancedPhysicsError("self collision forbidden")
    n = contact.normal_a_to_b
    ia = 1 / a.mass_kg
    ib = (1 / b.mass_kg) if b is not None else 0.
    va, vb = a.velocity, b.velocity if b is not None else ZERO
    wa, wb = a.angular_velocity, b.angular_velocity if b is not None else ZERO
    ra = contact.point - a.position
    rb = contact.point - b.position if b is not None else ZERO
    before = kinetic_energy(a) + (kinetic_energy(b) if b else 0)
    rel = (vb + wb.cross(rb)) - (va + wa.cross(ra))
    vn = rel.dot(n)
    restitution = min(contact.surface_restitution, a.restitution,
                      b.restitution if b else 1.)
    effective_normal = (ia + ib
                        + (ra.cross(n).dot(ra.cross(n)) / a.inertia_kg_m2)
                        + (rb.cross(n).dot(rb.cross(n)) / b.inertia_kg_m2
                           if b else 0))
    jn = max(0., -(1 + restitution) * vn / effective_normal)
    impulse_n = n.scaled(jn)
    new_va = va - impulse_n.scaled(ia)
    new_vb = vb + impulse_n.scaled(ib)
    new_wa = wa - ra.cross(impulse_n).scaled(1 / a.inertia_kg_m2)
    new_wb = (wb + rb.cross(impulse_n).scaled(1 / b.inertia_kg_m2)
              if b else ZERO)
    # Coulomb friction applied to post-normal-impulse contact velocity.
    rel2 = (new_vb + new_wb.cross(rb)) - (new_va + new_wa.cross(ra))
    tangent = rel2 - n.scaled(rel2.dot(n))
    tangent_len = vecnorm(tangent)
    jt = 0.
    if tangent_len > 1e-9 and jn > 0:
        t = tangent.scaled(1 / tangent_len)
        tangential_mass = (ia + ib
                          + ra.cross(t).dot(ra.cross(t)) / a.inertia_kg_m2
                          + (rb.cross(t).dot(rb.cross(t)) / b.inertia_kg_m2
                             if b else 0))
        mu = math.sqrt(a.friction * (b.friction if b else contact.surface_friction))
        # Correct sign: B-A tangential relative velocity decreases toward zero.
        jt = min(tangent_len / tangential_mass, mu * jn)
        tangent_impulse = t.scaled(-jt)
        new_va = new_va - tangent_impulse.scaled(ia)
        new_vb = new_vb + tangent_impulse.scaled(ib)
        new_wa = new_wa - ra.cross(tangent_impulse).scaled(1 / a.inertia_kg_m2)
        if b is not None:
            new_wb = new_wb + rb.cross(tangent_impulse).scaled(1 / b.inertia_kg_m2)
    penetration = contact.penetration_m
    # Slop and Baumgarte correction; never correct velocity with teleport.
    correction = max(0., penetration - .001) * .8
    total_inv = ia + ib
    new_pa = a.position - n.scaled(correction * ia / total_inv)
    new_pb = b.position + n.scaled(correction * ib / total_inv) if b else None
    body_a = replace(a, position=new_pa, velocity=new_va, angular_velocity=new_wa)
    body_b = (replace(b, position=new_pb, velocity=new_vb,
                      angular_velocity=new_wb) if b else None)
    after = kinetic_energy(body_a) + (kinetic_energy(body_b) if body_b else 0)
    loss = max(0., before - after)
    # Damage based on lost kinetic energy, never just mass or speed in isolation.
    damaged = max(0., loss - threshold) * scale
    momentum_before = va.scaled(a.mass_kg) + (vb.scaled(b.mass_kg) if b else ZERO)
    momentum_after = new_va.scaled(a.mass_kg) + (new_vb.scaled(b.mass_kg) if b else ZERO)
    residual = vecnorm(momentum_after - momentum_before) if b else 0.
    return CollisionResolution(body_a, body_b, jn, jt, before, after,
                               loss, correction, damaged * .5 if b else damaged,
                               damaged * .5 if b else 0., residual)


@dataclass(frozen=True)
class RealismIndicators:
    terminal_speed_mps: float
    current_fall_speed_mps: float
    wake_shelter_fraction: float
    updraft_mps: float
    turbulent_wind_mps: float
    air_density_kg_m3: float
    aerodynamic_dissipation_j: float
    slope_traction_margin: float
    climbing_safe: bool
    collision_impulse_ns: float
    collision_energy_loss_j: float
    collision_energy_nonincreasing: bool
    momentum_residual_ns: float
    environmental_wetness: float
    environmental_ice: float
    evidence_digest: str


def aggregate_realism(
    aero: AerodynamicStep, air: Airflow,
    traction: TractionDecision,
    surface: TractionSurface,
    collision: CollisionResolution | None = None,
) -> RealismIndicators:
    """Cross-domain deterministic indicators, not a self-awarded quality score."""
    record = {
        "aero": [aero.terminal_speed_mps, aero.body.velocity.z,
                 aero.drag_dissipation_j],
        "wake": air.wake_drag_multiplier,
        "updraft": air.updraft_mps,
        "gust": [air.turbulence.x, air.turbulence.y, air.turbulence.z],
        "rho": air.air_density_kg_m3,
        "slope": [traction.required_uphill_force_n,
                  traction.available_climbing_force_n, traction.climbing_possible],
        "contact": (
            [collision.normal_impulse_ns, collision.energy_before_j,
             collision.energy_after_j, collision.momentum_residual_ns]
            if collision else []),
        "weather": [surface.wetness, surface.ice_fraction],
    }
    digest = sha256(json.dumps(record, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return RealismIndicators(
        aero.terminal_speed_mps, max(0., -aero.body.velocity.z),
        1 - air.wake_drag_multiplier, air.updraft_mps,
        vecnorm(air.turbulence), air.air_density_kg_m3,
        aero.drag_dissipation_j,
        traction.available_climbing_force_n - traction.required_uphill_force_n,
        traction.climbing_possible,
        collision.normal_impulse_ns if collision else 0.,
        collision.energy_dissipated_j if collision else 0.,
        collision.energy_after_j <= collision.energy_before_j + 1e-7
        if collision else True,
        collision.momentum_residual_ns if collision else 0.,
        surface.wetness, surface.ice_fraction, digest,
    )


@dataclass(frozen=True)
class SweptContact:
    time_of_impact_s: float
    contact: CollisionContact
    source: str


def sweep_spheres(a: RigidBody, b: RigidBody, *, delta_s: float,
                  tolerance_m: float = 0.) -> SweptContact | None:
    """Analytic moving-sphere CCD to avoid high-speed tunneling.

    The detected contact is a candidate; host engine still owns the final
    collision loop, broadphase and arbitrary-mesh contact manifold.
    """
    dt = finite(delta_s, "CCD delta", 0, 10)
    extra = finite(tolerance_m, "CCD tolerance", 0, 1)
    start = b.position - a.position
    relative = b.velocity - a.velocity
    combined = a.radius_m + b.radius_m + extra
    c = start.dot(start) - combined * combined
    if c <= 0:
        t = 0.
    else:
        qa = relative.dot(relative)
        qb = 2 * start.dot(relative)
        if qa <= 1e-15 or qb >= 0:
            return None
        discriminant = qb * qb - 4 * qa * c
        if discriminant < 0:
            return None
        t = (-qb - math.sqrt(discriminant)) / (2 * qa)
        if not 0 <= t <= dt:
            return None
    displacement = start + relative.scaled(t)
    normal = unit(displacement) if vecnorm(displacement) > 1e-8 else unit(
        relative) if vecnorm(relative) > 1e-8 else Vec3(1, 0, 0)
    a_center = a.position + a.velocity.scaled(t)
    point = a_center + normal.scaled(a.radius_m)
    penetration = max(0., combined - vecnorm(displacement))
    return SweptContact(t, CollisionContact(point, normal, penetration,
                                           surface_friction=math.sqrt(a.friction*b.friction),
                                           surface_restitution=min(a.restitution,b.restitution)),
                        "sphere_sphere_linear_ccd")


def sweep_sphere_plane(
    body: RigidBody, *, plane_point: Vec3, plane_outward_normal: Vec3,
    delta_s: float, surface_friction: float = .7,
    surface_restitution: float = .2,
) -> SweptContact | None:
    """Sphere versus infinite plane: normal points toward the free half-space.

    Plane response needs opposite normal (A toward infinite-mass terrain B).
    A face crossing within the full sweep is detected even at large speed.
    """
    dt = finite(delta_s, "CCD delta", 0, 10)
    finite(surface_friction, "friction", 0, 3)
    finite(surface_restitution, "restitution", 0, 1)
    if abs(vecnorm(plane_outward_normal) - 1) > .0001:
        raise AdvancedPhysicsError("unit outward plane normal required")
    signed = (body.position - plane_point).dot(plane_outward_normal) - body.radius_m
    normal_speed = body.velocity.dot(plane_outward_normal)
    if signed <= 0:
        t = 0.
    elif normal_speed >= 0:
        return None
    else:
        t = -signed / normal_speed
        if t > dt:
            return None
    center = body.position + body.velocity.scaled(t)
    point = center - plane_outward_normal.scaled(body.radius_m)
    penetration = max(0., -signed) if t == 0 else 0.
    return SweptContact(t, CollisionContact(point,
                                           plane_outward_normal.scaled(-1),
                                           penetration, surface_friction,
                                           surface_restitution),
                        "sphere_plane_linear_ccd")
