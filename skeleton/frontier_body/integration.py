"""Explicit skin and fascia integration for another runtime to call.

``AnatomicalSkinIntegrator`` is the protocol. ``ReferenceAnatomicalSkinIntegrator``
drives the existing elastic skin solver and the existing soft-node cloth model
from one request: a collision impulse, wetness, a locomotion stride, and the
anatomical rig. Pinned rig vertices are written back to the posed anchors
after every solve. Strain on skin links and on fascia/cloth tethers is limited
to the elastic wrapper's ``maximum_strain``.

This module does not import a package named frontier_runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
from typing import Protocol, runtime_checkable

from skeleton.jeeves.game_frontier_elastic_skin3d import (
    ElasticBodySkin3D,
    ElasticSkinError,
    ElasticSkinFrame,
    ElasticSkinState,
    simulate_elastic_skin,
)
from skeleton.jeeves.game_frontier_motion import (
    CharacterState,
    CollisionPlane,
    MotionPhysicsError,
    SoftNode,
    Weather,
    simulate_character,
    simulate_soft_nodes,
)
from skeleton.jeeves.game_frontier_production import (
    AnimationClip,
    CharacterSkeleton,
    FrontierProductionError,
    SkinnedMesh,
    Vec3,
    pose_skinned_mesh,
)


class SkinIntegrationError(ValueError):
    """Rejected skin, fascia, cloth, or locomotion integration step."""


def _real(value: float, label: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value):
        raise SkinIntegrationError(f"{label} must be finite")
    if not lo <= float(value) <= hi:
        raise SkinIntegrationError(f"{label} must lie in [{lo}, {hi}]")
    return float(value)


def _length(vector: Vec3) -> float:
    return math.sqrt(vector.dot(vector))


@dataclass(frozen=True)
class SkinIntegrationRequest:
    skeleton: CharacterSkeleton
    mesh: SkinnedMesh
    clip: AnimationClip
    collision_impulse_n: Vec3
    wetness: float
    stride_m: float
    stride_length_m: float
    delta_s: float
    game_time_s: float
    pinned_vertices: tuple[int, ...] = (0,)
    elastic: ElasticBodySkin3D | None = None
    skin_state: ElasticSkinState | None = None
    locomotion: CharacterState | None = None
    surfaces: tuple[CollisionPlane, ...] = ()
    desired_velocity: Vec3 | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.skeleton, CharacterSkeleton):
            raise SkinIntegrationError("integration requires an anatomical skeleton")
        if not isinstance(self.mesh, SkinnedMesh):
            raise SkinIntegrationError("integration requires a skinned mesh")
        if not isinstance(self.clip, AnimationClip):
            raise SkinIntegrationError("integration requires an animation clip")
        if not isinstance(self.collision_impulse_n, Vec3):
            raise SkinIntegrationError("collision impulse must be a vector")
        _real(self.wetness, "wetness", 0, 1)
        _real(self.stride_m, "stride_m", 0, 10000)
        _real(self.stride_length_m, "stride_length_m", 1e-4, 1000)
        _real(self.delta_s, "delta_s", 0, 0.1)
        _real(self.game_time_s, "game_time_s", 0, 1e12)
        if type(self.pinned_vertices) is not tuple or not self.pinned_vertices:
            raise SkinIntegrationError("pinned rig vertices are required")
        if len(set(self.pinned_vertices)) != len(self.pinned_vertices):
            raise SkinIntegrationError("pinned rig vertices must be unique")
        if any(type(index) is not int or isinstance(index, bool) for index in self.pinned_vertices):
            raise SkinIntegrationError("pinned rig vertices must be integer indices")
        if self.elastic is not None and not isinstance(self.elastic, ElasticBodySkin3D):
            raise SkinIntegrationError("elastic wrapper must be ElasticBodySkin3D")
        if self.skin_state is not None and not isinstance(self.skin_state, ElasticSkinState):
            raise SkinIntegrationError("skin state must be ElasticSkinState")
        if self.locomotion is not None and not isinstance(self.locomotion, CharacterState):
            raise SkinIntegrationError("locomotion must be a character state")
        if type(self.surfaces) is not tuple or any(not isinstance(item, CollisionPlane) for item in self.surfaces):
            raise SkinIntegrationError("collision surfaces must be a tuple of planes")
        if self.desired_velocity is not None and not isinstance(self.desired_velocity, Vec3):
            raise SkinIntegrationError("desired velocity must be a vector")


@dataclass(frozen=True)
class SkinIntegrationResult:
    skin: ElasticSkinFrame
    fascia: tuple[SoftNode, ...]
    cloth: tuple[SoftNode, ...]
    pinned_vertices: tuple[int, ...]
    anchor_positions: tuple[Vec3, ...]
    stride_m: float
    stride_time_ms: int
    gait: str
    max_strain: float
    collision_impulse_n: Vec3
    wetness: float
    game_time_s: float
    locomotion_applied: bool
    label: str = "simulated"


@runtime_checkable
class AnatomicalSkinIntegrator(Protocol):
    """Call surface for a runtime that owns collision, cloth, and locomotion."""

    def integrate_character_skin(self, request: SkinIntegrationRequest) -> SkinIntegrationResult:
        """Advance skin and fascia from one typed request."""


def _gait_from_speed(speed_m_s: float) -> str:
    """Horizontal bands shared with ``simulate_character`` (walk / run / idle)."""

    if speed_m_s > 4.0:
        return "run"
    if speed_m_s < 0.1:
        return "idle"
    return "walk"


def _stride_time_ms(clip: AnimationClip, stride_m: float, stride_length_m: float) -> int:
    duration = clip.keyframes[-1].time_ms
    if duration <= 0:
        raise SkinIntegrationError("animation clip has no duration")
    phase = stride_m / stride_length_m
    sampled = int(round(phase * duration))
    if clip.loop:
        return sampled % duration
    return min(sampled, duration)


def _mesh_links(mesh: SkinnedMesh) -> tuple[tuple[int, int], ...]:
    links: set[tuple[int, int]] = set()
    for a, b, c in mesh.triangles:
        for left, right in ((a, b), (b, c), (c, a)):
            links.add((min(left, right), max(left, right)))
    return tuple(sorted(links))


def _link_strain(
    positions: tuple[Vec3, ...] | list[Vec3],
    links: tuple[tuple[int, int], ...],
    rest: tuple[float, ...],
) -> float:
    strain = 0.0
    for (start, end), length0 in zip(links, rest):
        if length0 > 1e-9:
            current = _length(positions[end] - positions[start])
            strain = max(strain, abs(current - length0) / length0)
    return strain


def _enforce_link_strain(
    positions: tuple[Vec3, ...],
    anchors: tuple[Vec3, ...],
    mesh: SkinnedMesh,
    pins: set[int],
    maximum_strain: float,
) -> tuple[tuple[Vec3, ...], float]:
    """Project shared edges until strain is inside the wrapper limit.

    The reference skin solver performs two projection passes. A hard collision
    can leave a remainder, so the integration step repeats the same pin-safe
    correction until the measured strain fits or the iteration budget ends.
    """

    links = _mesh_links(mesh)
    rest = tuple(_length(anchors[end] - anchors[start]) for start, end in links)
    current = list(positions)
    for _ in range(32):
        if _link_strain(current, links, rest) <= maximum_strain + 1e-8:
            break
        for (start, end), length0 in zip(links, rest):
            if length0 <= 1e-9:
                continue
            delta = current[end] - current[start]
            span = _length(delta)
            if span <= 1e-9:
                continue
            low = length0 * (1.0 - maximum_strain)
            high = length0 * (1.0 + maximum_strain)
            target = min(high, max(low, span))
            if abs(span - target) <= 1e-12:
                continue
            correction = delta.scaled((span - target) / span)
            if start in pins and end in pins:
                continue
            if start in pins:
                current[end] = current[end] - correction
            elif end in pins:
                current[start] = current[start] + correction
            else:
                current[start] = current[start] + correction.scaled(0.5)
                current[end] = current[end] - correction.scaled(0.5)
        for index in pins:
            current[index] = anchors[index]
    solved = tuple(current)
    return solved, _link_strain(solved, links, rest)


def _skin_frame(
    skin: ElasticSkinFrame,
    positions: tuple[Vec3, ...],
    anchors: tuple[Vec3, ...],
    strain: float,
    mesh_digest: str,
) -> ElasticSkinFrame:
    mean = sum(_length(position - anchor) for position, anchor in zip(positions, anchors)) / len(anchors)
    receipt = {
        "mesh_digest": mesh_digest,
        "vertex_count": len(positions),
        "strain": strain,
        "wet": skin.wetness,
        "temperature": skin.temperature_c,
        "collisions": skin.collision_count,
        "positions": [[point.x, point.y, point.z] for point in positions],
    }
    digest = sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ElasticSkinFrame(
        positions,
        skin.velocities,
        skin.wetness,
        skin.temperature_c,
        strain,
        skin.collision_count,
        mean,
        mesh_digest,
        digest,
    )


def _bound_tether(position: Vec3, anchor: Vec3, limit_m: float) -> Vec3:
    delta = position - anchor
    distance = _length(delta)
    if distance <= limit_m or distance <= 1e-12:
        return position
    return anchor + delta.scaled(limit_m / distance)


# The soft-node solver builds intermediate forces as Vec3 values, which reject
# components beyond 1e8. A collision impulse is applied in full up to the
# strain tether; any leftover speed above this cap is removed by that
# constraint before the material solve so the force vector stays in range.
_SOLVER_SPEED_LIMIT_M_S = 20.0


def _constrained_kick(anchor: Vec3, impulse: Vec3, mass_kg: float, delta_s: float, tether_limit_m: float) -> tuple[Vec3, Vec3]:
    kick = impulse.scaled(1.0 / mass_kg)
    speed = _length(kick)
    if speed <= 1e-12:
        return anchor, Vec3(0, 0, 0)
    direction = kick.scaled(1.0 / speed)
    if speed * delta_s > tether_limit_m:
        return anchor + direction.scaled(tether_limit_m), direction.scaled(min(speed, _SOLVER_SPEED_LIMIT_M_S))
    if speed > _SOLVER_SPEED_LIMIT_M_S:
        return anchor, direction.scaled(_SOLVER_SPEED_LIMIT_M_S)
    return anchor, kick


def _soft_layer(
    *,
    prefix: str,
    material: str,
    anchors: tuple[Vec3, ...],
    wetness: float,
    impulse: Vec3,
    weather: Weather,
    delta_s: float,
    pinned: set[int],
    tether_limit_m: float,
) -> tuple[SoftNode, ...]:
    nodes = []
    for index, anchor in enumerate(anchors):
        mass = 0.05
        if index in pinned:
            position, velocity = anchor, Vec3(0, 0, 0)
        else:
            position, velocity = _constrained_kick(anchor, impulse, mass, delta_s, tether_limit_m)
        nodes.append(SoftNode(
            f"{prefix}-{index}",
            material,
            anchor,
            position,
            velocity,
            mass,
            wetness,
            20.0,
        ))
    try:
        solved = simulate_soft_nodes(
            tuple(nodes),
            weather,
            anchors=anchors,
            delta_s=delta_s,
            gravity_mps2=0.0,
        )
    except (MotionPhysicsError, FrontierProductionError) as exc:
        raise SkinIntegrationError(str(exc)) from exc
    bounded = []
    for index, node in enumerate(solved):
        if index in pinned:
            bounded.append(replace(node, position=anchors[index], velocity=Vec3(0, 0, 0)))
            continue
        bounded.append(replace(node, position=_bound_tether(node.position, anchors[index], tether_limit_m)))
    return tuple(bounded)


class ReferenceAnatomicalSkinIntegrator:
    """Reference binding. Another runtime can substitute its own integrator."""

    def integrate_character_skin(self, request: SkinIntegrationRequest) -> SkinIntegrationResult:
        if not isinstance(request, SkinIntegrationRequest):
            raise SkinIntegrationError("integrator received an untyped request")
        elastic = request.elastic or ElasticBodySkin3D(collision_ground_z_m=-100.0)
        wetness = request.wetness
        impulse = request.collision_impulse_n
        stride_m = request.stride_m
        gait = _gait_from_speed(stride_m / request.delta_s if request.delta_s > 0.0 else 0.0)
        locomotion_applied = False
        if request.locomotion is not None:
            weather = Weather(
                wind=Vec3(0, 0, 0),
                temperature_c=20.0,
                precipitation_mm_h=wetness * 200.0,
                humidity=wetness,
                water_depth_m=0.0,
            )
            desired = request.desired_velocity or Vec3(0, 0, 0)
            try:
                step = simulate_character(
                    request.locomotion,
                    weather,
                    request.surfaces,
                    desired_velocity=desired,
                    delta_s=request.delta_s if request.delta_s > 0.0 else 1e-4,
                )
            except MotionPhysicsError as exc:
                raise SkinIntegrationError(str(exc)) from exc
            travel = step.state.position - request.locomotion.position
            stride_m = math.hypot(travel.x, travel.y)
            gait = step.state.gait
            wetness = max(wetness, step.state.clothing_wetness)
            if step.impacts and request.delta_s > 0.0:
                extra = Vec3(0, 0, 0)
                for impact in step.impacts:
                    extra = extra + impact.normal.scaled(impact.impulse_ns / request.delta_s)
                impulse = impulse + extra
            locomotion_applied = True
        try:
            time_ms = _stride_time_ms(request.clip, stride_m, request.stride_length_m)
            anchors = pose_skinned_mesh(request.skeleton, request.mesh, request.clip, time_ms)
        except FrontierProductionError as exc:
            raise SkinIntegrationError(str(exc)) from exc
        bone = request.skeleton.bones[0]
        bone_length = _length(bone.tail - bone.head)
        tether_limit = elastic.maximum_strain * max(bone_length, 1e-3)
        rainfall = wetness * 120.0
        state = request.skin_state
        if state is None:
            state = ElasticSkinState(anchors, tuple(Vec3(0, 0, 0) for _ in anchors), wetness, 20.0)
        elif abs(state.wetness - wetness) > 1e-12:
            state = ElasticSkinState(state.positions, state.velocities, wetness, state.temperature_c)
        try:
            skin = simulate_elastic_skin(
                request.skeleton,
                request.mesh,
                request.clip,
                elastic,
                time_ms=time_ms,
                delta_s=request.delta_s if request.delta_s > 0.0 else 0.0,
                rainfall_mm_h=rainfall,
                impact_force_n=impulse,
                pinned_vertices=request.pinned_vertices,
                state=state,
            )
        except ElasticSkinError as exc:
            raise SkinIntegrationError(str(exc)) from exc
        pins = set(request.pinned_vertices)
        projected, strain = _enforce_link_strain(
            skin.positions, anchors, request.mesh, pins, elastic.maximum_strain,
        )
        skin = _skin_frame(skin, projected, anchors, strain, request.mesh.digest)
        for index in pins:
            if skin.positions[index] != anchors[index]:
                raise SkinIntegrationError("pinned rig node drifted off the anatomical pose")
        if skin.max_measured_strain > elastic.maximum_strain + 1e-6:
            raise SkinIntegrationError("elastic skin strain exceeded the configured bound")
        cloth_weather = Weather(
            wind=Vec3(0, 0, 0),
            temperature_c=20.0,
            precipitation_mm_h=rainfall,
            humidity=wetness,
        )
        fascia = _soft_layer(
            prefix="fascia",
            material="skin",
            anchors=anchors,
            wetness=wetness,
            impulse=impulse,
            weather=cloth_weather,
            delta_s=max(request.delta_s, 1e-4),
            pinned=pins,
            tether_limit_m=tether_limit,
        )
        cloth = _soft_layer(
            prefix="cloth",
            material="cloth",
            anchors=anchors,
            wetness=wetness,
            impulse=impulse,
            weather=cloth_weather,
            delta_s=max(request.delta_s, 1e-4),
            pinned=set(),
            tether_limit_m=tether_limit,
        )
        worst = skin.max_measured_strain
        for layer in (fascia, cloth):
            for node, anchor in zip(layer, anchors):
                if bone_length > 1e-9:
                    worst = max(worst, _length(node.position - anchor) / bone_length)
        if worst > elastic.maximum_strain + 1e-6:
            raise SkinIntegrationError("fascia or cloth tether strain exceeded the configured bound")
        return SkinIntegrationResult(
            skin=skin,
            fascia=fascia,
            cloth=cloth,
            pinned_vertices=request.pinned_vertices,
            anchor_positions=anchors,
            stride_m=stride_m,
            stride_time_ms=time_ms,
            gait=gait,
            max_strain=worst,
            collision_impulse_n=impulse,
            wetness=skin.wetness,
            game_time_s=request.game_time_s,
            locomotion_applied=locomotion_applied,
        )
