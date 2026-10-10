"""Convex proximal and projection reference operators."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import l2_norm
from .numerics import compensated_sum


def soft_threshold(value: Real, threshold: Real) -> float:
    x = finite_scalar("value", value)
    lam = finite_scalar("threshold", threshold)
    if lam < 0.0:
        raise MathInvariantError(
            "soft-threshold parameter must be non-negative",
            reason="negative_threshold",
            field="threshold",
        )
    if x > lam:
        return x - lam
    if x < -lam:
        return x + lam
    return 0.0


def soft_threshold_vector(values: Sequence[Real], threshold: Real) -> Vector:
    vector = finite_vector("values", values)
    return tuple(soft_threshold(value, threshold) for value in vector)


def project_l2_ball(
    values: Sequence[Real],
    radius: Real = 1.0,
) -> Vector:
    vector = finite_vector("values", values)
    bound = positive_scalar("radius", radius)
    norm = l2_norm(vector)
    if norm <= bound:
        return vector
    factor = bound / norm
    return tuple(value * factor for value in vector)


def project_linf_ball(
    values: Sequence[Real],
    radius: Real = 1.0,
) -> Vector:
    vector = finite_vector("values", values)
    bound = positive_scalar("radius", radius)
    return tuple(max(-bound, min(bound, value)) for value in vector)


def project_l1_ball(
    values: Sequence[Real],
    radius: Real = 1.0,
) -> Vector:
    vector = finite_vector("values", values)
    bound = positive_scalar("radius", radius)
    norm = compensated_sum(abs(value) for value in vector)
    if norm <= bound:
        return vector
    ordered = sorted((abs(value) for value in vector), reverse=True)
    cumulative = 0.0
    rho = -1
    theta = 0.0
    for index, value in enumerate(ordered):
        cumulative += value
        candidate = (cumulative - bound) / (index + 1)
        if value > candidate:
            rho = index
            theta = candidate
    if rho < 0:
        raise MathInvariantError(
            "L1 projection failed to identify an active set",
            reason="numerical_invariant_failure",
            field="values",
        )
    return tuple(
        math.copysign(max(abs(value) - theta, 0.0), value)
        if value != 0.0 else 0.0
        for value in vector
    )


def proximal_elastic_net(
    values: Sequence[Real],
    *,
    step_size: Real,
    l1_weight: Real,
    l2_weight: Real,
) -> Vector:
    vector = finite_vector("values", values)
    step = positive_scalar("step_size", step_size)
    l1 = finite_scalar("l1_weight", l1_weight)
    l2 = finite_scalar("l2_weight", l2_weight)
    if l1 < 0.0 or l2 < 0.0:
        raise MathInvariantError(
            "elastic-net weights must be non-negative",
            reason="negative_regularization",
            field="weights",
        )
    denominator = 1.0 + step * l2
    threshold = step * l1
    return tuple(
        soft_threshold(value, threshold) / denominator
        for value in vector
    )


def group_l2_shrinkage(
    values: Sequence[Real],
    threshold: Real,
) -> Vector:
    vector = finite_vector("values", values)
    lam = finite_scalar("threshold", threshold)
    if lam < 0.0:
        raise MathInvariantError(
            "group threshold must be non-negative",
            reason="negative_threshold",
            field="threshold",
        )
    norm = l2_norm(vector)
    if norm == 0.0 or norm <= lam:
        return tuple(0.0 for _ in vector)
    factor = 1.0 - lam / norm
    return tuple(value * factor for value in vector)
