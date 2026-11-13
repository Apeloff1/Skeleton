"""P1-P3 frontier game geometry and world cognition in the Jeeves owner plane.

Real deterministic polygon generation/LOD, skeletal animation and colliders are
implemented here. This does NOT claim to run proprietary HY-World, SIMA or
TRELLIS checkpoints. Learned-model ingestion is a separately governed concern.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Iterable, Mapping

_SCHEMA = "skeleton.jeeves.frontier_production.v1"

# Max *triangles* per generated character, separately from renderer budgets.
ERA_TRIANGLE_BUDGETS = {
    "early_3d": 384,
    "fixed_3d": 1_024,
    "shader": 4_096,
    "hd": 12_288,
    "modern": 32_768,
    "next": 65_536,
}
ERA_RING_SIDES = {
    "early_3d": 4, "fixed_3d": 6, "shader": 10,
    "hd": 16, "modern": 24, "next": 32,
}


class FrontierProductionError(ValueError):
    pass


def _num(value: float, label: str, maximum: float = 1e8) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > maximum:
        raise FrontierProductionError(f"{label} must be bounded and finite")
    return float(value)


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "z"):
            _num(getattr(self, name), name)

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def scaled(self, value: float) -> "Vec3":
        v = _num(value, "scale")
        return Vec3(self.x * v, self.y * v, self.z * v)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(self.y * other.z - self.z * other.y,
                    self.z * other.x - self.x * other.z,
                    self.x * other.y - self.y * other.x)

    def normalized(self) -> "Vec3":
        length = math.sqrt(self.dot(self))
        if length < 1e-8:
            raise FrontierProductionError("zero-length direction")
        return self.scaled(1 / length)


@dataclass(frozen=True)
class Bone:
    name: str
    parent: int
    head: Vec3
    tail: Vec3
    radius_m: float

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 128 or "/" in self.name:
            raise FrontierProductionError("invalid bone name")
        if type(self.parent) is not int or self.parent < -1:
            raise FrontierProductionError("invalid parent bone")
        if (self.tail - self.head).dot(self.tail - self.head) < 1e-8:
            raise FrontierProductionError("bone cannot be zero length")
        if not .001 <= _num(self.radius_m, "radius_m") <= 100:
            raise FrontierProductionError("bone radius out of range")


@dataclass(frozen=True)
class CharacterSkeleton:
    bones: tuple[Bone, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.bones) <= 256 or len({b.name for b in self.bones}) != len(self.bones):
            raise FrontierProductionError("skeleton requires 1..256 unique bones")
        for i, bone in enumerate(self.bones):
            if bone.parent >= i:
                raise FrontierProductionError("bone hierarchy must be topologically ordered")

    def parents(self, bone_index: int) -> tuple[int, ...]:
        if not 0 <= bone_index < len(self.bones):
            raise FrontierProductionError("unknown bone")
        indices: list[int] = []
        while bone_index != -1:
            indices.append(bone_index)
            bone_index = self.bones[bone_index].parent
        return tuple(indices)


@dataclass(frozen=True)
class CollisionCapsule:
    bone_index: int
    head: Vec3
    tail: Vec3
    radius_m: float


@dataclass(frozen=True)
class SkinnedMesh:
    vertices: tuple[Vec3, ...]
    triangles: tuple[tuple[int, int, int], ...]
    bone_influences: tuple[int, ...]
    colliders: tuple[CollisionCapsule, ...]
    era: str
    regression_ratio: float

    def __post_init__(self) -> None:
        if len(self.vertices) != len(self.bone_influences):
            raise FrontierProductionError("missing skin influences")
        if any(min(face) < 0 or max(face) >= len(self.vertices)
               or len(set(face)) != 3 for face in self.triangles):
            raise FrontierProductionError("invalid triangle indices")

    @property
    def triangle_count(self) -> int:
        return len(self.triangles)

    @property
    def digest(self) -> str:
        record = {
            "schema": _SCHEMA, "era": self.era,
            "vertices": [[v.x, v.y, v.z] for v in self.vertices],
            "triangles": self.triangles,
            "influences": self.bone_influences,
        }
        return sha256(json.dumps(record, sort_keys=True,
                                 separators=(",", ":")).encode()).hexdigest()


def skeleton_to_polygon(skeleton: CharacterSkeleton, era: str, *,
                        max_triangles: int | None = None) -> SkinnedMesh:
    """Extrude watertight-at-each-bone tube/caps into triangles; preserve rig IDs.

    Regression automatically fits the budget by reducing ring sides across eras.
    It does not invent geometry from pixels; the skeleton is a typed input.
    """
    if era not in ERA_TRIANGLE_BUDGETS:
        raise FrontierProductionError("unknown 3D rendering era")
    budget = ERA_TRIANGLE_BUDGETS[era]
    if max_triangles is not None:
        if type(max_triangles) is not int or not 12 <= max_triangles <= budget:
            raise FrontierProductionError("invalid triangle budget")
        budget = max_triangles
    n = len(skeleton.bones)
    # Each closed capped cylinder costs 4 * sides triangles.
    sides = min(ERA_RING_SIDES[era], budget // (4 * n))
    if sides < 3:
        raise FrontierProductionError("budget cannot represent every skeletal bone")
    vertices: list[Vec3] = []
    faces: list[tuple[int, int, int]] = []
    influences: list[int] = []
    capsules: list[CollisionCapsule] = []
    for bone_index, bone in enumerate(skeleton.bones):
        tangent = (bone.tail - bone.head).normalized()
        reference = Vec3(0, 0, 1) if abs(tangent.z) < .9 else Vec3(0, 1, 0)
        normal = tangent.cross(reference).normalized()
        binormal = tangent.cross(normal).normalized()
        offset = len(vertices)
        for point in (bone.head, bone.tail):
            for j in range(sides):
                theta = 2 * math.pi * j / sides
                radial = normal.scaled(math.cos(theta) * bone.radius_m) + binormal.scaled(math.sin(theta) * bone.radius_m)
                vertices.append(point + radial)
                influences.append(bone_index)
        # Center points close the end caps for a collision-friendly source mesh.
        vertices.extend((bone.head, bone.tail))
        influences.extend((bone_index, bone_index))
        bottom_center, top_center = offset + 2 * sides, offset + 2 * sides + 1
        for j in range(sides):
            nxt = (j + 1) % sides
            a, b, c, d = offset+j, offset+nxt, offset+sides+j, offset+sides+nxt
            faces.extend(((a, b, d), (a, d, c), (bottom_center, b, a),
                          (top_center, c, d)))
        capsules.append(CollisionCapsule(bone_index, bone.head, bone.tail, bone.radius_m))
    return SkinnedMesh(tuple(vertices), tuple(faces), tuple(influences),
                       tuple(capsules), era,
                       len(faces) / (len(skeleton.bones) * 4 * ERA_RING_SIDES["next"]))


@dataclass(frozen=True)
class BonePose:
    translation: Vec3
    yaw_rad: float = 0.0

    def __post_init__(self) -> None:
        _num(self.yaw_rad, "yaw", maximum=10000)


@dataclass(frozen=True)
class AnimationKeyframe:
    time_ms: int
    poses: tuple[BonePose, ...]

    def __post_init__(self) -> None:
        if type(self.time_ms) is not int or not 0 <= self.time_ms <= 3_600_000:
            raise FrontierProductionError("invalid animation time")


@dataclass(frozen=True)
class AnimationClip:
    name: str
    keyframes: tuple[AnimationKeyframe, ...]
    loop: bool = True

    def __post_init__(self) -> None:
        if not self.name or not 2 <= len(self.keyframes) <= 4096:
            raise FrontierProductionError("clip requires name and 2..4096 keys")
        times = [k.time_ms for k in self.keyframes]
        if times[0] != 0 or any(b <= a for a, b in zip(times, times[1:])):
            raise FrontierProductionError("clip times must start at zero and strictly increase")
        n = len(self.keyframes[0].poses)
        if n < 1 or any(len(k.poses) != n for k in self.keyframes):
            raise FrontierProductionError("bone poses mismatch")


def sample_animation(clip: AnimationClip, at_ms: int) -> tuple[BonePose, ...]:
    if type(at_ms) is not int or at_ms < 0:
        raise FrontierProductionError("invalid sample time")
    keys = clip.keyframes
    duration = keys[-1].time_ms
    t = at_ms % duration if clip.loop else min(at_ms, duration)
    for a, b in zip(keys, keys[1:]):
        if t <= b.time_ms:
            f = (t - a.time_ms) / (b.time_ms - a.time_ms)
            return tuple(BonePose(
                x.translation.scaled(1 - f) + y.translation.scaled(f),
                x.yaw_rad * (1 - f) + y.yaw_rad * f,
            ) for x, y in zip(a.poses, b.poses))
    return keys[-1].poses


def pose_skinned_mesh(skeleton: CharacterSkeleton, mesh: SkinnedMesh,
                      clip: AnimationClip, at_ms: int) -> tuple[Vec3, ...]:
    """Apply rigid bone envelopes, including ancestor transformations.

    Returned vertices are ephemeral, never an authoritative replacement for
    the rest mesh. Colliders can be similarly transformed by the host engine.
    """
    poses = sample_animation(clip, at_ms)
    if len(poses) != len(skeleton.bones) or any(i >= len(poses) for i in mesh.bone_influences):
        raise FrontierProductionError("animation/mesh skeleton mismatch")
    result: list[Vec3] = []
    for vertex, bone_i in zip(mesh.vertices, mesh.bone_influences):
        point = vertex
        for i in skeleton.parents(bone_i):
            pose = poses[i]
            joint = skeleton.bones[i].head
            delta = point - joint
            c, s = math.cos(pose.yaw_rad), math.sin(pose.yaw_rad)
            point = joint + Vec3(delta.x * c - delta.y * s,
                                 delta.x * s + delta.y * c,
                                 delta.z) + pose.translation
        result.append(point)
    return tuple(result)


@dataclass(frozen=True)
class Percept:
    object_id: str
    kind: str
    visible: bool
    distance_m: float
    importance: float
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.object_id or not self.kind or not self.evidence_digest:
            raise FrontierProductionError("percept identity and evidence required")
        if len(self.evidence_digest) != 64 or any(c not in "0123456789abcdef" for c in self.evidence_digest):
            raise FrontierProductionError("invalid percept evidence digest")
        if not 0 <= _num(self.distance_m, "distance") <= 1e8:
            raise FrontierProductionError("negative percept distance")
        if not 0 <= _num(self.importance, "importance") <= 1:
            raise FrontierProductionError("invalid percept importance")


@dataclass(frozen=True)
class CinematicReason:
    shot: str
    focus_object_id: str
    rationale: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    authority: str = "proposal_only"


def plan_cinematic(percepts: Iterable[Percept], *, player_in_danger: bool = False,
                   world_establishing: bool = False) -> CinematicReason:
    """SIMA-inspired explainable shot selection from *observed* world facts.

    Generated rationale is an inspectable deterministic rule trace, not hidden
    model reasoning or proof of user intention.
    """
    observations = tuple(percepts)
    if not observations or len(observations) > 1024 or any(not isinstance(p, Percept) for p in observations):
        raise FrontierProductionError("1..1024 percepts required")
    visible = [p for p in observations if p.visible]
    if not visible:
        raise FrontierProductionError("no visible, evidenced cinematic targets")
    focus = max(visible, key=lambda p: (p.importance / (1 + p.distance_m / 30),
                                       p.importance, p.object_id))
    reasons = [f"visible source-attested {focus.kind}", f"salience={focus.importance:.3f}"]
    if player_in_danger:
        shot = "tracking_action"
        reasons.append("maintain player combat spatial awareness")
    elif world_establishing:
        shot = "establishing_wide"
        reasons.append("world context requested")
    elif focus.distance_m < 5:
        shot = "closeup"
        reasons.append("subject inside close-range camera envelope")
    elif focus.importance > .75:
        shot = "dolly_tracking"
        reasons.append("high-salience distant subject")
    else:
        shot = "medium_follow"
        reasons.append("preserve spatial context")
    return CinematicReason(shot, focus.object_id, tuple(reasons),
                           (focus.evidence_digest,))


@dataclass(frozen=True)
class ReasonedAction:
    action: str
    target: str
    rationale: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    authority: str = "proposed_not_executed"


def reason_about_world(percepts: Iterable[Percept], *,
                       goal_kind: str, available_actions: Iterable[str]) -> ReasonedAction:
    """Goal+observation grounded action proposal; no unverified task completion."""
    if not goal_kind or len(goal_kind) > 128:
        raise FrontierProductionError("goal_kind required")
    permitted = tuple(available_actions)
    if not permitted or len(permitted) > 64 or len(set(permitted)) != len(permitted):
        raise FrontierProductionError("invalid action catalog")
    choices = [p for p in percepts if isinstance(p, Percept) and p.visible and p.kind == goal_kind]
    if not choices:
        if "inspect" not in permitted:
            raise FrontierProductionError("unobserved goal; no inspection action")
        return ReasonedAction("inspect", "world", ("goal lacks evidence", "information-gathering only"), ())
    target = max(choices, key=lambda p: (p.importance, -p.distance_m))
    action = "interact" if "interact" in permitted and target.distance_m <= 3 else (
        "approach" if "approach" in permitted else "inspect" if "inspect" in permitted else None)
    if action is None:
        raise FrontierProductionError("no safe available world action")
    return ReasonedAction(action, target.object_id,
                          (f"visible {goal_kind} matches requested goal", "no state mutation authorized"),
                          (target.evidence_digest,))
