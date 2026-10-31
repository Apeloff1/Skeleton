"""Motion-coherent leaf shadows and 3D weather-dampened direct illumination.

CPU reference implementation: the same moving leaf geometry feeds
both ray-hit tests and projected shadow size. Atmospheric extinction uses
Beer–Lambert optical depth; light-source distance uses inverse-square falloff.
Neither method claims photoreal GPU path tracing.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .game_frontier_production import Vec3
from .game_frontier_lighting import LightSource, Ray, RayOccluder, SurfaceSample, trace_ray
from .game_frontier_ecosystem import AtmosphereSample, bounded, clamp


class PhotometryError(ValueError):
    pass


def norm(v: Vec3) -> float:
    return math.sqrt(v.dot(v))


def direction(v: Vec3) -> Vec3:
    length = norm(v)
    if length <= 1e-10:
        raise PhotometryError("zero-length geometry direction")
    return v.scaled(1 / length)


@dataclass(frozen=True)
class LeafPose:
    leaf_id: str
    anchor: Vec3
    center: Vec3
    velocity: Vec3
    normal: Vec3
    width_m: float
    length_m: float
    opacity: float = 1.
    mass_kg: float = .01
    stiffness: float = 5.

    def __post_init__(self) -> None:
        if not self.leaf_id or len(self.leaf_id) > 128:
            raise PhotometryError("leaf id required")
        if abs(norm(self.normal) - 1) > 1e-5:
            raise PhotometryError("unit leaf normal required")
        for name, hi in (("width_m", 10), ("length_m", 10),
                         ("mass_kg", 100), ("stiffness", 10000)):
            bounded(getattr(self, name), name, .000001, hi)
        bounded(self.opacity, "opacity", 0, 1)


def move_leaf(leaf: LeafPose, *, wind_mps: Vec3, dt_s: float,
              impact_impulse_ns: Vec3 = Vec3(0, 0, 0)) -> LeafPose:
    """Stable bounded spring/damper motion with character-impact impulse.

    Reorient the rectangle to its new motion; physical canopy/FEM attachment
    constraints remain owned by the native physics solver.
    """
    dt = bounded(dt_s, "leaf dt", 0, .1)
    steps = max(1, math.ceil(dt / .005))
    sub = dt / steps
    position, velocity = leaf.center, leaf.velocity
    for step in range(steps):
        restoring = (leaf.anchor - position).scaled(leaf.stiffness)
        damping = velocity.scaled(-.7 * math.sqrt(leaf.stiffness * leaf.mass_kg))
        windforce = (wind_mps - velocity).scaled(.015 * leaf.width_m * leaf.length_m)
        force = restoring + damping + windforce
        if step == 0 and dt > 0:
            force = force + impact_impulse_ns.scaled(1 / sub)
        acceleration = force.scaled(1 / leaf.mass_kg)
        speed = norm(acceleration)
        if speed > 100:
            acceleration = acceleration.scaled(100 / speed)
        velocity = velocity + acceleration.scaled(sub)
        position = position + velocity.scaled(sub)
    # Don't let orientation and shadow disagree about where the leaf has moved.
    sideways = Vec3(-velocity.y, velocity.x, .2)
    n = direction(sideways) if norm(velocity) > .01 else leaf.normal
    return replace(leaf, center=position, velocity=velocity, normal=n)


def _leaf_axes(leaf: LeafPose) -> tuple[Vec3, Vec3]:
    reference = Vec3(0, 0, 1) if abs(leaf.normal.z) < .9 else Vec3(0, 1, 0)
    u = direction(leaf.normal.cross(reference))
    v = direction(leaf.normal.cross(u))
    return u, v


def _corners(leaf: LeafPose) -> tuple[Vec3, ...]:
    u, v = _leaf_axes(leaf)
    a, b = u.scaled(leaf.length_m * .5), v.scaled(leaf.width_m * .5)
    return (leaf.center-a-b, leaf.center+a-b,
            leaf.center+a+b, leaf.center-a+b)


def ray_intersects_leaf(ray: Ray, leaf: LeafPose, max_distance: float) -> bool:
    bounded(max_distance, "max_distance", .00001, 1e8)
    divisor = ray.direction.dot(leaf.normal)
    if abs(divisor) < 1e-10:
        return False
    t = (leaf.center - ray.origin).dot(leaf.normal) / divisor
    if not 1e-6 < t < max_distance:
        return False
    displacement = ray.origin + ray.direction.scaled(t) - leaf.center
    u, v = _leaf_axes(leaf)
    return (abs(displacement.dot(u)) <= leaf.length_m * .5 + 1e-7
            and abs(displacement.dot(v)) <= leaf.width_m * .5 + 1e-7)


@dataclass(frozen=True)
class LeafShadowAudit:
    leaf_id: str
    polygon: tuple[Vec3, ...]
    ray_shadow_coverage: float
    geometric_area_m2: float
    predicted_area_m2: float
    area_error_m2: float
    verified: bool


def verify_leaf_shadow(leaf: LeafPose, *, sun_toward: Vec3,
                       receiver_z_m: float = 0.) -> LeafShadowAudit:
    sun = direction(sun_toward)
    ground = bounded(receiver_z_m, "receiver_z", -100000, 100000)
    if sun.z <= 1e-4 or any(p.z <= ground for p in _corners(leaf)):
        raise PhotometryError("sun above horizon and elevated leaf required")
    polygon = tuple(p - sun.scaled((p.z - ground) / sun.z)
                    for p in _corners(leaf))
    area = .5 * abs(sum(a.x*b.y-b.x*a.y for a, b in
                          zip(polygon, polygon[1:] + polygon[:1])))
    expected = (leaf.length_m * leaf.width_m *
                abs(leaf.normal.dot(sun)) / sun.z)
    # Independent ray-based coherence verifier follows the same moved pose.
    probe = (leaf.center,) + _corners(leaf)
    hit = 0
    for p in probe:
        landing = p - sun.scaled((p.z - ground) / sun.z)
        ray = Ray(landing + sun.scaled(.00001), sun)
        if ray_intersects_leaf(ray, leaf, 1e6):
            hit += 1
    error = abs(area - expected)
    verified = (error <= 1e-6 + expected * 1e-4) and hit == len(probe)
    return LeafShadowAudit(leaf.leaf_id, polygon, hit / len(probe),
                           area, expected, error, verified)


@dataclass(frozen=True)
class LightClimate:
    atmosphere: AtmosphereSample
    rain_mm_h: float = 0.
    cloud_opacity: float = 0.
    haze_extinction_per_m: float = 0.
    light_radius_bias_m: float = .25

    def __post_init__(self) -> None:
        bounded(self.rain_mm_h, "rain", 0, 1000)
        bounded(self.cloud_opacity, "cloud opacity", 0, 1)
        bounded(self.haze_extinction_per_m, "haze", 0, 1)
        bounded(self.light_radius_bias_m, "light radius bias", .001, 100)


@dataclass(frozen=True)
class PhotometricSurface:
    surface_id: str
    radiance_rgb: tuple[float, float, float]
    unoccluded_direct: float
    delivered_direct: float
    volumetric_transmission: float
    geometric_shadow_fraction: float
    leaf_shadow_fraction: float
    occluder_ids: tuple[str, ...]
    authority: str = "reference_cpu_3d_ray_geometry"


def illuminate_atmosphere_3d(
    surface: SurfaceSample, sources: tuple[LightSource, ...],
    occluders: tuple[RayOccluder, ...], leaves: tuple[LeafPose, ...],
    climate: LightClimate, *, area_samples: int = 4,
) -> PhotometricSurface:
    """Bounded 3D source–occluder–leaf–receiver calculations.

    Transparent objects compose transmittance multiplicatively, not as a
    nearest-hit approximation. Fog and rain attenuate source light without
    mathematically changing physical occluder shadow fraction.
    """
    if len(sources) > 64 or len(occluders) > 2048 or len(leaves) > 2048:
        raise PhotometryError("scene light budget exceeded")
    if type(area_samples) is not int or not 1 <= area_samples <= 16:
        raise PhotometryError("invalid area light sample count")
    result = [surface.emission] * 3
    unblocked = transmitted = volume_factor_sum = geometric_shadow = leaf_shadow = rays = 0.
    hits = set()
    for source in sources:
        count = area_samples if source.radius_m > 0 else 1
        for i in range(count):
            angle = 2 * math.pi * ((i * .61803398875) % 1)
            radius = source.radius_m * math.sqrt((i + .5) / count)
            target = source.position + Vec3(radius*math.cos(angle),
                                             radius*math.sin(angle), 0)
            delta = target - surface.position
            length = norm(delta)
            if length < 1e-5:
                continue
            unit_ray = delta.scaled(1 / length)
            lambert = max(0., surface.normal.dot(unit_ray))
            if lambert == 0:
                continue
            ray = Ray(surface.position + surface.normal.scaled(.0001), unit_ray)
            solid_transmission = 1.
            for obj in occluders:
                if obj.object_id == surface.object_id or obj.opacity == 0:
                    continue
                if trace_ray(ray, (obj,), max_distance=length-.0001) is not None:
                    solid_transmission *= 1-obj.opacity
                    hits.add(obj.object_id)
            geometric_shadow += 1-solid_transmission
            foliage_transmission = 1.
            for leaf in leaves:
                if ray_intersects_leaf(ray, leaf, length-.0001):
                    foliage_transmission *= 1-leaf.opacity
                    hits.add(leaf.leaf_id)
            leaf_shadow += 1-foliage_transmission
            # Aerosol extinction combines explicit fog, haze and rain optics.
            extinction = (climate.atmosphere.fog_extinction_per_m
                          + climate.haze_extinction_per_m
                          + climate.rain_mm_h*.000004)
            optical = math.exp(-min(700., extinction*length))
            optical *= (1.-.65*climate.cloud_opacity)
            intensity = source.intensity / (4*math.pi*
                              (length*length+climate.light_radius_bias_m**2))
            base = intensity*lambert/count
            unblocked += base
            value = base*solid_transmission*foliage_transmission*optical
            transmitted += value
            volume_factor_sum += optical
            # Wet surfaces generate stronger (bounded) direct highlights.
            # This view-independent approximation is a candidate BRDF cue.
            glint = value*surface.wetness*(1.-surface.roughness)*.5
            for channel in range(3):
                result[channel] += source.color[channel]*(value*surface.albedo[channel]+glint)
            rays += 1
    return PhotometricSurface(surface.object_id, tuple(result), unblocked,
                              transmitted,
                              volume_factor_sum/rays if rays else 1.,
                              geometric_shadow/rays if rays else 0.,
                              leaf_shadow/rays if rays else 0.,
                              tuple(sorted(hits)))
