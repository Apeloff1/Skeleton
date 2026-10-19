"""ElasticBodySkin3D: topology-aware, bone-anchored reference skin wrapper.

A pressure/shear/wetness responsive vertex model that retains original mesh,
normals, rig topology and bone IDs; its result is a candidate snapshot, not
a claim of production FEM tissue, cloth, skinning or SoftBody3D parity.

Skin nodes are tethered to sampled animation anchors and connected by the
mesh's actual triangle adjacency. Optional pinned nodes follow the exact
animated bone pose; unpinned nodes deform under wind, impacts and gravity.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math

from .game_frontier_production import (
    Vec3, CharacterSkeleton, SkinnedMesh, AnimationClip, pose_skinned_mesh,
)


class ElasticSkinError(ValueError):
    pass


def finite(v: float, name: str, lo: float, hi: float) -> float:
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
        raise ElasticSkinError(f"{name} must be finite in [{lo}, {hi}]")
    return float(v)


def length(vec: Vec3) -> float:
    return math.sqrt(vec.dot(vec))


@dataclass(frozen=True)
class ElasticBodySkin3D:
    mass_per_vertex_kg: float = .04
    anchor_stiffness_n_m: float = 18.
    shear_stiffness_n_m: float = 8.
    damping_n_s_m: float = 1.
    wind_drag: float = .12
    water_absorption: float = .1
    temperature_softening: float = .005
    maximum_strain: float = .5
    collision_ground_z_m: float = -100.
    gravity_mps2: float = 9.80665
    maximum_vertices: int = 4096

    def __post_init__(self) -> None:
        for key, a, b in (
            ("mass_per_vertex_kg", .0001, 100),
            ("anchor_stiffness_n_m", 0, 10000),
            ("shear_stiffness_n_m", 0, 10000),
            ("damping_n_s_m", 0, 10000),
            ("wind_drag", 0, 100),
            ("water_absorption", 0, 1),
            ("temperature_softening", 0, 1),
            ("maximum_strain", 0, 5),
            ("collision_ground_z_m", -10000, 10000),
            ("gravity_mps2", -100, 100),
        ):
            finite(getattr(self, key), key, a, b)
        if type(self.maximum_vertices) is not int or not 1 <= self.maximum_vertices <= 16384:
            raise ElasticSkinError("vertex budget invalid")


@dataclass(frozen=True)
class ElasticSkinState:
    positions: tuple[Vec3, ...]
    velocities: tuple[Vec3, ...]
    wetness: float = 0.
    temperature_c: float = 20.

    def __post_init__(self) -> None:
        if len(self.positions) != len(self.velocities):
            raise ElasticSkinError("position/velocity count mismatch")
        finite(self.wetness, "wetness", 0, 1)
        finite(self.temperature_c, "temperature", -120, 120)


@dataclass(frozen=True)
class ElasticSkinFrame:
    positions: tuple[Vec3, ...]
    velocities: tuple[Vec3, ...]
    wetness: float
    temperature_c: float
    max_measured_strain: float
    collision_count: int
    mean_anchor_displacement_m: float
    mesh_digest: str
    evidence_digest: str
    authority: str = "skin_wrapper_reference_not_native_fem"


def initial_skin_state(skeleton: CharacterSkeleton, mesh: SkinnedMesh,
                       clip: AnimationClip, *, time_ms: int) -> ElasticSkinState:
    positions = pose_skinned_mesh(skeleton, mesh, clip, time_ms)
    return ElasticSkinState(positions, tuple(Vec3(0, 0, 0) for _ in positions))


def _mesh_links(mesh: SkinnedMesh) -> tuple[tuple[int,int], ...]:
    links: set[tuple[int,int]] = set()
    for a,b,c in mesh.triangles:
        for x,y in ((a,b),(b,c),(c,a)):
            links.add((min(x,y), max(x,y)))
    return tuple(sorted(links))


def simulate_elastic_skin(
    skeleton: CharacterSkeleton,
    mesh: SkinnedMesh,
    clip: AnimationClip,
    wrapper: ElasticBodySkin3D,
    *,
    time_ms: int,
    delta_s: float,
    wind_mps: Vec3 = Vec3(0, 0, 0),
    rainfall_mm_h: float = 0.,
    air_temperature_c: float = 20.,
    impact_force_n: Vec3 = Vec3(0, 0, 0),
    pinned_vertices: tuple[int, ...] = (0,),
    state: ElasticSkinState | None = None,
) -> ElasticSkinFrame:
    """Semi-implicit damped reference integration with coherent bone anchors.

    This does not create a Godot softbody automatically; Forge may export the
    candidate mesh and separate pinned/elasticity information for inspection.
    """
    dt = finite(delta_s, "elastic dt", 0, .2)
    rain = finite(rainfall_mm_h, "rain", 0, 1000)
    ambient = finite(air_temperature_c, "air temperature", -120, 120)
    if len(mesh.vertices) > wrapper.maximum_vertices or len(mesh.vertices) == 0:
        raise ElasticSkinError("explicit elastic vertex budget exceeded")
    if not pinned_vertices or len(set(pinned_vertices)) != len(pinned_vertices):
        raise ElasticSkinError("pinned vertex identifiers required")
    if any(type(k) is not int or not 0 <= k < len(mesh.vertices) for k in pinned_vertices):
        raise ElasticSkinError("pinned vertex index invalid")
    anchors = pose_skinned_mesh(skeleton, mesh, clip, time_ms)
    current = state or ElasticSkinState(anchors,tuple(Vec3(0,0,0) for _ in anchors))
    if len(current.positions) != len(anchors):
        raise ElasticSkinError("state mesh dimension mismatch")
    pins = set(pinned_vertices)
    links = _mesh_links(mesh)
    rest_lengths = [length(anchors[b]-anchors[a]) for a,b in links]
    steps = max(1, math.ceil(dt / .005))
    h = dt / steps
    positions = list(current.positions)
    velocities = list(current.velocities)
    wet = current.wetness
    temp = current.temperature_c
    collisions = 0
    for _ in range(steps):
        wet = min(1.,max(0.,wet+(1-wet)*rain*h*wrapper.water_absorption/200))
        temp += (ambient-temp)*min(1., h*.12)
        effective_shear = wrapper.shear_stiffness_n_m * (
            1 - min(.75,wrapper.temperature_softening*max(0,temp-20)))
        forces = [Vec3(0,0,0) for _ in positions]
        # Link springs computed from current distances, not initial geometry.
        for (a,b),original in zip(links,rest_lengths):
            difference = positions[b]-positions[a]
            current_len = length(difference)
            if current_len <= 1e-9 or original <= 1e-9:
                continue
            # Limit elastic force impulse for stability without invalidating
            # the non-stretched reference topology.
            elongation = max(-wrapper.maximum_strain*original,
                             min(wrapper.maximum_strain*original,
                                 current_len-original))
            force = difference.scaled(effective_shear*elongation/current_len)
            forces[a] = forces[a] + force
            forces[b] = forces[b] - force
        for i, pos in enumerate(positions):
            if i in pins:
                positions[i] = anchors[i]
                velocities[i] = Vec3(0,0,0)
                continue
            mass = wrapper.mass_per_vertex_kg*(1+wet*.3)
            acceleration = (
                (anchors[i]-pos).scaled(wrapper.anchor_stiffness_n_m)
                + forces[i]
                + (wind_mps-velocities[i]).scaled(wrapper.wind_drag)
                + velocities[i].scaled(-wrapper.damping_n_s_m)
                + impact_force_n.scaled(1/max(1,len(positions)-len(pins)))
                + Vec3(0,0,-wrapper.gravity_mps2*mass)
            ).scaled(1/mass)
            magnitude = length(acceleration)
            if magnitude > 500:
                acceleration = acceleration.scaled(500/magnitude)
            velocities[i] = velocities[i] + acceleration.scaled(h)
            positions[i] = pos + velocities[i].scaled(h)
            if positions[i].z < wrapper.collision_ground_z_m:
                p = positions[i]
                positions[i] = Vec3(p.x,p.y,wrapper.collision_ground_z_m)
                v = velocities[i]
                velocities[i] = Vec3(v.x*.8,v.y*.8,max(0,-v.z*.08))
                collisions += 1
    strain = 0.
    for (a,b),rest in zip(links,rest_lengths):
        if rest > 1e-9:
            strain = max(strain,abs(length(positions[b]-positions[a])-rest)/rest)
    mean_disp = sum(length(p-a) for p,a in zip(positions,anchors))/len(anchors)
    receipt = {
        "mesh_digest": mesh.digest,
        "vertex_count": len(positions), "strain": strain,
        "wet":wet, "temperature":temp,
        "collisions": collisions,
        "positions": [[p.x,p.y,p.z] for p in positions],
    }
    digest=sha256(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return ElasticSkinFrame(
        tuple(positions),tuple(velocities),wet,temp,strain,
        collisions,mean_disp,mesh.digest,digest,
    )
