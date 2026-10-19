"""Deterministic responsive character, materials, weather and built-world motion.

A bounded CPU reference simulation for gameplay candidate evaluation. All
forces, contacts, wetness, temperatures, damage, construction and repair state
are explicit. Host physics and renderer still own authoritative scene updates.
No neural weights, GPU cloth solver or external model execution is implied.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .game_frontier_production import Vec3


class MotionPhysicsError(ValueError):
    pass


def _bound(x: float, label: str, lo: float, hi: float) -> float:
    if type(x) not in (int, float) or not math.isfinite(x) or not lo <= x <= hi:
        raise MotionPhysicsError(f"{label}: finite value in {lo}..{hi} required")
    return float(x)


def _clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return min(hi, max(lo, x))


def _magnitude(v: Vec3) -> float:
    return math.sqrt(v.dot(v))


def _distance(a: Vec3, b: Vec3) -> float:
    return _magnitude(a - b)


@dataclass(frozen=True)
class Weather:
    wind: Vec3
    temperature_c: float
    precipitation_mm_h: float = 0.0
    humidity: float = .5
    water_depth_m: float = 0.0
    sunlight: float = .8
    snow_depth_m: float = 0.0
    airborne_dust: float = 0.0

    def __post_init__(self) -> None:
        _bound(self.temperature_c, "temperature", -120, 120)
        _bound(self.precipitation_mm_h, "precipitation", 0, 1000)
        _bound(self.humidity, "humidity", 0, 1)
        _bound(self.water_depth_m, "water depth", 0, 1000)
        _bound(self.sunlight, "sunlight", 0, 1)
        _bound(self.snow_depth_m, "snow", 0, 100)
        _bound(self.airborne_dust, "dust", 0, 1)
        if _magnitude(self.wind) > 250:
            raise MotionPhysicsError("wind velocity beyond reference solver envelope")


@dataclass(frozen=True)
class Material:
    name: str
    elasticity_n_m: float
    damping_n_s_m: float
    wind_drag: float
    absorption_rate: float
    drying_rate: float
    thermal_conductivity: float
    impact_resilience: float
    surface_friction: float
    permeability: float

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 128:
            raise MotionPhysicsError("named material required")
        _bound(self.elasticity_n_m, "elasticity", 0, 100000)
        _bound(self.damping_n_s_m, "damping", 0, 10000)
        for key in ("wind_drag", "absorption_rate", "drying_rate",
                    "thermal_conductivity", "impact_resilience",
                    "surface_friction", "permeability"):
            _bound(getattr(self, key), key, 0, 1)


MATERIALS = {
    "skin": Material("skin", 900, 18, .05, .3, .2, .6, .7, .85, .05),
    "cloth": Material("cloth", 70, 4, .7, .75, .3, .25, .15, .55, .65),
    "hair": Material("hair", 32, 2.5, .9, .8, .45, .4, .08, .4, .75),
    "leather_boot": Material("leather_boot", 2200, 45, .05, .28, .2, .28, .62, .86, .04),
    "wool": Material("wool", 100, 8, .65, .7, .18, .12, .17, .65, .3),
    "steel": Material("steel", 100000, 300, .04, .02, .8, .9, .95, .52, 0),
    "wood": Material("wood", 1500, 90, .25, .5, .16, .35, .5, .7, .18),
    "stone": Material("stone", 20000, 400, .02, .12, .5, .6, .8, .82, .08),
}


@dataclass(frozen=True)
class SoftNode:
    node_id: str
    material: str
    rest_position: Vec3
    position: Vec3
    velocity: Vec3
    mass_kg: float
    wetness: float = 0.0
    temperature_c: float = 20.0

    def __post_init__(self) -> None:
        if not self.node_id or len(self.node_id) > 128:
            raise MotionPhysicsError("node identity required")
        if self.material not in MATERIALS:
            raise MotionPhysicsError("unknown soft material")
        _bound(self.mass_kg, "mass", .0001, 10000)
        _bound(self.wetness, "wetness", 0, 1)
        _bound(self.temperature_c, "node temperature", -120, 120)


def _wetness(current: float, material: Material, weather: Weather,
             delta_s: float, *, immersed: bool) -> float:
    # Rain mm/h is converted to an exposure fraction per reference second.
    exposure = min(1, weather.precipitation_mm_h / 60)
    immersion = 1.0 if immersed else exposure
    gain = (1 - current) * material.absorption_rate * immersion * delta_s
    evaporative = (.1 + weather.sunlight * .55
                   + _magnitude(weather.wind) / 200
                   + max(0, weather.temperature_c) / 100)
    loss = current * material.drying_rate * evaporative * delta_s
    if immersed:
        loss = 0
    return _clamp(current + gain - loss)


def simulate_soft_nodes(nodes: tuple[SoftNode, ...], weather: Weather, *,
                        anchors: tuple[Vec3, ...], delta_s: float,
                        gravity_mps2: float = 9.81) -> tuple[SoftNode, ...]:
    """Substepped elastic hair/cloth/skin/boot nodes driven by weather.

    Each node is tethered to its rest position plus a pose-derived anchor
    displacement. The host must supply updated anchors for moving characters.
    This is intentionally a reference spring model, not a FEM cloth solver.
    """
    if not 0 < len(nodes) <= 16384 or len(nodes) != len(anchors):
        raise MotionPhysicsError("1..16384 nodes with one anchor each required")
    dt = _bound(delta_s, "soft dt", 0, .25)
    _bound(gravity_mps2, "gravity", -50, 50)
    count = max(1, math.ceil(dt / .005))
    step = dt / count
    current = list(nodes)
    for _ in range(count):
        updated = []
        for node, anchor in zip(current, anchors):
            if not isinstance(node, SoftNode) or not isinstance(anchor, Vec3):
                raise MotionPhysicsError("typed node and anchor required")
            material = MATERIALS[node.material]
            wet = _wetness(node.wetness, material, weather, step,
                           immersed=node.position.z < weather.water_depth_m)
            # Per-node mass rises with absorbed liquids.
            mass = node.mass_kg * (1 + wet * material.absorption_rate)
            displacement = node.position - anchor
            rel_wind = weather.wind - node.velocity
            spring_force = displacement.scaled(-material.elasticity_n_m)
            damping_force = node.velocity.scaled(-material.damping_n_s_m)
            drag_force = rel_wind.scaled(material.wind_drag * (1 + wet * .7))
            gravity = Vec3(0, 0, -gravity_mps2 * mass)
            acceleration = (spring_force + damping_force + drag_force + gravity).scaled(1 / mass)
            # Cap stiffness-induced accelerations for stable large elasticities.
            acc_len = _magnitude(acceleration)
            if acc_len > 500:
                acceleration = acceleration.scaled(500 / acc_len)
            velocity = node.velocity + acceleration.scaled(step)
            position = node.position + velocity.scaled(step)
            if position.z < 0:
                position = Vec3(position.x, position.y, 0)
                velocity = Vec3(velocity.x * .7, velocity.y * .7,
                                max(0, -velocity.z * material.impact_resilience * .4))
            thermal_rate = material.thermal_conductivity * step
            temp = node.temperature_c + (weather.temperature_c - node.temperature_c) * thermal_rate
            updated.append(replace(node, position=position, velocity=velocity,
                                   wetness=wet, temperature_c=temp))
        current = updated
    return tuple(current)


@dataclass(frozen=True)
class CollisionPlane:
    plane_id: str
    point: Vec3
    normal: Vec3
    material: str = "stone"
    dynamic_velocity: Vec3 = Vec3(0, 0, 0)

    def __post_init__(self) -> None:
        if not self.plane_id or len(self.plane_id) > 128:
            raise MotionPhysicsError("plane id required")
        if abs(_magnitude(self.normal) - 1) > .0001:
            raise MotionPhysicsError("collision normal must be normalized")
        if self.material not in MATERIALS:
            raise MotionPhysicsError("unknown surface material")


@dataclass(frozen=True)
class Impact:
    surface_id: str
    relative_speed_mps: float
    impulse_ns: float
    damage: float
    normal: Vec3
    material: str

    def __post_init__(self) -> None:
        for key in ("relative_speed_mps", "impulse_ns", "damage"):
            _bound(getattr(self, key), key, 0, 1e9)


@dataclass(frozen=True)
class CharacterState:
    position: Vec3
    velocity: Vec3
    radius_m: float
    mass_kg: float
    core_temperature_c: float = 37.0
    clothing_wetness: float = 0.0
    hair_wetness: float = 0.0
    boot_wetness: float = 0.0
    warmth: float = .5
    stamina: float = 1.0
    health: float = 1.0
    gait: str = "idle"

    def __post_init__(self) -> None:
        _bound(self.radius_m, "radius", .05, 10)
        _bound(self.mass_kg, "character mass", .1, 10000)
        _bound(self.core_temperature_c, "core temp", 20, 45)
        for key in ("clothing_wetness", "hair_wetness", "boot_wetness",
                    "warmth", "stamina", "health"):
            _bound(getattr(self, key), key, 0, 1)
        if self.gait not in ("idle", "walk", "run", "crouch", "swim", "stumble"):
            raise MotionPhysicsError("invalid gait")


@dataclass(frozen=True)
class CharacterAwareness:
    cold_stress: float
    heat_stress: float
    wet_stress: float
    slip_risk: float
    impact_alarm: float
    weather_exposure: float
    protective_action: str
    factual_basis: tuple[str, ...]
    authority: str = "reference_model_candidate_not_character_decision"


@dataclass(frozen=True)
class CharacterStep:
    state: CharacterState
    awareness: CharacterAwareness
    impacts: tuple[Impact, ...]
    friction_coefficient: float


def simulate_character(
    state: CharacterState, weather: Weather, surfaces: tuple[CollisionPlane, ...],
    *, desired_velocity: Vec3, delta_s: float, gravity_mps2: float = 9.81,
    impact_damage_scale: float = .00002,
) -> CharacterStep:
    """Collision-aware movement, liquid-sensitive traction and temperature.

    Ground contacts are solved as plane projections; the host physics engine
    still decides accepted game-world movement and contact authority.
    """
    dt = _bound(delta_s, "character dt", 0, .1)
    _bound(gravity_mps2, "gravity", -50, 50)
    _bound(impact_damage_scale, "damage_scale", 0, .01)
    if len(surfaces) > 256 or any(not isinstance(s, CollisionPlane) for s in surfaces):
        raise MotionPhysicsError("too many or invalid collision surfaces")
    cloth = _wetness(state.clothing_wetness, MATERIALS["cloth"], weather, dt,
                      immersed=state.position.z < weather.water_depth_m)
    hair = _wetness(state.hair_wetness, MATERIALS["hair"], weather, dt,
                     immersed=state.position.z < weather.water_depth_m)
    boots = _wetness(state.boot_wetness, MATERIALS["leather_boot"], weather, dt,
                      immersed=state.position.z < weather.water_depth_m)
    snow_drag = min(1, weather.snow_depth_m * .8)
    immersion_drag = min(1, weather.water_depth_m / max(state.radius_m * 2, .1))
    traction = _clamp((1 - boots * .5) * (1 - immersion_drag * .6)
                      * (1 - snow_drag * .45), .08, 1)
    steering = (desired_velocity - state.velocity).scaled(min(1, dt * 6 * traction))
    wind_force = weather.wind.scaled(.02 * (1 + cloth))
    fluid_drag = state.velocity.scaled(-immersion_drag * dt * 2)
    velocity = state.velocity + steering + wind_force.scaled(dt) + fluid_drag
    velocity = Vec3(velocity.x, velocity.y, velocity.z - gravity_mps2 * dt)
    position = state.position + velocity.scaled(dt)
    impacts = []
    for surface in surfaces:
        penetration = state.radius_m - (position - surface.point).dot(surface.normal)
        if penetration <= 0:
            continue
        relative = velocity - surface.dynamic_velocity
        inward = relative.dot(surface.normal)
        position = position + surface.normal.scaled(penetration)
        if inward < 0:
            mat = MATERIALS[surface.material]
            bounce = -inward * mat.impact_resilience * .25
            tangential = relative - surface.normal.scaled(inward)
            tangential = tangential.scaled(_clamp(1 - mat.surface_friction * traction * dt * 10))
            velocity = surface.dynamic_velocity + tangential + surface.normal.scaled(bounce)
            impulse = state.mass_kg * (bounce - inward)
            damage = max(0, impulse - 500) * impact_damage_scale * (1 - mat.impact_resilience * .5)
            impacts.append(Impact(surface.plane_id, -inward, impulse, damage,
                                  surface.normal, surface.material))
    insulation = _clamp(state.warmth * (1 - cloth * .65))
    perceived_air = weather.temperature_c - min(18, _magnitude(weather.wind) * .25) * (1 - insulation)
    cold = _clamp((15 - perceived_air) / 40)
    heat = _clamp((perceived_air - 30) / 35)
    wetstress = _clamp((cloth + hair + boots) / 3)
    core_delta = (perceived_air - state.core_temperature_c) * (1 - insulation) * dt * .0007
    core = max(20, min(45, state.core_temperature_c + core_delta))
    danger = _clamp(max((i.damage for i in impacts), default=0))
    protection = ("recover_balance" if danger > .15 else
                  "seek_shelter" if cold > .65 or heat > .65 else
                  "reduce_speed" if traction < .4 else
                  "dry_equipment" if wetstress > .6 else "continue")
    awareness = CharacterAwareness(
        cold, heat, wetstress, 1 - traction, danger,
        _clamp((weather.precipitation_mm_h / 100 + _magnitude(weather.wind) / 80) / 2),
        protection, ("air_temperature_c", "wind_mps", "surface_contacts",
                     "water_depth_m", "garment_wetness", "thermal_insulation"))
    damage_total = sum(i.damage for i in impacts)
    speed = math.hypot(velocity.x, velocity.y)
    gait = ("stumble" if danger > .15 else "swim" if immersion_drag > .6
            else "idle" if speed < .1 else "run" if speed > 4 else "walk")
    stamina = _clamp(state.stamina - dt * (.002 + speed * .0008 + cold * .002 + heat * .003))
    new_state = replace(state, position=position, velocity=velocity,
                        core_temperature_c=core, clothing_wetness=cloth,
                        hair_wetness=hair, boot_wetness=boots,
                        stamina=stamina, health=_clamp(state.health - damage_total),
                        gait=gait)
    return CharacterStep(new_state, awareness, tuple(impacts), traction)


@dataclass(frozen=True)
class EnvironmentalState:
    soil_saturation: float = 0.3
    erosion: float = 0.0
    foliage_bend: float = 0.0
    vegetation_health: float = 1.0
    puddle_depth_m: float = 0.0
    snow_load: float = 0.0
    debris_fraction: float = 0.0

    def __post_init__(self) -> None:
        for key in ("soil_saturation", "erosion", "foliage_bend",
                    "vegetation_health", "snow_load", "debris_fraction"):
            _bound(getattr(self, key), key, 0, 1)
        _bound(self.puddle_depth_m, "puddles", 0, 100)


def advance_environment(state: EnvironmentalState, weather: Weather, *,
                        delta_days: float, impact: Impact | None = None) -> EnvironmentalState:
    days = _bound(delta_days, "environment days", 0, 30)
    rain = weather.precipitation_mm_h / 1000
    wind = _magnitude(weather.wind)
    saturated = _clamp(state.soil_saturation + rain * days * 3
                       - max(0, weather.temperature_c) * days * .0008)
    erosion = _clamp(state.erosion + days * (.002 * saturated + rain * .04
                                            + wind * .000015))
    bending = _clamp(state.foliage_bend + days * (wind / 3000 - .002))
    cold = _clamp((0 - weather.temperature_c) / 60)
    drought = 1 - saturated
    vegetation = _clamp(state.vegetation_health - days * (cold * .002
                           + drought * .0015 + weather.airborne_dust * .002))
    puddle = max(0, state.puddle_depth_m + days * (rain * .3 -
               max(0, weather.temperature_c) * .00007))
    snow = _clamp(state.snow_load + (days * rain * cold * 3) -
                  (days * max(0, weather.temperature_c) * .002))
    debris = state.debris_fraction
    if impact is not None:
        debris = _clamp(debris + impact.impulse_ns / 1e6)
        erosion = _clamp(erosion + impact.damage * .05)
        vegetation = _clamp(vegetation - impact.damage * .02)
    return EnvironmentalState(saturated, erosion, bending, vegetation,
                              min(100, puddle), snow, debris)


@dataclass(frozen=True)
class StructureState:
    structure_id: str
    material: str
    construction_required_days: float
    construction_progress_days: float = 0.0
    age_days: float = 0.0
    integrity: float = 1.0
    surface_weathering: float = 0.0
    biological_growth: float = 0.0
    water_infiltration: float = 0.0
    maintenance_debt: float = 0.0

    def __post_init__(self) -> None:
        if not self.structure_id or len(self.structure_id) > 128:
            raise MotionPhysicsError("structure identity required")
        if self.material not in MATERIALS:
            raise MotionPhysicsError("unknown construction material")
        _bound(self.construction_required_days, "construction required", .001, 1e8)
        _bound(self.construction_progress_days, "construction progress", 0, 1e8)
        _bound(self.age_days, "age", 0, 1e8)
        for key in ("integrity", "surface_weathering", "biological_growth",
                    "water_infiltration", "maintenance_debt"):
            _bound(getattr(self, key), key, 0, 1)

    @property
    def complete(self) -> bool:
        return self.construction_progress_days >= self.construction_required_days


def age_structure(state: StructureState, weather: Weather, *,
                  elapsed_days: float, work_days: float = 0.0,
                  maintenance_days: float = 0.0,
                  impact: Impact | None = None) -> StructureState:
    """Simulate construction, maintenance and long-term weather/nature wear.

    Work and maintenance are explicit inputs, never silently inferred from time.
    Conversion of days to game-world ticks belongs to the host.
    """
    days = _bound(elapsed_days, "elapsed_days", 0, 3650)
    work = _bound(work_days, "work_days", 0, 3650)
    maintenance = _bound(maintenance_days, "maintenance_days", 0, 3650)
    if work > days * 100 or maintenance > days * 100:
        raise MotionPhysicsError("unreasonably high construction/repair throughput")
    progress = min(state.construction_required_days,
                   state.construction_progress_days + work)
    if progress < state.construction_required_days:
        # Unfinished builds can deteriorate, but cannot be declared complete.
        exposure_factor = .2
    else:
        exposure_factor = 1
    mat = MATERIALS[state.material]
    wet = _clamp(state.water_infiltration + days * weather.precipitation_mm_h
                 * mat.absorption_rate / 12000
                 - days * mat.drying_rate * max(0, weather.temperature_c) / 1000)
    freeze = max(0, -weather.temperature_c) / 100
    wind = _magnitude(weather.wind)
    weather_damage = exposure_factor * days * (
        .00002 + .000035 * wet + freeze * .00006 + wind * .0000004
        + weather.airborne_dust * .00002) * (1.2 - mat.impact_resilience)
    impact_damage = (impact.damage if impact is not None else 0) * .05
    repaired = min(.3, maintenance * .002 * mat.impact_resilience)
    integrity = _clamp(state.integrity - weather_damage - impact_damage + repaired)
    surface = _clamp(state.surface_weathering + days * (
        wind * .000003 + weather.precipitation_mm_h * .000002
        + weather.airborne_dust * .0001) - repaired)
    growth_rate = days * wet * max(0, weather.temperature_c) * .000001
    growth = _clamp(state.biological_growth + growth_rate - maintenance * .005)
    debt = _clamp(state.maintenance_debt + days * (
        .00001 + wet * .00003 + freeze * .00006)
        - maintenance * .002)
    return replace(state, construction_progress_days=progress,
                   age_days=state.age_days + days, integrity=integrity,
                   surface_weathering=surface, biological_growth=growth,
                   water_infiltration=wet, maintenance_debt=debt)
