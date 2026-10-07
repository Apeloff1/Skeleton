"""Deterministic historical physics systems for Jeeves game projects.

This module is the simulation authority for the project-level physics evidence
plane. Older backend physics routes are API/curriculum and HTML-playable
surfaces; they are intentionally not imported here.

The solver evolves with the engine era while retaining one deterministic API:
- Pong through 16-bit: 2D fixed-step AABB mechanics.
- Early 3D: deterministic 3D AABB rigid-lite simulation.
- Fixed-function/shader: sphere + box contacts, friction and angular state.
- HD/open-world: iterative constraints, sleeping and deterministic broadphase.
- Modern/next: bounded conservative substeps for fast bodies and larger solver
  budgets.

Physics configuration is data-only and compiles to physics/compiled files.
No generated source is executed as authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    NumericMode,
    SandboxPatch,
    engine_era_profile,
)
from .game_engine_runtime import RoutedEngineSandbox


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _q(
    mode: NumericMode,
    value: float,
) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise GameEngineLabError(
            "physics value must be finite"
        )
    if mode is NumericMode.INTEGER:
        return float(round(value))
    if mode is NumericMode.FIXED8:
        return round(value * 256) / 256
    if mode is NumericMode.FIXED16:
        return round(value * 65_536) / 65_536
    if mode is NumericMode.FLOAT32:
        return struct.unpack(
            "!f",
            struct.pack("!f", value),
        )[0]
    return round(value, 12)


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        for value in (
            self.x,
            self.y,
            self.z,
        ):
            if not math.isfinite(
                float(value)
            ):
                raise GameEngineLabError(
                    "vector must be finite"
                )

    def __add__(
        self,
        other: "Vec3",
    ) -> "Vec3":
        return Vec3(
            self.x + other.x,
            self.y + other.y,
            self.z + other.z,
        )

    def __sub__(
        self,
        other: "Vec3",
    ) -> "Vec3":
        return Vec3(
            self.x - other.x,
            self.y - other.y,
            self.z - other.z,
        )

    def __mul__(
        self,
        scalar: float,
    ) -> "Vec3":
        return Vec3(
            self.x * scalar,
            self.y * scalar,
            self.z * scalar,
        )

    __rmul__ = __mul__

    def __truediv__(
        self,
        scalar: float,
    ) -> "Vec3":
        if scalar == 0:
            raise GameEngineLabError(
                "cannot divide vector by zero"
            )
        return self * (
            1.0 / scalar
        )

    def dot(
        self,
        other: "Vec3",
    ) -> float:
        return (
            self.x * other.x
            + self.y * other.y
            + self.z * other.z
        )

    def cross(
        self,
        other: "Vec3",
    ) -> "Vec3":
        return Vec3(
            self.y * other.z
            - self.z * other.y,
            self.z * other.x
            - self.x * other.z,
            self.x * other.y
            - self.y * other.x,
        )

    def length_sq(self) -> float:
        return self.dot(self)

    def length(self) -> float:
        return math.sqrt(
            self.length_sq()
        )

    def normalized(self) -> "Vec3":
        size = self.length()
        if size <= 1e-12:
            return Vec3(
                0.0,
                0.0,
                0.0,
            )
        return self / size


ZERO3 = Vec3(
    0.0,
    0.0,
    0.0,
)


@dataclass(frozen=True, slots=True)
class Quat:
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        for value in (
            self.w,
            self.x,
            self.y,
            self.z,
        ):
            if not math.isfinite(
                float(value)
            ):
                raise GameEngineLabError(
                    "quaternion must be finite"
                )

    def normalized(self) -> "Quat":
        magnitude = math.sqrt(
            self.w * self.w
            + self.x * self.x
            + self.y * self.y
            + self.z * self.z
        )
        if magnitude <= 1e-12:
            return Quat()
        return Quat(
            self.w / magnitude,
            self.x / magnitude,
            self.y / magnitude,
            self.z / magnitude,
        )

    def __mul__(
        self,
        other: "Quat",
    ) -> "Quat":
        return Quat(
            self.w * other.w
            - self.x * other.x
            - self.y * other.y
            - self.z * other.z,
            self.w * other.x
            + self.x * other.w
            + self.y * other.z
            - self.z * other.y,
            self.w * other.y
            - self.x * other.z
            + self.y * other.w
            + self.z * other.x,
            self.w * other.z
            + self.x * other.y
            - self.y * other.x
            + self.z * other.w,
        )

    @classmethod
    def from_angular_step(
        cls,
        angular_velocity: Vec3,
        dt: float,
    ) -> "Quat":
        speed = angular_velocity.length()
        if speed <= 1e-12:
            return cls()
        angle = speed * dt
        half = angle * 0.5
        axis = angular_velocity / speed
        scale = math.sin(half)
        return cls(
            math.cos(half),
            axis.x * scale,
            axis.y * scale,
            axis.z * scale,
        )


class ShapeKind(str, Enum):
    AABB = "aabb"
    SPHERE = "sphere"


class BroadphaseKind(str, Enum):
    ALL_PAIRS = "all_pairs"
    SWEEP_X = "sweep_x"
    UNIFORM_GRID = "uniform_grid"


@dataclass(frozen=True, slots=True)
class PhysicsEraPolicy:
    era: EngineEra
    dimensions: int
    shapes: tuple[ShapeKind, ...]
    broadphase: BroadphaseKind
    solver_iterations: int
    substeps: int
    max_bodies: int
    max_constraints: int
    friction: bool
    rotation: bool
    constraints: bool
    sleeping: bool
    conservative_ccd: bool
    max_toi_events: int
    grid_cell_size: float
    sleep_threshold: float
    sleep_frames: int
    numeric_mode: NumericMode

    def __post_init__(self) -> None:
        if self.dimensions not in {
            2,
            3,
        }:
            raise GameEngineLabError(
                "physics dimensions must be 2 or 3"
            )
        if not self.shapes:
            raise GameEngineLabError(
                "physics policy needs collision shapes"
            )
        for value in (
            self.solver_iterations,
            self.substeps,
            self.max_bodies,
            self.sleep_frames,
            self.max_toi_events,
        ):
            if value < 1:
                raise GameEngineLabError(
                    "physics positive bounds required"
                )
        if self.max_constraints < 0:
            raise GameEngineLabError(
                "constraint budget cannot be negative"
            )
        if self.grid_cell_size <= 0:
            raise GameEngineLabError(
                "grid cell size must be positive"
            )
        if self.sleep_threshold < 0:
            raise GameEngineLabError(
                "sleep threshold cannot be negative"
            )


def _policy(
    era: EngineEra,
    *,
    dimensions: int,
    shapes: tuple[ShapeKind, ...],
    broadphase: BroadphaseKind,
    solver_iterations: int,
    substeps: int,
    max_constraints: int,
    friction: bool,
    rotation: bool,
    constraints: bool,
    sleeping: bool,
    ccd: bool,
    grid: float,
    sleep_threshold: float = 0.02,
    sleep_frames: int = 30,
) -> PhysicsEraPolicy:
    profile = engine_era_profile(
        era
    )
    return PhysicsEraPolicy(
        era=era,
        dimensions=dimensions,
        shapes=shapes,
        broadphase=broadphase,
        solver_iterations=solver_iterations,
        substeps=substeps,
        max_bodies=profile.entity_budget,
        max_constraints=max_constraints,
        friction=friction,
        rotation=rotation,
        constraints=constraints,
        sleeping=sleeping,
        conservative_ccd=ccd,
        max_toi_events=(
            max(
                4,
                substeps * 4,
            )
            if ccd
            else 1
        ),
        grid_cell_size=grid,
        sleep_threshold=sleep_threshold,
        sleep_frames=sleep_frames,
        numeric_mode=profile.numeric_mode,
    )


PHYSICS_POLICIES: Mapping[
    EngineEra,
    PhysicsEraPolicy,
] = {
    EngineEra.PONG: _policy(
        EngineEra.PONG,
        dimensions=2,
        shapes=(ShapeKind.AABB,),
        broadphase=BroadphaseKind.ALL_PAIRS,
        solver_iterations=1,
        substeps=1,
        max_constraints=0,
        friction=False,
        rotation=False,
        constraints=False,
        sleeping=False,
        ccd=False,
        grid=32.0,
    ),
    EngineEra.ARCADE: _policy(
        EngineEra.ARCADE,
        dimensions=2,
        shapes=(ShapeKind.AABB,),
        broadphase=BroadphaseKind.ALL_PAIRS,
        solver_iterations=1,
        substeps=1,
        max_constraints=0,
        friction=False,
        rotation=False,
        constraints=False,
        sleeping=False,
        ccd=False,
        grid=32.0,
    ),
    EngineEra.EIGHT_BIT: _policy(
        EngineEra.EIGHT_BIT,
        dimensions=2,
        shapes=(ShapeKind.AABB,),
        broadphase=BroadphaseKind.ALL_PAIRS,
        solver_iterations=2,
        substeps=1,
        max_constraints=0,
        friction=True,
        rotation=False,
        constraints=False,
        sleeping=False,
        ccd=False,
        grid=32.0,
    ),
    EngineEra.SIXTEEN_BIT: _policy(
        EngineEra.SIXTEEN_BIT,
        dimensions=2,
        shapes=(ShapeKind.AABB,),
        broadphase=BroadphaseKind.SWEEP_X,
        solver_iterations=3,
        substeps=1,
        max_constraints=0,
        friction=True,
        rotation=False,
        constraints=False,
        sleeping=False,
        ccd=False,
        grid=32.0,
    ),
    EngineEra.EARLY_3D: _policy(
        EngineEra.EARLY_3D,
        dimensions=3,
        shapes=(ShapeKind.AABB,),
        broadphase=BroadphaseKind.SWEEP_X,
        solver_iterations=3,
        substeps=1,
        max_constraints=0,
        friction=True,
        rotation=False,
        constraints=False,
        sleeping=False,
        ccd=False,
        grid=32.0,
    ),
    EngineEra.FIXED_3D: _policy(
        EngineEra.FIXED_3D,
        dimensions=3,
        shapes=(
            ShapeKind.AABB,
            ShapeKind.SPHERE,
        ),
        broadphase=BroadphaseKind.SWEEP_X,
        solver_iterations=4,
        substeps=1,
        max_constraints=32,
        friction=True,
        rotation=True,
        constraints=False,
        sleeping=True,
        ccd=False,
        grid=32.0,
    ),
    EngineEra.SHADER: _policy(
        EngineEra.SHADER,
        dimensions=3,
        shapes=(
            ShapeKind.AABB,
            ShapeKind.SPHERE,
        ),
        broadphase=BroadphaseKind.SWEEP_X,
        solver_iterations=6,
        substeps=1,
        max_constraints=128,
        friction=True,
        rotation=True,
        constraints=True,
        sleeping=True,
        ccd=False,
        grid=48.0,
    ),
    EngineEra.HD: _policy(
        EngineEra.HD,
        dimensions=3,
        shapes=(
            ShapeKind.AABB,
            ShapeKind.SPHERE,
        ),
        broadphase=BroadphaseKind.SWEEP_X,
        solver_iterations=8,
        substeps=2,
        max_constraints=512,
        friction=True,
        rotation=True,
        constraints=True,
        sleeping=True,
        ccd=True,
        grid=64.0,
    ),
    EngineEra.OPEN_WORLD: _policy(
        EngineEra.OPEN_WORLD,
        dimensions=3,
        shapes=(
            ShapeKind.AABB,
            ShapeKind.SPHERE,
        ),
        broadphase=BroadphaseKind.UNIFORM_GRID,
        solver_iterations=8,
        substeps=2,
        max_constraints=2_048,
        friction=True,
        rotation=True,
        constraints=True,
        sleeping=True,
        ccd=True,
        grid=64.0,
    ),
    EngineEra.MODERN: _policy(
        EngineEra.MODERN,
        dimensions=3,
        shapes=(
            ShapeKind.AABB,
            ShapeKind.SPHERE,
        ),
        broadphase=BroadphaseKind.UNIFORM_GRID,
        solver_iterations=12,
        substeps=4,
        max_constraints=8_192,
        friction=True,
        rotation=True,
        constraints=True,
        sleeping=True,
        ccd=True,
        grid=96.0,
        sleep_threshold=0.01,
        sleep_frames=45,
    ),
    EngineEra.NEXT: _policy(
        EngineEra.NEXT,
        dimensions=3,
        shapes=(
            ShapeKind.AABB,
            ShapeKind.SPHERE,
        ),
        broadphase=BroadphaseKind.UNIFORM_GRID,
        solver_iterations=16,
        substeps=8,
        max_constraints=16_384,
        friction=True,
        rotation=True,
        constraints=True,
        sleeping=True,
        ccd=True,
        grid=128.0,
        sleep_threshold=0.005,
        sleep_frames=60,
    ),
}


def physics_policy(
    era: EngineEra | str,
) -> PhysicsEraPolicy:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    return PHYSICS_POLICIES[key]


@dataclass(slots=True)
class RigidBody:
    body_id: str
    shape: ShapeKind
    position: Vec3
    velocity: Vec3 = ZERO3
    half_extent: Vec3 = Vec3(
        0.5,
        0.5,
        0.5,
    )
    radius: float = 0.5
    mass: float = 1.0
    restitution: float = 0.2
    friction: float = 0.5
    static: bool = False
    orientation: Quat = Quat()
    angular_velocity: Vec3 = ZERO3
    force: Vec3 = ZERO3
    torque: Vec3 = ZERO3
    linear_damping: float = 0.999
    angular_damping: float = 0.995
    sleeping: bool = False
    sleep_counter: int = 0

    def __post_init__(self) -> None:
        if (
            not self.body_id
            or len(self.body_id) > 64
        ):
            raise GameEngineLabError(
                "physics body id must be bounded non-empty text"
            )
        if not isinstance(
            self.shape,
            ShapeKind,
        ):
            self.shape = ShapeKind(
                str(self.shape)
            )
        if (
            self.half_extent.x <= 0
            or self.half_extent.y <= 0
            or self.half_extent.z <= 0
        ):
            raise GameEngineLabError(
                "body extents must be positive"
            )
        if self.radius <= 0:
            raise GameEngineLabError(
                "sphere radius must be positive"
            )
        if self.static:
            self.mass = 0.0
        elif (
            not math.isfinite(self.mass)
            or self.mass <= 0
        ):
            raise GameEngineLabError(
                "dynamic body mass must be positive"
            )
        if not 0 <= self.restitution <= 1:
            raise GameEngineLabError(
                "restitution must be within [0, 1]"
            )
        if not 0 <= self.friction <= 2:
            raise GameEngineLabError(
                "friction must be within [0, 2]"
            )
        if not 0 <= self.linear_damping <= 1:
            raise GameEngineLabError(
                "linear damping must be within [0, 1]"
            )
        if not 0 <= self.angular_damping <= 1:
            raise GameEngineLabError(
                "angular damping must be within [0, 1]"
            )

    @property
    def inv_mass(self) -> float:
        if self.static:
            return 0.0
        return 1.0 / self.mass

    @property
    def inv_inertia(self) -> float:
        if self.static:
            return 0.0
        if self.shape is ShapeKind.SPHERE:
            inertia = (
                0.4
                * self.mass
                * self.radius
                * self.radius
            )
        else:
            width = (
                self.half_extent.x
                * 2.0
            )
            height = (
                self.half_extent.y
                * 2.0
            )
            depth = (
                self.half_extent.z
                * 2.0
            )
            inertia = (
                self.mass
                * (
                    width * width
                    + height * height
                    + depth * depth
                )
                / 18.0
            )
        if inertia <= 1e-12:
            return 0.0
        return 1.0 / inertia

    def wake(self) -> None:
        if not self.static:
            self.sleeping = False
            self.sleep_counter = 0


@dataclass(frozen=True, slots=True)
class Contact:
    a: str
    b: str
    normal: Vec3
    penetration: float
    point: Vec3


@dataclass(frozen=True, slots=True)
class SweepHit:
    moving: str
    other: str
    toi: float
    normal: Vec3
    point: Vec3


@dataclass(frozen=True, slots=True)
class RayHit:
    body_id: str
    distance: float
    point: Vec3
    normal: Vec3
    static: bool
    shape: ShapeKind


@dataclass(frozen=True, slots=True)
class DistanceConstraint:
    constraint_id: str
    a: str
    b: str
    rest_length: float
    stiffness: float = 1.0

    def __post_init__(self) -> None:
        if (
            not self.constraint_id
            or len(self.constraint_id) > 64
        ):
            raise GameEngineLabError(
                "constraint id must be bounded"
            )
        if self.a == self.b:
            raise GameEngineLabError(
                "constraint bodies must differ"
            )
        if self.rest_length <= 0:
            raise GameEngineLabError(
                "constraint rest length must be positive"
            )
        if not 0 < self.stiffness <= 1:
            raise GameEngineLabError(
                "constraint stiffness must be within (0, 1]"
            )


@dataclass(frozen=True, slots=True)
class PhysicsSnapshot:
    era: EngineEra
    tick: int
    body_state: tuple[
        tuple[str, tuple[object, ...]],
        ...,
    ]
    constraint_state: tuple[
        tuple[str, str, str, float, float],
        ...,
    ]
    digest: str


def _body_state(
    body: RigidBody,
) -> tuple[object, ...]:
    return (
        body.shape.value,
        body.position.x,
        body.position.y,
        body.position.z,
        body.velocity.x,
        body.velocity.y,
        body.velocity.z,
        body.orientation.w,
        body.orientation.x,
        body.orientation.y,
        body.orientation.z,
        body.angular_velocity.x,
        body.angular_velocity.y,
        body.angular_velocity.z,
        body.force.x,
        body.force.y,
        body.force.z,
        body.torque.x,
        body.torque.y,
        body.torque.z,
        body.sleeping,
        body.sleep_counter,
    )


class HistoricalPhysicsWorld:
    """Era-gated deterministic rigid-lite game physics world."""

    def __init__(
        self,
        era: EngineEra | str,
        *,
        bounds: Vec3 = Vec3(
            100.0,
            100.0,
            100.0,
        ),
        gravity: Vec3 = Vec3(
            0.0,
            -9.8,
            0.0,
        ),
    ) -> None:
        self.policy = physics_policy(
            era
        )
        if (
            bounds.x <= 0
            or bounds.y <= 0
            or bounds.z <= 0
        ):
            raise GameEngineLabError(
                "physics bounds must be positive"
            )
        self.bounds = bounds
        self.gravity = gravity
        self.tick = 0
        self._bodies: dict[
            str,
            RigidBody,
        ] = {}
        self._constraints: dict[
            str,
            DistanceConstraint,
        ] = {}
        self.last_contacts: tuple[
            Contact,
            ...,
        ] = ()

    @property
    def bodies(
        self,
    ) -> tuple[RigidBody, ...]:
        return tuple(
            self._bodies[key]
            for key in sorted(
                self._bodies
            )
        )

    @property
    def constraints(
        self,
    ) -> tuple[
        DistanceConstraint,
        ...,
    ]:
        return tuple(
            self._constraints[key]
            for key in sorted(
                self._constraints
            )
        )

    def _quantize_vec(
        self,
        value: Vec3,
    ) -> Vec3:
        z = (
            0.0
            if self.policy.dimensions == 2
            else value.z
        )
        return Vec3(
            _q(
                self.policy.numeric_mode,
                value.x,
            ),
            _q(
                self.policy.numeric_mode,
                value.y,
            ),
            _q(
                self.policy.numeric_mode,
                z,
            ),
        )

    def spawn(
        self,
        body: RigidBody,
    ) -> None:
        if body.body_id in self._bodies:
            raise GameEngineLabError(
                "duplicate physics body id"
            )
        if (
            len(self._bodies)
            >= self.policy.max_bodies
        ):
            raise GameEngineLabError(
                "physics body budget exceeded"
            )
        if (
            body.shape
            not in self.policy.shapes
        ):
            raise GameEngineLabError(
                f"{body.shape.value} unavailable in {self.policy.era.value}"
            )
        if (
            self.policy.dimensions == 2
            and (
                abs(body.position.z) > 1e-12
                or abs(body.velocity.z) > 1e-12
                or abs(body.angular_velocity.x)
                > 1e-12
                or abs(body.angular_velocity.y)
                > 1e-12
                or abs(body.angular_velocity.z)
                > 1e-12
            )
        ):
            raise GameEngineLabError(
                "2D era body carries unsupported 3D state"
            )
        body.position = (
            self._quantize_vec(
                body.position
            )
        )
        body.velocity = (
            self._quantize_vec(
                body.velocity
            )
        )
        body.force = self._quantize_vec(
            body.force
        )
        body.torque = (
            self._quantize_vec(
                body.torque
            )
            if self.policy.rotation
            else ZERO3
        )
        if not self.policy.rotation:
            body.orientation = Quat()
            body.angular_velocity = ZERO3
        if not self.policy.friction:
            body.friction = 0.0
        self._bodies[
            body.body_id
        ] = body

    def add_constraint(
        self,
        constraint: DistanceConstraint,
    ) -> None:
        if not self.policy.constraints:
            raise GameEngineLabError(
                "constraints unavailable in this engine era"
            )
        if (
            constraint.constraint_id
            in self._constraints
        ):
            raise GameEngineLabError(
                "duplicate constraint id"
            )
        if (
            len(self._constraints)
            >= self.policy.max_constraints
        ):
            raise GameEngineLabError(
                "constraint budget exceeded"
            )
        if (
            constraint.a not in self._bodies
            or constraint.b not in self._bodies
        ):
            raise GameEngineLabError(
                "constraint references missing body"
            )
        self._constraints[
            constraint.constraint_id
        ] = constraint

    def apply_force(
        self,
        body_id: str,
        force: Vec3,
        *,
        torque: Vec3 = ZERO3,
    ) -> None:
        try:
            body = self._bodies[
                body_id
            ]
        except KeyError as exc:
            raise GameEngineLabError(
                "unknown physics body"
            ) from exc
        if body.static:
            return
        body.force = (
            body.force + force
        )
        if self.policy.rotation:
            body.torque = (
                body.torque + torque
            )
        body.wake()

    def _extent(
        self,
        body: RigidBody,
    ) -> Vec3:
        if body.shape is ShapeKind.SPHERE:
            return Vec3(
                body.radius,
                body.radius,
                body.radius,
            )
        return body.half_extent

    def _aabb(
        self,
        body: RigidBody,
    ) -> tuple[
        Vec3,
        Vec3,
    ]:
        extent = self._extent(
            body
        )
        return (
            body.position - extent,
            body.position + extent,
        )

    def _candidate_pairs(
        self,
    ) -> tuple[
        tuple[str, str],
        ...,
    ]:
        ids = sorted(
            self._bodies
        )
        if (
            self.policy.broadphase
            is BroadphaseKind.ALL_PAIRS
        ):
            return tuple(
                (
                    first,
                    second,
                )
                for index, first
                in enumerate(ids)
                for second
                in ids[
                    index + 1:
                ]
                if not (
                    self._bodies[
                        first
                    ].static
                    and self._bodies[
                        second
                    ].static
                )
            )

        if (
            self.policy.broadphase
            is BroadphaseKind.SWEEP_X
        ):
            ordered = sorted(
                ids,
                key=lambda key: (
                    self._aabb(
                        self._bodies[key]
                    )[0].x,
                    key,
                ),
            )
            pairs: list[
                tuple[str, str]
            ] = []
            for index, first in enumerate(
                ordered
            ):
                a = self._bodies[
                    first
                ]
                _, amax = self._aabb(
                    a
                )
                for second in ordered[
                    index + 1:
                ]:
                    b = self._bodies[
                        second
                    ]
                    bmin, _ = self._aabb(
                        b
                    )
                    if bmin.x > amax.x:
                        break
                    if not (
                        a.static
                        and b.static
                    ):
                        pairs.append(
                            tuple(
                                sorted(
                                    (
                                        first,
                                        second,
                                    )
                                )
                            )
                        )
            return tuple(
                sorted(
                    set(pairs)
                )
            )

        cell_size = (
            self.policy.grid_cell_size
        )
        cells: dict[
            tuple[int, int, int],
            list[str],
        ] = {}
        for key in ids:
            body = self._bodies[
                key
            ]
            lower, upper = self._aabb(
                body
            )
            z_lower = (
                0
                if self.policy.dimensions
                == 2
                else math.floor(
                    lower.z
                    / cell_size
                )
            )
            z_upper = (
                0
                if self.policy.dimensions
                == 2
                else math.floor(
                    upper.z
                    / cell_size
                )
            )
            for x in range(
                math.floor(
                    lower.x
                    / cell_size
                ),
                math.floor(
                    upper.x
                    / cell_size
                )
                + 1,
            ):
                for y in range(
                    math.floor(
                        lower.y
                        / cell_size
                    ),
                    math.floor(
                        upper.y
                        / cell_size
                    )
                    + 1,
                ):
                    for z in range(
                        z_lower,
                        z_upper + 1,
                    ):
                        cells.setdefault(
                            (
                                x,
                                y,
                                z,
                            ),
                            [],
                        ).append(key)
        pairs: set[
            tuple[str, str]
        ] = set()
        for cell in sorted(
            cells
        ):
            members = sorted(
                cells[cell]
            )
            for index, first in enumerate(
                members
            ):
                for second in members[
                    index + 1:
                ]:
                    a = self._bodies[
                        first
                    ]
                    b = self._bodies[
                        second
                    ]
                    if (
                        a.static
                        and b.static
                    ):
                        continue
                    pairs.add(
                        (
                            first,
                            second,
                        )
                    )
        return tuple(
            sorted(pairs)
        )

    def _aabb_contact(
        self,
        a: RigidBody,
        b: RigidBody,
    ) -> Contact | None:
        ae = a.half_extent
        be = b.half_extent
        delta = (
            b.position
            - a.position
        )
        overlaps = [
            (
                ae.x
                + be.x
                - abs(delta.x),
                Vec3(
                    1.0
                    if delta.x >= 0
                    else -1.0,
                    0.0,
                    0.0,
                ),
            ),
            (
                ae.y
                + be.y
                - abs(delta.y),
                Vec3(
                    0.0,
                    1.0
                    if delta.y >= 0
                    else -1.0,
                    0.0,
                ),
            ),
        ]
        if self.policy.dimensions == 3:
            overlaps.append(
                (
                    ae.z
                    + be.z
                    - abs(delta.z),
                    Vec3(
                        0.0,
                        0.0,
                        1.0
                        if delta.z >= 0
                        else -1.0,
                    ),
                )
            )
        if any(
            overlap <= 0
            for overlap, _
            in overlaps
        ):
            return None
        penetration, normal = min(
            overlaps,
            key=lambda item: (
                item[0],
                item[1].x,
                item[1].y,
                item[1].z,
            ),
        )
        return Contact(
            a.body_id,
            b.body_id,
            normal,
            penetration,
            (
                a.position
                + b.position
            )
            * 0.5,
        )

    def _sphere_contact(
        self,
        a: RigidBody,
        b: RigidBody,
    ) -> Contact | None:
        delta = (
            b.position
            - a.position
        )
        distance_sq = (
            delta.length_sq()
        )
        radius = (
            a.radius
            + b.radius
        )
        if distance_sq >= (
            radius * radius
        ):
            return None
        distance = math.sqrt(
            max(
                distance_sq,
                0.0,
            )
        )
        normal = (
            Vec3(
                1.0,
                0.0,
                0.0,
            )
            if distance <= 1e-12
            else delta / distance
        )
        return Contact(
            a.body_id,
            b.body_id,
            normal,
            radius - distance,
            a.position
            + normal
            * a.radius,
        )

    def _sphere_aabb_contact(
        self,
        sphere: RigidBody,
        box: RigidBody,
        *,
        sphere_first: bool,
    ) -> Contact | None:
        lower = (
            box.position
            - box.half_extent
        )
        upper = (
            box.position
            + box.half_extent
        )
        closest = Vec3(
            min(
                upper.x,
                max(
                    lower.x,
                    sphere.position.x,
                ),
            ),
            min(
                upper.y,
                max(
                    lower.y,
                    sphere.position.y,
                ),
            ),
            (
                min(
                    upper.z,
                    max(
                        lower.z,
                        sphere.position.z,
                    ),
                )
                if self.policy.dimensions
                == 3
                else 0.0
            ),
        )
        delta = (
            sphere.position
            - closest
        )
        distance_sq = (
            delta.length_sq()
        )
        if (
            distance_sq
            >= sphere.radius
            * sphere.radius
        ):
            return None
        distance = math.sqrt(
            max(
                distance_sq,
                0.0,
            )
        )
        if distance <= 1e-12:
            raw = (
                sphere.position
                - box.position
            )
            axes = (
                (
                    abs(raw.x),
                    Vec3(
                        1.0
                        if raw.x >= 0
                        else -1.0,
                        0.0,
                        0.0,
                    ),
                ),
                (
                    abs(raw.y),
                    Vec3(
                        0.0,
                        1.0
                        if raw.y >= 0
                        else -1.0,
                        0.0,
                    ),
                ),
                (
                    abs(raw.z),
                    Vec3(
                        0.0,
                        0.0,
                        1.0
                        if raw.z >= 0
                        else -1.0,
                    ),
                ),
            )
            normal_box_to_sphere = max(
                axes[
                    :2
                    if self.policy.dimensions
                    == 2
                    else 3
                ],
                key=lambda item:
                    item[0],
            )[1]
        else:
            normal_box_to_sphere = (
                delta / distance
            )
        normal = (
            normal_box_to_sphere
            * -1.0
            if sphere_first
            else normal_box_to_sphere
        )
        return Contact(
            (
                sphere.body_id
                if sphere_first
                else box.body_id
            ),
            (
                box.body_id
                if sphere_first
                else sphere.body_id
            ),
            normal,
            sphere.radius - distance,
            closest,
        )

    def _contact(
        self,
        a: RigidBody,
        b: RigidBody,
    ) -> Contact | None:
        if (
            a.shape
            is ShapeKind.AABB
            and b.shape
            is ShapeKind.AABB
        ):
            return self._aabb_contact(
                a,
                b,
            )
        if (
            a.shape
            is ShapeKind.SPHERE
            and b.shape
            is ShapeKind.SPHERE
        ):
            return self._sphere_contact(
                a,
                b,
            )
        if (
            a.shape
            is ShapeKind.SPHERE
        ):
            return self._sphere_aabb_contact(
                a,
                b,
                sphere_first=True,
            )
        return self._sphere_aabb_contact(
            b,
            a,
            sphere_first=False,
        )

    def _contacts(
        self,
    ) -> tuple[
        Contact,
        ...,
    ]:
        rows: list[
            Contact
        ] = []
        for first, second in (
            self._candidate_pairs()
        ):
            contact = self._contact(
                self._bodies[first],
                self._bodies[second],
            )
            if contact is not None:
                rows.append(contact)
        return tuple(
            sorted(
                rows,
                key=lambda value: (
                    value.a,
                    value.b,
                    value.normal.x,
                    value.normal.y,
                    value.normal.z,
                ),
            )
        )

    def _query_direction(
        self,
        direction: Vec3,
    ) -> Vec3:
        planar = (
            Vec3(
                direction.x,
                direction.y,
                0.0,
            )
            if self.policy.dimensions
            == 2
            else direction
        )
        length = planar.length()
        if length <= 1e-12:
            raise GameEngineLabError(
                "physics query direction must be non-zero"
            )
        return planar / length

    def _ray_aabb_hit(
        self,
        origin: Vec3,
        direction: Vec3,
        maximum: float,
        body: RigidBody,
    ) -> RayHit | None:
        lower, upper = (
            self._aabb(
                body
            )
        )
        axes = (
            (
                origin.x,
                direction.x,
                lower.x,
                upper.x,
                Vec3(
                    1.0,
                    0.0,
                    0.0,
                ),
            ),
            (
                origin.y,
                direction.y,
                lower.y,
                upper.y,
                Vec3(
                    0.0,
                    1.0,
                    0.0,
                ),
            ),
            (
                origin.z,
                direction.z,
                lower.z,
                upper.z,
                Vec3(
                    0.0,
                    0.0,
                    1.0,
                ),
            ),
        )
        if self.policy.dimensions == 2:
            axes = axes[:2]

        entry = 0.0
        exit_time = maximum
        normal = ZERO3
        inside = True
        for start, delta, minimum, upper_value, axis in axes:
            if (
                start < minimum
                or start > upper_value
            ):
                inside = False
            if abs(delta) <= 1e-15:
                if (
                    start < minimum
                    or start > upper_value
                ):
                    return None
                continue
            first = (
                minimum - start
            ) / delta
            second = (
                upper_value - start
            ) / delta
            near = min(
                first,
                second,
            )
            far = max(
                first,
                second,
            )
            if near > entry:
                entry = near
                normal = (
                    axis * -1.0
                    if delta > 0
                    else axis
                )
            exit_time = min(
                exit_time,
                far,
            )
            if entry > exit_time:
                return None

        if inside:
            entry = 0.0
            normal = direction * -1.0
        if (
            entry < 0.0
            or entry > maximum
            or exit_time < 0.0
        ):
            return None
        point = (
            origin
            + direction
            * entry
        )
        return RayHit(
            body.body_id,
            round(
                entry,
                12,
            ),
            self._quantize_vec(
                point
            ),
            self._quantize_vec(
                normal
            ),
            body.static,
            body.shape,
        )

    def _ray_sphere_hit(
        self,
        origin: Vec3,
        direction: Vec3,
        maximum: float,
        body: RigidBody,
    ) -> RayHit | None:
        relative = (
            origin
            - body.position
        )
        if self.policy.dimensions == 2:
            relative = Vec3(
                relative.x,
                relative.y,
                0.0,
            )
        c_value = (
            relative.length_sq()
            - body.radius
            * body.radius
        )
        inside = (
            c_value <= 0.0
        )
        if inside:
            distance = 0.0
        else:
            projection = (
                relative.dot(
                    direction
                )
            )
            discriminant = (
                projection
                * projection
                - c_value
            )
            if discriminant < 0.0:
                return None
            distance = (
                -projection
                - math.sqrt(
                    max(
                        0.0,
                        discriminant,
                    )
                )
            )
            if distance < 0.0:
                return None
        if distance > maximum:
            return None
        point = (
            origin
            + direction
            * distance
        )
        if inside:
            outward = (
                relative.normalized()
                if relative.length_sq()
                > 1e-24
                else direction
                * -1.0
            )
        else:
            outward = (
                point
                - body.position
            ).normalized()
        return RayHit(
            body.body_id,
            round(
                distance,
                12,
            ),
            self._quantize_vec(
                point
            ),
            self._quantize_vec(
                outward
            ),
            body.static,
            body.shape,
        )

    def raycast(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float,
        *,
        include_static: bool = True,
        include_dynamic: bool = True,
        exclude: tuple[str, ...] = (),
    ) -> tuple[
        RayHit,
        ...,
    ]:
        """Return every bounded ray hit ordered by distance then stable body id."""
        maximum = float(
            max_distance
        )
        if (
            not math.isfinite(
                maximum
            )
            or maximum <= 0.0
        ):
            raise GameEngineLabError(
                "physics ray distance must be finite and positive"
            )
        if (
            not include_static
            and not include_dynamic
        ):
            return ()
        if len(exclude) > 1024:
            raise GameEngineLabError(
                "physics ray exclusion set exceeds bounds"
            )
        excluded = frozenset(
            str(value)
            for value in exclude
        )
        ray_origin = (
            Vec3(
                origin.x,
                origin.y,
                0.0,
            )
            if self.policy.dimensions
            == 2
            else origin
        )
        ray_direction = (
            self._query_direction(
                direction
            )
        )
        hits: list[
            RayHit
        ] = []
        for key in sorted(
            self._bodies
        ):
            if key in excluded:
                continue
            body = self._bodies[
                key
            ]
            if (
                body.static
                and not include_static
            ):
                continue
            if (
                not body.static
                and not include_dynamic
            ):
                continue
            hit = (
                self._ray_sphere_hit(
                    ray_origin,
                    ray_direction,
                    maximum,
                    body,
                )
                if body.shape
                is ShapeKind.SPHERE
                else self._ray_aabb_hit(
                    ray_origin,
                    ray_direction,
                    maximum,
                    body,
                )
            )
            if hit is not None:
                hits.append(
                    hit
                )
        hits.sort(
            key=lambda value: (
                value.distance,
                value.body_id,
            )
        )
        return tuple(
            hits
        )

    def raycast_first(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float,
        *,
        include_static: bool = True,
        include_dynamic: bool = True,
        exclude: tuple[str, ...] = (),
    ) -> RayHit | None:
        hits = self.raycast(
            origin,
            direction,
            max_distance,
            include_static=
                include_static,
            include_dynamic=
                include_dynamic,
            exclude=exclude,
        )
        return (
            hits[0]
            if hits
            else None
        )

    def overlap_aabb(
        self,
        center: Vec3,
        half_extent: Vec3,
        *,
        include_static: bool = True,
        include_dynamic: bool = True,
    ) -> tuple[str, ...]:
        """Return exact bodies overlapping an axis-aligned query box."""
        if (
            half_extent.x <= 0
            or half_extent.y <= 0
            or (
                self.policy.dimensions
                == 3
                and half_extent.z
                <= 0
            )
        ):
            raise GameEngineLabError(
                "physics overlap extents must be positive"
            )
        query_center = (
            Vec3(
                center.x,
                center.y,
                0.0,
            )
            if self.policy.dimensions
            == 2
            else center
        )
        query_extent = (
            Vec3(
                half_extent.x,
                half_extent.y,
                0.0,
            )
            if self.policy.dimensions
            == 2
            else half_extent
        )
        lower = (
            query_center
            - query_extent
        )
        upper = (
            query_center
            + query_extent
        )
        result: list[str] = []
        for key in sorted(
            self._bodies
        ):
            body = self._bodies[
                key
            ]
            if (
                body.static
                and not include_static
            ):
                continue
            if (
                not body.static
                and not include_dynamic
            ):
                continue
            if body.shape is ShapeKind.AABB:
                body_lower, body_upper = (
                    self._aabb(
                        body
                    )
                )
                overlaps = (
                    body_upper.x
                    >= lower.x
                    and body_lower.x
                    <= upper.x
                    and body_upper.y
                    >= lower.y
                    and body_lower.y
                    <= upper.y
                    and (
                        self.policy.dimensions
                        == 2
                        or (
                            body_upper.z
                            >= lower.z
                            and body_lower.z
                            <= upper.z
                        )
                    )
                )
            else:
                closest = Vec3(
                    min(
                        upper.x,
                        max(
                            lower.x,
                            body.position.x,
                        ),
                    ),
                    min(
                        upper.y,
                        max(
                            lower.y,
                            body.position.y,
                        ),
                    ),
                    (
                        min(
                            upper.z,
                            max(
                                lower.z,
                                body.position.z,
                            ),
                        )
                        if self.policy.dimensions
                        == 3
                        else 0.0
                    ),
                )
                delta = (
                    body.position
                    - closest
                )
                if self.policy.dimensions == 2:
                    delta = Vec3(
                        delta.x,
                        delta.y,
                        0.0,
                    )
                overlaps = (
                    delta.length_sq()
                    <= body.radius
                    * body.radius
                )
            if overlaps:
                result.append(
                    key
                )
        return tuple(
            result
        )

    def overlap_sphere(
        self,
        center: Vec3,
        radius: float,
        *,
        include_static: bool = True,
        include_dynamic: bool = True,
    ) -> tuple[str, ...]:
        """Return exact bodies overlapping a bounded spherical/circular query."""
        radius_value = float(
            radius
        )
        if (
            not math.isfinite(
                radius_value
            )
            or radius_value <= 0.0
        ):
            raise GameEngineLabError(
                "physics overlap radius must be finite and positive"
            )
        query_center = (
            Vec3(
                center.x,
                center.y,
                0.0,
            )
            if self.policy.dimensions
            == 2
            else center
        )
        result: list[str] = []
        for key in sorted(
            self._bodies
        ):
            body = self._bodies[
                key
            ]
            if (
                body.static
                and not include_static
            ):
                continue
            if (
                not body.static
                and not include_dynamic
            ):
                continue
            if body.shape is ShapeKind.SPHERE:
                delta = (
                    body.position
                    - query_center
                )
                if self.policy.dimensions == 2:
                    delta = Vec3(
                        delta.x,
                        delta.y,
                        0.0,
                    )
                overlaps = (
                    delta.length_sq()
                    <= (
                        body.radius
                        + radius_value
                    )
                    ** 2
                )
            else:
                lower, upper = (
                    self._aabb(
                        body
                    )
                )
                closest = Vec3(
                    min(
                        upper.x,
                        max(
                            lower.x,
                            query_center.x,
                        ),
                    ),
                    min(
                        upper.y,
                        max(
                            lower.y,
                            query_center.y,
                        ),
                    ),
                    (
                        min(
                            upper.z,
                            max(
                                lower.z,
                                query_center.z,
                            ),
                        )
                        if self.policy.dimensions
                        == 3
                        else 0.0
                    ),
                )
                delta = (
                    query_center
                    - closest
                )
                if self.policy.dimensions == 2:
                    delta = Vec3(
                        delta.x,
                        delta.y,
                        0.0,
                    )
                overlaps = (
                    delta.length_sq()
                    <= radius_value
                    * radius_value
                )
            if overlaps:
                result.append(
                    key
                )
        return tuple(
            result
        )

    def _sweep_body_static(
        self,
        moving: RigidBody,
        obstacle: RigidBody,
        displacement: Vec3,
    ) -> SweepHit | None:
        """Sweep one dynamic extent against one static AABB via Minkowski slabs."""
        if (
            moving.static
            or not obstacle.static
            or obstacle.shape
            is not ShapeKind.AABB
        ):
            return None
        if (
            displacement.length_sq()
            <= 1e-24
        ):
            return None
        # Existing overlap belongs to the discrete manifold path.
        if (
            self._contact(
                moving,
                obstacle,
            )
            is not None
        ):
            return None

        moving_extent = (
            self._extent(
                moving
            )
        )
        lower = (
            obstacle.position
            - obstacle.half_extent
            - moving_extent
        )
        upper = (
            obstacle.position
            + obstacle.half_extent
            + moving_extent
        )
        axes = (
            (
                moving.position.x,
                displacement.x,
                lower.x,
                upper.x,
                Vec3(
                    1.0,
                    0.0,
                    0.0,
                ),
            ),
            (
                moving.position.y,
                displacement.y,
                lower.y,
                upper.y,
                Vec3(
                    0.0,
                    1.0,
                    0.0,
                ),
            ),
            (
                moving.position.z,
                displacement.z,
                lower.z,
                upper.z,
                Vec3(
                    0.0,
                    0.0,
                    1.0,
                ),
            ),
        )
        if self.policy.dimensions == 2:
            axes = axes[:2]

        entry = 0.0
        exit_time = 1.0
        normal = ZERO3
        for start, delta, minimum, maximum, axis in axes:
            if abs(delta) <= 1e-15:
                if (
                    start < minimum
                    or start > maximum
                ):
                    return None
                continue
            first = (
                minimum - start
            ) / delta
            second = (
                maximum - start
            ) / delta
            near = min(
                first,
                second,
            )
            far = max(
                first,
                second,
            )
            if (
                near > entry
                + 1e-15
            ):
                entry = near
                normal = (
                    axis
                    if delta > 0
                    else axis * -1.0
                )
            exit_time = min(
                exit_time,
                far,
            )
            if (
                entry
                > exit_time
                + 1e-15
            ):
                return None

        if (
            entry < 0.0
            or entry > 1.0
            or exit_time < 0.0
            or normal.length_sq()
            <= 1e-24
        ):
            return None

        center = (
            moving.position
            + displacement
            * entry
        )
        support = Vec3(
            moving_extent.x
            * normal.x,
            moving_extent.y
            * normal.y,
            (
                moving_extent.z
                * normal.z
                if self.policy.dimensions
                == 3
                else 0.0
            ),
        )
        return SweepHit(
            moving.body_id,
            obstacle.body_id,
            round(
                entry,
                15,
            ),
            normal,
            self._quantize_vec(
                center + support
            ),
        )

    def sweep_static(
        self,
        body_id: str,
        displacement: Vec3,
    ) -> SweepHit | None:
        """Return deterministic earliest dynamic-to-static time of impact."""
        try:
            moving = self._bodies[
                body_id
            ]
        except KeyError as exc:
            raise GameEngineLabError(
                "unknown physics body"
            ) from exc
        if moving.static:
            return None
        candidates: list[
            SweepHit
        ] = []
        for key in sorted(
            self._bodies
        ):
            obstacle = self._bodies[
                key
            ]
            if (
                not obstacle.static
                or key
                == body_id
            ):
                continue
            hit = self._sweep_body_static(
                moving,
                obstacle,
                displacement,
            )
            if hit is not None:
                candidates.append(
                    hit
                )
        if not candidates:
            return None
        candidates.sort(
            key=lambda hit: (
                hit.toi,
                hit.other,
                hit.normal.x,
                hit.normal.y,
                hit.normal.z,
            )
        )
        return candidates[0]

    def _sweep_pair(
        self,
        a: RigidBody,
        b: RigidBody,
        dt: float,
    ) -> SweepHit | None:
        """Return normalized TOI for a non-overlapping pair under relative motion."""
        if (
            dt <= 0.0
            or (
                a.static
                and b.static
            )
            or self._contact(
                a,
                b,
            )
            is not None
        ):
            return None

        a_velocity = (
            ZERO3
            if (
                a.static
                or a.sleeping
            )
            else a.velocity
        )
        b_velocity = (
            ZERO3
            if (
                b.static
                or b.sleeping
            )
            else b.velocity
        )
        relative_velocity = (
            b_velocity
            - a_velocity
        )
        if (
            relative_velocity.length_sq()
            <= 1e-24
        ):
            return None

        if (
            a.shape
            is ShapeKind.SPHERE
            and b.shape
            is ShapeKind.SPHERE
        ):
            relative_position = (
                b.position
                - a.position
            )
            relative_displacement = (
                relative_velocity
                * dt
            )
            radius = (
                a.radius
                + b.radius
            )
            quadratic_a = (
                relative_displacement.length_sq()
            )
            quadratic_b = (
                2.0
                * relative_position.dot(
                    relative_displacement
                )
            )
            quadratic_c = (
                relative_position.length_sq()
                - radius * radius
            )
            if quadratic_a <= 1e-24:
                return None
            discriminant = (
                quadratic_b
                * quadratic_b
                - 4.0
                * quadratic_a
                * quadratic_c
            )
            if discriminant < 0.0:
                return None
            root = math.sqrt(
                max(
                    0.0,
                    discriminant,
                )
            )
            toi = (
                -quadratic_b
                - root
            ) / (
                2.0
                * quadratic_a
            )
            if (
                toi < 0.0
                or toi > 1.0
            ):
                return None
            separation = (
                relative_position
                + relative_displacement
                * toi
            )
            distance = (
                separation.length()
            )
            if distance <= 1e-12:
                return None
            normal = (
                separation
                / distance
            )
        else:
            a_extent = (
                self._extent(
                    a
                )
            )
            b_extent = (
                self._extent(
                    b
                )
            )
            combined = (
                a_extent
                + b_extent
            )
            relative_position = (
                a.position
                - b.position
            )
            relative_displacement = (
                (
                    a_velocity
                    - b_velocity
                )
                * dt
            )
            axes = [
                (
                    relative_position.x,
                    relative_displacement.x,
                    combined.x,
                    Vec3(
                        1.0,
                        0.0,
                        0.0,
                    ),
                ),
                (
                    relative_position.y,
                    relative_displacement.y,
                    combined.y,
                    Vec3(
                        0.0,
                        1.0,
                        0.0,
                    ),
                ),
            ]
            if (
                self.policy.dimensions
                == 3
            ):
                axes.append(
                    (
                        relative_position.z,
                        relative_displacement.z,
                        combined.z,
                        Vec3(
                            0.0,
                            0.0,
                            1.0,
                        ),
                    )
                )
            entry = 0.0
            exit_time = 1.0
            normal = ZERO3
            for (
                position,
                displacement,
                half_extent,
                axis,
            ) in axes:
                if (
                    abs(
                        displacement
                    )
                    <= 1e-15
                ):
                    if (
                        abs(
                            position
                        )
                        > half_extent
                    ):
                        return None
                    continue
                first = (
                    -half_extent
                    - position
                ) / displacement
                second = (
                    half_extent
                    - position
                ) / displacement
                near = min(
                    first,
                    second,
                )
                far = max(
                    first,
                    second,
                )
                if (
                    near
                    > entry + 1e-15
                ):
                    entry = near
                    normal = (
                        axis
                        if displacement > 0.0
                        else axis * -1.0
                    )
                exit_time = min(
                    exit_time,
                    far,
                )
                if (
                    entry
                    > exit_time + 1e-15
                ):
                    return None
            if (
                entry < 0.0
                or entry > 1.0
                or exit_time < 0.0
                or normal.length_sq()
                <= 1e-24
            ):
                return None
            toi = entry

        if (
            relative_velocity.dot(
                normal
            )
            >= -1e-12
        ):
            return None

        a_at_hit = (
            a.position
            + a_velocity
            * (
                dt * toi
            )
        )
        extent = (
            self._extent(
                a
            )
        )
        if (
            a.shape
            is ShapeKind.SPHERE
        ):
            support = (
                normal
                * a.radius
            )
        else:
            support = Vec3(
                extent.x
                * normal.x,
                extent.y
                * normal.y,
                (
                    extent.z
                    * normal.z
                    if self.policy.dimensions
                    == 3
                    else 0.0
                ),
            )
        return SweepHit(
            a.body_id,
            b.body_id,
            round(
                toi,
                15,
            ),
            normal,
            self._quantize_vec(
                a_at_hit
                + support
            ),
        )

    def _swept_pair_candidates(
        self,
        dt: float,
    ) -> tuple[
        tuple[str, str],
        ...,
    ]:
        bounds: dict[
            str,
            tuple[Vec3, Vec3],
        ] = {}
        for body in self.bodies:
            extent = (
                self._extent(
                    body
                )
            )
            velocity = (
                ZERO3
                if (
                    body.static
                    or body.sleeping
                )
                else body.velocity
            )
            end = (
                body.position
                + velocity
                * dt
            )
            lower = Vec3(
                min(
                    body.position.x,
                    end.x,
                )
                - extent.x,
                min(
                    body.position.y,
                    end.y,
                )
                - extent.y,
                (
                    min(
                        body.position.z,
                        end.z,
                    )
                    - extent.z
                    if self.policy.dimensions
                    == 3
                    else 0.0
                ),
            )
            upper = Vec3(
                max(
                    body.position.x,
                    end.x,
                )
                + extent.x,
                max(
                    body.position.y,
                    end.y,
                )
                + extent.y,
                (
                    max(
                        body.position.z,
                        end.z,
                    )
                    + extent.z
                    if self.policy.dimensions
                    == 3
                    else 0.0
                ),
            )
            bounds[
                body.body_id
            ] = (
                lower,
                upper,
            )

        ordered = sorted(
            bounds,
            key=lambda key: (
                bounds[key][0].x,
                key,
            ),
        )
        pairs: list[
            tuple[str, str]
        ] = []
        for index, first in enumerate(
            ordered
        ):
            a = self._bodies[
                first
            ]
            amin, amax = bounds[
                first
            ]
            for second in ordered[
                index + 1:
            ]:
                bmin, bmax = bounds[
                    second
                ]
                if (
                    bmin.x
                    > amax.x
                ):
                    break
                b = self._bodies[
                    second
                ]
                if (
                    a.static
                    and b.static
                ):
                    continue
                if (
                    bmin.y
                    > amax.y
                    or amin.y
                    > bmax.y
                ):
                    continue
                if (
                    self.policy.dimensions
                    == 3
                    and (
                        bmin.z
                        > amax.z
                        or amin.z
                        > bmax.z
                    )
                ):
                    continue
                pairs.append(
                    tuple(
                        sorted(
                            (
                                first,
                                second,
                            )
                        )
                    )
                )
        return tuple(
            sorted(
                set(
                    pairs
                )
            )
        )

    def _earliest_pair_sweep(
        self,
        dt: float,
    ) -> SweepHit | None:
        hits: list[
            SweepHit
        ] = []
        for first, second in (
            self._swept_pair_candidates(
                dt
            )
        ):
            a = self._bodies[
                first
            ]
            b = self._bodies[
                second
            ]
            hit = self._sweep_pair(
                a,
                b,
                dt,
            )
            if hit is not None:
                hits.append(
                    hit
                )
        if not hits:
            return None
        return min(
            hits,
            key=lambda hit: (
                hit.toi,
                hit.moving,
                hit.other,
                hit.normal.x,
                hit.normal.y,
                hit.normal.z,
            ),
        )

    def _integrate_ccd_velocities(
        self,
        dt: float,
    ) -> None:
        for body in self.bodies:
            if (
                body.static
                or body.sleeping
            ):
                continue
            acceleration = (
                self.gravity
                + body.force
                * body.inv_mass
            )
            body.velocity = (
                self._quantize_vec(
                    (
                        body.velocity
                        + acceleration
                        * dt
                    )
                    * body.linear_damping
                )
            )
            if self.policy.rotation:
                angular_acceleration = (
                    body.torque
                    * body.inv_inertia
                )
                body.angular_velocity = (
                    self._quantize_vec(
                        (
                            body.angular_velocity
                            + angular_acceleration
                            * dt
                        )
                        * body.angular_damping
                    )
                )
                rotation_step = (
                    Quat.from_angular_step(
                        body.angular_velocity,
                        dt,
                    )
                )
                body.orientation = (
                    (
                        rotation_step
                        * body.orientation
                    ).normalized()
                )

    def _advance_ccd_world(
        self,
        dt: float,
    ) -> None:
        if dt <= 0.0:
            return
        for body in self.bodies:
            if (
                body.static
                or body.sleeping
            ):
                continue
            body.position = (
                self._quantize_vec(
                    body.position
                    + body.velocity
                    * dt
                )
            )
            self._solve_bounds(
                body
            )

    def _integrate_world_ccd(
        self,
        dt: float,
    ) -> tuple[
        Contact,
        ...,
    ]:
        """Advance all bodies against the globally earliest swept TOI."""
        self._integrate_ccd_velocities(
            dt
        )
        remaining = dt
        contacts: list[
            Contact
        ] = []
        impact_budget = (
            self.policy.max_toi_events
        )
        epsilon = max(
            1e-12,
            dt * 1e-9,
        )
        for _impact in range(
            impact_budget
        ):
            if remaining <= epsilon:
                break
            hit = (
                self._earliest_pair_sweep(
                    remaining
                )
            )
            if hit is None:
                self._advance_ccd_world(
                    remaining
                )
                remaining = 0.0
                break

            safe_fraction = max(
                0.0,
                hit.toi
                - 1e-9,
            )
            travel = (
                remaining
                * safe_fraction
            )
            if travel > 0.0:
                self._advance_ccd_world(
                    travel
                )
            remaining *= max(
                0.0,
                1.0
                - safe_fraction,
            )

            contact = Contact(
                hit.moving,
                hit.other,
                hit.normal,
                0.0,
                hit.point,
            )
            before_speed = (
                (
                    self._bodies[
                        hit.other
                    ].velocity
                    - self._bodies[
                        hit.moving
                    ].velocity
                ).dot(
                    hit.normal
                )
            )
            self._apply_impulse(
                contact
            )
            contacts.append(
                contact
            )
            after_speed = (
                (
                    self._bodies[
                        hit.other
                    ].velocity
                    - self._bodies[
                        hit.moving
                    ].velocity
                ).dot(
                    hit.normal
                )
            )
            if (
                hit.toi <= 1e-12
                and abs(
                    after_speed
                    - before_speed
                )
                <= 1e-12
            ):
                break

        if remaining > epsilon:
            self._advance_ccd_world(
                remaining
            )
        return tuple(
            contacts
        )

    def _integrate_body(
        self,
        body: RigidBody,
        dt: float,
    ) -> None:
        if (
            body.static
            or body.sleeping
        ):
            return
        acceleration = (
            self.gravity
            + body.force
            * body.inv_mass
        )
        velocity = (
            body.velocity
            + acceleration
            * dt
        ) * body.linear_damping
        position = (
            body.position
            + velocity
            * dt
        )
        body.velocity = (
            self._quantize_vec(
                velocity
            )
        )
        body.position = (
            self._quantize_vec(
                position
            )
        )

        if self.policy.rotation:
            angular_acceleration = (
                body.torque
                * body.inv_inertia
            )
            angular_velocity = (
                body.angular_velocity
                + angular_acceleration
                * dt
            ) * body.angular_damping
            body.angular_velocity = (
                self._quantize_vec(
                    angular_velocity
                )
            )
            step = (
                Quat.from_angular_step(
                    body.angular_velocity,
                    dt,
                )
            )
            body.orientation = (
                (
                    step
                    * body.orientation
                ).normalized()
            )

    def _solve_bounds(
        self,
        body: RigidBody,
    ) -> None:
        if body.static:
            return
        extent = self._extent(
            body
        )
        axes = [
            (
                "x",
                extent.x,
                self.bounds.x,
            ),
            (
                "y",
                extent.y,
                self.bounds.y,
            ),
        ]
        if self.policy.dimensions == 3:
            axes.append(
                (
                    "z",
                    extent.z,
                    self.bounds.z,
                )
            )
        pos = {
            "x": body.position.x,
            "y": body.position.y,
            "z": body.position.z,
        }
        vel = {
            "x": body.velocity.x,
            "y": body.velocity.y,
            "z": body.velocity.z,
        }
        changed = False
        for axis, half, maximum in axes:
            if pos[axis] - half < 0:
                pos[axis] = half
                vel[axis] = abs(
                    vel[axis]
                ) * body.restitution
                changed = True
            elif (
                pos[axis] + half
                > maximum
            ):
                pos[axis] = (
                    maximum
                    - half
                )
                vel[axis] = -abs(
                    vel[axis]
                ) * body.restitution
                changed = True
        if changed:
            body.position = (
                self._quantize_vec(
                    Vec3(
                        pos["x"],
                        pos["y"],
                        pos["z"],
                    )
                )
            )
            body.velocity = (
                self._quantize_vec(
                    Vec3(
                        vel["x"],
                        vel["y"],
                        vel["z"],
                    )
                )
            )
            body.wake()

    def _apply_impulse(
        self,
        contact: Contact,
    ) -> None:
        a = self._bodies[
            contact.a
        ]
        b = self._bodies[
            contact.b
        ]
        total_inv_mass = (
            a.inv_mass
            + b.inv_mass
        )
        if total_inv_mass <= 0:
            return

        ra = (
            contact.point
            - a.position
        )
        rb = (
            contact.point
            - b.position
        )

        def point_velocity(
            body: RigidBody,
            arm: Vec3,
        ) -> Vec3:
            if (
                not self.policy.rotation
                or body.static
            ):
                return body.velocity
            return (
                body.velocity
                + body.angular_velocity.cross(
                    arm
                )
            )

        def effective_mass(
            direction: Vec3,
        ) -> float:
            value = (
                total_inv_mass
            )
            if self.policy.rotation:
                if not a.static:
                    angular_a = (
                        ra.cross(
                            direction
                        )
                        * a.inv_inertia
                    ).cross(
                        ra
                    )
                    value += (
                        angular_a.dot(
                            direction
                        )
                    )
                if not b.static:
                    angular_b = (
                        rb.cross(
                            direction
                        )
                        * b.inv_inertia
                    ).cross(
                        rb
                    )
                    value += (
                        angular_b.dot(
                            direction
                        )
                    )
            return max(
                value,
                1e-12,
            )

        def apply_pair_impulse(
            impulse: Vec3,
        ) -> None:
            if not a.static:
                a.velocity = (
                    self._quantize_vec(
                        a.velocity
                        - impulse
                        * a.inv_mass
                    )
                )
                if self.policy.rotation:
                    a.angular_velocity = (
                        self._quantize_vec(
                            a.angular_velocity
                            - ra.cross(
                                impulse
                            )
                            * a.inv_inertia
                        )
                    )
                a.wake()
            if not b.static:
                b.velocity = (
                    self._quantize_vec(
                        b.velocity
                        + impulse
                        * b.inv_mass
                    )
                )
                if self.policy.rotation:
                    b.angular_velocity = (
                        self._quantize_vec(
                            b.angular_velocity
                            + rb.cross(
                                impulse
                            )
                            * b.inv_inertia
                        )
                    )
                b.wake()

        relative = (
            point_velocity(
                b,
                rb,
            )
            - point_velocity(
                a,
                ra,
            )
        )
        normal_speed = (
            relative.dot(
                contact.normal
            )
        )
        restitution = min(
            a.restitution,
            b.restitution,
        )
        normal_impulse = 0.0
        if normal_speed < 0:
            normal_impulse = (
                -(1.0 + restitution)
                * normal_speed
                / effective_mass(
                    contact.normal
                )
            )
            apply_pair_impulse(
                contact.normal
                * normal_impulse
            )

        if (
            self.policy.friction
            and normal_impulse > 0
        ):
            updated_relative = (
                point_velocity(
                    b,
                    rb,
                )
                - point_velocity(
                    a,
                    ra,
                )
            )
            tangent = (
                updated_relative
                - contact.normal
                * updated_relative.dot(
                    contact.normal
                )
            )
            tangent_length = (
                tangent.length()
            )
            if tangent_length > 1e-12:
                direction = (
                    tangent
                    / tangent_length
                )
                friction_impulse = (
                    -updated_relative.dot(
                        direction
                    )
                    / effective_mass(
                        direction
                    )
                )
                coefficient = math.sqrt(
                    a.friction
                    * b.friction
                )
                limit = (
                    normal_impulse
                    * coefficient
                )
                friction_impulse = max(
                    -limit,
                    min(
                        limit,
                        friction_impulse,
                    ),
                )
                apply_pair_impulse(
                    direction
                    * friction_impulse
                )

    def _correct_contact(
        self,
        contact: Contact,
    ) -> None:
        a = self._bodies[
            contact.a
        ]
        b = self._bodies[
            contact.b
        ]
        total_inv_mass = (
            a.inv_mass
            + b.inv_mass
        )
        if total_inv_mass <= 0:
            return
        slop = 0.001
        depth = max(
            0.0,
            contact.penetration
            - slop,
        )
        if depth <= 0:
            return
        percent = 0.8
        correction = (
            contact.normal
            * (
                depth
                * percent
                / total_inv_mass
            )
        )
        if not a.static:
            a.position = (
                self._quantize_vec(
                    a.position
                    - correction
                    * a.inv_mass
                )
            )
        if not b.static:
            b.position = (
                self._quantize_vec(
                    b.position
                    + correction
                    * b.inv_mass
                )
            )

    def _solve_constraint(
        self,
        constraint: DistanceConstraint,
    ) -> None:
        a = self._bodies[
            constraint.a
        ]
        b = self._bodies[
            constraint.b
        ]
        delta = (
            b.position
            - a.position
        )
        distance = delta.length()
        if distance <= 1e-12:
            return
        total_inv_mass = (
            a.inv_mass
            + b.inv_mass
        )
        if total_inv_mass <= 0:
            return
        error = (
            distance
            - constraint.rest_length
        )
        correction = (
            delta
            / distance
            * (
                error
                * constraint.stiffness
                / total_inv_mass
            )
        )
        if not a.static:
            a.position = (
                self._quantize_vec(
                    a.position
                    + correction
                    * a.inv_mass
                )
            )
            a.wake()
        if not b.static:
            b.position = (
                self._quantize_vec(
                    b.position
                    - correction
                    * b.inv_mass
                )
            )
            b.wake()

    def _update_sleeping(
        self,
        body: RigidBody,
    ) -> None:
        if (
            body.static
            or not self.policy.sleeping
        ):
            return
        motion = (
            body.velocity.length_sq()
            + body.angular_velocity.length_sq()
        )
        threshold_sq = (
            self.policy.sleep_threshold
            * self.policy.sleep_threshold
        )
        if motion <= threshold_sq:
            body.sleep_counter += 1
            if (
                body.sleep_counter
                >= self.policy.sleep_frames
            ):
                body.sleeping = True
                body.velocity = ZERO3
                body.angular_velocity = ZERO3
        else:
            body.sleep_counter = 0
            body.sleeping = False

    def _clear_accumulators(
        self,
    ) -> None:
        for body in self.bodies:
            body.force = ZERO3
            body.torque = ZERO3

    def step(
        self,
        count: int = 1,
    ) -> None:
        if (
            type(count) is not int
            or not 1 <= count <= 100_000
        ):
            raise GameEngineLabError(
                "physics step count outside [1, 100000]"
            )
        base_dt = (
            1.0
            / engine_era_profile(
                self.policy.era
            ).tick_hz
        )
        for _ in range(count):
            substeps = (
                self.policy.substeps
                if self.policy.conservative_ccd
                else 1
            )
            dt = (
                base_dt
                / substeps
            )
            tick_contact_rows: list[
                Contact
            ] = []
            for _substep in range(
                substeps
            ):
                if (
                    self.policy.conservative_ccd
                ):
                    ccd_contacts = list(
                        self._integrate_world_ccd(
                            dt
                        )
                    )
                else:
                    ccd_contacts: list[
                        Contact
                    ] = []
                    for body in self.bodies:
                        self._integrate_body(
                            body,
                            dt,
                        )
                        self._solve_bounds(
                            body
                        )
                contacts = (
                    self._contacts()
                )
                tick_contact_rows.extend(
                    (
                        *ccd_contacts,
                        *contacts,
                    )
                )
                for _iteration in range(
                    self.policy.solver_iterations
                ):
                    for contact in contacts:
                        self._apply_impulse(
                            contact
                        )
                    for constraint in (
                        self.constraints
                    ):
                        self._solve_constraint(
                            constraint
                        )
                for contact in contacts:
                    self._correct_contact(
                        contact
                    )
            self.last_contacts = tuple(
                sorted(
                    tick_contact_rows,
                    key=lambda value: (
                        value.a,
                        value.b,
                        value.normal.x,
                        value.normal.y,
                        value.normal.z,
                        value.penetration,
                        value.point.x,
                        value.point.y,
                        value.point.z,
                    ),
                )
            )
            for body in self.bodies:
                self._update_sleeping(
                    body
                )
            self._clear_accumulators()
            self.tick += 1

    def snapshot(
        self,
    ) -> "PhysicsSnapshot":
        rows = tuple(
            (
                body.body_id,
                _body_state(
                    body
                ),
            )
            for body in self.bodies
        )
        constraints = tuple(
            (
                constraint.constraint_id,
                constraint.a,
                constraint.b,
                constraint.rest_length,
                constraint.stiffness,
            )
            for constraint
            in self.constraints
        )
        payload = {
            "era": self.policy.era.value,
            "tick": self.tick,
            "body_state": rows,
            "constraint_state": constraints,
        }
        return PhysicsSnapshot(
            self.policy.era,
            self.tick,
            rows,
            constraints,
            _digest(payload),
        )

    def restore(
        self,
        snapshot: "PhysicsSnapshot",
    ) -> None:
        if (
            snapshot.era
            is not self.policy.era
        ):
            raise GameEngineLabError(
                "physics snapshot era mismatch"
            )
        payload = {
            "era": snapshot.era.value,
            "tick": snapshot.tick,
            "body_state":
                snapshot.body_state,
            "constraint_state":
                snapshot.constraint_state,
        }
        if (
            _digest(payload)
            != snapshot.digest
        ):
            raise GameEngineLabError(
                "physics snapshot digest mismatch"
            )
        state = dict(
            snapshot.body_state
        )
        expected_constraints = tuple(
            (
                constraint.constraint_id,
                constraint.a,
                constraint.b,
                constraint.rest_length,
                constraint.stiffness,
            )
            for constraint
            in self.constraints
        )
        if (
            snapshot.constraint_state
            != expected_constraints
        ):
            raise GameEngineLabError(
                "physics snapshot constraint set mismatch"
            )
        if set(state) != set(
            self._bodies
        ):
            raise GameEngineLabError(
                "physics snapshot body set mismatch"
            )
        for key in sorted(state):
            values = state[key]
            body = self._bodies[key]
            if (
                values[0]
                != body.shape.value
            ):
                raise GameEngineLabError(
                    "physics snapshot shape mismatch"
                )
            body.position = Vec3(
                float(values[1]),
                float(values[2]),
                float(values[3]),
            )
            body.velocity = Vec3(
                float(values[4]),
                float(values[5]),
                float(values[6]),
            )
            body.orientation = Quat(
                float(values[7]),
                float(values[8]),
                float(values[9]),
                float(values[10]),
            )
            body.angular_velocity = Vec3(
                float(values[11]),
                float(values[12]),
                float(values[13]),
            )
            body.force = Vec3(
                float(values[14]),
                float(values[15]),
                float(values[16]),
            )
            body.torque = Vec3(
                float(values[17]),
                float(values[18]),
                float(values[19]),
            )
            body.sleeping = bool(
                values[20]
            )
            body.sleep_counter = int(
                values[21]
            )
        self.tick = (
            snapshot.tick
        )
        self.last_contacts = ()

    def fingerprint(
        self,
    ) -> str:
        return self.snapshot().digest


@dataclass(frozen=True, slots=True)
class BodyRecipe:
    body_id: str
    shape: ShapeKind
    position: Vec3
    velocity: Vec3 = ZERO3
    half_extent: Vec3 = Vec3(
        0.5,
        0.5,
        0.5,
    )
    radius: float = 0.5
    mass: float = 1.0
    restitution: float = 0.2
    friction: float = 0.5
    static: bool = False
    angular_velocity: Vec3 = ZERO3

    def __post_init__(self) -> None:
        if not self.body_id:
            raise GameEngineLabError(
                "body recipe id required"
            )
        if not isinstance(
            self.shape,
            ShapeKind,
        ):
            object.__setattr__(
                self,
                "shape",
                ShapeKind(
                    str(self.shape)
                ),
            )


@dataclass(frozen=True, slots=True)
class ConstraintRecipe:
    constraint_id: str
    a: str
    b: str
    rest_length: float
    stiffness: float = 1.0


@dataclass(frozen=True, slots=True)
class PhysicsSceneSource:
    bounds: Vec3
    gravity: Vec3
    bodies: tuple[BodyRecipe, ...]
    constraints: tuple[
        ConstraintRecipe,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        if not self.bodies:
            raise GameEngineLabError(
                "physics scene requires bodies"
            )


def _recipe_document(
    recipe: BodyRecipe,
) -> dict[str, object]:
    return {
        "body_id": recipe.body_id,
        "shape": recipe.shape.value,
        "position": [
            recipe.position.x,
            recipe.position.y,
            recipe.position.z,
        ],
        "velocity": [
            recipe.velocity.x,
            recipe.velocity.y,
            recipe.velocity.z,
        ],
        "half_extent": [
            recipe.half_extent.x,
            recipe.half_extent.y,
            recipe.half_extent.z,
        ],
        "radius": recipe.radius,
        "mass": recipe.mass,
        "restitution":
            recipe.restitution,
        "friction": recipe.friction,
        "static": recipe.static,
        "angular_velocity": [
            recipe.angular_velocity.x,
            recipe.angular_velocity.y,
            recipe.angular_velocity.z,
        ],
    }


def _constraint_document(
    recipe: ConstraintRecipe,
) -> dict[str, object]:
    return {
        "constraint_id":
            recipe.constraint_id,
        "a": recipe.a,
        "b": recipe.b,
        "rest_length":
            recipe.rest_length,
        "stiffness":
            recipe.stiffness,
    }


def _scene_document(
    source: PhysicsSceneSource,
) -> dict[str, object]:
    return {
        "bounds": [
            source.bounds.x,
            source.bounds.y,
            source.bounds.z,
        ],
        "gravity": [
            source.gravity.x,
            source.gravity.y,
            source.gravity.z,
        ],
        "bodies": [
            _recipe_document(
                recipe
            )
            for recipe
            in source.bodies
        ],
        "constraints": [
            _constraint_document(
                recipe
            )
            for recipe
            in source.constraints
        ],
    }


def validate_physics_source(
    era: EngineEra | str,
    source: PhysicsSceneSource,
) -> None:
    policy = physics_policy(
        era
    )
    if (
        len(source.bodies)
        > policy.max_bodies
    ):
        raise GameEngineLabError(
            "physics source body budget exceeded"
        )
    if (
        source.constraints
        and not policy.constraints
    ):
        raise GameEngineLabError(
            "constraints unavailable in this engine era"
        )
    if (
        len(source.constraints)
        > policy.max_constraints
    ):
        raise GameEngineLabError(
            "physics source constraint budget exceeded"
        )
    ids = [
        recipe.body_id
        for recipe in source.bodies
    ]
    if len(ids) != len(set(ids)):
        raise GameEngineLabError(
            "physics body recipe ids must be unique"
        )
    constraint_ids = [
        recipe.constraint_id
        for recipe in source.constraints
    ]
    if (
        len(constraint_ids)
        != len(set(constraint_ids))
    ):
        raise GameEngineLabError(
            "constraint recipe ids must be unique"
        )
    if (
        source.bounds.x <= 0
        or source.bounds.y <= 0
        or source.bounds.z <= 0
    ):
        raise GameEngineLabError(
            "physics source bounds must be positive"
        )
    for recipe in source.bodies:
        if (
            recipe.shape
            not in policy.shapes
        ):
            raise GameEngineLabError(
                f"{recipe.shape.value} unavailable in {policy.era.value}"
            )
        body = RigidBody(
            recipe.body_id,
            recipe.shape,
            recipe.position,
            recipe.velocity,
            recipe.half_extent,
            recipe.radius,
            recipe.mass,
            recipe.restitution,
            recipe.friction,
            recipe.static,
            angular_velocity=
                recipe.angular_velocity,
        )
        if (
            policy.dimensions == 2
            and (
                abs(body.position.z)
                > 1e-12
                or abs(
                    body.velocity.z
                )
                > 1e-12
                or body.angular_velocity.length_sq()
                > 1e-12
            )
        ):
            raise GameEngineLabError(
                "2D physics recipe contains 3D state"
            )
        if (
            not policy.rotation
            and body.angular_velocity.length_sq()
            > 1e-12
        ):
            raise GameEngineLabError(
                "angular velocity unavailable in this era"
            )
        extent = (
            Vec3(
                body.radius,
                body.radius,
                body.radius,
            )
            if body.shape
            is ShapeKind.SPHERE
            else body.half_extent
        )
        if (
            body.position.x
            - extent.x < 0
            or body.position.x
            + extent.x
            > source.bounds.x
            or body.position.y
            - extent.y < 0
            or body.position.y
            + extent.y
            > source.bounds.y
            or (
                policy.dimensions
                == 3
                and (
                    body.position.z
                    - extent.z < 0
                    or body.position.z
                    + extent.z
                    > source.bounds.z
                )
            )
        ):
            raise GameEngineLabError(
                "physics body starts outside world bounds"
            )
    known = set(ids)
    for recipe in source.constraints:
        if (
            recipe.a not in known
            or recipe.b not in known
        ):
            raise GameEngineLabError(
                "constraint recipe references missing body"
            )
        DistanceConstraint(
            recipe.constraint_id,
            recipe.a,
            recipe.b,
            recipe.rest_length,
            recipe.stiffness,
        )


@dataclass(frozen=True, slots=True)
class PhysicsBuild:
    era: EngineEra
    source_digest: str
    policy_digest: str
    manifest_digest: str
    scene_document: dict[
        str,
        object,
    ]

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "engine_era": self.era.value,
            "source_digest":
                self.source_digest,
            "policy_digest":
                self.policy_digest,
            "manifest_digest":
                self.manifest_digest,
            "deterministic": True,
            "host_code_execution":
                False,
        }


def _policy_document(
    policy: PhysicsEraPolicy,
) -> dict[str, object]:
    return {
        "engine_era":
            policy.era.value,
        "dimensions":
            policy.dimensions,
        "shapes": [
            shape.value
            for shape in policy.shapes
        ],
        "broadphase":
            policy.broadphase.value,
        "solver_iterations":
            policy.solver_iterations,
        "substeps":
            policy.substeps,
        "max_bodies":
            policy.max_bodies,
        "max_constraints":
            policy.max_constraints,
        "friction":
            policy.friction,
        "rotation":
            policy.rotation,
        "constraints":
            policy.constraints,
        "sleeping":
            policy.sleeping,
        "conservative_ccd":
            policy.conservative_ccd,
        "max_toi_events":
            policy.max_toi_events,
        "grid_cell_size":
            policy.grid_cell_size,
        "numeric_mode":
            policy.numeric_mode.value,
    }


def compile_physics_build(
    era: EngineEra | str,
    source: PhysicsSceneSource,
) -> PhysicsBuild:
    policy = physics_policy(
        era
    )
    validate_physics_source(
        policy.era,
        source,
    )
    scene = _scene_document(
        source
    )
    policy_doc = _policy_document(
        policy
    )
    source_digest = _digest(
        scene
    )
    policy_digest = _digest(
        policy_doc
    )
    manifest_identity = {
        "schema_version": 1,
        "engine_era":
            policy.era.value,
        "source_digest":
            source_digest,
        "policy_digest":
            policy_digest,
    }
    return PhysicsBuild(
        policy.era,
        source_digest,
        policy_digest,
        _digest(
            manifest_identity
        ),
        scene,
    )


def physics_build_patches(
    build: PhysicsBuild,
) -> tuple[SandboxPatch, ...]:
    policy_doc = (
        _policy_document(
            physics_policy(
                build.era
            )
        )
    )
    return (
        SandboxPatch(
            "physics/compiled/manifest.json",
            json.dumps(
                build.manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "physics/compiled/policy.json",
            json.dumps(
                policy_doc,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "physics/compiled/scene.json",
            json.dumps(
                build.scene_document,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
    )


def attach_physics_build(
    sandbox: RoutedEngineSandbox,
    source: PhysicsSceneSource,
) -> RoutedEngineSandbox:
    build = compile_physics_build(
        sandbox.era,
        source,
    )
    patches = tuple(
        SandboxPatch(
            patch.path,
            patch.content,
            sandbox.tree.file_digest(
                patch.path
            ),
        )
        for patch
        in physics_build_patches(
            build
        )
    )
    return sandbox.apply(
        patches
    )


def canonical_physics_patches(
    sandbox: RoutedEngineSandbox,
    source: PhysicsSceneSource,
) -> tuple[SandboxPatch, ...]:
    build = compile_physics_build(
        sandbox.era,
        source,
    )
    expected = {
        patch.path: patch.content
        for patch
        in physics_build_patches(
            build
        )
    }
    existing = {
        path
        for path in sandbox.tree.files
        if path.startswith(
            "physics/compiled/"
        )
    }
    patches: list[
        SandboxPatch
    ] = []
    for path in sorted(
        set(expected)
        | existing
    ):
        wanted = expected.get(
            path
        )
        try:
            current = sandbox.tree.read(
                path
            )
        except GameEngineLabError:
            current = None
        if current == wanted:
            continue
        patches.append(
            SandboxPatch(
                path,
                wanted,
                sandbox.tree.file_digest(
                    path
                ),
            )
        )
    return tuple(patches)


def world_from_source(
    era: EngineEra | str,
    source: PhysicsSceneSource,
) -> HistoricalPhysicsWorld:
    policy = physics_policy(
        era
    )
    validate_physics_source(
        policy.era,
        source,
    )
    world = HistoricalPhysicsWorld(
        policy.era,
        bounds=source.bounds,
        gravity=source.gravity,
    )
    for recipe in source.bodies:
        world.spawn(
            RigidBody(
                body_id=
                    recipe.body_id,
                shape=recipe.shape,
                position=
                    recipe.position,
                velocity=
                    recipe.velocity,
                half_extent=
                    recipe.half_extent,
                radius=
                    recipe.radius,
                mass=recipe.mass,
                restitution=
                    recipe.restitution,
                friction=
                    recipe.friction,
                static=recipe.static,
                angular_velocity=
                    recipe.angular_velocity,
            )
        )
    for recipe in source.constraints:
        world.add_constraint(
            DistanceConstraint(
                recipe.constraint_id,
                recipe.a,
                recipe.b,
                recipe.rest_length,
                recipe.stiffness,
            )
        )
    return world


@dataclass(frozen=True, slots=True)
class PhysicsProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PhysicsQualityReport:
    era: EngineEra
    probes: tuple[
        PhysicsProbe,
        ...,
    ]

    @property
    def passed(self) -> bool:
        return bool(self.probes) and all(
            probe.passed
            for probe in self.probes
        )

    @property
    def score(self) -> float:
        return sum(
            probe.passed
            for probe in self.probes
        ) / max(
            1,
            len(self.probes),
        )

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            probe.name
            for probe in self.probes
            if not probe.passed
        )


class PhysicsAdversary:
    """Recompile, replay and stress the physics evidence plane."""

    def evaluate(
        self,
        sandbox: RoutedEngineSandbox,
        source: PhysicsSceneSource,
    ) -> PhysicsQualityReport:
        try:
            expected = compile_physics_build(
                sandbox.era,
                source,
            )
            manifest = json.loads(
                sandbox.tree.read(
                    "physics/compiled/manifest.json"
                )
            )
            policy_doc = json.loads(
                sandbox.tree.read(
                    "physics/compiled/policy.json"
                )
            )
            scene_doc = json.loads(
                sandbox.tree.read(
                    "physics/compiled/scene.json"
                )
            )
        except (
            GameEngineLabError,
            json.JSONDecodeError,
        ) as exc:
            detail = str(exc)
            return PhysicsQualityReport(
                sandbox.era,
                tuple(
                    PhysicsProbe(
                        name,
                        False,
                        detail,
                    )
                    for name in (
                        "manifest",
                        "inventory",
                        "integrity",
                        "replay",
                        "snapshot",
                        "contact",
                        "bounds",
                        "constraints",
                        "ccd",
                        "queries",
                    )
                ),
            )

        expected_paths = {
            patch.path
            for patch
            in physics_build_patches(
                expected
            )
        }
        actual_paths = {
            path
            for path in sandbox.tree.files
            if path.startswith(
                "physics/compiled/"
            )
        }
        manifest_ok = (
            manifest
            == expected.manifest()
        )
        inventory_ok = (
            expected_paths
            == actual_paths
        )
        integrity_ok = (
            policy_doc
            == _policy_document(
                physics_policy(
                    sandbox.era
                )
            )
            and scene_doc
            == expected.scene_document
        )

        first = world_from_source(
            sandbox.era,
            source,
        )
        second = world_from_source(
            sandbox.era,
            source,
        )
        first.step(120)
        second.step(120)
        replay_ok = (
            first.fingerprint()
            == second.fingerprint()
        )

        snap_world = world_from_source(
            sandbox.era,
            source,
        )
        snap_world.step(20)
        snapshot = snap_world.snapshot()
        before = (
            snap_world.fingerprint()
        )
        snap_world.step(10)
        snap_world.restore(
            snapshot
        )
        snapshot_ok = (
            snap_world.fingerprint()
            == before
        )

        contact_world = (
            HistoricalPhysicsWorld(
                sandbox.era,
                bounds=Vec3(
                    100.0,
                    100.0,
                    100.0,
                ),
                gravity=ZERO3,
            )
        )
        shape = (
            ShapeKind.AABB
            if ShapeKind.AABB
            in contact_world.policy.shapes
            else contact_world.policy.shapes[0]
        )
        contact_world.spawn(
            RigidBody(
                "contact_a",
                shape,
                Vec3(
                    45.0,
                    50.0,
                    0.0,
                ),
                Vec3(
                    5.0,
                    0.0,
                    0.0,
                ),
                half_extent=
                    Vec3(
                        6.0,
                        6.0,
                        6.0,
                    ),
                radius=6.0,
            )
        )
        contact_world.spawn(
            RigidBody(
                "contact_b",
                shape,
                Vec3(
                    55.0,
                    50.0,
                    0.0,
                ),
                Vec3(
                    -5.0,
                    0.0,
                    0.0,
                ),
                half_extent=
                    Vec3(
                        6.0,
                        6.0,
                        6.0,
                    ),
                radius=6.0,
            )
        )
        initial_contacts = (
            contact_world._contacts()
        )
        initial_penetration = max(
            (
                contact.penetration
                for contact
                in initial_contacts
            ),
            default=0.0,
        )
        contact_world.step()
        a, b = (
            contact_world.bodies
        )
        remaining_contacts = (
            contact_world._contacts()
        )
        remaining_penetration = max(
            (
                contact.penetration
                for contact
                in remaining_contacts
            ),
            default=0.0,
        )
        contact_ok = (
            bool(initial_contacts)
            and remaining_penetration
            < initial_penetration
            and all(
                math.isfinite(
                    value
                )
                for value in (
                    a.position.x,
                    a.position.y,
                    a.position.z,
                    b.position.x,
                    b.position.y,
                    b.position.z,
                )
            )
        )

        bounds_ok = all(
            (
                0
                <= body.position.x
                <= first.bounds.x
                and 0
                <= body.position.y
                <= first.bounds.y
                and (
                    first.policy.dimensions
                    == 2
                    or 0
                    <= body.position.z
                    <= first.bounds.z
                )
            )
            for body
            in first.bodies
        )

        if first.policy.constraints:
            constraints_ok = True
            for constraint in (
                first.constraints
            ):
                a_body = first._bodies[
                    constraint.a
                ]
                b_body = first._bodies[
                    constraint.b
                ]
                error = abs(
                    (
                        b_body.position
                        - a_body.position
                    ).length()
                    - constraint.rest_length
                )
                if error > 1.0:
                    constraints_ok = False
                    break
        else:
            constraints_ok = (
                not source.constraints
            )

        ccd_ok = True
        if first.policy.conservative_ccd:
            ccd_world = (
                HistoricalPhysicsWorld(
                    sandbox.era,
                    bounds=Vec3(
                        200.0,
                        100.0,
                        100.0,
                    ),
                    gravity=ZERO3,
                )
            )
            ccd_world.spawn(
                RigidBody(
                    "projectile",
                    ShapeKind.SPHERE,
                    Vec3(
                        10.0,
                        50.0,
                        50.0,
                    ),
                    Vec3(
                        12_000.0,
                        0.0,
                        0.0,
                    ),
                    radius=0.5,
                    mass=1.0,
                    restitution=0.0,
                    friction=0.0,
                )
            )
            ccd_world.spawn(
                RigidBody(
                    "thin_wall",
                    ShapeKind.AABB,
                    Vec3(
                        50.0,
                        50.0,
                        50.0,
                    ),
                    half_extent=Vec3(
                        0.25,
                        20.0,
                        20.0,
                    ),
                    restitution=0.0,
                    friction=0.0,
                    static=True,
                )
            )
            ccd_world.step()
            projectile = (
                ccd_world._bodies[
                    "projectile"
                ]
            )
            static_ccd_ok = (
                projectile.position.x
                < 50.0
                and projectile.velocity.x
                <= 0.0
                and math.isfinite(
                    projectile.position.x
                )
                and math.isfinite(
                    projectile.velocity.x
                )
            )

            dynamic_world = (
                HistoricalPhysicsWorld(
                    sandbox.era,
                    bounds=Vec3(
                        200.0,
                        100.0,
                        100.0,
                    ),
                    gravity=ZERO3,
                )
            )
            for (
                body_id,
                x,
                velocity,
            ) in (
                (
                    "fast_left",
                    90.0,
                    4_000.0,
                ),
                (
                    "fast_right",
                    110.0,
                    -4_000.0,
                ),
            ):
                dynamic_world.spawn(
                    RigidBody(
                        body_id,
                        ShapeKind.SPHERE,
                        Vec3(
                            x,
                            50.0,
                            50.0,
                        ),
                        Vec3(
                            velocity,
                            0.0,
                            0.0,
                        ),
                        radius=1.0,
                        mass=1.0,
                        restitution=0.0,
                        friction=0.0,
                    )
                )
            dynamic_world.step()
            left = (
                dynamic_world._bodies[
                    "fast_left"
                ]
            )
            right = (
                dynamic_world._bodies[
                    "fast_right"
                ]
            )
            dynamic_ccd_ok = (
                left.position.x
                < right.position.x
                and (
                    right.position.x
                    - left.position.x
                )
                >= 2.0 - 1e-5
                and left.velocity.x
                <= right.velocity.x
                + 1e-6
                and any(
                    {
                        contact.a,
                        contact.b,
                    }
                    == {
                        "fast_left",
                        "fast_right",
                    }
                    for contact
                    in dynamic_world.last_contacts
                )
            )
            ccd_ok = (
                static_ccd_ok
                and dynamic_ccd_ok
            )

        query_world = world_from_source(
            sandbox.era,
            source,
        )
        query_target = (
            query_world.bodies[0]
            if query_world.bodies
            else None
        )
        if query_target is None:
            query_ok = False
        else:
            query_origin = (
                query_target.position
            )
            first_queries = (
                query_world.raycast(
                    query_origin,
                    Vec3(
                        1.0,
                        0.0,
                        0.0,
                    ),
                    1.0,
                )
            )
            second_queries = (
                query_world.raycast(
                    query_origin,
                    Vec3(
                        1.0,
                        0.0,
                        0.0,
                    ),
                    1.0,
                )
            )
            query_extent = Vec3(
                0.25,
                0.25,
                (
                    0.25
                    if query_world.policy.dimensions
                    == 3
                    else 0.0
                ),
            )
            query_ok = (
                first_queries
                == second_queries
                and any(
                    (
                        hit.body_id
                        == query_target.body_id
                        and hit.distance
                        == 0.0
                    )
                    for hit
                    in first_queries
                )
                and query_target.body_id
                in query_world.overlap_aabb(
                    query_target.position,
                    query_extent,
                )
                and query_target.body_id
                in query_world.overlap_sphere(
                    query_target.position,
                    0.25,
                )
            )

        return PhysicsQualityReport(
            sandbox.era,
            (
                PhysicsProbe(
                    "manifest",
                    manifest_ok,
                    "canonical physics manifest",
                ),
                PhysicsProbe(
                    "inventory",
                    inventory_ok,
                    "exact compiled physics inventory",
                ),
                PhysicsProbe(
                    "integrity",
                    integrity_ok,
                    "policy and scene attested",
                ),
                PhysicsProbe(
                    "replay",
                    replay_ok,
                    "deterministic 120-tick replay",
                ),
                PhysicsProbe(
                    "snapshot",
                    snapshot_ok,
                    "physics state roundtrip",
                ),
                PhysicsProbe(
                    "contact",
                    contact_ok,
                    "finite deterministic contact response",
                ),
                PhysicsProbe(
                    "bounds",
                    bounds_ok,
                    "world containment",
                ),
                PhysicsProbe(
                    "constraints",
                    constraints_ok,
                    "constraint capability contract",
                ),
                PhysicsProbe(
                    "ccd",
                    ccd_ok,
                    (
                        "global swept TOI prevents static and dynamic tunneling"
                        if first.policy.conservative_ccd
                        else "CCD unavailable by historical policy"
                    ),
                ),
                PhysicsProbe(
                    "queries",
                    query_ok,
                    "deterministic ray and overlap query contract",
                ),
            ),
        )


def canonical_physics_source(
    era: EngineEra | str,
) -> PhysicsSceneSource:
    policy = physics_policy(
        era
    )
    dynamic_shape = (
        ShapeKind.SPHERE
        if (
            ShapeKind.SPHERE
            in policy.shapes
            and policy.rotation
        )
        else ShapeKind.AABB
    )
    z = (
        0.0
        if policy.dimensions == 2
        else 50.0
    )
    bodies = [
        BodyRecipe(
            "floor",
            ShapeKind.AABB,
            Vec3(
                50.0,
                5.0,
                z,
            ),
            half_extent=Vec3(
                50.0,
                5.0,
                50.0,
            ),
            mass=1.0,
            restitution=0.1,
            friction=0.8,
            static=True,
        ),
        BodyRecipe(
            "body_a",
            dynamic_shape,
            Vec3(
                45.0,
                40.0,
                z,
            ),
            Vec3(
                2.0,
                0.0,
                0.0,
            ),
            half_extent=Vec3(
                2.5,
                2.5,
                2.5,
            ),
            radius=2.5,
            mass=1.0,
            restitution=0.3,
            friction=0.5,
            angular_velocity=(
                Vec3(
                    0.0,
                    0.4,
                    0.0,
                )
                if policy.rotation
                else ZERO3
            ),
        ),
        BodyRecipe(
            "body_b",
            dynamic_shape,
            Vec3(
                55.0,
                40.0,
                z,
            ),
            Vec3(
                -2.0,
                0.0,
                0.0,
            ),
            half_extent=Vec3(
                2.5,
                2.5,
                2.5,
            ),
            radius=2.5,
            mass=1.0,
            restitution=0.3,
            friction=0.5,
        ),
    ]
    constraints: tuple[
        ConstraintRecipe,
        ...,
    ] = ()
    if policy.constraints:
        constraints = (
            ConstraintRecipe(
                "link",
                "body_a",
                "body_b",
                10.0,
                0.75,
            ),
        )
    return PhysicsSceneSource(
        bounds=Vec3(
            100.0,
            100.0,
            (
                1.0
                if policy.dimensions
                == 2
                else 100.0
            ),
        ),
        gravity=Vec3(
            0.0,
            (
                -1.0
                if policy.era
                in {
                    EngineEra.PONG,
                    EngineEra.ARCADE,
                }
                else -9.8
            ),
            0.0,
        ),
        bodies=tuple(bodies),
        constraints=constraints,
    )
