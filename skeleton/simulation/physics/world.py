"""Deterministic fixed-step 3D rigid-body world."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..ecs.canonical import digest
from .body import BodyType, RigidBody
from .collision import ContactManifold, SweepAndPruneBroadPhase, generate_manifolds
from .errors import BodyNotFoundError, DuplicateBodyError, PhysicsValidationError
from .math3d import AABB, Vec3
from .queries import Ray, RayHit, raycast_body, sort_hits, sphere_cast_body
from .shapes import BoxShape, PlaneShape, SphereShape
from .solver import SequentialImpulseSolver, SolverStats

MAX_WORLD_BODIES = 100_000
MAX_STEP_COUNT = 10_000


def _positive(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise PhysicsValidationError(f"{name} must be finite and positive")
    return value


@dataclass(frozen=True, slots=True)
class PhysicsSettings:
    fixed_dt: float = 1.0 / 60.0
    gravity: Vec3 = Vec3(0.0, -9.81, 0.0)
    sleep_linear_speed: float = 0.03
    sleep_angular_speed: float = 0.03
    sleep_after_seconds: float = 0.75
    max_bodies: int = 16_384
    max_pairs: int = 250_000
    velocity_iterations: int = 10
    position_iterations: int = 4

    def __post_init__(self) -> None:
        object.__setattr__(self, "fixed_dt", _positive(self.fixed_dt, name="fixed_dt"))
        object.__setattr__(
            self,
            "sleep_after_seconds",
            _positive(self.sleep_after_seconds, name="sleep_after_seconds"),
        )
        for name in ("sleep_linear_speed", "sleep_angular_speed"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PhysicsValidationError(f"{name} must be numeric")
            value = float(value)
            if not math.isfinite(value) or value < 0.0:
                raise PhysicsValidationError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)
        if (
            isinstance(self.max_bodies, bool)
            or not isinstance(self.max_bodies, int)
            or not 1 <= self.max_bodies <= MAX_WORLD_BODIES
        ):
            raise PhysicsValidationError("max_bodies outside supported range")
        if (
            isinstance(self.max_pairs, bool)
            or not isinstance(self.max_pairs, int)
            or not 1 <= self.max_pairs <= 1_000_000
        ):
            raise PhysicsValidationError("max_pairs outside supported range")
        for name in ("velocity_iterations", "position_iterations"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 128:
                raise PhysicsValidationError(f"{name} outside supported range")

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.settings.v1",
                "fixed_dt": self.fixed_dt,
                "gravity": self.gravity.to_tuple(),
                "sleep_linear_speed": self.sleep_linear_speed,
                "sleep_angular_speed": self.sleep_angular_speed,
                "sleep_after_seconds": self.sleep_after_seconds,
                "max_bodies": self.max_bodies,
                "max_pairs": self.max_pairs,
                "velocity_iterations": self.velocity_iterations,
                "position_iterations": self.position_iterations,
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
    kinetic_energy: float
    sleeping_bodies: int
    solver: SolverStats

    @property
    def changed(self) -> bool:
        return self.before_digest != self.after_digest


class PhysicsWorld:
    def __init__(self, settings: PhysicsSettings | None = None) -> None:
        self.settings = settings or PhysicsSettings()
        self._bodies: dict[str, RigidBody] = {}
        self._tick = 0
        self._broad_phase = SweepAndPruneBroadPhase(max_pairs=self.settings.max_pairs)
        self._solver = SequentialImpulseSolver(
            velocity_iterations=self.settings.velocity_iterations,
            position_iterations=self.settings.position_iterations,
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
        if body.body_id in self._bodies:
            raise DuplicateBodyError(body.body_id)
        if len(self._bodies) >= self.settings.max_bodies:
            raise PhysicsValidationError("physics world body bound exceeded")
        self._bodies[body.body_id] = body
        return body

    def remove_body(self, body_id: str) -> RigidBody:
        try:
            return self._bodies.pop(body_id)
        except KeyError as exc:
            raise BodyNotFoundError(body_id) from exc

    def contacts(self) -> tuple[ContactManifold, ...]:
        return self._last_manifolds

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
                "domain": "skeleton.simulation.physics.world_state.v1",
                "settings": self.settings.fingerprint,
                "tick": self._tick,
                "bodies": [self._body_record(body) for body in self.bodies()],
            }
        )

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
        dt = self.settings.fixed_dt
        before = self.state_digest

        for body in self.bodies():
            body.integrate_forces(dt, self.settings.gravity)
        for body in self.bodies():
            body.integrate_velocity(dt)

        pairs = self._broad_phase.compute_pairs(self.bodies())
        manifolds = generate_manifolds(self._bodies, pairs)
        solver_stats = self._solver.solve(self._bodies, manifolds)

        for body in self.bodies():
            body.clear_accumulators()
        self._update_sleep(dt)

        self._last_manifolds = manifolds
        self._tick += 1
        after = self.state_digest
        energy = sum(body.kinetic_energy() for body in self.bodies())
        sleeping = sum(
            1
            for body in self.bodies()
            if body.body_type is BodyType.DYNAMIC and not body.awake
        )

        return PhysicsStepReceipt(
            tick=self._tick,
            dt=dt,
            before_digest=before,
            after_digest=after,
            broad_phase_pairs=len(pairs),
            manifolds=len(manifolds),
            contact_points=sum(len(row.points) for row in manifolds),
            kinetic_energy=energy,
            sleeping_bodies=sleeping,
            solver=solver_stats,
        )

    def step(self, steps: int = 1) -> tuple[PhysicsStepReceipt, ...]:
        if (
            isinstance(steps, bool)
            or not isinstance(steps, int)
            or not 1 <= steps <= MAX_STEP_COUNT
        ):
            raise PhysicsValidationError("steps outside supported range")
        return tuple(self._step_once() for _ in range(steps))
