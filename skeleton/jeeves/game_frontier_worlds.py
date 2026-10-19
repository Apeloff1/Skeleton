"""Deterministic multi-family world transforms and era-neutral 2D/2.5-2.9D/3D projections.

World variants are generated from a *canonical source world*, retaining its
seed and coordinates for reversible transforms and inspectable lineage.
Learned world-image generation, GPU rendering and gameplay authority are NOT
provided by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .game_frontier_dynamics import WorldAxis, WorldCell, generate_world_cell
from .game_frontier_production import Vec3


class WorldGeometryError(ValueError):
    pass


def _finite(v: float, name: str, lo: float = -1e8, hi: float = 1e8) -> float:
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
        raise WorldGeometryError(f"{name} must be finite within [{lo},{hi}]")
    return float(v)


def _unit(v: float, name: str) -> float:
    return _finite(v, name, 0, 1)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class WorldFamily(str, Enum):
    ORIGINAL = "original"
    INVERSE = "inverse"
    MIRROR = "mirror"
    ELEMENTAL = "elemental"
    ETHEREAL = "ethereal"
    MYTHIC = "mythic"
    LENSED = "lensed"
    SHADOW = "shadow"
    CELESTIAL = "celestial"


ELEMENTS = frozenset(("earth", "air", "water", "fire", "ice", "lightning", "aether"))


class ProjectionMode(str, Enum):
    TOP_DOWN = "top_down"
    PLATFORMER = "platformer"
    FULL_3D = "3d"
    DEPTH_25 = "2.5d"
    DEPTH_26 = "2.6d"
    DEPTH_27 = "2.7d"
    DEPTH_28 = "2.8d"
    DEPTH_29 = "2.9d"


DEPTH_WEIGHT = {
    ProjectionMode.DEPTH_25: 0.5,
    ProjectionMode.DEPTH_26: 0.6,
    ProjectionMode.DEPTH_27: 0.7,
    ProjectionMode.DEPTH_28: 0.8,
    ProjectionMode.DEPTH_29: 0.9,
}


@dataclass(frozen=True)
class WorldVariant:
    family: WorldFamily
    element: str = "earth"
    intensity: float = 0.7
    mirror_axis_x: int = 0
    lens_scale: float = 0.15
    world_time_days: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.family, WorldFamily):
            raise WorldGeometryError("family must be WorldFamily")
        if self.element not in ELEMENTS:
            raise WorldGeometryError("unsupported element")
        _unit(self.intensity, "intensity")
        _finite(self.lens_scale, "lens_scale", 0, 0.8)
        _finite(self.world_time_days, "world_time_days", 0, 1e7)
        if type(self.mirror_axis_x) is not int or abs(self.mirror_axis_x) > 10**7:
            raise WorldGeometryError("invalid reflection axis")


@dataclass(frozen=True)
class VariantCell:
    family: WorldFamily
    source_x: int
    source_y: int
    x: int
    y: int
    elevation: float
    humidity: float
    temperature: float
    luminance: float
    permeability: float
    gravity_sign: int
    world_energy: float
    celestial_altitude: float
    sky_island: bool
    dominant_element: str
    biome: str
    source_seed: int


def _world_coord(variant: WorldVariant, x: int, y: int) -> tuple[int, int]:
    if any(type(v) is not int or abs(v) > 10**7 for v in (x, y)):
        raise WorldGeometryError("world coordinates must be bounded integers")
    if variant.family is WorldFamily.MIRROR:
        return 2 * variant.mirror_axis_x - x, y
    return x, y


def variant_world_cell(axes: WorldAxis, variant: WorldVariant, x: int, y: int) -> VariantCell:
    """Compute a coherent semantic alternative while maintaining seed lineage."""
    sx, sy = _world_coord(variant, x, y)
    base = generate_world_cell(axes, sx, sy)
    strength = variant.intensity
    elev, humidity, temp = base.elevation, base.humidity, base.temperature
    light, permeability, energy = 0.7, 0.0, 0.2
    sign, altitude, floating = 1, 0.0, base.sky_island
    element = "earth"
    family = variant.family
    if family is WorldFamily.INVERSE:
        elev = _clamp(elev * (1 - strength) + (1 - elev) * strength)
        humidity = _clamp(humidity * (1 - strength) + (1 - humidity) * strength)
        temp = _clamp(temp * (1 - strength) + (1 - temp) * strength)
        sign = -1 if strength >= .5 else 1
        light = _clamp(.7 - .4 * strength)
    elif family is WorldFamily.MIRROR:
        # Reflection is in source sampling, not destructive world mutation.
        light = _clamp(.75 + .15 * strength)
    elif family is WorldFamily.ELEMENTAL:
        element = variant.element
        if element == "fire":
            temp = _clamp(temp + strength * .55)
            humidity = _clamp(humidity - strength * .45)
        elif element == "water":
            humidity = _clamp(humidity + strength * .5)
            elev = _clamp(elev - strength * .15)
        elif element == "ice":
            temp = _clamp(temp - strength * .5)
        elif element == "air":
            floating = floating or (elev + strength > 1.2)
        elif element == "earth":
            elev = _clamp(elev + strength * .25)
        elif element == "lightning":
            light = _clamp(light + strength * .2)
        else:
            permeability = strength * .5
        energy = _clamp(.25 + strength * .7)
    elif family is WorldFamily.ETHEREAL:
        permeability = .85 * strength
        energy = _clamp(.3 + .65 * strength)
        light = _clamp(.4 + strength * .5)
        sign = -1 if strength > .85 else 1
    elif family is WorldFamily.MYTHIC:
        phase = 2 * math.pi * (variant.world_time_days / 29.5 + (sx + sy) / 1536)
        energy = _clamp(.3 + .5 * strength + .15 * math.sin(phase))
        floating = floating or (energy > .82 and elev > .5)
        light = _clamp(.65 + .25 * math.sin(phase) * strength)
    elif family is WorldFamily.LENSED:
        # Coordinate distortion is resolved in the camera projection below;
        # preserve engine-world topology and authoritative collision geometry.
        energy = _clamp(.25 + .5 * strength)
        light = _clamp(.65 + .2 * strength)
    elif family is WorldFamily.SHADOW:
        light = _clamp(.7 * (1 - .9 * strength))
        temp = _clamp(temp - .1 * strength)
        energy = _clamp(.25 + .6 * strength)
    elif family is WorldFamily.CELESTIAL:
        altitude = (elev + axes.verticality * .5 + strength) * 2000
        floating = True if strength >= .5 else floating
        light = _clamp(.7 + strength * .25)
        energy = _clamp(.25 + strength * .7)
    return VariantCell(family, sx, sy, x, y, elev, humidity, temp,
                       light, permeability, sign, energy, altitude,
                       floating, element, base.biome, axes.seed)


@dataclass(frozen=True)
class CameraSpec:
    mode: ProjectionMode
    position: Vec3 = Vec3(0, -12, 8)
    yaw_rad: float = 0
    pitch_rad: float = 0
    focal_length: float = 1.0
    orthographic_scale: float = 1.0
    parallax_scale: float = .2
    near_plane: float = .01

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ProjectionMode):
            raise WorldGeometryError("invalid camera mode")
        _finite(self.yaw_rad, "yaw", -100, 100)
        _finite(self.pitch_rad, "pitch", -math.pi / 2, math.pi / 2)
        _finite(self.focal_length, "focal_length", .01, 100)
        _finite(self.orthographic_scale, "orthographic_scale", .001, 10000)
        _finite(self.parallax_scale, "parallax_scale", 0, 10)
        _finite(self.near_plane, "near_plane", .0001, 100)


@dataclass(frozen=True)
class ProjectedPoint:
    screen_x: float
    screen_y: float
    depth: float
    perspective_scale: float
    visible: bool
    projection: ProjectionMode


def project_point(world: Vec3, camera: CameraSpec, *,
                  variant: WorldVariant | None = None) -> ProjectedPoint:
    """Project engine-space XYZ to a camera plane, without altering colliders."""
    d = world - camera.position
    cy, sy = math.cos(camera.yaw_rad), math.sin(camera.yaw_rad)
    # Rotate around world Z; forward is +Y, right is +X.
    right = d.x * cy - d.y * sy
    forward = d.x * sy + d.y * cy
    cp, sp = math.cos(camera.pitch_rad), math.sin(camera.pitch_rad)
    height = d.z * cp - forward * sp
    depth = forward * cp + d.z * sp
    if camera.mode is ProjectionMode.TOP_DOWN:
        x, y, scale = right, forward, camera.orthographic_scale
        visible = True
    elif camera.mode is ProjectionMode.PLATFORMER:
        x, y, scale = right, height, camera.orthographic_scale
        visible = True
    else:
        # Pseudo-3D modes blend orthographic and true perspective projection.
        # FULL_3D uses 100% perspective; 2.5–2.9 use weighted depth.
        weight = 1.0 if camera.mode is ProjectionMode.FULL_3D else DEPTH_WEIGHT[camera.mode]
        visible = depth > camera.near_plane
        denominator = max(camera.near_plane, depth)
        perspective = camera.focal_length / denominator
        scale = camera.orthographic_scale * (1 - weight) + perspective * weight
        x, y = right, height
        if camera.mode in DEPTH_WEIGHT:
            x += depth * camera.parallax_scale * (1 - weight)
    if variant is not None and variant.family is WorldFamily.LENSED:
        # Radial lens warp applies only to render projection, never physics.
        r2 = (x * x + y * y) / (1 + x * x + y * y)
        gain = 1 + variant.lens_scale * variant.intensity * r2
        x, y = x * gain, y * gain
    return ProjectedPoint(x * scale, y * scale, depth, scale, visible, camera.mode)


def project_scene(points: tuple[Vec3, ...], camera: CameraSpec,
                  *, variant: WorldVariant | None = None) -> tuple[ProjectedPoint, ...]:
    if len(points) > 2_000_000 or any(not isinstance(p, Vec3) for p in points):
        raise WorldGeometryError("point cloud exceeds budget or contains non-Vec3")
    return tuple(project_point(p, camera, variant=variant) for p in points)
