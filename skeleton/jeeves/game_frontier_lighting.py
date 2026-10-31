"""Character- and environment-aware CPU reference ray tracing and lighting.

Computes real ray/occluder intersections and direct illumination, penumbra
sampling, cast shadows, wet reflectance and low-cost reflected ambient light.
This is NOT GPU path tracing or an Nvidia RTX/photoreal neural renderer.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .game_frontier_production import Vec3


class LightingError(ValueError):
    pass


def _number(v: float, name: str, lo: float, hi: float) -> float:
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
        raise LightingError(f"invalid {name}")
    return float(v)


def _length(v: Vec3) -> float:
    return math.sqrt(v.dot(v))


def _normal(v: Vec3) -> Vec3:
    length = _length(v)
    if length <= 1e-10:
        raise LightingError("zero length direction")
    return v.scaled(1 / length)


@dataclass(frozen=True)
class Ray:
    origin: Vec3
    direction: Vec3

    def __post_init__(self) -> None:
        if abs(_length(self.direction) - 1) > 1e-4:
            raise LightingError("ray direction must be unit length")


@dataclass(frozen=True)
class RayOccluder:
    object_id: str
    category: str
    center: Vec3
    shape: str
    radius_m: float = .5
    half_extents: Vec3 = Vec3(.5, .5, .5)
    opacity: float = 1.0
    reflectivity: float = .1

    def __post_init__(self) -> None:
        if not self.object_id or len(self.object_id) > 128:
            raise LightingError("occluder identity required")
        if self.category not in ("character", "foliage", "building", "terrain",
                                 "clothing", "object", "cloud"):
            raise LightingError("unsupported occluder category")
        if self.shape not in ("sphere", "box"):
            raise LightingError("occluder must be sphere or box")
        _number(self.radius_m, "radius_m", .001, 1e5)
        for name in ("x", "y", "z"):
            _number(getattr(self.half_extents, name), "half extent", .001, 1e5)
        _number(self.opacity, "opacity", 0, 1)
        _number(self.reflectivity, "reflectivity", 0, 1)


@dataclass(frozen=True)
class LightSource:
    light_id: str
    position: Vec3
    intensity: float
    radius_m: float = 0.0
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        if not self.light_id or len(self.light_id) > 128:
            raise LightingError("light ID required")
        _number(self.intensity, "light intensity", 0, 1e7)
        _number(self.radius_m, "area light radius", 0, 10000)
        if len(self.color) != 3:
            raise LightingError("RGB triplet required")
        for c in self.color:
            _number(c, "color", 0, 1)


@dataclass(frozen=True)
class RayHit:
    object_id: str
    category: str
    distance_m: float
    point: Vec3
    opacity: float
    reflectivity: float


def _intersection(ray: Ray, object: RayOccluder, max_distance: float) -> float | None:
    if object.shape == "sphere":
        oc = ray.origin - object.center
        b = 2 * oc.dot(ray.direction)
        c = oc.dot(oc) - object.radius_m ** 2
        disc = b * b - 4 * c
        if disc < 0:
            return None
        root = math.sqrt(disc)
        roots = ((-b - root) / 2, (-b + root) / 2)
        return next((t for t in roots if 1e-5 < t < max_distance), None)
    # Axis aligned slab algorithm; zero direction components are handled
    # explicitly to avoid inf*0 and silently missed occluders.
    near, far = 0.0, max_distance
    for axis in ("x", "y", "z"):
        start = getattr(ray.origin, axis) - getattr(object.center, axis)
        direct = getattr(ray.direction, axis)
        ext = getattr(object.half_extents, axis)
        if abs(direct) < 1e-12:
            if not -ext <= start <= ext:
                return None
            continue
        a, b = (-ext - start) / direct, (ext - start) / direct
        near = max(near, min(a, b))
        far = min(far, max(a, b))
        if near > far:
            return None
    distance = near if near > 1e-5 else far
    return distance if 1e-5 < distance < max_distance else None


def trace_ray(ray: Ray, occluders: tuple[RayOccluder, ...], *,
              max_distance: float, exclude_id: str | None = None) -> RayHit | None:
    if len(occluders) > 65536:
        raise LightingError("occluder budget exceeded")
    _number(max_distance, "max_distance", .00001, 1e9)
    winner: RayHit | None = None
    closest = max_distance
    for obj in occluders:
        if not isinstance(obj, RayOccluder):
            raise LightingError("invalid ray occluder")
        if obj.object_id == exclude_id or obj.opacity <= 0:
            continue
        distance = _intersection(ray, obj, closest)
        if distance is not None:
            closest = distance
            winner = RayHit(obj.object_id, obj.category, distance,
                            ray.origin + ray.direction.scaled(distance),
                            obj.opacity, obj.reflectivity)
    return winner


@dataclass(frozen=True)
class SurfaceSample:
    object_id: str
    position: Vec3
    normal: Vec3
    albedo: tuple[float, float, float] = (.7, .7, .7)
    roughness: float = .8
    wetness: float = 0.0
    emission: float = 0.0

    def __post_init__(self) -> None:
        if not self.object_id or len(self.object_id) > 128:
            raise LightingError("surface identity required")
        if abs(_length(self.normal) - 1) > 1e-4:
            raise LightingError("surface normal must be normalized")
        if len(self.albedo) != 3:
            raise LightingError("albedo RGB triplet required")
        for c in self.albedo:
            _number(c, "albedo", 0, 1)
        for n in ("roughness", "wetness"):
            _number(getattr(self, n), n, 0, 1)
        _number(self.emission, "emission", 0, 1e5)


@dataclass(frozen=True)
class LightingSample:
    object_id: str
    radiance_rgb: tuple[float, float, float]
    direct_light: float
    ambient_light: float
    shadow_occlusion: float
    wet_specular: float
    source_occluders: tuple[str, ...]
    character_occluders: tuple[str, ...]
    model: str = "direct_ray_intersections_reference_v1"


def _light_point(light: LightSource, index: int, total: int) -> Vec3:
    if light.radius_m == 0 or total == 1:
        return light.position
    # Deterministic disk-like area source offsets, aligned to XY.
    theta = 2 * math.pi * ((index * .618033988749895) % 1)
    radius = light.radius_m * math.sqrt((index + .5) / total)
    return light.position + Vec3(math.cos(theta) * radius,
                                  math.sin(theta) * radius, 0)


def illuminate_surface(surface: SurfaceSample,
                       lights: tuple[LightSource, ...],
                       occluders: tuple[RayOccluder, ...], *,
                       ambient_rgb: tuple[float, float, float] = (.1, .1, .1),
                       shadow_rays_per_light: int = 4,
                       shadow_world_factor: float = 1.0) -> LightingSample:
    if len(lights) > 256:
        raise LightingError("too many lights")
    if type(shadow_rays_per_light) is not int or not 1 <= shadow_rays_per_light <= 32:
        raise LightingError("shadow sampling out of bounds")
    _number(shadow_world_factor, "shadow_world_factor", 0, 2)
    if len(ambient_rgb) != 3:
        raise LightingError("ambient RGB required")
    for v in ambient_rgb:
        _number(v, "ambient", 0, 1e4)
    result = [v * a + surface.emission for v, a in zip(ambient_rgb, surface.albedo)]
    ambient = sum(result) / 3
    direct, shadow_total, ray_total = 0.0, 0.0, 0
    blockers = set()
    character_blockers = set()
    wet_glint = 0.0
    for source in lights:
        if not isinstance(source, LightSource):
            raise LightingError("LightSource required")
        n = shadow_rays_per_light if source.radius_m > 0 else 1
        for i in range(n):
            target = _light_point(source, i, n)
            delta = target - surface.position
            distance = _length(delta)
            if distance <= .001:
                continue
            direction = delta.scaled(1 / distance)
            cosine = max(0, surface.normal.dot(direction))
            if cosine <= 0:
                continue
            ray_total += 1
            offset_origin = surface.position + surface.normal.scaled(.001)
            hit = trace_ray(Ray(offset_origin, direction), occluders,
                            max_distance=distance - .001,
                            exclude_id=surface.object_id)
            occlusion = hit.opacity if hit else 0.0
            shadow_total += occlusion
            if hit:
                blockers.add(hit.object_id)
                if hit.category == "character":
                    character_blockers.add(hit.object_id)
            transmission = 1 - occlusion
            # Attenuation is intentionally finite and bounded near emitters.
            attenuation = source.intensity / (1 + .1 * distance * distance)
            Lambert = cosine * attenuation * transmission / n
            direct += Lambert
            for j in range(3):
                result[j] += source.color[j] * surface.albedo[j] * Lambert
            # Wet surfaces are more specular; this is only one simple
            # view-independent highlight proxy, not a path-traced BRDF.
            gloss = surface.wetness * (1 - surface.roughness) * Lambert
            wet_glint += gloss
            for j in range(3):
                result[j] += source.color[j] * gloss
    shadow = _clamp_shadow((shadow_total / ray_total) if ray_total else 0,
                           shadow_world_factor)
    return LightingSample(surface.object_id, tuple(result), direct, ambient,
                          shadow, wet_glint,
                          tuple(sorted(blockers)), tuple(sorted(character_blockers)))


def _clamp_shadow(value: float, strength: float) -> float:
    return min(1.0, max(0, value * strength))


def illuminate_scene(surfaces: tuple[SurfaceSample, ...],
                     lights: tuple[LightSource, ...],
                     occluders: tuple[RayOccluder, ...], *,
                     ambient_rgb: tuple[float, float, float] = (.1, .1, .1),
                     shadow_rays_per_light: int = 4) -> tuple[LightingSample, ...]:
    if len(surfaces) > 4096:
        raise LightingError("sample budget exceeded")
    return tuple(illuminate_surface(s, lights, occluders,
                                    ambient_rgb=ambient_rgb,
                                    shadow_rays_per_light=shadow_rays_per_light)
                 for s in surfaces)
