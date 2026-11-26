"""Committed fixed-step world. Invalid mass, NaN and duplicate ids never enter it."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
from typing import Mapping

from skeleton.jeeves.game_frontier_advanced_physics import TractionSurface
from skeleton.jeeves.game_frontier_ecosystem import AirConditions
from skeleton.jeeves.game_frontier_motion import (
    MATERIALS,
    CharacterState,
    CollisionPlane,
    EnvironmentalState,
    SoftNode,
    StructureState,
    Weather,
)
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_weather_physics import Microclimate

from skeleton.frontier_runtime.eras import EraSolverError, era_solver


class StepRejected(ValueError):
    """The fixed step did not commit. The previous snapshot stays authoritative."""


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_bytes(value: object) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise StepRejected(f"{label} must be finite")
    if isinstance(value, float) and math.isnan(value):
        raise StepRejected("NaN")
    if not math.isfinite(float(value)):
        raise StepRejected(f"{label} must be finite")
    return float(value)


def _xyz(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise StepRejected(f"{label} must be an xyz tuple")
    return tuple(_finite(component, label) for component in value)  # type: ignore[return-value]


def _mass(value: object, label: str, low: float, high: float) -> float:
    number = _finite(value, label)
    if number < 0:
        raise StepRejected("negative mass")
    if not low <= number <= high:
        raise StepRejected(f"{label} out of range")
    return number


def _ident(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value) > 64:
        raise StepRejected(f"{label} id required")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
    if any(char not in allowed for char in value):
        raise StepRejected(f"{label} id is not a stable token")
    return value


def _unit(value: tuple[float, float, float], label: str) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in value))
    if abs(length - 1.0) > 1e-4:
        raise StepRejected(f"{label} must be a unit vector")
    return value


def reject_nonfinite(value: object) -> None:
    """Walk a public snapshot and refuse NaN before any sub-step runs."""
    if isinstance(value, Mapping):
        for item in value.values():
            reject_nonfinite(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            reject_nonfinite(item)
        return
    if isinstance(value, float) and math.isnan(value):
        raise StepRejected("NaN")
    if isinstance(value, float) and not math.isfinite(value):
        raise StepRejected("NaN")
    if type(value) is int and not isinstance(value, bool):
        return
    if value is None or type(value) is str or type(value) is bool:
        return
    if type(value) is float:
        return
    raise StepRejected("snapshot contains a non-finite value")


@dataclass(frozen=True)
class WeatherState:
    wind: tuple[float, float, float]
    temperature_c: float
    precipitation_mm_h: float = 0.0
    humidity: float = 0.5
    water_depth_m: float = 0.0
    sunlight: float = 0.8
    snow_depth_m: float = 0.0
    airborne_dust: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "wind", _xyz(self.wind, "wind"))
        object.__setattr__(self, "temperature_c", _finite(self.temperature_c, "temperature"))
        object.__setattr__(self, "precipitation_mm_h", _finite(self.precipitation_mm_h, "rain"))
        object.__setattr__(self, "humidity", _finite(self.humidity, "humidity"))
        object.__setattr__(self, "water_depth_m", _finite(self.water_depth_m, "water"))
        object.__setattr__(self, "sunlight", _finite(self.sunlight, "sunlight"))
        object.__setattr__(self, "snow_depth_m", _finite(self.snow_depth_m, "snow"))
        object.__setattr__(self, "airborne_dust", _finite(self.airborne_dust, "dust"))
        self.as_weather()

    def as_weather(self) -> Weather:
        try:
            return Weather(
                Vec3(*self.wind), self.temperature_c, self.precipitation_mm_h,
                self.humidity, self.water_depth_m, self.sunlight,
                self.snow_depth_m, self.airborne_dust,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        return {
            "wind": list(self.wind),
            "temperature_c": self.temperature_c,
            "precipitation_mm_h": self.precipitation_mm_h,
            "humidity": self.humidity,
            "water_depth_m": self.water_depth_m,
            "sunlight": self.sunlight,
            "snow_depth_m": self.snow_depth_m,
            "airborne_dust": self.airborne_dust,
        }


@dataclass(frozen=True)
class SoftBodyState:
    node_id: str
    material: str
    rest_position: tuple[float, float, float]
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    mass_kg: float
    wetness: float = 0.0
    temperature_c: float = 20.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _ident(self.node_id, "soft body"))
        if self.material not in MATERIALS:
            raise StepRejected("unknown soft material")
        object.__setattr__(self, "rest_position", _xyz(self.rest_position, "rest"))
        object.__setattr__(self, "position", _xyz(self.position, "soft position"))
        object.__setattr__(self, "velocity", _xyz(self.velocity, "soft velocity"))
        object.__setattr__(self, "mass_kg", _mass(self.mass_kg, "soft mass", 0.0001, 10000))
        object.__setattr__(self, "wetness", _finite(self.wetness, "wetness"))
        object.__setattr__(self, "temperature_c", _finite(self.temperature_c, "soft temperature"))
        self.as_node()

    def as_node(self) -> SoftNode:
        try:
            return SoftNode(
                self.node_id, self.material, Vec3(*self.rest_position),
                Vec3(*self.position), Vec3(*self.velocity), self.mass_kg,
                self.wetness, self.temperature_c,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        return {
            "id": self.node_id,
            "material": self.material,
            "rest": list(self.rest_position),
            "xyz": list(self.position),
            "velocity": list(self.velocity),
            "mass_kg": self.mass_kg,
            "wetness": self.wetness,
            "temperature_c": self.temperature_c,
        }


@dataclass(frozen=True)
class StructureBody:
    structure_id: str
    material: str
    construction_required_days: float
    construction_progress_days: float
    age_days: float
    integrity: float
    surface_weathering: float
    biological_growth: float
    water_infiltration: float
    maintenance_debt: float
    xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "structure_id", _ident(self.structure_id, "structure"))
        object.__setattr__(self, "xyz", _xyz(self.xyz, "structure"))
        self.as_structure()

    def as_structure(self) -> StructureState:
        try:
            return StructureState(
                self.structure_id, self.material, self.construction_required_days,
                self.construction_progress_days, self.age_days, self.integrity,
                self.surface_weathering, self.biological_growth,
                self.water_infiltration, self.maintenance_debt,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        state = self.as_structure()
        return {
            "id": state.structure_id,
            "material": state.material,
            "built": state.complete,
            "construction_required_days": state.construction_required_days,
            "construction_progress_days": state.construction_progress_days,
            "age_days": state.age_days,
            "integrity": state.integrity,
            "weathering": state.surface_weathering,
            "biological_growth": state.biological_growth,
            "water_infiltration": state.water_infiltration,
            "maintenance_debt": state.maintenance_debt,
            "xyz": list(self.xyz),
        }


@dataclass(frozen=True)
class EnvironmentBody:
    soil_saturation: float = 0.3
    erosion: float = 0.0
    foliage_bend: float = 0.0
    vegetation_health: float = 1.0
    puddle_depth_m: float = 0.0
    snow_load: float = 0.0
    debris_fraction: float = 0.0

    def as_environment(self) -> EnvironmentalState:
        try:
            return EnvironmentalState(
                self.soil_saturation, self.erosion, self.foliage_bend,
                self.vegetation_health, self.puddle_depth_m, self.snow_load,
                self.debris_fraction,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        state = self.as_environment()
        return {
            "soil_saturation": state.soil_saturation,
            "erosion": state.erosion,
            "foliage_bend": state.foliage_bend,
            "vegetation_health": state.vegetation_health,
            "puddle_depth_m": state.puddle_depth_m,
            "snow_load": state.snow_load,
            "debris_fraction": state.debris_fraction,
        }


@dataclass(frozen=True)
class PlaneBody:
    plane_id: str
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    material: str = "stone"

    def __post_init__(self) -> None:
        object.__setattr__(self, "plane_id", _ident(self.plane_id, "plane"))
        object.__setattr__(self, "point", _xyz(self.point, "plane point"))
        object.__setattr__(self, "normal", _unit(_xyz(self.normal, "plane normal"), "plane normal"))
        self.as_plane()

    def as_plane(self) -> CollisionPlane:
        try:
            return CollisionPlane(self.plane_id, Vec3(*self.point), Vec3(*self.normal), self.material)
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc


@dataclass(frozen=True)
class CharacterBody:
    character_id: str
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    radius_m: float
    mass_kg: float
    core_temperature_c: float = 37.0
    clothing_wetness: float = 0.0
    hair_wetness: float = 0.0
    boot_wetness: float = 0.0
    warmth: float = 0.5
    stamina: float = 1.0
    health: float = 1.0
    gait: str = "idle"

    def __post_init__(self) -> None:
        object.__setattr__(self, "character_id", _ident(self.character_id, "character"))
        object.__setattr__(self, "position", _xyz(self.position, "character position"))
        object.__setattr__(self, "velocity", _xyz(self.velocity, "character velocity"))
        object.__setattr__(self, "mass_kg", _mass(self.mass_kg, "character mass", 0.1, 10000))
        self.as_character()

    def as_character(self) -> CharacterState:
        try:
            return CharacterState(
                Vec3(*self.position), Vec3(*self.velocity), self.radius_m, self.mass_kg,
                self.core_temperature_c, self.clothing_wetness, self.hair_wetness,
                self.boot_wetness, self.warmth, self.stamina, self.health, self.gait,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        return {
            "id": self.character_id,
            "position": list(self.position),
            "velocity": list(self.velocity),
            "radius_m": self.radius_m,
            "mass_kg": self.mass_kg,
            "core_temperature_c": self.core_temperature_c,
            "clothing_wetness": self.clothing_wetness,
            "hair_wetness": self.hair_wetness,
            "boot_wetness": self.boot_wetness,
            "warmth": self.warmth,
            "stamina": self.stamina,
            "health": self.health,
            "gait": self.gait,
        }


@dataclass(frozen=True)
class ActorState:
    actor_id: str
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    mass_kg: float
    radius_m: float
    desired_velocity: tuple[float, float, float]
    restitution: float = 0.2
    friction: float = 0.6
    angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    last_contact_impulse_ns: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", _ident(self.actor_id, "actor"))
        object.__setattr__(self, "position", _xyz(self.position, "actor position"))
        object.__setattr__(self, "velocity", _xyz(self.velocity, "actor velocity"))
        object.__setattr__(self, "desired_velocity", _xyz(self.desired_velocity, "desired velocity"))
        object.__setattr__(self, "angular_velocity", _xyz(self.angular_velocity, "angular velocity"))
        object.__setattr__(self, "mass_kg", _mass(self.mass_kg, "actor mass", 0.001, 1000000))
        object.__setattr__(self, "radius_m", _finite(self.radius_m, "radius"))
        object.__setattr__(self, "restitution", _finite(self.restitution, "restitution"))
        object.__setattr__(self, "friction", _finite(self.friction, "friction"))
        object.__setattr__(self, "last_contact_impulse_ns", _finite(self.last_contact_impulse_ns, "impulse"))
        if self.last_contact_impulse_ns < 0:
            raise StepRejected("negative contact impulse")
        if not 0.001 <= self.radius_m <= 1000:
            raise StepRejected("radius out of range")
        if not 0.0 <= self.restitution <= 1.0:
            raise StepRejected("restitution out of range")
        if not 0.0 <= self.friction <= 3.0:
            raise StepRejected("friction out of range")

    def public(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "position": list(self.position),
            "velocity": list(self.velocity),
            "angular_velocity": list(self.angular_velocity),
            "mass_kg": self.mass_kg,
            "radius_m": self.radius_m,
            "restitution": self.restitution,
            "friction": self.friction,
            "desired_velocity": list(self.desired_velocity),
            "last_contact_impulse_ns": self.last_contact_impulse_ns,
        }


@dataclass(frozen=True)
class WallState:
    wall_id: str
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    half_thickness_m: float
    friction: float = 0.6
    restitution: float = 0.2

    def __post_init__(self) -> None:
        object.__setattr__(self, "wall_id", _ident(self.wall_id, "wall"))
        object.__setattr__(self, "point", _xyz(self.point, "wall point"))
        object.__setattr__(self, "normal", _unit(_xyz(self.normal, "wall normal"), "wall normal"))
        object.__setattr__(self, "half_thickness_m", _finite(self.half_thickness_m, "thickness"))
        object.__setattr__(self, "friction", _finite(self.friction, "wall friction"))
        object.__setattr__(self, "restitution", _finite(self.restitution, "wall restitution"))
        if not 1e-6 <= self.half_thickness_m <= 10:
            raise StepRejected("wall thickness out of range")
        if not 0.0 <= self.friction <= 3 or not 0.0 <= self.restitution <= 1:
            raise StepRejected("wall material out of range")

    def public(self) -> dict[str, object]:
        return {
            "wall_id": self.wall_id,
            "point": list(self.point),
            "normal": list(self.normal),
            "half_thickness_m": self.half_thickness_m,
            "friction": self.friction,
            "restitution": self.restitution,
        }


@dataclass(frozen=True)
class MicroclimateState:
    terrain_temperature_c: float
    soil_water_fraction: float
    ground_ice_fraction: float
    loose_sediment_fraction: float
    surface_roughness: float
    vegetation_cover: float
    pressure_gradient_pa_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    ground_heat_flux_w_m2: float = 0.0
    convection_radius_m: float = 12.0
    convection_height_m: float = 120.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "pressure_gradient_pa_m", _xyz(self.pressure_gradient_pa_m, "pressure"))
        self.as_microclimate()

    def as_microclimate(self) -> Microclimate:
        try:
            return Microclimate(
                self.terrain_temperature_c, self.soil_water_fraction,
                self.ground_ice_fraction, self.loose_sediment_fraction,
                self.surface_roughness, self.vegetation_cover,
                Vec3(*self.pressure_gradient_pa_m), self.ground_heat_flux_w_m2,
                self.convection_radius_m, self.convection_height_m,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        climate = self.as_microclimate()
        return {
            "terrain_temperature_c": climate.terrain_temperature_c,
            "soil_water_fraction": climate.soil_water_fraction,
            "ground_ice_fraction": climate.ground_ice_fraction,
            "loose_sediment_fraction": climate.loose_sediment_fraction,
            "surface_roughness": climate.surface_roughness,
            "vegetation_cover": climate.vegetation_cover,
            "pressure_gradient_pa_m": list(self.pressure_gradient_pa_m),
            "ground_heat_flux_w_m2": climate.ground_heat_flux_w_m2,
            "convection_radius_m": climate.convection_radius_m,
            "convection_height_m": climate.convection_height_m,
        }


@dataclass(frozen=True)
class TractionBody:
    normal: tuple[float, float, float]
    friction_static: float
    friction_dynamic: float
    rock_roughness: float = 0.5
    wetness: float = 0.0
    ice_fraction: float = 0.0
    loose_gravel: float = 0.0
    foothold_quality: float = 0.5
    temperature_c: float = 15.0
    deformation: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "normal", _unit(_xyz(self.normal, "traction normal"), "traction normal"))
        self.as_traction()

    def as_traction(self) -> TractionSurface:
        try:
            return TractionSurface(
                Vec3(*self.normal), self.friction_static, self.friction_dynamic,
                self.rock_roughness, self.wetness, self.ice_fraction, self.loose_gravel,
                self.foothold_quality, self.temperature_c, self.deformation,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        surface = self.as_traction()
        return {
            "normal": list(self.normal),
            "friction_static": surface.friction_static,
            "friction_dynamic": surface.friction_dynamic,
            "rock_roughness": surface.rock_roughness,
            "wetness": surface.wetness,
            "ice_fraction": surface.ice_fraction,
            "loose_gravel": surface.loose_gravel,
            "foothold_quality": surface.foothold_quality,
            "temperature_c": surface.temperature_c,
            "deformation": surface.deformation,
        }


@dataclass(frozen=True)
class AirBody:
    altitude_m: float = 830.0
    temperature_c: float = 15.0
    relative_humidity: float = 0.5
    fog_liquid_g_m3: float = 0.0
    rain_mm_h: float = 0.0
    particulate_index: float = 0.3
    cold_wind_damping: float = 0.0

    def as_air(self) -> AirConditions:
        try:
            return AirConditions(
                self.altitude_m, self.temperature_c, self.relative_humidity,
                self.fog_liquid_g_m3, self.rain_mm_h, self.particulate_index,
                self.cold_wind_damping,
            )
        except ValueError as exc:
            raise StepRejected(str(exc)) from exc

    def public(self) -> dict[str, object]:
        air = self.as_air()
        return {
            "altitude_m": air.altitude_m,
            "temperature_c": air.temperature_c,
            "relative_humidity": air.relative_humidity,
            "fog_liquid_g_m3": air.fog_liquid_g_m3,
            "rain_mm_h": air.rain_mm_h,
            "particulate_index": air.particulate_index,
            "cold_wind_damping": air.cold_wind_damping,
        }


@dataclass(frozen=True)
class ImpactBody:
    surface_id: str
    relative_speed_mps: float
    impulse_ns: float
    damage: float
    normal: tuple[float, float, float]
    material: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface_id", _ident(self.surface_id, "impact"))
        object.__setattr__(self, "normal", _unit(_xyz(self.normal, "impact normal"), "impact normal"))
        for name in ("relative_speed_mps", "impulse_ns", "damage"):
            number = _finite(getattr(self, name), name)
            if number < 0:
                raise StepRejected(f"{name} cannot be negative")
            object.__setattr__(self, name, number)
        if self.material not in MATERIALS:
            raise StepRejected("unknown impact material")

    def public(self) -> dict[str, object]:
        return {
            "surface": self.surface_id,
            "relative_speed_mps": self.relative_speed_mps,
            "impulse_ns": self.impulse_ns,
            "damage": self.damage,
            "normal": list(self.normal),
            "material": self.material,
        }


@dataclass(frozen=True)
class WorldState:
    engine_era: str
    weather: WeatherState
    soft_nodes: tuple[SoftBodyState, ...]
    soft_anchors: tuple[tuple[float, float, float], ...]
    environment: EnvironmentBody
    structures: tuple[StructureBody, ...]
    actors: tuple[ActorState, ...]
    walls: tuple[WallState, ...]
    microclimate: MicroclimateState
    traction: TractionBody
    air: AirBody
    character: CharacterBody | None = None
    character_surfaces: tuple[PlaneBody, ...] = ()
    desired_character_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    construction_work_days: float = 0.0
    maintenance_days: float = 0.0
    prior_impact: ImpactBody | None = None
    chunk_size_m: float = 16.0
    step_index: int = 0
    parent_digest: str | None = None
    admitted_candidate_digest: str | None = None

    def __post_init__(self) -> None:
        try:
            era_solver(self.engine_era)
        except EraSolverError as exc:
            raise StepRejected(str(exc)) from exc
        if type(self.step_index) is not int or self.step_index < 0:
            raise StepRejected("step index invalid")
        object.__setattr__(self, "soft_nodes", tuple(self.soft_nodes))
        object.__setattr__(self, "soft_anchors", tuple(_xyz(anchor, "anchor") for anchor in self.soft_anchors))
        object.__setattr__(self, "structures", tuple(self.structures))
        object.__setattr__(self, "actors", tuple(self.actors))
        object.__setattr__(self, "walls", tuple(self.walls))
        object.__setattr__(self, "character_surfaces", tuple(self.character_surfaces))
        object.__setattr__(
            self, "desired_character_velocity", _xyz(self.desired_character_velocity, "desired character velocity"),
        )
        object.__setattr__(self, "construction_work_days", _finite(self.construction_work_days, "work"))
        object.__setattr__(self, "maintenance_days", _finite(self.maintenance_days, "maintenance"))
        object.__setattr__(self, "chunk_size_m", _finite(self.chunk_size_m, "chunk size"))
        if self.construction_work_days < 0 or self.maintenance_days < 0:
            raise StepRejected("negative work")
        if not 0.1 <= self.chunk_size_m <= 10000:
            raise StepRejected("chunk size out of range")
        if len(self.soft_nodes) != len(self.soft_anchors):
            raise StepRejected("soft body anchors must match nodes")
        if self.character is None and self.character_surfaces:
            raise StepRejected("character surfaces require a character")
        actor_ids = [actor.actor_id for actor in self.actors]
        if self.character is not None:
            actor_ids.append(self.character.character_id)
        if len(actor_ids) != len(set(actor_ids)):
            raise StepRejected("duplicate actor id")
        soft_ids = [node.node_id for node in self.soft_nodes]
        if len(soft_ids) != len(set(soft_ids)):
            raise StepRejected("duplicate soft-body id")
        structure_ids = [item.structure_id for item in self.structures]
        if len(structure_ids) != len(set(structure_ids)):
            raise StepRejected("duplicate structure id")
        wall_ids = [wall.wall_id for wall in self.walls]
        if len(wall_ids) != len(set(wall_ids)):
            raise StepRejected("duplicate wall id")
        for actor in self.actors:
            if actor.mass_kg < 0:
                raise StepRejected("negative mass")
        if self.parent_digest is not None and (
            type(self.parent_digest) is not str or len(self.parent_digest) != 64
        ):
            raise StepRejected("parent digest invalid")
        if self.admitted_candidate_digest is not None and (
            type(self.admitted_candidate_digest) is not str or len(self.admitted_candidate_digest) != 64
        ):
            raise StepRejected("candidate digest invalid")
        # Construct the reference objects once so a bad world cannot be stored.
        self.weather.as_weather()
        self.environment.as_environment()
        self.microclimate.as_microclimate()
        self.traction.as_traction()
        self.air.as_air()
        reject_nonfinite(self.public())

    def public(self) -> dict[str, object]:
        return {
            "engine_era": self.engine_era,
            "step_index": self.step_index,
            "parent_digest": self.parent_digest,
            "admitted_candidate_digest": self.admitted_candidate_digest,
            "chunk_size_m": self.chunk_size_m,
            "construction_work_days": self.construction_work_days,
            "maintenance_days": self.maintenance_days,
            "desired_character_velocity": list(self.desired_character_velocity),
            "weather": self.weather.public(),
            "soft_nodes": [node.public() for node in self.soft_nodes],
            "soft_anchors": [list(anchor) for anchor in self.soft_anchors],
            "environment": self.environment.public(),
            "structures": [item.public() for item in self.structures],
            "character": None if self.character is None else self.character.public(),
            "actors": [actor.public() for actor in self.actors],
            "walls": [wall.public() for wall in self.walls],
            "microclimate": self.microclimate.public(),
            "traction": self.traction.public(),
            "air": self.air.public(),
            "prior_impact": None if self.prior_impact is None else self.prior_impact.public(),
        }

    def digest(self) -> str:
        return digest_bytes(self.public())


def with_updates(world: WorldState, **changes: object) -> WorldState:
    return replace(world, **changes)
