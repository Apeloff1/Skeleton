"""Deterministic rigid-body joint constraints.

This module keeps joints engine-neutral and explicit.  Every joint has stable
identity, explicit body/anchor references, bounded validated parameters and a
canonical state record.  The solver uses deterministic projected scalar
constraints so the same primitives can later be grouped, colored and parallelized
without changing their semantic contract.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from .body import BodyType, RigidBody
from .errors import BodyNotFoundError, PhysicsValidationError
from .math3d import EPSILON, Vec3

_JOINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _finite(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PhysicsValidationError(f"{name} must be finite")
    return value


def _non_negative(value: float, *, name: str) -> float:
    value = _finite(value, name=name)
    if value < 0.0:
        raise PhysicsValidationError(f"{name} must be non-negative")
    return value


def _positive(value: float, *, name: str) -> float:
    value = _finite(value, name=name)
    if value <= 0.0:
        raise PhysicsValidationError(f"{name} must be positive")
    return value


def _unit_interval(value: float, *, name: str) -> float:
    value = _non_negative(value, name=name)
    if value > 1.0:
        raise PhysicsValidationError(f"{name} must be in [0, 1]")
    return value


def _validate_joint_identity(
    joint_id: str,
    body_a: str,
    body_b: str,
) -> None:
    if not isinstance(joint_id, str) or not _JOINT_ID_RE.fullmatch(joint_id):
        raise PhysicsValidationError("invalid joint_id")
    if not isinstance(body_a, str) or not isinstance(body_b, str):
        raise PhysicsValidationError("joint body ids must be strings")
    if not body_a or not body_b or body_a == body_b:
        raise PhysicsValidationError("joint requires distinct body ids")


def _validate_anchors(anchor_a: Vec3, anchor_b: Vec3) -> None:
    if not isinstance(anchor_a, Vec3) or not isinstance(anchor_b, Vec3):
        raise PhysicsValidationError("joint anchors must be Vec3")


class JointKind(str, Enum):
    DISTANCE = "distance"
    POINT = "point"
    SPRING = "spring"
    DISTANCE_LIMIT = "distance_limit"


@dataclass(frozen=True, slots=True)
class DistanceJoint:
    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    rest_length: float = 1.0
    bias_factor: float = 0.2

    def __post_init__(self) -> None:
        _validate_joint_identity(self.joint_id, self.body_a, self.body_b)
        _validate_anchors(self.local_anchor_a, self.local_anchor_b)
        rest_length = _non_negative(self.rest_length, name="rest_length")
        if rest_length <= EPSILON:
            raise PhysicsValidationError(
                "distance joint rest_length must be positive; "
                "use PointJoint for coincident anchors"
            )
        object.__setattr__(self, "rest_length", rest_length)
        object.__setattr__(
            self,
            "bias_factor",
            _unit_interval(self.bias_factor, name="bias_factor"),
        )

    @property
    def kind(self) -> JointKind:
        return JointKind.DISTANCE

    def state_record(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "rest_length": self.rest_length,
            "bias_factor": self.bias_factor,
        }


@dataclass(frozen=True, slots=True)
class PointJoint:
    """Ball/socket style joint that makes two world anchors coincide."""

    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    bias_factor: float = 0.2

    def __post_init__(self) -> None:
        _validate_joint_identity(self.joint_id, self.body_a, self.body_b)
        _validate_anchors(self.local_anchor_a, self.local_anchor_b)
        object.__setattr__(
            self,
            "bias_factor",
            _unit_interval(self.bias_factor, name="bias_factor"),
        )

    @property
    def kind(self) -> JointKind:
        return JointKind.POINT

    def state_record(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "bias_factor": self.bias_factor,
        }


@dataclass(frozen=True, slots=True)
class SpringJoint:
    """Implicit damped spring along the line between two anchors."""

    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    rest_length: float = 1.0
    stiffness: float = 100.0
    damping: float = 10.0
    max_force: float | None = None

    def __post_init__(self) -> None:
        _validate_joint_identity(self.joint_id, self.body_a, self.body_b)
        _validate_anchors(self.local_anchor_a, self.local_anchor_b)
        object.__setattr__(
            self,
            "rest_length",
            _non_negative(self.rest_length, name="rest_length"),
        )
        object.__setattr__(
            self,
            "stiffness",
            _positive(self.stiffness, name="stiffness"),
        )
        object.__setattr__(
            self,
            "damping",
            _non_negative(self.damping, name="damping"),
        )
        if self.max_force is not None:
            object.__setattr__(
                self,
                "max_force",
                _positive(self.max_force, name="max_force"),
            )

    @property
    def kind(self) -> JointKind:
        return JointKind.SPRING

    def state_record(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "rest_length": self.rest_length,
            "stiffness": self.stiffness,
            "damping": self.damping,
            "max_force": self.max_force,
        }


@dataclass(frozen=True, slots=True)
class DistanceLimitJoint:
    """Keep anchor separation inside an inclusive [minimum, maximum] range."""

    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    minimum_length: float = 0.0
    maximum_length: float = 1.0
    bias_factor: float = 0.2

    def __post_init__(self) -> None:
        _validate_joint_identity(self.joint_id, self.body_a, self.body_b)
        _validate_anchors(self.local_anchor_a, self.local_anchor_b)
        minimum = _non_negative(self.minimum_length, name="minimum_length")
        maximum = _non_negative(self.maximum_length, name="maximum_length")
        if maximum < minimum:
            raise PhysicsValidationError(
                "maximum_length must be greater than or equal to minimum_length"
            )
        object.__setattr__(self, "minimum_length", minimum)
        object.__setattr__(self, "maximum_length", maximum)
        object.__setattr__(
            self,
            "bias_factor",
            _unit_interval(self.bias_factor, name="bias_factor"),
        )

    @property
    def kind(self) -> JointKind:
        return JointKind.DISTANCE_LIMIT

    def state_record(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "minimum_length": self.minimum_length,
            "maximum_length": self.maximum_length,
            "bias_factor": self.bias_factor,
        }


JointConstraint: TypeAlias = (
    DistanceJoint | PointJoint | SpringJoint | DistanceLimitJoint
)
JOINT_TYPES = (DistanceJoint, PointJoint, SpringJoint, DistanceLimitJoint)


def is_joint_constraint(value: object) -> bool:
    return isinstance(value, JOINT_TYPES)


@dataclass(frozen=True, slots=True)
class ConstraintStats:
    joints: int
    velocity_impulses: int
    position_corrections: int
    maximum_error: float
    distance_joints: int = 0
    point_joints: int = 0
    spring_joints: int = 0
    limit_joints: int = 0


@dataclass(frozen=True, slots=True)
class _AnchorState:
    anchor_a: Vec3
    anchor_b: Vec3
    arm_a: Vec3
    arm_b: Vec3


class ConstraintSolver:
    def __init__(
        self,
        *,
        velocity_iterations: int = 8,
        position_iterations: int = 4,
        position_slop: float = 0.001,
        position_correction: float = 0.65,
    ) -> None:
        for name, value in (
            ("velocity_iterations", velocity_iterations),
            ("position_iterations", position_iterations),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 128:
                raise PhysicsValidationError(f"{name} outside supported range")
        self.velocity_iterations = velocity_iterations
        self.position_iterations = position_iterations
        self.position_slop = _non_negative(position_slop, name="position_slop")
        self.position_correction = _unit_interval(
            position_correction,
            name="position_correction",
        )

    @staticmethod
    def _anchors(
        joint: JointConstraint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> _AnchorState:
        arm_a = body_a.orientation.rotate(joint.local_anchor_a)
        arm_b = body_b.orientation.rotate(joint.local_anchor_b)
        return _AnchorState(
            anchor_a=body_a.position + arm_a,
            anchor_b=body_b.position + arm_b,
            arm_a=arm_a,
            arm_b=arm_b,
        )

    @staticmethod
    def _effective_mass(body: RigidBody, arm: Vec3, axis: Vec3) -> float:
        if body.inverse_mass <= 0.0:
            return 0.0
        angular = body.world_inverse_inertia().mul_vec(
            arm.cross(axis)
        ).cross(arm)
        return body.inverse_mass + axis.dot(angular)

    @staticmethod
    def _denominator(
        body_a: RigidBody,
        body_b: RigidBody,
        anchors: _AnchorState,
        axis: Vec3,
    ) -> float:
        return (
            ConstraintSolver._effective_mass(body_a, anchors.arm_a, axis)
            + ConstraintSolver._effective_mass(body_b, anchors.arm_b, axis)
        )

    @staticmethod
    def _relative_velocity(
        body_a: RigidBody,
        body_b: RigidBody,
        anchors: _AnchorState,
    ) -> Vec3:
        return (
            body_b.velocity_at_world_point(anchors.anchor_b)
            - body_a.velocity_at_world_point(anchors.anchor_a)
        )

    @staticmethod
    def _apply_impulse(
        body_a: RigidBody,
        body_b: RigidBody,
        impulse: Vec3,
        anchors: _AnchorState,
    ) -> None:
        body_a.apply_impulse(-impulse, point=anchors.anchor_a)
        body_b.apply_impulse(impulse, point=anchors.anchor_b)

    @staticmethod
    def _axis_and_length(delta: Vec3) -> tuple[Vec3, float]:
        length = delta.length()
        axis = Vec3.axis(0) if length <= EPSILON else delta / length
        return axis, length

    def _validate_joint(
        self,
        joint: JointConstraint,
        bodies: dict[str, RigidBody],
    ) -> tuple[RigidBody, RigidBody]:
        if not is_joint_constraint(joint):
            raise PhysicsValidationError("unsupported joint constraint")
        try:
            body_a = bodies[joint.body_a]
            body_b = bodies[joint.body_b]
        except KeyError as exc:
            raise BodyNotFoundError(str(exc)) from exc
        if body_a.body_type is BodyType.STATIC and body_b.body_type is BodyType.STATIC:
            raise PhysicsValidationError("joint cannot bind two static bodies")
        return body_a, body_b

    def _solve_scalar_velocity(
        self,
        body_a: RigidBody,
        body_b: RigidBody,
        anchors: _AnchorState,
        axis: Vec3,
        *,
        error: float,
        bias_factor: float,
        dt: float,
    ) -> int:
        denominator = self._denominator(
            body_a,
            body_b,
            anchors,
            axis,
        )
        if denominator <= EPSILON:
            return 0
        relative_speed = self._relative_velocity(
            body_a,
            body_b,
            anchors,
        ).dot(axis)
        bias = bias_factor * error / dt
        impulse_magnitude = -(relative_speed + bias) / denominator
        if not math.isfinite(impulse_magnitude):
            raise PhysicsValidationError(
                "joint produced non-finite scalar impulse"
            )
        if abs(impulse_magnitude) <= EPSILON:
            return 0
        self._apply_impulse(
            body_a,
            body_b,
            axis * impulse_magnitude,
            anchors,
        )
        return 1

    def _solve_distance_velocity(
        self,
        joint: DistanceJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
    ) -> tuple[int, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        axis, length = self._axis_and_length(delta)
        error = length - joint.rest_length
        count = self._solve_scalar_velocity(
            body_a,
            body_b,
            anchors,
            axis,
            error=error,
            bias_factor=joint.bias_factor,
            dt=dt,
        )
        return count, abs(error)

    def _solve_point_velocity(
        self,
        joint: PointJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
    ) -> tuple[int, float]:
        impulses = 0
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        maximum_error = delta.length()

        # Recompute anchor velocities/arms after each scalar impulse so angular
        # coupling is reflected by subsequent axes.
        for axis_index in range(3):
            anchors = self._anchors(joint, body_a, body_b)
            delta = anchors.anchor_b - anchors.anchor_a
            axis = Vec3.axis(axis_index)
            impulses += self._solve_scalar_velocity(
                body_a,
                body_b,
                anchors,
                axis,
                error=delta.dot(axis),
                bias_factor=joint.bias_factor,
                dt=dt,
            )
        return impulses, maximum_error

    def _limit_error(
        self,
        joint: DistanceLimitJoint,
        length: float,
    ) -> float | None:
        if length < joint.minimum_length:
            return length - joint.minimum_length
        if length > joint.maximum_length:
            return length - joint.maximum_length
        return None

    def _solve_limit_velocity(
        self,
        joint: DistanceLimitJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
    ) -> tuple[int, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        axis, length = self._axis_and_length(delta)
        error = self._limit_error(joint, length)
        if error is None:
            return 0, 0.0
        count = self._solve_scalar_velocity(
            body_a,
            body_b,
            anchors,
            axis,
            error=error,
            bias_factor=joint.bias_factor,
            dt=dt,
        )
        return count, abs(error)

    def _solve_spring_velocity(
        self,
        joint: SpringJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
        accumulated_impulse: float,
    ) -> tuple[int, float, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        axis, length = self._axis_and_length(delta)
        error = length - joint.rest_length
        denominator = self._denominator(
            body_a,
            body_b,
            anchors,
            axis,
        )
        if denominator <= EPSILON:
            return 0, abs(error), accumulated_impulse

        softness_denominator = dt * (
            joint.damping + dt * joint.stiffness
        )
        gamma = (
            0.0
            if softness_denominator <= EPSILON
            else 1.0 / softness_denominator
        )
        bias = error * dt * joint.stiffness * gamma
        relative_speed = self._relative_velocity(
            body_a,
            body_b,
            anchors,
        ).dot(axis)

        delta_impulse = -(
            relative_speed
            + bias
            + gamma * accumulated_impulse
        ) / (denominator + gamma)
        new_impulse = accumulated_impulse + delta_impulse

        if joint.max_force is not None:
            maximum_impulse = joint.max_force * dt
            new_impulse = min(
                maximum_impulse,
                max(-maximum_impulse, new_impulse),
            )

        applied = new_impulse - accumulated_impulse
        if not math.isfinite(applied):
            raise PhysicsValidationError(
                "spring joint produced non-finite impulse"
            )
        if abs(applied) <= EPSILON:
            return 0, abs(error), new_impulse

        self._apply_impulse(
            body_a,
            body_b,
            axis * applied,
            anchors,
        )
        return 1, abs(error), new_impulse

    def _translate_position(
        self,
        body_a: RigidBody,
        body_b: RigidBody,
        correction: Vec3,
    ) -> int:
        inverse_mass_sum = body_a.inverse_mass + body_b.inverse_mass
        if inverse_mass_sum <= EPSILON:
            return 0
        if body_a.inverse_mass > 0.0:
            body_a.position = (
                body_a.position
                + correction * (body_a.inverse_mass / inverse_mass_sum)
            )
            body_a.wake()
        if body_b.inverse_mass > 0.0:
            body_b.position = (
                body_b.position
                - correction * (body_b.inverse_mass / inverse_mass_sum)
            )
            body_b.wake()
        return 1

    def _solve_distance_position(
        self,
        joint: DistanceJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[int, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        axis, length = self._axis_and_length(delta)
        error = length - joint.rest_length
        corrected = math.copysign(
            max(0.0, abs(error) - self.position_slop),
            error,
        )
        if abs(corrected) <= EPSILON:
            return 0, abs(error)
        magnitude = (
            corrected
            * (self.position_correction / self.position_iterations)
        )
        count = self._translate_position(
            body_a,
            body_b,
            axis * magnitude,
        )
        return count, abs(error)

    def _solve_limit_position(
        self,
        joint: DistanceLimitJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[int, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        axis, length = self._axis_and_length(delta)
        error = self._limit_error(joint, length)
        if error is None:
            return 0, 0.0
        corrected = math.copysign(
            max(0.0, abs(error) - self.position_slop),
            error,
        )
        if abs(corrected) <= EPSILON:
            return 0, abs(error)
        magnitude = (
            corrected
            * (self.position_correction / self.position_iterations)
        )
        count = self._translate_position(
            body_a,
            body_b,
            axis * magnitude,
        )
        return count, abs(error)

    def _solve_point_position(
        self,
        joint: PointJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[int, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        length = delta.length()
        corrected_length = max(0.0, length - self.position_slop)
        if corrected_length <= EPSILON or length <= EPSILON:
            return 0, length
        correction = (
            delta / length
        ) * (
            corrected_length
            * (self.position_correction / self.position_iterations)
        )
        count = self._translate_position(
            body_a,
            body_b,
            correction,
        )
        return count, length

    def solve(
        self,
        bodies: dict[str, RigidBody],
        joints: tuple[JointConstraint, ...],
        *,
        dt: float,
    ) -> ConstraintStats:
        if isinstance(dt, bool) or not isinstance(dt, (int, float)):
            raise PhysicsValidationError("constraint dt must be numeric")
        dt = float(dt)
        if not math.isfinite(dt) or dt <= 0.0:
            raise PhysicsValidationError("constraint dt must be positive")

        ordered = tuple(sorted(joints, key=lambda row: row.joint_id))
        maximum_error = 0.0
        velocity_impulses = 0
        position_corrections = 0
        spring_impulses = {
            joint.joint_id: 0.0
            for joint in ordered
            if isinstance(joint, SpringJoint)
        }

        counts = {
            JointKind.DISTANCE: 0,
            JointKind.POINT: 0,
            JointKind.SPRING: 0,
            JointKind.DISTANCE_LIMIT: 0,
        }

        for joint in ordered:
            self._validate_joint(joint, bodies)
            counts[joint.kind] += 1

        for _ in range(self.velocity_iterations):
            for joint in ordered:
                body_a, body_b = self._validate_joint(joint, bodies)
                if isinstance(joint, DistanceJoint):
                    count, error = self._solve_distance_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                    )
                elif isinstance(joint, PointJoint):
                    count, error = self._solve_point_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                    )
                elif isinstance(joint, SpringJoint):
                    count, error, accumulated = self._solve_spring_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        accumulated_impulse=spring_impulses[joint.joint_id],
                    )
                    spring_impulses[joint.joint_id] = accumulated
                elif isinstance(joint, DistanceLimitJoint):
                    count, error = self._solve_limit_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                    )
                else:
                    raise PhysicsValidationError("unsupported joint constraint")
                velocity_impulses += count
                maximum_error = max(maximum_error, error)

        for _ in range(self.position_iterations):
            for joint in ordered:
                body_a, body_b = self._validate_joint(joint, bodies)
                if isinstance(joint, DistanceJoint):
                    count, error = self._solve_distance_position(
                        joint,
                        body_a,
                        body_b,
                    )
                elif isinstance(joint, PointJoint):
                    count, error = self._solve_point_position(
                        joint,
                        body_a,
                        body_b,
                    )
                elif isinstance(joint, DistanceLimitJoint):
                    count, error = self._solve_limit_position(
                        joint,
                        body_a,
                        body_b,
                    )
                elif isinstance(joint, SpringJoint):
                    # Springs remain soft constraints: no hard position projection.
                    anchors = self._anchors(joint, body_a, body_b)
                    error = abs(
                        (anchors.anchor_b - anchors.anchor_a).length()
                        - joint.rest_length
                    )
                    count = 0
                else:
                    raise PhysicsValidationError("unsupported joint constraint")
                position_corrections += count
                maximum_error = max(maximum_error, error)

        return ConstraintStats(
            joints=len(ordered),
            velocity_impulses=velocity_impulses,
            position_corrections=position_corrections,
            maximum_error=maximum_error,
            distance_joints=counts[JointKind.DISTANCE],
            point_joints=counts[JointKind.POINT],
            spring_joints=counts[JointKind.SPRING],
            limit_joints=counts[JointKind.DISTANCE_LIMIT],
        )
