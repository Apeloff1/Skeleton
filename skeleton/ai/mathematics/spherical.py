"""Unit-sphere geodesic, logarithmic, exponential, and interpolation references."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import dot, l2_norm


def unit_vector(values: Sequence[Real]) -> Vector:
    vector = finite_vector("values", values)
    norm = l2_norm(vector)
    if norm == 0.0:
        raise MathInvariantError(
            "unit-sphere geometry requires a non-zero vector",
            reason="zero_norm",
            field="values",
        )
    return tuple(value / norm for value in vector)


def spherical_angle(left: Sequence[Real], right: Sequence[Real]) -> float:
    a = unit_vector(left)
    b = unit_vector(right)
    if len(a) != len(b):
        raise MathInvariantError(
            "spherical vectors must share dimension",
            reason="dimension_mismatch",
            field="vectors",
        )
    cosine = max(-1.0, min(1.0, dot(a, b)))
    return math.acos(cosine)


def great_circle_distance(
    left: Sequence[Real],
    right: Sequence[Real],
    *,
    radius: Real = 1.0,
) -> float:
    scale = positive_scalar("radius", radius)
    return scale * spherical_angle(left, right)


def sphere_log_map(base: Sequence[Real], target: Sequence[Real]) -> Vector:
    p = unit_vector(base)
    q = unit_vector(target)
    if len(p) != len(q):
        raise MathInvariantError(
            "sphere log-map vectors must share dimension",
            reason="dimension_mismatch",
            field="vectors",
        )
    cosine = max(-1.0, min(1.0, dot(p, q)))
    angle = math.acos(cosine)
    if angle <= 1e-15:
        return tuple(0.0 for _ in p)
    if math.pi - angle <= 1e-12:
        raise MathInvariantError(
            "sphere log map is ambiguous at antipodal points",
            reason="antipodal_ambiguity",
            field="target",
        )
    tangent = tuple(q[i] - cosine * p[i] for i in range(len(p)))
    norm = l2_norm(tangent)
    return tuple(angle * value / norm for value in tangent)


def sphere_exp_map(base: Sequence[Real], tangent: Sequence[Real]) -> Vector:
    p = unit_vector(base)
    v = finite_vector("tangent", tangent)
    if len(p) != len(v):
        raise MathInvariantError(
            "sphere exp-map tangent dimension mismatch",
            reason="dimension_mismatch",
            field="tangent",
        )
    radial = dot(p, v)
    if abs(radial) > 1e-10 * max(1.0, l2_norm(v)):
        raise MathInvariantError(
            "sphere exp-map tangent must be orthogonal to base",
            reason="non_tangent_vector",
            field="tangent",
        )
    norm = l2_norm(v)
    if norm == 0.0:
        return p
    result = tuple(
        math.cos(norm) * p[i] + math.sin(norm) * v[i] / norm
        for i in range(len(p))
    )
    return unit_vector(result)


def spherical_interpolate(
    left: Sequence[Real],
    right: Sequence[Real],
    fraction: Real,
) -> Vector:
    p = unit_vector(left)
    q = unit_vector(right)
    if len(p) != len(q):
        raise MathInvariantError(
            "spherical interpolation vectors must share dimension",
            reason="dimension_mismatch",
            field="vectors",
        )
    t = finite_scalar("fraction", fraction)
    if not 0.0 <= t <= 1.0:
        raise MathInvariantError(
            "spherical interpolation fraction must lie in [0, 1]",
            reason="invalid_probability",
            field="fraction",
        )
    angle = spherical_angle(p, q)
    if angle <= 1e-15:
        return p
    if math.pi - angle <= 1e-12:
        raise MathInvariantError(
            "spherical interpolation is ambiguous for antipodal points",
            reason="antipodal_ambiguity",
            field="right",
        )
    sine = math.sin(angle)
    left_weight = math.sin((1.0 - t) * angle) / sine
    right_weight = math.sin(t * angle) / sine
    return unit_vector(
        tuple(left_weight * p[i] + right_weight * q[i] for i in range(len(p)))
    )
