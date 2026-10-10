"""Quaternion and rigid-rotation reference mathematics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector


@dataclass(frozen=True, slots=True)
class Quaternion:
    w: float
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "w", finite_scalar("w", self.w))
        object.__setattr__(self, "x", finite_scalar("x", self.x))
        object.__setattr__(self, "y", finite_scalar("y", self.y))
        object.__setattr__(self, "z", finite_scalar("z", self.z))

    @property
    def norm(self) -> float:
        return math.sqrt(self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> "Quaternion":
        norm = self.norm
        if norm == 0.0:
            raise MathInvariantError(
                "zero quaternion cannot represent a rotation",
                reason="zero_norm",
                field="quaternion",
            )
        return Quaternion(self.w / norm, self.x / norm, self.y / norm, self.z / norm)

    def conjugate(self) -> "Quaternion":
        return Quaternion(self.w, -self.x, -self.y, -self.z)


def quaternion_from_axis_angle(axis: Sequence[Real], angle: Real) -> Quaternion:
    vector = finite_vector("axis", axis)
    if len(vector) != 3:
        raise MathInvariantError(
            "rotation axis must be three-dimensional",
            reason="dimension_mismatch",
            field="axis",
        )
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise MathInvariantError(
            "rotation axis must be non-zero",
            reason="zero_norm",
            field="axis",
        )
    theta = finite_scalar("angle", angle)
    half = 0.5 * theta
    scale = math.sin(half) / norm
    return Quaternion(math.cos(half), *(value * scale for value in vector)).normalized()


def quaternion_multiply(left: Quaternion, right: Quaternion) -> Quaternion:
    return Quaternion(
        left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
        left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
        left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
        left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w,
    )


def quaternion_rotate_vector(quaternion: Quaternion, vector: Sequence[Real]) -> Vector:
    q = quaternion.normalized()
    values = finite_vector("vector", vector)
    if len(values) != 3:
        raise MathInvariantError(
            "rotated vector must be three-dimensional",
            reason="dimension_mismatch",
            field="vector",
        )
    pure = Quaternion(0.0, values[0], values[1], values[2])
    result = quaternion_multiply(quaternion_multiply(q, pure), q.conjugate())
    return (result.x, result.y, result.z)


def quaternion_slerp(left: Quaternion, right: Quaternion, fraction: Real) -> Quaternion:
    t = finite_scalar("fraction", fraction)
    if not 0.0 <= t <= 1.0:
        raise MathInvariantError(
            "SLERP fraction must lie in [0, 1]",
            reason="invalid_interpolation_fraction",
            field="fraction",
        )
    a = left.normalized()
    b = right.normalized()
    dot = a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z
    if dot < 0.0:
        b = Quaternion(-b.w, -b.x, -b.y, -b.z)
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        blended = Quaternion(
            a.w + t * (b.w - a.w),
            a.x + t * (b.x - a.x),
            a.y + t * (b.y - a.y),
            a.z + t * (b.z - a.z),
        )
        return blended.normalized()
    theta = math.acos(dot)
    sin_theta = math.sin(theta)
    first = math.sin((1.0 - t) * theta) / sin_theta
    second = math.sin(t * theta) / sin_theta
    return Quaternion(
        first * a.w + second * b.w,
        first * a.x + second * b.x,
        first * a.y + second * b.y,
        first * a.z + second * b.z,
    ).normalized()


def quaternion_to_rotation_matrix(quaternion: Quaternion) -> Matrix:
    q = quaternion.normalized()
    w, x, y, z = q.w, q.x, q.y, q.z
    return (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    )
