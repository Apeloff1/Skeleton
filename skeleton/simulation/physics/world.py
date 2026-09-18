"""Deterministic fixed-step 3D rigid-body world."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..ecs.canonical import digest
from .body import BodyType, RigidBody
from .calculations import PhysicsAggregate, aggregate_physics
from .ccd import ContinuousCollisionDetector, TOIEvent
from .character import (
    CharacterGroundState,
    CharacterMoveResult,
    KinematicCapsuleController,
)
from .collision import (
    ContactManifold,
    SweepAndPruneBroadPhase,
    detect_collision,
    generate_manifolds,
)
from .coloring import ConstraintColorSchedule, color_constraints
from .constraints import (
    ConstraintSolver,
    ConstraintStats,
    JointConstraint,
    is_joint_constraint,
)
from .contacts import ContactCache, ContactCacheEntry
from .errors import (
    BodyNotFoundError,
    DuplicateBodyError,
    DuplicateJointError,
    JointNotFoundError,
    PhysicsSnapshotError,
    PhysicsValidationError,
)
from .islands import IslandGraph, IslandGraphStats, build_islands, solve_islands
from .joint_cache import JointImpulseCache, JointImpulseEntry
from .math3d import EPSILON, AABB, Quat, Vec3
from .queries import Ray, RayHit, raycast_body, sort_hits, sphere_cast_body
from .shapes import BoxShape, CapsuleShape, CylinderShape, PlaneShape, SphereShape
from .snapshots import (
    PhysicsBodyState,
    PhysicsSnapshot,
    build_snapshot,
    verify_snapshot,
)
from .solver import SequentialImpulseSolver, SolverStats

MAX_WORLD_BODIES = 100_000
MAX_WORLD_JOINTS = 100_000
MAX_STEP_COUNT = 10_000


@dataclass(frozen=True, slots=True)
class _BodyStepState:
    position: Vec3
    orientation: Quat
    linear_velocity: Vec3
    angular_velocity: Vec3
    force: Vec3
    torque: Vec3
    awake: bool
    sleep_time: float


@dataclass(frozen=True, slots=True)
class _StepCheckpoint:
    tick: int
    body_states: tuple[tuple[str, _BodyStepState], ...]
    contact_cache: tuple[ContactCacheEntry, ...]
    joint_cache: tuple[JointImpulseEntry, ...]
    manifolds: tuple[ContactManifold, ...]
    state_digest: str


def _positive(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise PhysicsValidationError(f"{name} must be finite and positive")
    return value


def _bounded_int(value: int, *, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise PhysicsValidationError(f"{name} outside supported range")
    return value


@dataclass(frozen=True, slots=True)
class PhysicsSettings:
    fixed_dt: float = 1.0 / 60.0
    gravity: Vec3 = Vec3(0.0, -9.81, 0.0)
    sleep_linear_speed: float = 0.03
    sleep_angular_speed: float = 0.03
    sleep_after_seconds: float = 0.75
    max_bodies: int = 16_384
    max_joints: int = 16_384
    max_pairs: int = 250_000
    velocity_iterations: int = 10
    position_iterations: int = 4
    contact_cache_entries: int = 65_536
    contact_cache_age_ticks: int = 8
    joint_cache_entries: int = 65_536
    joint_cache_age_ticks: int = 8
    ccd_enabled: bool = True
    ccd_motion_threshold: float = 0.5
    ccd_contact_slop: float = 1.0e-7
    ccd_max_substeps: int = 8
    ccd_min_advance_fraction: float = 1.0e-6
    max_ccd_checks: int = 65_536
    constraint_velocity_iterations: int = 8
    constraint_position_iterations: int = 4

    def __post_init__(self) -> None:
        if not isinstance(self.gravity, Vec3):
            raise PhysicsValidationError("gravity must be Vec3")
        if not isinstance(self.ccd_enabled, bool):
            raise PhysicsValidationError("ccd_enabled must be boolean")
        object.__setattr__(self, "fixed_dt", _positive(self.fixed_dt, name="fixed_dt"))
        object.__setattr__(
            self,
            "sleep_after_seconds",
            _positive(self.sleep_after_seconds, name="sleep_after_seconds"),
        )
        object.__setattr__(
            self,
            "ccd_motion_threshold",
            _positive(self.ccd_motion_threshold, name="ccd_motion_threshold"),
        )
        if (
            isinstance(self.ccd_contact_slop, bool)
            or not isinstance(self.ccd_contact_slop, (int, float))
            or not math.isfinite(float(self.ccd_contact_slop))
            or float(self.ccd_contact_slop) < 0.0
        ):
            raise PhysicsValidationError("ccd_contact_slop must be finite and non-negative")
        object.__setattr__(self, "ccd_contact_slop", float(self.ccd_contact_slop))
        if (
            isinstance(self.ccd_min_advance_fraction, bool)
            or not isinstance(self.ccd_min_advance_fraction, (int, float))
            or not math.isfinite(float(self.ccd_min_advance_fraction))
            or not 0.0 < float(self.ccd_min_advance_fraction) <= 0.1
        ):
            raise PhysicsValidationError(
                "ccd_min_advance_fraction must be in (0, 0.1]"
            )
        object.__setattr__(
            self,
            "ccd_min_advance_fraction",
            float(self.ccd_min_advance_fraction),
        )
        for name in ("sleep_linear_speed", "sleep_angular_speed"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PhysicsValidationError(f"{name} must be numeric")
            value = float(value)
            if not math.isfinite(value) or value < 0.0:
                raise PhysicsValidationError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)

        _bounded_int(self.max_bodies, name="max_bodies", maximum=MAX_WORLD_BODIES)
        _bounded_int(self.max_joints, name="max_joints", maximum=MAX_WORLD_JOINTS)
        _bounded_int(self.max_pairs, name="max_pairs", maximum=1_000_000)
        _bounded_int(
            self.contact_cache_entries,
            name="contact_cache_entries",
            maximum=1_000_000,
        )
        _bounded_int(
            self.contact_cache_age_ticks,
            name="contact_cache_age_ticks",
            maximum=10_000,
        )
        _bounded_int(
            self.joint_cache_entries,
            name="joint_cache_entries",
            maximum=1_000_000,
        )
        _bounded_int(
            self.joint_cache_age_ticks,
            name="joint_cache_age_ticks",
            maximum=10_000,
        )
        _bounded_int(self.max_ccd_checks, name="max_ccd_checks", maximum=1_000_000)
        _bounded_int(
            self.ccd_max_substeps,
            name="ccd_max_substeps",
            maximum=128,
        )
        for name in (
            "velocity_iterations",
            "position_iterations",
            "constraint_velocity_iterations",
            "constraint_position_iterations",
        ):
            _bounded_int(getattr(self, name), name=name, maximum=128)

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.settings.v4",
                "fixed_dt": self.fixed_dt,
                "gravity": self.gravity.to_tuple(),
                "sleep_linear_speed": self.sleep_linear_speed,
                "sleep_angular_speed": self.sleep_angular_speed,
                "sleep_after_seconds": self.sleep_after_seconds,
                "max_bodies": self.max_bodies,
                "max_joints": self.max_joints,
                "max_pairs": self.max_pairs,
                "velocity_iterations": self.velocity_iterations,
                "position_iterations": self.position_iterations,
                "contact_cache_entries": self.contact_cache_entries,
                "contact_cache_age_ticks": self.contact_cache_age_ticks,
                "joint_cache_entries": self.joint_cache_entries,
                "joint_cache_age_ticks": self.joint_cache_age_ticks,
                "ccd_enabled": self.ccd_enabled,
                "ccd_motion_threshold": self.ccd_motion_threshold,
                "ccd_contact_slop": self.ccd_contact_slop,
                "ccd_max_substeps": self.ccd_max_substeps,
                "ccd_min_advance_fraction": self.ccd_min_advance_fraction,
                "max_ccd_checks": self.max_ccd_checks,
                "constraint_velocity_iterations": self.constraint_velocity_iterations,
                "constraint_position_iterations": self.constraint_position_iterations,
            }
        )


@dataclass(frozen=True, slots=True)
class PhysicsStepReceipt:
    tick: int
    dt: float
    before_digest: str
    after_digest: str
    broad_phase_pairs: int
    manifolds: int
    contact_points: int
    ccd_clamps: int
    kinetic_energy: float
    sleeping_bodies: int
    solver: SolverStats
    constraints: ConstraintStats
    islands: IslandGraphStats

    @property
    def changed(self) -> bool:
        return self.before_digest != self.after_digest


class PhysicsWorld:
    def __init__(self, settings: PhysicsSettings | None = None) -> None:
        if settings is not None and not isinstance(settings, PhysicsSettings):
            raise PhysicsValidationError("settings must be PhysicsSettings")
        self.settings = settings or PhysicsSettings()
        self._bodies: dict[str, RigidBody] = {}
        self._joints: dict[str, JointConstraint] = {}
        self._tick = 0
        self._broad_phase = SweepAndPruneBroadPhase(max_pairs=self.settings.max_pairs)
        self._solver = SequentialImpulseSolver(
            velocity_iterations=self.settings.velocity_iterations,
            position_iterations=self.settings.position_iterations,
        )
        self._constraint_solver = ConstraintSolver(
            velocity_iterations=self.settings.constraint_velocity_iterations,
            position_iterations=self.settings.constraint_position_iterations,
        )
        self._contact_cache = ContactCache(
            max_entries=self.settings.contact_cache_entries,
            max_age_ticks=self.settings.contact_cache_age_ticks,
        )
        self._joint_cache = JointImpulseCache(
            max_entries=self.settings.joint_cache_entries,
            max_age_ticks=self.settings.joint_cache_age_ticks,
        )
        self._ccd = ContinuousCollisionDetector(
            motion_threshold=self.settings.ccd_motion_threshold,
            max_checks=self.settings.max_ccd_checks,
        )
        self._last_manifolds: tuple[ContactManifold, ...] = ()

    @property
    def tick(self) -> int:
        return self._tick

    def body_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._bodies))

    def bodies(self) -> tuple[RigidBody, ...]:
        return tuple(self._bodies[body_id] for body_id in self.body_ids())

    def get_body(self, body_id: str) -> RigidBody:
        try:
            return self._bodies[body_id]
        except KeyError as exc:
            raise BodyNotFoundError(body_id) from exc

    def add_body(self, body: RigidBody) -> RigidBody:
        if not isinstance(body, RigidBody):
            raise PhysicsValidationError("body must be RigidBody")
        if body.body_id in self._bodies:
            raise DuplicateBodyError(body.body_id)
        if len(self._bodies) >= self.settings.max_bodies:
            raise PhysicsValidationError("physics world body bound exceeded")
        self._bodies[body.body_id] = body
        return body

    def remove_body(self, body_id: str) -> RigidBody:
        if any(
            joint.body_a == body_id or joint.body_b == body_id
            for joint in self._joints.values()
        ):
            raise PhysicsValidationError("cannot remove body referenced by joint")
        try:
            body = self._bodies.pop(body_id)
        except KeyError as exc:
            raise BodyNotFoundError(body_id) from exc
        self._contact_cache.remove_body(body_id)
        self._joint_cache.remove_body(body_id)
        self._last_manifolds = tuple(
            row
            for row in self._last_manifolds
            if row.body_a != body_id and row.body_b != body_id
        )
        return body

    def joint_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._joints))

    def joints(self) -> tuple[JointConstraint, ...]:
        return tuple(self._joints[joint_id] for joint_id in self.joint_ids())

    def get_joint(self, joint_id: str) -> JointConstraint:
        try:
            return self._joints[joint_id]
        except KeyError as exc:
            raise JointNotFoundError(joint_id) from exc

    def add_joint(self, joint: JointConstraint) -> JointConstraint:
        if not is_joint_constraint(joint):
            raise PhysicsValidationError("unsupported joint constraint")
        if joint.joint_id in self._joints:
            raise DuplicateJointError(joint.joint_id)
        if len(self._joints) >= self.settings.max_joints:
            raise PhysicsValidationError("physics world joint bound exceeded")
        body_a = self.get_body(joint.body_a)
        body_b = self.get_body(joint.body_b)
        if body_a.body_type is BodyType.STATIC and body_b.body_type is BodyType.STATIC:
            raise PhysicsValidationError("cannot bind two static bodies")
        self._joints[joint.joint_id] = joint
        return joint

    def remove_joint(self, joint_id: str) -> JointConstraint:
        try:
            joint = self._joints.pop(joint_id)
        except KeyError as exc:
            raise JointNotFoundError(joint_id) from exc
        self._joint_cache.remove_joint(joint_id)
        return joint

    def contacts(self) -> tuple[ContactManifold, ...]:
        return self._last_manifolds

    def contact_cache_size(self) -> int:
        return len(self._contact_cache)

    def joint_cache_size(self) -> int:
        return len(self._joint_cache)

    def constraint_schedule(self) -> ConstraintColorSchedule:
        return color_constraints(
            self._bodies,
            self._last_manifolds,
            self.joints(),
        )

    def measure(
        self,
        *,
        angular_origin: Vec3 = Vec3(),
        potential_reference: Vec3 = Vec3(),
    ) -> PhysicsAggregate:
        return aggregate_physics(
            self.bodies(),
            self.settings.gravity,
            angular_origin=angular_origin,
            potential_reference=potential_reference,
        )

    def query_aabb(self, bounds: AABB) -> tuple[str, ...]:
        matches: list[str] = []
        for body in self.bodies():
            body_bounds = body.shape.aabb(body.transform)
            if body_bounds is not None and body_bounds.overlaps(bounds):
                matches.append(body.body_id)
        return tuple(matches)

    def raycast(
        self,
        ray: Ray,
        *,
        ignore: tuple[str, ...] = (),
    ) -> tuple[RayHit, ...]:
        ignored = set(ignore)
        hits = [
            hit
            for body in self.bodies()
            if body.body_id not in ignored
            if (hit := raycast_body(ray, body)) is not None
        ]
        return sort_hits(hits)

    def raycast_closest(
        self,
        ray: Ray,
        *,
        ignore: tuple[str, ...] = (),
    ) -> RayHit | None:
        hits = self.raycast(ray, ignore=ignore)
        return hits[0] if hits else None

    def sphere_cast(
        self,
        ray: Ray,
        radius: float,
        *,
        ignore: tuple[str, ...] = (),
    ) -> tuple[RayHit, ...]:
        ignored = set(ignore)
        hits = [
            hit
            for body in self.bodies()
            if body.body_id not in ignored
            if (hit := sphere_cast_body(ray, radius, body)) is not None
        ]
        return sort_hits(hits)

    def move_character(
        self,
        controller: KinematicCapsuleController,
        displacement: Vec3,
        *,
        dt: float | None = None,
        ignore: tuple[str, ...] = (),
    ) -> CharacterMoveResult:
        if not isinstance(controller, KinematicCapsuleController):
            raise PhysicsValidationError(
                "controller must be KinematicCapsuleController"
            )
        step_dt = self.settings.fixed_dt if dt is None else _positive(
            dt,
            name="character dt",
        )
        return controller.move(
            displacement,
            self.bodies(),
            dt=step_dt,
            ignore=ignore,
        )

    def probe_character_ground(
        self,
        controller: KinematicCapsuleController,
        *,
        dt: float | None = None,
        ignore: tuple[str, ...] = (),
        distance: float | None = None,
    ) -> CharacterGroundState:
        if not isinstance(controller, KinematicCapsuleController):
            raise PhysicsValidationError(
                "controller must be KinematicCapsuleController"
            )
        step_dt = self.settings.fixed_dt if dt is None else _positive(
            dt,
            name="character dt",
        )
        return controller.ground_probe(
            self.bodies(),
            dt=step_dt,
            ignore=ignore,
            distance=distance,
        )

    def _shape_record(self, body: RigidBody) -> dict[str, object]:
        shape = body.shape
        if isinstance(shape, SphereShape):
            return {"kind": shape.kind.value, "radius": shape.radius}
        if isinstance(shape, BoxShape):
            return {"kind": shape.kind.value, "half_extents": shape.half_extents.to_tuple()}
        if isinstance(shape, PlaneShape):
            return {
                "kind": shape.kind.value,
                "normal": shape.normal.to_tuple(),
                "offset": shape.offset,
            }
        if isinstance(shape, CapsuleShape):
            return {
                "kind": shape.kind.value,
                "radius": shape.radius,
                "half_height": shape.half_height,
            }
        if isinstance(shape, CylinderShape):
            return {
                "kind": shape.kind.value,
                "radius": shape.radius,
                "half_height": shape.half_height,
            }
        raise PhysicsValidationError("unknown shape implementation")

    @staticmethod
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

    def _body_configuration_record(self, body: RigidBody) -> dict[str, object]:
        return {
            "body_id": body.body_id,
            "type": body.body_type.value,
            "shape_config": self._shape_record(body),
            "mass": body.mass if math.isfinite(body.mass) else None,
            "inverse_mass": body.inverse_mass,
            "material": {
                "friction": body.material.friction,
                "restitution": body.material.restitution,
                "rolling_friction": body.material.rolling_friction,
                "friction_rule": body.material.friction_rule.value,
                "restitution_rule": body.material.restitution_rule.value,
            },
            "local_inertia": body.local_inertia.to_tuple(),
            "local_inverse_inertia": body.local_inverse_inertia.to_tuple(),
            "linear_damping": body.linear_damping,
            "angular_damping": body.angular_damping,
            "gravity_scale": body.gravity_scale,
            "continuous": body.continuous,
        }

    def _body_record(self, body: RigidBody) -> dict[str, object]:
        return {
            **body.state_record(),
            "shape_config": self._shape_record(body),
            "mass": body.mass if math.isfinite(body.mass) else None,
            "inverse_mass": body.inverse_mass,
            "material": {
                "friction": body.material.friction,
                "restitution": body.material.restitution,
                "rolling_friction": body.material.rolling_friction,
                "friction_rule": body.material.friction_rule.value,
                "restitution_rule": body.material.restitution_rule.value,
            },
            "local_inertia": body.local_inertia.to_tuple(),
            "local_inverse_inertia": body.local_inverse_inertia.to_tuple(),
        }

    @property
    def configuration_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.configuration.v1",
                "settings": self.settings.fingerprint,
                "bodies": [
                    self._body_configuration_record(body)
                    for body in self.bodies()
                ],
                "joints": [joint.state_record() for joint in self.joints()],
            }
        )

    @property
    def state_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.world_state.v4",
                "settings": self.settings.fingerprint,
                "tick": self._tick,
                "bodies": [self._body_record(body) for body in self.bodies()],
                "joints": [joint.state_record() for joint in self.joints()],
                "contact_cache": self._contact_cache.state_record(),
                "joint_cache": self._joint_cache.state_record(),
                "last_manifolds": [
                    self._manifold_record(manifold)
                    for manifold in self._last_manifolds
                ],
            }
        )

    def capture_snapshot(self) -> PhysicsSnapshot:
        body_states = tuple(
            PhysicsBodyState(
                body_id=body.body_id,
                position=body.position,
                orientation=body.orientation,
                linear_velocity=body.linear_velocity,
                angular_velocity=body.angular_velocity,
                force=body.force,
                torque=body.torque,
                awake=body.awake,
                sleep_time=body.sleep_time,
            )
            for body in self.bodies()
        )
        return build_snapshot(
            tick=self._tick,
            configuration_digest=self.configuration_digest,
            body_states=body_states,
            contact_cache=self._contact_cache.snapshot(),
            manifolds=self._last_manifolds,
            state_digest=self.state_digest,
            joint_cache=self._joint_cache.snapshot(),
        )

    def _apply_snapshot_state(self, snapshot: PhysicsSnapshot) -> None:
        for state in snapshot.body_states:
            body = self._bodies[state.body_id]
            body.position = state.position
            body.orientation = state.orientation
            body.linear_velocity = state.linear_velocity
            body.angular_velocity = state.angular_velocity
            body.force = state.force
            body.torque = state.torque
            body.awake = state.awake
            body.sleep_time = state.sleep_time
        self._contact_cache.restore(snapshot.contact_cache)
        self._joint_cache.restore(snapshot.joint_cache)
        self._last_manifolds = snapshot.manifolds
        self._tick = snapshot.tick

    def restore_snapshot(self, snapshot: PhysicsSnapshot) -> None:
        if not isinstance(snapshot, PhysicsSnapshot):
            raise PhysicsSnapshotError("restore requires PhysicsSnapshot")
        verify_snapshot(snapshot)
        if snapshot.configuration_digest != self.configuration_digest:
            raise PhysicsSnapshotError("physics snapshot configuration mismatch")
        expected_ids = self.body_ids()
        snapshot_ids = tuple(row.body_id for row in snapshot.body_states)
        if snapshot_ids != expected_ids:
            raise PhysicsSnapshotError("physics snapshot body set mismatch")

        previous = self.capture_snapshot()
        try:
            self._apply_snapshot_state(snapshot)
            if self.state_digest != snapshot.state_digest:
                raise PhysicsSnapshotError("physics snapshot state digest mismatch")
        except Exception:
            self._apply_snapshot_state(previous)
            if self.state_digest != previous.state_digest:
                raise PhysicsSnapshotError(
                    "physics snapshot restore rollback failed"
                )
            raise

    def _capture_step_checkpoint(self) -> _StepCheckpoint:
        states = tuple(
            (
                body.body_id,
                _BodyStepState(
                    position=body.position,
                    orientation=body.orientation,
                    linear_velocity=body.linear_velocity,
                    angular_velocity=body.angular_velocity,
                    force=body.force,
                    torque=body.torque,
                    awake=body.awake,
                    sleep_time=body.sleep_time,
                ),
            )
            for body in self.bodies()
        )
        return _StepCheckpoint(
            tick=self._tick,
            body_states=states,
            contact_cache=self._contact_cache.snapshot(),
            joint_cache=self._joint_cache.snapshot(),
            manifolds=self._last_manifolds,
            state_digest=self.state_digest,
        )

    def _restore_step_checkpoint(self, checkpoint: _StepCheckpoint) -> None:
        if tuple(body_id for body_id, _ in checkpoint.body_states) != self.body_ids():
            raise PhysicsValidationError("physics step checkpoint body set changed")
        for body_id, state in checkpoint.body_states:
            body = self._bodies[body_id]
            body.position = state.position
            body.orientation = state.orientation
            body.linear_velocity = state.linear_velocity
            body.angular_velocity = state.angular_velocity
            body.force = state.force
            body.torque = state.torque
            body.awake = state.awake
            body.sleep_time = state.sleep_time
        self._contact_cache.restore(checkpoint.contact_cache)
        self._joint_cache.restore(checkpoint.joint_cache)
        self._tick = checkpoint.tick
        self._last_manifolds = checkpoint.manifolds
        if self.state_digest != checkpoint.state_digest:
            raise PhysicsValidationError("physics step checkpoint failed exact restoration")

    def _advance_all_bodies(self, dt: float) -> None:
        if dt <= 0.0:
            return
        for body in self.bodies():
            body.integrate_velocity(dt)

    def _bias_toi_pair_into_contact(self, event: TOIEvent) -> None:
        slop = self.settings.ccd_contact_slop
        if slop <= 0.0:
            return
        body_a = self._bodies[event.body_a]
        body_b = self._bodies[event.body_b]
        inverse_mass_sum = body_a.inverse_mass + body_b.inverse_mass
        if inverse_mass_sum <= 0.0:
            return
        if body_a.inverse_mass > 0.0:
            weight_a = body_a.inverse_mass / inverse_mass_sum
            # TOI is ideally exactly touching. Bias a microscopic amount into
            # contact so narrow phase has a resolvable manifold despite roundoff.
            body_a.position = body_a.position + event.normal * (slop * weight_a)
            body_a.wake()
        if body_b.inverse_mass > 0.0:
            weight_b = body_b.inverse_mass / inverse_mass_sum
            body_b.position = body_b.position - event.normal * (slop * weight_b)
            body_b.wake()

    def _resolve_toi_event(self, event: TOIEvent, *, tick: int) -> None:
        self._bias_toi_pair_into_contact(event)
        manifold = detect_collision(
            self._bodies[event.body_a],
            self._bodies[event.body_b],
        )
        if manifold is None:
            raise PhysicsValidationError(
                "CCD TOI failed to produce a resolvable contact manifold"
            )
        # Do not persist interim impulses into the frame cache. The final
        # discrete solve owns next-frame warm-start state; caching here would
        # re-apply the same impact impulse later in this tick.
        self._solver.solve(
            self._bodies,
            (manifold,),
            cache=None,
            tick=tick,
        )

    def _integrate_velocity_phase(
        self,
        dt: float,
        *,
        tick: int,
    ) -> tuple[TOIEvent, ...]:
        if not self.settings.ccd_enabled:
            self._advance_all_bodies(dt)
            return ()

        remaining = dt
        events: list[TOIEvent] = []
        minimum_advance = dt * self.settings.ccd_min_advance_fraction

        for _ in range(self.settings.ccd_max_substeps):
            if remaining <= EPSILON:
                remaining = 0.0
                break

            event = self._ccd.earliest_event(self.bodies(), remaining)
            if event is None:
                self._advance_all_bodies(remaining)
                remaining = 0.0
                break

            advance = event.time
            if advance > 0.0:
                self._advance_all_bodies(advance)
                remaining = max(0.0, remaining - advance)

            self._resolve_toi_event(event, tick=tick)
            events.append(event)

            if remaining <= EPSILON:
                remaining = 0.0
                break

            if advance <= minimum_advance:
                escape = min(remaining, minimum_advance)
                self._advance_all_bodies(escape)
                remaining = max(0.0, remaining - escape)

        if remaining > EPSILON:
            pending = self._ccd.earliest_event(self.bodies(), remaining)
            if pending is not None:
                raise PhysicsValidationError("CCD substep bound exceeded")
            self._advance_all_bodies(remaining)

        return tuple(events)

    def _update_sleep(self, graph: IslandGraph, dt: float) -> None:
        linear_limit_sq = self.settings.sleep_linear_speed**2
        angular_limit_sq = self.settings.sleep_angular_speed**2

        for island in graph.islands:
            dynamic = tuple(self._bodies[body_id] for body_id in island.dynamic_bodies)
            active = any(
                body.linear_velocity.length_squared() > linear_limit_sq
                or body.angular_velocity.length_squared() > angular_limit_sq
                or body.force.length_squared() > 0.0
                or body.torque.length_squared() > 0.0
                for body in dynamic
            )

            if active:
                for body in dynamic:
                    body.sleep_time = 0.0
                continue

            all_ready = True
            for body in dynamic:
                if body.awake:
                    body.sleep_time += dt
                if body.sleep_time < self.settings.sleep_after_seconds:
                    all_ready = False

            if all_ready:
                for body in dynamic:
                    body.sleep()

    def _step_once(self) -> PhysicsStepReceipt:
        checkpoint = self._capture_step_checkpoint()
        dt = self.settings.fixed_dt
        before = checkpoint.state_digest
        next_tick = self._tick + 1

        try:
            previous_graph = build_islands(
                self._bodies,
                self._last_manifolds,
                self.joints(),
            )
            previous_graph.propagate_awake(self._bodies)

            for body in self.bodies():
                body.integrate_forces(dt, self.settings.gravity)
            ccd_hits = self._integrate_velocity_phase(dt, tick=next_tick)

            pairs = self._broad_phase.compute_pairs(self.bodies())
            manifolds = generate_manifolds(self._bodies, pairs)
            graph = build_islands(
                self._bodies,
                manifolds,
                self.joints(),
            )
            graph.propagate_awake(self._bodies)
            island_solve = solve_islands(
                self._bodies,
                graph,
                contact_solver=self._solver,
                constraint_solver=self._constraint_solver,
                cache=self._contact_cache,
                joint_cache=self._joint_cache,
                tick=next_tick,
                dt=dt,
            )
            solver_stats = island_solve.solver
            constraint_stats = island_solve.constraints

            self._update_sleep(graph, dt)
            for body in self.bodies():
                body.clear_accumulators()

            self._last_manifolds = manifolds
            self._tick = next_tick
            after = self.state_digest
            energy = sum(body.kinetic_energy() for body in self.bodies())
            sleeping = sum(
                1
                for body in self.bodies()
                if body.body_type is BodyType.DYNAMIC and not body.awake
            )
        except Exception:
            self._restore_step_checkpoint(checkpoint)
            raise

        return PhysicsStepReceipt(
            tick=self._tick,
            dt=dt,
            before_digest=before,
            after_digest=after,
            broad_phase_pairs=len(pairs),
            manifolds=len(manifolds),
            contact_points=sum(len(row.points) for row in manifolds),
            ccd_clamps=len(ccd_hits),
            kinetic_energy=energy,
            sleeping_bodies=sleeping,
            solver=solver_stats,
            constraints=constraint_stats,
            islands=graph.stats,
        )

    def step(self, steps: int = 1) -> tuple[PhysicsStepReceipt, ...]:
        if (
            isinstance(steps, bool)
            or not isinstance(steps, int)
            or not 1 <= steps <= MAX_STEP_COUNT
        ):
            raise PhysicsValidationError("steps outside supported range")
        return tuple(self._step_once() for _ in range(steps))
