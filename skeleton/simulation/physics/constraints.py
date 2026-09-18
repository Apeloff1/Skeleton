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
from .joint_cache import JointImpulseCache
from .math3d import EPSILON, Quat, Vec3

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


def _normalized_axis(value: Vec3, *, name: str) -> Vec3:
    if not isinstance(value, Vec3):
        raise PhysicsValidationError(f"{name} must be Vec3")
    try:
        return value.normalized()
    except Exception as exc:
        raise PhysicsValidationError(f"{name} must be non-zero") from exc


def _reference_perpendicular(
    axis: Vec3,
    reference: Vec3,
    *,
    name: str,
) -> Vec3:
    if not isinstance(reference, Vec3):
        raise PhysicsValidationError(f"{name} must be Vec3")
    projected = reference - axis * reference.dot(axis)
    try:
        return projected.normalized()
    except Exception as exc:
        raise PhysicsValidationError(
            f"{name} must not be parallel to joint axis"
        ) from exc


class JointKind(str, Enum):
    DISTANCE = "distance"
    POINT = "point"
    SPRING = "spring"
    DISTANCE_LIMIT = "distance_limit"
    HINGE = "hinge"
    FIXED = "fixed"
    SLIDER = "slider"


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


@dataclass(frozen=True, slots=True)
class HingeJoint:
    """Anchor-coincident single-axis rotational joint with optional stops/motor."""

    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    local_axis_a: Vec3 = Vec3(0.0, 1.0, 0.0)
    local_axis_b: Vec3 = Vec3(0.0, 1.0, 0.0)
    local_reference_a: Vec3 = Vec3(1.0, 0.0, 0.0)
    local_reference_b: Vec3 = Vec3(1.0, 0.0, 0.0)
    bias_factor: float = 0.2
    lower_angle: float | None = None
    upper_angle: float | None = None
    motor_speed: float | None = None
    max_motor_torque: float | None = None

    def __post_init__(self) -> None:
        _validate_joint_identity(self.joint_id, self.body_a, self.body_b)
        _validate_anchors(self.local_anchor_a, self.local_anchor_b)
        axis_a = _normalized_axis(self.local_axis_a, name="local_axis_a")
        axis_b = _normalized_axis(self.local_axis_b, name="local_axis_b")
        object.__setattr__(self, "local_axis_a", axis_a)
        object.__setattr__(self, "local_axis_b", axis_b)
        object.__setattr__(
            self,
            "local_reference_a",
            _reference_perpendicular(
                axis_a,
                self.local_reference_a,
                name="local_reference_a",
            ),
        )
        object.__setattr__(
            self,
            "local_reference_b",
            _reference_perpendicular(
                axis_b,
                self.local_reference_b,
                name="local_reference_b",
            ),
        )
        object.__setattr__(
            self,
            "bias_factor",
            _unit_interval(self.bias_factor, name="bias_factor"),
        )

        lower = (
            None
            if self.lower_angle is None
            else _finite(self.lower_angle, name="lower_angle")
        )
        upper = (
            None
            if self.upper_angle is None
            else _finite(self.upper_angle, name="upper_angle")
        )
        if lower is not None and not -math.pi <= lower <= math.pi:
            raise PhysicsValidationError("lower_angle must be in [-pi, pi]")
        if upper is not None and not -math.pi <= upper <= math.pi:
            raise PhysicsValidationError("upper_angle must be in [-pi, pi]")
        if lower is not None and upper is not None and upper < lower:
            raise PhysicsValidationError(
                "upper_angle must be greater than or equal to lower_angle"
            )
        object.__setattr__(self, "lower_angle", lower)
        object.__setattr__(self, "upper_angle", upper)

        speed = (
            None
            if self.motor_speed is None
            else _finite(self.motor_speed, name="motor_speed")
        )
        torque = (
            None
            if self.max_motor_torque is None
            else _positive(self.max_motor_torque, name="max_motor_torque")
        )
        if (speed is None) != (torque is None):
            raise PhysicsValidationError(
                "hinge motor requires motor_speed and max_motor_torque together"
            )
        object.__setattr__(self, "motor_speed", speed)
        object.__setattr__(self, "max_motor_torque", torque)

    @property
    def kind(self) -> JointKind:
        return JointKind.HINGE

    def state_record(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "local_axis_a": self.local_axis_a.to_tuple(),
            "local_axis_b": self.local_axis_b.to_tuple(),
            "local_reference_a": self.local_reference_a.to_tuple(),
            "local_reference_b": self.local_reference_b.to_tuple(),
            "bias_factor": self.bias_factor,
            "lower_angle": self.lower_angle,
            "upper_angle": self.upper_angle,
            "motor_speed": self.motor_speed,
            "max_motor_torque": self.max_motor_torque,
        }


@dataclass(frozen=True, slots=True)
class FixedJoint:
    """Lock two explicit local frames in both translation and rotation."""

    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    local_frame_a: Quat = Quat.identity()
    local_frame_b: Quat = Quat.identity()
    bias_factor: float = 0.2

    def __post_init__(self) -> None:
        _validate_joint_identity(self.joint_id, self.body_a, self.body_b)
        _validate_anchors(self.local_anchor_a, self.local_anchor_b)
        if not isinstance(self.local_frame_a, Quat) or not isinstance(
            self.local_frame_b,
            Quat,
        ):
            raise PhysicsValidationError("fixed joint frames must be Quat")
        object.__setattr__(self, "local_frame_a", self.local_frame_a.normalized())
        object.__setattr__(self, "local_frame_b", self.local_frame_b.normalized())
        object.__setattr__(
            self,
            "bias_factor",
            _unit_interval(self.bias_factor, name="bias_factor"),
        )

    @property
    def kind(self) -> JointKind:
        return JointKind.FIXED

    def state_record(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "local_frame_a": (
                self.local_frame_a.w,
                self.local_frame_a.x,
                self.local_frame_a.y,
                self.local_frame_a.z,
            ),
            "local_frame_b": (
                self.local_frame_b.w,
                self.local_frame_b.x,
                self.local_frame_b.y,
                self.local_frame_b.z,
            ),
            "bias_factor": self.bias_factor,
        }


@dataclass(frozen=True, slots=True)
class SliderJoint:
    """Five-DOF lock with one signed translation axis, stops and motor."""

    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    local_axis_a: Vec3 = Vec3(1.0, 0.0, 0.0)
    local_axis_b: Vec3 = Vec3(1.0, 0.0, 0.0)
    local_reference_a: Vec3 = Vec3(0.0, 1.0, 0.0)
    local_reference_b: Vec3 = Vec3(0.0, 1.0, 0.0)
    bias_factor: float = 0.2
    lower_translation: float | None = None
    upper_translation: float | None = None
    motor_speed: float | None = None
    max_motor_force: float | None = None

    def __post_init__(self) -> None:
        _validate_joint_identity(self.joint_id, self.body_a, self.body_b)
        _validate_anchors(self.local_anchor_a, self.local_anchor_b)
        axis_a = _normalized_axis(self.local_axis_a, name="local_axis_a")
        axis_b = _normalized_axis(self.local_axis_b, name="local_axis_b")
        object.__setattr__(self, "local_axis_a", axis_a)
        object.__setattr__(self, "local_axis_b", axis_b)
        object.__setattr__(
            self,
            "local_reference_a",
            _reference_perpendicular(
                axis_a,
                self.local_reference_a,
                name="local_reference_a",
            ),
        )
        object.__setattr__(
            self,
            "local_reference_b",
            _reference_perpendicular(
                axis_b,
                self.local_reference_b,
                name="local_reference_b",
            ),
        )
        object.__setattr__(
            self,
            "bias_factor",
            _unit_interval(self.bias_factor, name="bias_factor"),
        )

        lower = (
            None
            if self.lower_translation is None
            else _finite(self.lower_translation, name="lower_translation")
        )
        upper = (
            None
            if self.upper_translation is None
            else _finite(self.upper_translation, name="upper_translation")
        )
        if lower is not None and upper is not None and upper < lower:
            raise PhysicsValidationError(
                "upper_translation must be greater than or equal to lower_translation"
            )
        object.__setattr__(self, "lower_translation", lower)
        object.__setattr__(self, "upper_translation", upper)

        speed = (
            None
            if self.motor_speed is None
            else _finite(self.motor_speed, name="motor_speed")
        )
        force = (
            None
            if self.max_motor_force is None
            else _positive(self.max_motor_force, name="max_motor_force")
        )
        if (speed is None) != (force is None):
            raise PhysicsValidationError(
                "slider motor requires motor_speed and max_motor_force together"
            )
        object.__setattr__(self, "motor_speed", speed)
        object.__setattr__(self, "max_motor_force", force)

    @property
    def kind(self) -> JointKind:
        return JointKind.SLIDER

    def state_record(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "local_axis_a": self.local_axis_a.to_tuple(),
            "local_axis_b": self.local_axis_b.to_tuple(),
            "local_reference_a": self.local_reference_a.to_tuple(),
            "local_reference_b": self.local_reference_b.to_tuple(),
            "bias_factor": self.bias_factor,
            "lower_translation": self.lower_translation,
            "upper_translation": self.upper_translation,
            "motor_speed": self.motor_speed,
            "max_motor_force": self.max_motor_force,
        }


JointConstraint: TypeAlias = (
    DistanceJoint
    | PointJoint
    | SpringJoint
    | DistanceLimitJoint
    | HingeJoint
    | FixedJoint
    | SliderJoint
)
JOINT_TYPES = (
    DistanceJoint,
    PointJoint,
    SpringJoint,
    DistanceLimitJoint,
    HingeJoint,
    FixedJoint,
    SliderJoint,
)


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
    hinge_joints: int = 0
    fixed_joints: int = 0
    slider_joints: int = 0
    warm_started_rows: int = 0
    cached_rows: int = 0


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
    def _angular_effective_mass(body: RigidBody, axis: Vec3) -> float:
        if body.inverse_mass <= 0.0:
            return 0.0
        return axis.dot(body.world_inverse_inertia().mul_vec(axis))

    @staticmethod
    def _apply_angular_pair_impulse(
        body_a: RigidBody,
        body_b: RigidBody,
        impulse: Vec3,
    ) -> None:
        body_a.apply_angular_impulse(-impulse)
        body_b.apply_angular_impulse(impulse)

    @staticmethod
    def _orthonormal_tangents(axis: Vec3) -> tuple[Vec3, Vec3]:
        candidates = (Vec3.axis(0), Vec3.axis(1), Vec3.axis(2))
        helper = min(candidates, key=lambda row: (abs(axis.dot(row)), row.to_tuple()))
        tangent_a = axis.cross(helper).normalized()
        tangent_b = axis.cross(tangent_a).normalized()
        return tangent_a, tangent_b

    def _solve_angular_scalar(
        self,
        body_a: RigidBody,
        body_b: RigidBody,
        axis: Vec3,
        *,
        error: float,
        bias_factor: float,
        dt: float,
        target_speed: float = 0.0,
        accumulated_impulse: float = 0.0,
        maximum_impulse: float | None = None,
        row_impulses: dict[str, float] | None = None,
        row_id: str | None = None,
    ) -> tuple[int, float]:
        denominator = (
            self._angular_effective_mass(body_a, axis)
            + self._angular_effective_mass(body_b, axis)
        )
        if denominator <= EPSILON:
            return 0, accumulated_impulse

        relative_speed = (
            body_b.angular_velocity - body_a.angular_velocity
        ).dot(axis)
        bias = bias_factor * error / dt
        delta_impulse = -(
            relative_speed - target_speed + bias
        ) / denominator
        previous = (
            accumulated_impulse
            if row_impulses is None or row_id is None
            else row_impulses.get(row_id, accumulated_impulse)
        )
        new_impulse = previous + delta_impulse
        if maximum_impulse is not None:
            new_impulse = min(
                maximum_impulse,
                max(-maximum_impulse, new_impulse),
            )
        applied = new_impulse - previous
        if row_impulses is not None and row_id is not None:
            row_impulses[row_id] = new_impulse
        if not math.isfinite(applied):
            raise PhysicsValidationError(
                "joint produced non-finite angular impulse"
            )
        if abs(applied) <= EPSILON:
            return 0, new_impulse
        self._apply_angular_pair_impulse(
            body_a,
            body_b,
            axis * applied,
        )
        return 1, new_impulse

    @staticmethod
    def _hinge_geometry(
        joint: HingeJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[Vec3, Vec3, Vec3, Vec3, float]:
        axis_a = body_a.orientation.rotate(joint.local_axis_a).normalized()
        axis_b = body_b.orientation.rotate(joint.local_axis_b).normalized()
        reference_a = body_a.orientation.rotate(
            joint.local_reference_a
        )
        reference_b = body_b.orientation.rotate(
            joint.local_reference_b
        )
        reference_a = (
            reference_a - axis_a * reference_a.dot(axis_a)
        ).normalized()
        projected_b = reference_b - axis_a * reference_b.dot(axis_a)
        if projected_b.length_squared() <= EPSILON * EPSILON:
            reference_b = reference_a
        else:
            reference_b = projected_b.normalized()
        sine = axis_a.dot(reference_a.cross(reference_b))
        cosine = max(-1.0, min(1.0, reference_a.dot(reference_b)))
        angle = math.atan2(sine, cosine)
        return axis_a, axis_b, reference_a, reference_b, angle

    @staticmethod
    def _hinge_limit_error(
        joint: HingeJoint,
        angle: float,
    ) -> float | None:
        if joint.lower_angle is not None and angle < joint.lower_angle:
            return angle - joint.lower_angle
        if joint.upper_angle is not None and angle > joint.upper_angle:
            return angle - joint.upper_angle
        return None

    @staticmethod
    def _hinge_limit_row(
        joint: HingeJoint,
        angle: float,
    ) -> str | None:
        if joint.lower_angle is not None and angle < joint.lower_angle:
            return "limit:lower"
        if joint.upper_angle is not None and angle > joint.upper_angle:
            return "limit:upper"
        return None

    @staticmethod
    def _orientation_error_vector(
        world_frame_a: Quat,
        world_frame_b: Quat,
    ) -> Vec3:
        relative = (world_frame_b * world_frame_a.conjugate()).normalized()
        if relative.w < 0.0:
            relative = Quat(
                -relative.w,
                -relative.x,
                -relative.y,
                -relative.z,
            )
        vector = Vec3(relative.x, relative.y, relative.z)
        magnitude = vector.length()
        if magnitude <= EPSILON:
            return Vec3.zero()
        angle = 2.0 * math.atan2(magnitude, max(EPSILON, relative.w))
        return vector * (angle / magnitude)

    @staticmethod
    def _slider_geometry(
        joint: SliderJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[Vec3, Vec3, Vec3, Vec3, float, Vec3]:
        axis_a = body_a.orientation.rotate(joint.local_axis_a).normalized()
        axis_b = body_b.orientation.rotate(joint.local_axis_b).normalized()
        reference_a = body_a.orientation.rotate(
            joint.local_reference_a
        )
        reference_b = body_b.orientation.rotate(
            joint.local_reference_b
        )
        reference_a = (
            reference_a - axis_a * reference_a.dot(axis_a)
        ).normalized()
        projected_b = reference_b - axis_a * reference_b.dot(axis_a)
        reference_b = (
            reference_a
            if projected_b.length_squared() <= EPSILON * EPSILON
            else projected_b.normalized()
        )
        anchors = ConstraintSolver._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        translation = delta.dot(axis_a)
        return (
            axis_a,
            axis_b,
            reference_a,
            reference_b,
            translation,
            delta,
        )

    @staticmethod
    def _slider_limit_error(
        joint: SliderJoint,
        translation: float,
    ) -> float | None:
        if (
            joint.lower_translation is not None
            and translation < joint.lower_translation
        ):
            return translation - joint.lower_translation
        if (
            joint.upper_translation is not None
            and translation > joint.upper_translation
        ):
            return translation - joint.upper_translation
        return None

    @staticmethod
    def _slider_limit_row(
        joint: SliderJoint,
        translation: float,
    ) -> str | None:
        if (
            joint.lower_translation is not None
            and translation < joint.lower_translation
        ):
            return "limit:lower"
        if (
            joint.upper_translation is not None
            and translation > joint.upper_translation
        ):
            return "limit:upper"
        return None

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

    def _warm_start_joint(
        self,
        joint: JointConstraint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        cache: JointImpulseCache | None,
        tick: int,
    ) -> tuple[dict[str, float], int]:
        rows: dict[str, float] = {}
        if cache is None:
            return rows, 0

        both_quiet = (
            (not body_a.dynamic_body or not body_a.awake)
            and (not body_b.dynamic_body or not body_b.awake)
        )
        if both_quiet:
            return rows, 0

        warm_started = 0

        def load(row_id: str) -> float:
            entry = cache.lookup(joint, row_id, tick=tick)
            if entry is None:
                return 0.0
            rows[row_id] = entry.impulse
            return entry.impulse

        def linear(row_id: str, axis: Vec3, anchors: _AnchorState) -> None:
            nonlocal warm_started
            impulse = load(row_id)
            if abs(impulse) <= EPSILON:
                return
            self._apply_impulse(
                body_a,
                body_b,
                axis * impulse,
                anchors,
            )
            warm_started += 1

        def angular(row_id: str, axis: Vec3) -> None:
            nonlocal warm_started
            impulse = load(row_id)
            if abs(impulse) <= EPSILON:
                return
            self._apply_angular_pair_impulse(
                body_a,
                body_b,
                axis * impulse,
            )
            warm_started += 1

        if isinstance(joint, DistanceJoint):
            anchors = self._anchors(joint, body_a, body_b)
            axis, _ = self._axis_and_length(
                anchors.anchor_b - anchors.anchor_a
            )
            linear("distance", axis, anchors)

        elif isinstance(joint, PointJoint):
            for axis_index in range(3):
                linear(
                    f"point:{axis_index}",
                    Vec3.axis(axis_index),
                    self._anchors(joint, body_a, body_b),
                )

        elif isinstance(joint, SpringJoint):
            anchors = self._anchors(joint, body_a, body_b)
            axis, _ = self._axis_and_length(
                anchors.anchor_b - anchors.anchor_a
            )
            linear("spring", axis, anchors)

        elif isinstance(joint, DistanceLimitJoint):
            anchors = self._anchors(joint, body_a, body_b)
            axis, length = self._axis_and_length(
                anchors.anchor_b - anchors.anchor_a
            )
            row_id = self._distance_limit_row(joint, length)
            if row_id is not None:
                linear(row_id, axis, anchors)

        elif isinstance(joint, HingeJoint):
            for axis_index in range(3):
                linear(
                    f"linear:{axis_index}",
                    Vec3.axis(axis_index),
                    self._anchors(joint, body_a, body_b),
                )
            axis_a, axis_b, _, _, angle = self._hinge_geometry(
                joint,
                body_a,
                body_b,
            )
            del axis_b
            tangent_a, tangent_b = self._orthonormal_tangents(axis_a)
            for index, tangent in enumerate((tangent_a, tangent_b)):
                angular(f"swing:{index}", tangent)
            row_id = self._hinge_limit_row(joint, angle)
            if row_id is not None:
                angular(row_id, axis_a)
            if (
                joint.motor_speed is not None
                and joint.max_motor_torque is not None
            ):
                angular("motor", axis_a)

        elif isinstance(joint, FixedJoint):
            for axis_index in range(3):
                linear(
                    f"linear:{axis_index}",
                    Vec3.axis(axis_index),
                    self._anchors(joint, body_a, body_b),
                )
                angular(
                    f"angular:{axis_index}",
                    Vec3.axis(axis_index),
                )

        elif isinstance(joint, SliderJoint):
            axis_a, axis_b, _, _, translation, _ = self._slider_geometry(
                joint,
                body_a,
                body_b,
            )
            del axis_b
            tangent_a, tangent_b = self._orthonormal_tangents(axis_a)
            for index, tangent in enumerate((tangent_a, tangent_b)):
                linear(
                    f"linear:{index}",
                    tangent,
                    self._anchors(joint, body_a, body_b),
                )
                angular(f"swing:{index}", tangent)
            angular("twist", axis_a)
            row_id = self._slider_limit_row(joint, translation)
            if row_id is not None:
                linear(
                    row_id,
                    axis_a,
                    self._anchors(joint, body_a, body_b),
                )
            if (
                joint.motor_speed is not None
                and joint.max_motor_force is not None
            ):
                linear(
                    "motor",
                    axis_a,
                    self._anchors(joint, body_a, body_b),
                )

        else:
            raise PhysicsValidationError("unsupported joint constraint")

        return rows, warm_started

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
        row_impulses: dict[str, float] | None = None,
        row_id: str | None = None,
        maximum_impulse: float | None = None,
        target_speed: float = 0.0,
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
        delta_impulse = -(
            relative_speed - target_speed + bias
        ) / denominator
        if not math.isfinite(delta_impulse):
            raise PhysicsValidationError(
                "joint produced non-finite scalar impulse"
            )

        previous = (
            0.0
            if row_impulses is None or row_id is None
            else row_impulses.get(row_id, 0.0)
        )
        accumulated = previous + delta_impulse
        if maximum_impulse is not None:
            accumulated = min(
                maximum_impulse,
                max(-maximum_impulse, accumulated),
            )
        applied = accumulated - previous
        if row_impulses is not None and row_id is not None:
            row_impulses[row_id] = accumulated
        if abs(applied) <= EPSILON:
            return 0
        self._apply_impulse(
            body_a,
            body_b,
            axis * applied,
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
        row_impulses: dict[str, float],
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
            row_impulses=row_impulses,
            row_id="distance",
        )
        return count, abs(error)

    def _solve_point_velocity(
        self,
        joint: PointJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
        row_impulses: dict[str, float],
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
                row_impulses=row_impulses,
                row_id=f"point:{axis_index}",
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

    @staticmethod
    def _distance_limit_row(
        joint: DistanceLimitJoint,
        length: float,
    ) -> str | None:
        if length < joint.minimum_length:
            return "limit:lower"
        if length > joint.maximum_length:
            return "limit:upper"
        return None

    def _solve_limit_velocity(
        self,
        joint: DistanceLimitJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
        row_impulses: dict[str, float],
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
            row_impulses=row_impulses,
            row_id=self._distance_limit_row(joint, length),
        )
        return count, abs(error)

    def _solve_spring_velocity(
        self,
        joint: SpringJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
        row_impulses: dict[str, float],
    ) -> tuple[int, float]:
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
        accumulated_impulse = row_impulses.get("spring", 0.0)
        if denominator <= EPSILON:
            return 0, abs(error)

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
        row_impulses["spring"] = new_impulse
        if abs(applied) <= EPSILON:
            return 0, abs(error)

        self._apply_impulse(
            body_a,
            body_b,
            axis * applied,
            anchors,
        )
        return 1, abs(error)

    def _solve_hinge_velocity(
        self,
        joint: HingeJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
        row_impulses: dict[str, float],
    ) -> tuple[int, float]:
        impulses = 0

        # Three translational rows keep hinge anchors coincident.
        anchors = self._anchors(joint, body_a, body_b)
        anchor_error = anchors.anchor_b - anchors.anchor_a
        maximum_error = anchor_error.length()
        for axis_index in range(3):
            anchors = self._anchors(joint, body_a, body_b)
            delta = anchors.anchor_b - anchors.anchor_a
            impulses += self._solve_scalar_velocity(
                body_a,
                body_b,
                anchors,
                Vec3.axis(axis_index),
                error=delta.to_tuple()[axis_index],
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=f"linear:{axis_index}",
            )

        axis_a, axis_b, _, _, angle = self._hinge_geometry(
            joint,
            body_a,
            body_b,
        )

        # Two angular rows remove swing and preserve twist around the hinge axis.
        swing_error = axis_a.cross(axis_b)
        tangent_a, tangent_b = self._orthonormal_tangents(axis_a)
        for tangent_index, tangent in enumerate((tangent_a, tangent_b)):
            count, _ = self._solve_angular_scalar(
                body_a,
                body_b,
                tangent,
                error=swing_error.dot(tangent),
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=f"swing:{tangent_index}",
            )
            impulses += count
        axis_misalignment = math.acos(
            max(-1.0, min(1.0, axis_a.dot(axis_b)))
        )
        maximum_error = max(maximum_error, axis_misalignment)

        limit_error = self._hinge_limit_error(joint, angle)
        if limit_error is not None:
            count, _ = self._solve_angular_scalar(
                body_a,
                body_b,
                axis_a,
                error=limit_error,
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=self._hinge_limit_row(joint, angle),
            )
            impulses += count
            maximum_error = max(maximum_error, abs(limit_error))

        if (
            joint.motor_speed is not None
            and joint.max_motor_torque is not None
        ):
            count, motor_impulse = self._solve_angular_scalar(
                body_a,
                body_b,
                axis_a,
                error=0.0,
                bias_factor=0.0,
                dt=dt,
                target_speed=joint.motor_speed,
                maximum_impulse=joint.max_motor_torque * dt,
                row_impulses=row_impulses,
                row_id="motor",
            )
            impulses += count

        return impulses, maximum_error

    def _solve_fixed_velocity(
        self,
        joint: FixedJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
        row_impulses: dict[str, float],
    ) -> tuple[int, float]:
        impulses = 0
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        maximum_error = delta.length()

        for axis_index in range(3):
            anchors = self._anchors(joint, body_a, body_b)
            current_delta = anchors.anchor_b - anchors.anchor_a
            impulses += self._solve_scalar_velocity(
                body_a,
                body_b,
                anchors,
                Vec3.axis(axis_index),
                error=current_delta.to_tuple()[axis_index],
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=f"linear:{axis_index}",
            )

        frame_a = (body_a.orientation * joint.local_frame_a).normalized()
        frame_b = (body_b.orientation * joint.local_frame_b).normalized()
        orientation_error = self._orientation_error_vector(frame_a, frame_b)
        maximum_error = max(maximum_error, orientation_error.length())
        for axis_index in range(3):
            axis = Vec3.axis(axis_index)
            count, _ = self._solve_angular_scalar(
                body_a,
                body_b,
                axis,
                error=orientation_error.to_tuple()[axis_index],
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=f"angular:{axis_index}",
            )
            impulses += count
        return impulses, maximum_error

    def _solve_slider_velocity(
        self,
        joint: SliderJoint,
        body_a: RigidBody,
        body_b: RigidBody,
        *,
        dt: float,
        row_impulses: dict[str, float],
    ) -> tuple[int, float]:
        impulses = 0
        axis_a, axis_b, reference_a, reference_b, translation, delta = (
            self._slider_geometry(joint, body_a, body_b)
        )
        tangent_a, tangent_b = self._orthonormal_tangents(axis_a)

        # Only the two perpendicular linear rows are locked.
        for tangent_index, tangent in enumerate((tangent_a, tangent_b)):
            anchors = self._anchors(joint, body_a, body_b)
            current_delta = anchors.anchor_b - anchors.anchor_a
            impulses += self._solve_scalar_velocity(
                body_a,
                body_b,
                anchors,
                tangent,
                error=current_delta.dot(tangent),
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=f"linear:{tangent_index}",
            )

        # Lock all rotational DOFs: two swing rows plus twist around slider axis.
        swing_error = axis_a.cross(axis_b)
        for tangent_index, tangent in enumerate((tangent_a, tangent_b)):
            count, _ = self._solve_angular_scalar(
                body_a,
                body_b,
                tangent,
                error=swing_error.dot(tangent),
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=f"swing:{tangent_index}",
            )
            impulses += count

        twist_sine = axis_a.dot(reference_a.cross(reference_b))
        twist_cosine = max(-1.0, min(1.0, reference_a.dot(reference_b)))
        twist_error = math.atan2(twist_sine, twist_cosine)
        count, _ = self._solve_angular_scalar(
            body_a,
            body_b,
            axis_a,
            error=twist_error,
            bias_factor=joint.bias_factor,
            dt=dt,
            row_impulses=row_impulses,
            row_id="twist",
        )
        impulses += count

        maximum_error = max(
            (delta - axis_a * translation).length(),
            math.acos(max(-1.0, min(1.0, axis_a.dot(axis_b)))),
            abs(twist_error),
        )

        limit_error = self._slider_limit_error(joint, translation)
        if limit_error is not None:
            anchors = self._anchors(joint, body_a, body_b)
            impulses += self._solve_scalar_velocity(
                body_a,
                body_b,
                anchors,
                axis_a,
                error=limit_error,
                bias_factor=joint.bias_factor,
                dt=dt,
                row_impulses=row_impulses,
                row_id=self._slider_limit_row(joint, translation),
            )
            maximum_error = max(maximum_error, abs(limit_error))

        if (
            joint.motor_speed is not None
            and joint.max_motor_force is not None
        ):
            anchors = self._anchors(joint, body_a, body_b)
            impulses += self._solve_scalar_velocity(
                body_a,
                body_b,
                anchors,
                axis_a,
                error=0.0,
                bias_factor=0.0,
                dt=dt,
                row_impulses=row_impulses,
                row_id="motor",
                maximum_impulse=joint.max_motor_force * dt,
                target_speed=joint.motor_speed,
            )

        return impulses, maximum_error

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

    def _solve_hinge_position(
        self,
        joint: HingeJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[int, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        length = delta.length()
        corrected_length = max(0.0, length - self.position_slop)
        count = 0
        if corrected_length > EPSILON and length > EPSILON:
            correction = (
                delta / length
            ) * (
                corrected_length
                * (self.position_correction / self.position_iterations)
            )
            count += self._translate_position(
                body_a,
                body_b,
                correction,
            )

        axis_a, axis_b, _, _, angle = self._hinge_geometry(
            joint,
            body_a,
            body_b,
        )
        axis_error = math.acos(
            max(-1.0, min(1.0, axis_a.dot(axis_b)))
        )
        limit_error = self._hinge_limit_error(joint, angle)
        maximum_error = max(
            length,
            axis_error,
            0.0 if limit_error is None else abs(limit_error),
        )
        return count, maximum_error

    def _solve_fixed_position(
        self,
        joint: FixedJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[int, float]:
        anchors = self._anchors(joint, body_a, body_b)
        delta = anchors.anchor_b - anchors.anchor_a
        length = delta.length()
        count = 0
        corrected = max(0.0, length - self.position_slop)
        if corrected > EPSILON and length > EPSILON:
            count += self._translate_position(
                body_a,
                body_b,
                (delta / length)
                * (
                    corrected
                    * (self.position_correction / self.position_iterations)
                ),
            )
        frame_a = (body_a.orientation * joint.local_frame_a).normalized()
        frame_b = (body_b.orientation * joint.local_frame_b).normalized()
        orientation_error = self._orientation_error_vector(frame_a, frame_b)
        return count, max(length, orientation_error.length())

    def _solve_slider_position(
        self,
        joint: SliderJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[int, float]:
        axis_a, axis_b, reference_a, reference_b, translation, delta = (
            self._slider_geometry(joint, body_a, body_b)
        )
        perpendicular = delta - axis_a * translation
        correction = perpendicular
        maximum_error = perpendicular.length()

        limit_error = self._slider_limit_error(joint, translation)
        if limit_error is not None:
            correction = correction + axis_a * limit_error
            maximum_error = max(maximum_error, abs(limit_error))

        count = 0
        length = correction.length()
        corrected = max(0.0, length - self.position_slop)
        if corrected > EPSILON and length > EPSILON:
            count += self._translate_position(
                body_a,
                body_b,
                (correction / length)
                * (
                    corrected
                    * (self.position_correction / self.position_iterations)
                ),
            )

        twist_sine = axis_a.dot(reference_a.cross(reference_b))
        twist_cosine = max(-1.0, min(1.0, reference_a.dot(reference_b)))
        maximum_error = max(
            maximum_error,
            math.acos(max(-1.0, min(1.0, axis_a.dot(axis_b)))),
            abs(math.atan2(twist_sine, twist_cosine)),
        )
        return count, maximum_error

    def solve(
        self,
        bodies: dict[str, RigidBody],
        joints: tuple[JointConstraint, ...],
        *,
        dt: float,
        cache: JointImpulseCache | None = None,
        tick: int = 0,
    ) -> ConstraintStats:
        if isinstance(dt, bool) or not isinstance(dt, (int, float)):
            raise PhysicsValidationError("constraint dt must be numeric")
        dt = float(dt)
        if not math.isfinite(dt) or dt <= 0.0:
            raise PhysicsValidationError("constraint dt must be positive")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsValidationError(
                "constraint tick must be non-negative integer"
            )

        ordered = tuple(sorted(joints, key=lambda row: row.joint_id))
        maximum_error = 0.0
        velocity_impulses = 0
        position_corrections = 0
        row_impulses: dict[str, dict[str, float]] = {}
        warm_started_rows = 0

        counts = {
            JointKind.DISTANCE: 0,
            JointKind.POINT: 0,
            JointKind.SPRING: 0,
            JointKind.DISTANCE_LIMIT: 0,
            JointKind.HINGE: 0,
            JointKind.FIXED: 0,
            JointKind.SLIDER: 0,
        }

        for joint in ordered:
            body_a, body_b = self._validate_joint(joint, bodies)
            counts[joint.kind] += 1
            rows, warmed = self._warm_start_joint(
                joint,
                body_a,
                body_b,
                cache=cache,
                tick=tick,
            )
            row_impulses[joint.joint_id] = rows
            warm_started_rows += warmed

        for _ in range(self.velocity_iterations):
            for joint in ordered:
                body_a, body_b = self._validate_joint(joint, bodies)
                if isinstance(joint, DistanceJoint):
                    count, error = self._solve_distance_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        row_impulses=row_impulses[joint.joint_id],
                    )
                elif isinstance(joint, PointJoint):
                    count, error = self._solve_point_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        row_impulses=row_impulses[joint.joint_id],
                    )
                elif isinstance(joint, SpringJoint):
                    count, error = self._solve_spring_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        row_impulses=row_impulses[joint.joint_id],
                    )
                elif isinstance(joint, DistanceLimitJoint):
                    count, error = self._solve_limit_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        row_impulses=row_impulses[joint.joint_id],
                    )
                elif isinstance(joint, HingeJoint):
                    count, error = self._solve_hinge_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        row_impulses=row_impulses[joint.joint_id],
                    )
                elif isinstance(joint, FixedJoint):
                    count, error = self._solve_fixed_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        row_impulses=row_impulses[joint.joint_id],
                    )
                elif isinstance(joint, SliderJoint):
                    count, error = self._solve_slider_velocity(
                        joint,
                        body_a,
                        body_b,
                        dt=dt,
                        row_impulses=row_impulses[joint.joint_id],
                    )
                else:
                    raise PhysicsValidationError("unsupported joint constraint")
                velocity_impulses += count
                maximum_error = max(maximum_error, error)

        if cache is not None:
            joint_by_id = {joint.joint_id: joint for joint in ordered}
            for joint_id in sorted(row_impulses):
                joint = joint_by_id[joint_id]
                for row_id in sorted(row_impulses[joint_id]):
                    cache.store(
                        joint,
                        row_id,
                        impulse=row_impulses[joint_id][row_id],
                        tick=tick,
                    )
            cache.prune(tick=tick)

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
                elif isinstance(joint, HingeJoint):
                    count, error = self._solve_hinge_position(
                        joint,
                        body_a,
                        body_b,
                    )
                elif isinstance(joint, FixedJoint):
                    count, error = self._solve_fixed_position(
                        joint,
                        body_a,
                        body_b,
                    )
                elif isinstance(joint, SliderJoint):
                    count, error = self._solve_slider_position(
                        joint,
                        body_a,
                        body_b,
                    )
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
            hinge_joints=counts[JointKind.HINGE],
            fixed_joints=counts[JointKind.FIXED],
            slider_joints=counts[JointKind.SLIDER],
            warm_started_rows=warm_started_rows,
            cached_rows=0 if cache is None else len(cache),
        )
