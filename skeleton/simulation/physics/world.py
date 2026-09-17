"""Deterministic fixed-step 3D rigid-body world."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..ecs.canonical import digest
from .body import BodyType, RigidBody
from .calculations import PhysicsAggregate, aggregate_physics
from .ccd import CCDHit, ContinuousCollisionDetector
from .collision import ContactManifold, SweepAndPruneBroadPhase, generate_manifolds
from .constraints import ConstraintSolver, ConstraintStats, DistanceJoint
from .contacts import ContactCache, ContactCacheEntry
from .errors import (
    BodyNotFoundError,
    DuplicateBodyError,
    DuplicateJointError,
    JointNotFoundError,
    PhysicsValidationError,
)
from .math3d import AABB, Quat, Vec3
from .queries import Ray, RayHit, raycast_body, sort_hits, sphere_cast_body
from .shapes import BoxShape, PlaneShape, SphereShape
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
    ccd_enabled: bool = True
    ccd_motion_threshold: float = 0.5
    ccd_contact_slop: float = 1.0e-7
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
        _bounded_int(self.max_ccd_checks, name="max_ccd_checks", maximum=1_000_000)
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
                "domain": "skeleton.simulation.physics.settings.v2",
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
                "ccd_enabled": self.ccd_enabled,
                "ccd_motion_threshold": self.ccd_motion_threshold,
                "ccd_contact_slop": self.ccd_contact_slop,
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

    @property
    def changed(self) -> bool:
        return self.before_digest != self.after_digest


class PhysicsWorld:
    def __init__(self, settings: PhysicsSettings | None = None) -> None:
        if settings is not None and not isinstance(settings, PhysicsSettings):
            raise PhysicsValidationError("settings must be PhysicsSettings")
        self.settings = settings or PhysicsSettings()
        self._bodies: dict[str, RigidBody] = {}
        self._joints: dict[str, DistanceJoint] = {}
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
        self._last_manifolds = tuple(
            row
            for row in self._last_manifolds
            if row.body_a != body_id and row.body_b != body_id
        )
        return body

    def joint_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._joints))

    def joints(self) -> tuple[DistanceJoint, ...]:
        return tuple(self._joints[joint_id] for joint_id in self.joint_ids())

    def get_joint(self, joint_id: str) -> DistanceJoint:
        try:
            return self._joints[joint_id]
        except KeyError as exc:
            raise JointNotFoundError(joint_id) from exc

    def add_joint(self, joint: DistanceJoint) -> DistanceJoint:
        if not isinstance(joint, DistanceJoint):
            raise PhysicsValidationError("joint must be DistanceJoint")
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

    def remove_joint(self, joint_id: str) -> DistanceJoint:
        try:
            return self._joints.pop(joint_id)
        except KeyError as exc:
            raise JointNotFoundError(joint_id) from exc

    def contacts(self) -> tuple[ContactManifold, ...]:
        return self._last_manifolds

    def contact_cache_size(self) -> int:
        return len(self._contact_cache)

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
        raise PhysicsValidationError("unknown shape implementation")

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
    def state_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.world_state.v2",
                "settings": self.settings.fingerprint,
                "tick": self._tick,
                "bodies": [self._body_record(body) for body in self.bodies()],
                "joints": [joint.state_record() for joint in self.joints()],
                "contact_cache": self._contact_cache.state_record(),
            }
        )

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
        self._tick = checkpoint.tick
        self._last_manifolds = checkpoint.manifolds
        if self.state_digest != checkpoint.state_digest:
            raise PhysicsValidationError("physics step checkpoint failed exact restoration")

    def _integrate_velocity_phase(self, dt: float) -> tuple[CCDHit, ...]:
        bodies = self.bodies()
        hits: list[CCDHit] = []
        for body in bodies:
            hit = None
            if self.settings.ccd_enabled:
                hit = self._ccd.sweep(body, bodies, dt)
            if hit is None:
                body.integrate_velocity(dt)
                continue
            body.position = hit.center - hit.normal * self.settings.ccd_contact_slop
            body.integrate_orientation(dt)
            hits.append(hit)
        return tuple(hits)

    def _update_sleep(self, dt: float) -> None:
        linear_limit_sq = self.settings.sleep_linear_speed**2
        angular_limit_sq = self.settings.sleep_angular_speed**2
        for body in self.bodies():
            if body.body_type is not BodyType.DYNAMIC or not body.awake:
                continue
            quiet = (
                body.linear_velocity.length_squared() <= linear_limit_sq
                and body.angular_velocity.length_squared() <= angular_limit_sq
                and body.force.length_squared() == 0.0
                and body.torque.length_squared() == 0.0
            )
            if quiet:
                body.sleep_time += dt
                if body.sleep_time >= self.settings.sleep_after_seconds:
                    body.sleep()
            else:
                body.sleep_time = 0.0

    def _step_once(self) -> PhysicsStepReceipt:
        checkpoint = self._capture_step_checkpoint()
        dt = self.settings.fixed_dt
        before = checkpoint.state_digest
        next_tick = self._tick + 1

        try:
            for body in self.bodies():
                body.integrate_forces(dt, self.settings.gravity)
            ccd_hits = self._integrate_velocity_phase(dt)

            pairs = self._broad_phase.compute_pairs(self.bodies())
            manifolds = generate_manifolds(self._bodies, pairs)
            solver_stats = self._solver.solve(
                self._bodies,
                manifolds,
                cache=self._contact_cache,
                tick=next_tick,
            )
            constraint_stats = self._constraint_solver.solve(
                self._bodies,
                self.joints(),
                dt=dt,
            )

            self._update_sleep(dt)
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
        )

    def step(self, steps: int = 1) -> tuple[PhysicsStepReceipt, ...]:
        if (
            isinstance(steps, bool)
            or not isinstance(steps, int)
            or not 1 <= steps <= MAX_STEP_COUNT
        ):
            raise PhysicsValidationError("steps outside supported range")
        return tuple(self._step_once() for _ in range(steps))
