"""Small, dependency-free 3D math primitives for deterministic simulation.

The implementation intentionally avoids NumPy and engine-specific vector types so
physics state can be serialized, replayed, tested, and embedded in server-side
simulation.  Every public primitive rejects NaN and infinity at construction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import DegenerateGeometryError, PhysicsValidationError

EPSILON = 1.0e-9
NORMAL_EPSILON = 1.0e-12


def _finite(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise PhysicsValidationError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, name="x"))
        object.__setattr__(self, "y", _finite(self.y, name="y"))
        object.__setattr__(self, "z", _finite(self.z, name="z"))

    @staticmethod
    def zero() -> "Vec3":
        return Vec3()

    @staticmethod
    def one() -> "Vec3":
        return Vec3(1.0, 1.0, 1.0)

    @staticmethod
    def axis(index: int) -> "Vec3":
        if index == 0:
            return Vec3(1.0, 0.0, 0.0)
        if index == 1:
            return Vec3(0.0, 1.0, 0.0)
        if index == 2:
            return Vec3(0.0, 0.0, 1.0)
        raise PhysicsValidationError("axis index must be 0, 1, or 2")

    def __add__(self, other: "Vec3") -> "Vec3":
        if not isinstance(other, Vec3):
            return NotImplemented
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        if not isinstance(other, Vec3):
            return NotImplemented
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __neg__(self) -> "Vec3":
        return Vec3(-self.x, -self.y, -self.z)

    def __mul__(self, scalar: float) -> "Vec3":
        scalar = _finite(scalar, name="scalar")
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> "Vec3":
        return self * scalar

    def __truediv__(self, scalar: float) -> "Vec3":
        scalar = _finite(scalar, name="scalar")
        if abs(scalar) <= EPSILON:
            raise PhysicsValidationError("cannot divide vector by zero")
        inv = 1.0 / scalar
        return self * inv

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def hadamard(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x * other.x, self.y * other.y, self.z * other.z)

    def length_squared(self) -> float:
        return self.dot(self)

    def length(self) -> float:
        return math.sqrt(self.length_squared())

    def normalized(self, *, fallback: "Vec3 | None" = None) -> "Vec3":
        length = self.length()
        if length <= NORMAL_EPSILON:
            if fallback is not None:
                return fallback.normalized()
            raise DegenerateGeometryError("cannot normalize near-zero vector")
        return self / length

    def normalized_or_zero(self) -> "Vec3":
        length = self.length()
        return Vec3.zero() if length <= NORMAL_EPSILON else self / length

    def clamp(self, minimum: "Vec3", maximum: "Vec3") -> "Vec3":
        return Vec3(
            min(max(self.x, minimum.x), maximum.x),
            min(max(self.y, minimum.y), maximum.y),
            min(max(self.z, minimum.z), maximum.z),
        )

    def abs(self) -> "Vec3":
        return Vec3(abs(self.x), abs(self.y), abs(self.z))

    def min(self, other: "Vec3") -> "Vec3":
        return Vec3(min(self.x, other.x), min(self.y, other.y), min(self.z, other.z))

    def max(self, other: "Vec3") -> "Vec3":
        return Vec3(max(self.x, other.x), max(self.y, other.y), max(self.z, other.z))

    def max_component(self) -> float:
        return max(self.x, self.y, self.z)

    def min_component(self) -> float:
        return min(self.x, self.y, self.z)

    def almost_equal(self, other: "Vec3", *, tolerance: float = 1.0e-9) -> bool:
        return (
            abs(self.x - other.x) <= tolerance
            and abs(self.y - other.y) <= tolerance
            and abs(self.z - other.z) <= tolerance
        )

    def to_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True, slots=True)
class Mat3:
    m00: float
    m01: float
    m02: float
    m10: float
    m11: float
    m12: float
    m20: float
    m21: float
    m22: float

    def __post_init__(self) -> None:
        for name in (
            "m00", "m01", "m02", "m10", "m11", "m12", "m20", "m21", "m22"
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name=name))

    @staticmethod
    def identity() -> "Mat3":
        return Mat3(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

    @staticmethod
    def zero() -> "Mat3":
        return Mat3(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    @staticmethod
    def diagonal(value: Vec3) -> "Mat3":
        return Mat3(value.x, 0.0, 0.0, 0.0, value.y, 0.0, 0.0, 0.0, value.z)

    @staticmethod
    def from_columns(x: Vec3, y: Vec3, z: Vec3) -> "Mat3":
        return Mat3(x.x, y.x, z.x, x.y, y.y, z.y, x.z, y.z, z.z)

    def row(self, index: int) -> Vec3:
        if index == 0:
            return Vec3(self.m00, self.m01, self.m02)
        if index == 1:
            return Vec3(self.m10, self.m11, self.m12)
        if index == 2:
            return Vec3(self.m20, self.m21, self.m22)
        raise PhysicsValidationError("row index must be 0, 1, or 2")

    def column(self, index: int) -> Vec3:
        if index == 0:
            return Vec3(self.m00, self.m10, self.m20)
        if index == 1:
            return Vec3(self.m01, self.m11, self.m21)
        if index == 2:
            return Vec3(self.m02, self.m12, self.m22)
        raise PhysicsValidationError("column index must be 0, 1, or 2")

    def __add__(self, other: "Mat3") -> "Mat3":
        if not isinstance(other, Mat3):
            return NotImplemented
        return Mat3(*(a + b for a, b in zip(self.to_tuple(), other.to_tuple())))

    def __mul__(self, scalar: float) -> "Mat3":
        scalar = _finite(scalar, name="scalar")
        return Mat3(*(value * scalar for value in self.to_tuple()))

    def __rmul__(self, scalar: float) -> "Mat3":
        return self * scalar

    def mul_vec(self, vector: Vec3) -> Vec3:
        return Vec3(self.row(0).dot(vector), self.row(1).dot(vector), self.row(2).dot(vector))

    def mul_mat(self, other: "Mat3") -> "Mat3":
        rows = [self.row(i) for i in range(3)]
        cols = [other.column(i) for i in range(3)]
        values = [rows[r].dot(cols[c]) for r in range(3) for c in range(3)]
        return Mat3(*values)

    def transpose(self) -> "Mat3":
        return Mat3(
            self.m00, self.m10, self.m20,
            self.m01, self.m11, self.m21,
            self.m02, self.m12, self.m22,
        )

    def determinant(self) -> float:
        return (
            self.m00 * (self.m11 * self.m22 - self.m12 * self.m21)
            - self.m01 * (self.m10 * self.m22 - self.m12 * self.m20)
            + self.m02 * (self.m10 * self.m21 - self.m11 * self.m20)
        )

    def inverse(self) -> "Mat3":
        det = self.determinant()
        if abs(det) <= EPSILON:
            raise DegenerateGeometryError("matrix is singular")
        inv = 1.0 / det
        return Mat3(
            (self.m11 * self.m22 - self.m12 * self.m21) * inv,
            (self.m02 * self.m21 - self.m01 * self.m22) * inv,
            (self.m01 * self.m12 - self.m02 * self.m11) * inv,
            (self.m12 * self.m20 - self.m10 * self.m22) * inv,
            (self.m00 * self.m22 - self.m02 * self.m20) * inv,
            (self.m02 * self.m10 - self.m00 * self.m12) * inv,
            (self.m10 * self.m21 - self.m11 * self.m20) * inv,
            (self.m01 * self.m20 - self.m00 * self.m21) * inv,
            (self.m00 * self.m11 - self.m01 * self.m10) * inv,
        )

    def to_tuple(self) -> tuple[float, ...]:
        return (
            self.m00, self.m01, self.m02,
            self.m10, self.m11, self.m12,
            self.m20, self.m21, self.m22,
        )


@dataclass(frozen=True, slots=True)
class Quat:
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "w", _finite(self.w, name="w"))
        object.__setattr__(self, "x", _finite(self.x, name="x"))
        object.__setattr__(self, "y", _finite(self.y, name="y"))
        object.__setattr__(self, "z", _finite(self.z, name="z"))

    @staticmethod
    def identity() -> "Quat":
        return Quat()

    @staticmethod
    def from_axis_angle(axis: Vec3, radians: float) -> "Quat":
        radians = _finite(radians, name="radians")
        axis = axis.normalized()
        half = radians * 0.5
        scale = math.sin(half)
        return Quat(math.cos(half), axis.x * scale, axis.y * scale, axis.z * scale)

    def __add__(self, other: "Quat") -> "Quat":
        if not isinstance(other, Quat):
            return NotImplemented
        return Quat(self.w + other.w, self.x + other.x, self.y + other.y, self.z + other.z)

    def __mul__(self, other: "Quat | float") -> "Quat":
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            scalar = _finite(other, name="scalar")
            return Quat(self.w * scalar, self.x * scalar, self.y * scalar, self.z * scalar)
        if not isinstance(other, Quat):
            return NotImplemented
        return Quat(
            self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z,
            self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y,
            self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x,
            self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w,
        )

    def __rmul__(self, scalar: float) -> "Quat":
        return self * scalar

    def length_squared(self) -> float:
        return self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z

    def normalized(self) -> "Quat":
        length = math.sqrt(self.length_squared())
        if length <= NORMAL_EPSILON:
            raise DegenerateGeometryError("cannot normalize near-zero quaternion")
        inv = 1.0 / length
        return Quat(self.w * inv, self.x * inv, self.y * inv, self.z * inv)

    def conjugate(self) -> "Quat":
        return Quat(self.w, -self.x, -self.y, -self.z)

    def rotate(self, vector: Vec3) -> Vec3:
        q = self.normalized()
        qv = Vec3(q.x, q.y, q.z)
        t = 2.0 * qv.cross(vector)
        return vector + q.w * t + qv.cross(t)

    def to_matrix(self) -> Mat3:
        q = self.normalized()
        w, x, y, z = q.w, q.x, q.y, q.z
        return Mat3(
            1.0 - 2.0 * (y * y + z * z),
            2.0 * (x * y - z * w),
            2.0 * (x * z + y * w),
            2.0 * (x * y + z * w),
            1.0 - 2.0 * (x * x + z * z),
            2.0 * (y * z - x * w),
            2.0 * (x * z - y * w),
            2.0 * (y * z + x * w),
            1.0 - 2.0 * (x * x + y * y),
        )

    def integrate_world_angular_velocity(self, angular_velocity: Vec3, dt: float) -> "Quat":
        dt = _finite(dt, name="dt")
        if dt < 0.0:
            raise PhysicsValidationError("dt must be non-negative")
        omega = Quat(0.0, angular_velocity.x, angular_velocity.y, angular_velocity.z)
        derivative = (omega * self) * 0.5
        return (self + derivative * dt).normalized()


@dataclass(frozen=True, slots=True)
class Transform:
    position: Vec3 = Vec3()
    rotation: Quat = Quat()

    def transform_point(self, point: Vec3) -> Vec3:
        return self.position + self.rotation.rotate(point)

    def transform_vector(self, vector: Vec3) -> Vec3:
        return self.rotation.rotate(vector)

    def inverse_transform_point(self, point: Vec3) -> Vec3:
        return self.rotation.conjugate().normalized().rotate(point - self.position)

    def inverse_transform_vector(self, vector: Vec3) -> Vec3:
        return self.rotation.conjugate().normalized().rotate(vector)


@dataclass(frozen=True, slots=True)
class AABB:
    minimum: Vec3
    maximum: Vec3

    def __post_init__(self) -> None:
        if (
            self.minimum.x > self.maximum.x
            or self.minimum.y > self.maximum.y
            or self.minimum.z > self.maximum.z
        ):
            raise PhysicsValidationError("AABB minimum must not exceed maximum")

    @staticmethod
    def from_center_half_extents(center: Vec3, half_extents: Vec3) -> "AABB":
        if half_extents.min_component() < 0.0:
            raise PhysicsValidationError("AABB half extents must be non-negative")
        return AABB(center - half_extents, center + half_extents)

    def center(self) -> Vec3:
        return (self.minimum + self.maximum) * 0.5

    def half_extents(self) -> Vec3:
        return (self.maximum - self.minimum) * 0.5

    def overlaps(self, other: "AABB") -> bool:
        return not (
            self.maximum.x < other.minimum.x
            or self.minimum.x > other.maximum.x
            or self.maximum.y < other.minimum.y
            or self.minimum.y > other.maximum.y
            or self.maximum.z < other.minimum.z
            or self.minimum.z > other.maximum.z
        )

    def contains(self, point: Vec3) -> bool:
        return (
            self.minimum.x <= point.x <= self.maximum.x
            and self.minimum.y <= point.y <= self.maximum.y
            and self.minimum.z <= point.z <= self.maximum.z
        )

    def combine(self, other: "AABB") -> "AABB":
        return AABB(self.minimum.min(other.minimum), self.maximum.max(other.maximum))

    def expanded(self, amount: float) -> "AABB":
        amount = _finite(amount, name="amount")
        if amount < 0.0:
            raise PhysicsValidationError("AABB expansion must be non-negative")
        delta = Vec3.one() * amount
        return AABB(self.minimum - delta, self.maximum + delta)

    def surface_area(self) -> float:
        size = self.maximum - self.minimum
        return 2.0 * (size.x * size.y + size.y * size.z + size.z * size.x)
