"""Public deterministic physics snapshots.

Snapshots bind topology/configuration separately from mutable simulation state.
They are safe for rollback only into a world with the same settings, body
configuration, shapes/materials/inertia, and joint graph.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..ecs.canonical import digest
from .collision import ContactManifold
from .contacts import ContactCacheEntry
from .errors import PhysicsSnapshotError
from .joint_cache import JointImpulseEntry
from .math3d import Quat, Vec3


def _digest_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise PhysicsSnapshotError(f"{name} must be sha256 text")
    try:
        int(value, 16)
    except ValueError as exc:
        raise PhysicsSnapshotError(f"{name} must be sha256 text") from exc
    return value


@dataclass(frozen=True, slots=True)
class PhysicsBodyState:
    body_id: str
    position: Vec3
    orientation: Quat
    linear_velocity: Vec3
    angular_velocity: Vec3
    force: Vec3
    torque: Vec3
    awake: bool
    sleep_time: float

    def __post_init__(self) -> None:
        if not isinstance(self.body_id, str) or not self.body_id:
            raise PhysicsSnapshotError("snapshot body_id must be non-empty")
        for name in (
            "position",
            "linear_velocity",
            "angular_velocity",
            "force",
            "torque",
        ):
            if not isinstance(getattr(self, name), Vec3):
                raise PhysicsSnapshotError(f"{name} must be Vec3")
        if not isinstance(self.orientation, Quat):
            raise PhysicsSnapshotError("orientation must be Quat")
        if not isinstance(self.awake, bool):
            raise PhysicsSnapshotError("awake must be boolean")
        if (
            isinstance(self.sleep_time, bool)
            or not isinstance(self.sleep_time, (int, float))
            or not math.isfinite(float(self.sleep_time))
            or float(self.sleep_time) < 0.0
        ):
            raise PhysicsSnapshotError("sleep_time must be finite and non-negative")
        object.__setattr__(self, "sleep_time", float(self.sleep_time))


@dataclass(frozen=True, slots=True)
class PhysicsSnapshot:
    tick: int
    configuration_digest: str
    body_states: tuple[PhysicsBodyState, ...]
    contact_cache: tuple[ContactCacheEntry, ...]
    manifolds: tuple[ContactManifold, ...]
    state_digest: str
    snapshot_digest: str
    joint_cache: tuple[JointImpulseEntry, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise PhysicsSnapshotError("snapshot tick must be non-negative integer")
        _digest_text(self.configuration_digest, name="configuration_digest")
        _digest_text(self.state_digest, name="state_digest")
        _digest_text(self.snapshot_digest, name="snapshot_digest")
        try:
            body_states = tuple(self.body_states)
            contact_cache = tuple(self.contact_cache)
            manifolds = tuple(self.manifolds)
            joint_cache = tuple(self.joint_cache)
        except TypeError as exc:
            raise PhysicsSnapshotError("snapshot collections must be iterable") from exc
        object.__setattr__(self, "body_states", body_states)
        object.__setattr__(self, "contact_cache", contact_cache)
        object.__setattr__(self, "manifolds", manifolds)
        object.__setattr__(self, "joint_cache", joint_cache)
        if not all(isinstance(row, PhysicsBodyState) for row in self.body_states):
            raise PhysicsSnapshotError("snapshot contains invalid body state")
        if not all(isinstance(row, ContactCacheEntry) for row in self.contact_cache):
            raise PhysicsSnapshotError("snapshot contains invalid contact cache entry")
        if not all(isinstance(row, ContactManifold) for row in self.manifolds):
            raise PhysicsSnapshotError("snapshot contains invalid manifold")
        if not all(isinstance(row, JointImpulseEntry) for row in self.joint_cache):
            raise PhysicsSnapshotError("snapshot contains invalid joint cache entry")
        if tuple(sorted(row.body_id for row in self.body_states)) != tuple(
            row.body_id for row in self.body_states
        ):
            raise PhysicsSnapshotError("snapshot body states must be sorted by body_id")
        if len({row.body_id for row in self.body_states}) != len(self.body_states):
            raise PhysicsSnapshotError("snapshot body ids must be unique")


def _body_state_record(state: PhysicsBodyState) -> dict[str, object]:
    return {
        "body_id": state.body_id,
        "position": state.position.to_tuple(),
        "orientation": (
            state.orientation.w,
            state.orientation.x,
            state.orientation.y,
            state.orientation.z,
        ),
        "linear_velocity": state.linear_velocity.to_tuple(),
        "angular_velocity": state.angular_velocity.to_tuple(),
        "force": state.force.to_tuple(),
        "torque": state.torque.to_tuple(),
        "awake": state.awake,
        "sleep_time": state.sleep_time,
    }


def _cache_record(entry: ContactCacheEntry) -> dict[str, object]:
    return {
        "key": entry.key,
        "body_a": entry.body_a,
        "body_b": entry.body_b,
        "feature_id": entry.feature_id,
        "normal": entry.normal.to_tuple(),
        "normal_impulse": entry.normal_impulse,
        "tangent": entry.tangent.to_tuple(),
        "tangent_impulse": entry.tangent_impulse,
        "last_tick": entry.last_tick,
    }


def _joint_cache_record(entry: JointImpulseEntry) -> dict[str, object]:
    return {
        "key": entry.key,
        "joint_id": entry.joint_id,
        "body_a": entry.body_a,
        "body_b": entry.body_b,
        "row_id": entry.row_id,
        "impulse": entry.impulse,
        "last_tick": entry.last_tick,
    }


def _manifold_record(manifold: ContactManifold) -> dict[str, object]:
    return {
        "body_a": manifold.body_a,
        "body_b": manifold.body_b,
        "normal": manifold.normal.to_tuple(),
        "points": [
            {
                "position": point.position.to_tuple(),
                "penetration": point.penetration,
                "feature_id": point.feature_id,
            }
            for point in manifold.points
        ],
        "material": {
            "friction": manifold.material.friction,
            "restitution": manifold.material.restitution,
            "rolling_friction": manifold.material.rolling_friction,
        },
    }


def snapshot_material(
    *,
    tick: int,
    configuration_digest: str,
    body_states: tuple[PhysicsBodyState, ...],
    contact_cache: tuple[ContactCacheEntry, ...],
    manifolds: tuple[ContactManifold, ...],
    state_digest: str,
    joint_cache: tuple[JointImpulseEntry, ...] = (),
) -> dict[str, object]:
    return {
        "domain": "skeleton.simulation.physics.snapshot.v2",
        "tick": tick,
        "configuration_digest": configuration_digest,
        "body_states": [_body_state_record(row) for row in body_states],
        "contact_cache": [_cache_record(row) for row in contact_cache],
        "joint_cache": [_joint_cache_record(row) for row in joint_cache],
        "manifolds": [_manifold_record(row) for row in manifolds],
        "state_digest": state_digest,
    }


def build_snapshot(
    *,
    tick: int,
    configuration_digest: str,
    body_states: tuple[PhysicsBodyState, ...],
    contact_cache: tuple[ContactCacheEntry, ...],
    manifolds: tuple[ContactManifold, ...],
    state_digest: str,
    joint_cache: tuple[JointImpulseEntry, ...] = (),
) -> PhysicsSnapshot:
    try:
        body_states = tuple(body_states)
        contact_cache = tuple(contact_cache)
        manifolds = tuple(manifolds)
        joint_cache = tuple(joint_cache)
    except TypeError as exc:
        raise PhysicsSnapshotError("snapshot collections must be iterable") from exc
    if not all(isinstance(row, PhysicsBodyState) for row in body_states):
        raise PhysicsSnapshotError("snapshot contains invalid body state")
    if not all(isinstance(row, ContactCacheEntry) for row in contact_cache):
        raise PhysicsSnapshotError("snapshot contains invalid contact cache entry")
    if not all(isinstance(row, ContactManifold) for row in manifolds):
        raise PhysicsSnapshotError("snapshot contains invalid manifold")
    if not all(isinstance(row, JointImpulseEntry) for row in joint_cache):
        raise PhysicsSnapshotError("snapshot contains invalid joint cache entry")

    material = snapshot_material(
        tick=tick,
        configuration_digest=configuration_digest,
        body_states=body_states,
        contact_cache=contact_cache,
        manifolds=manifolds,
        state_digest=state_digest,
        joint_cache=joint_cache,
    )
    return PhysicsSnapshot(
        tick=tick,
        configuration_digest=configuration_digest,
        body_states=body_states,
        contact_cache=contact_cache,
        manifolds=manifolds,
        state_digest=state_digest,
        snapshot_digest=digest(material),
        joint_cache=joint_cache,
    )


def verify_snapshot(snapshot: PhysicsSnapshot) -> None:
    expected = digest(
        snapshot_material(
            tick=snapshot.tick,
            configuration_digest=snapshot.configuration_digest,
            body_states=snapshot.body_states,
            contact_cache=snapshot.contact_cache,
            manifolds=snapshot.manifolds,
            state_digest=snapshot.state_digest,
            joint_cache=snapshot.joint_cache,
        )
    )
    if expected != snapshot.snapshot_digest:
        raise PhysicsSnapshotError("physics snapshot digest mismatch")



class PhysicsSnapshotHistory:
    """Bounded tick-indexed immutable snapshot history for rollback workflows."""

    def __init__(self, capacity: int = 256) -> None:
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or not 1 <= capacity <= 100_000
        ):
            raise PhysicsSnapshotError("snapshot history capacity outside supported range")
        self.capacity = capacity
        self._snapshots: dict[int, PhysicsSnapshot] = {}

    def __len__(self) -> int:
        return len(self._snapshots)

    def ticks(self) -> tuple[int, ...]:
        return tuple(sorted(self._snapshots))

    def append(self, snapshot: PhysicsSnapshot) -> PhysicsSnapshot:
        if not isinstance(snapshot, PhysicsSnapshot):
            raise PhysicsSnapshotError("history requires PhysicsSnapshot")
        verify_snapshot(snapshot)
        existing = self._snapshots.get(snapshot.tick)
        if existing is not None and existing != snapshot:
            raise PhysicsSnapshotError(
                "history tick already contains different snapshot"
            )
        self._snapshots[snapshot.tick] = snapshot
        while len(self._snapshots) > self.capacity:
            del self._snapshots[min(self._snapshots)]
        return snapshot

    def at_tick(self, tick: int) -> PhysicsSnapshot:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsSnapshotError("history tick must be non-negative integer")
        try:
            return self._snapshots[tick]
        except KeyError as exc:
            raise PhysicsSnapshotError(f"snapshot tick not retained: {tick}") from exc

    def latest(self) -> PhysicsSnapshot:
        if not self._snapshots:
            raise PhysicsSnapshotError("snapshot history is empty")
        return self._snapshots[max(self._snapshots)]

    def truncate_after(self, tick: int) -> int:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsSnapshotError("history tick must be non-negative integer")
        future = [value for value in self._snapshots if value > tick]
        for value in sorted(future):
            del self._snapshots[value]
        return len(future)

    def clear(self) -> None:
        self._snapshots.clear()
