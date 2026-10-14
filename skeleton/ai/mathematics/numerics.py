"""Numerically stable scalar/vector primitives used as AI reference math."""
from __future__ import annotations

import math
from numbers import Real
from typing import Iterable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar


def compensated_sum(values: Iterable[Real]) -> float:
    """Neumaier compensated sum with fail-closed finite validation."""

    total = 0.0
    correction = 0.0
    seen = False
    for index, raw in enumerate(values):
        value = finite_scalar(f"values[{index}]", raw)
        seen = True
        merged = total + value
        if abs(total) >= abs(value):
            correction += (total - merged) + value
        else:
            correction += (value - merged) + total
        total = merged
    if not seen:
        return 0.0
    result = total + correction
    if not math.isfinite(result):
        raise MathInvariantError(
            "compensated sum overflowed",
            reason="non_finite_result",
            field="values",
        )
    return result


def stable_mean(values: Sequence[Real] | Iterable[Real]) -> float:
    vector = finite_vector("values", values)
    return compensated_sum(vector) / len(vector)


def logsumexp(values: Sequence[Real] | Iterable[Real]) -> float:
    vector = finite_vector("values", values)
    maximum = max(vector)
    shifted = (math.exp(value - maximum) for value in vector)
    result = maximum + math.log(compensated_sum(shifted))
    if not math.isfinite(result):
        raise MathInvariantError(
            "logsumexp produced a non-finite result",
            reason="non_finite_result",
            field="values",
        )
    return result


def stable_softmax(
    values: Sequence[Real] | Iterable[Real],
    *,
    temperature: Real = 1.0,
) -> Vector:
    vector = finite_vector("values", values)
    temp = positive_scalar("temperature", temperature)
    scaled = tuple(value / temp for value in vector)
    maximum = max(scaled)
    exponentials = tuple(math.exp(value - maximum) for value in scaled)
    denominator = compensated_sum(exponentials)
    if denominator <= 0.0 or not math.isfinite(denominator):
        raise MathInvariantError(
            "softmax normalization is invalid",
            reason="invalid_normalization",
            field="values",
        )
    output = tuple(value / denominator for value in exponentials)
    if any(not math.isfinite(value) for value in output):
        raise MathInvariantError(
            "softmax produced non-finite probabilities",
            reason="non_finite_result",
            field="values",
        )
    return output


def normalize_log_weights(
    log_weights: Sequence[Real] | Iterable[Real],
) -> tuple[Vector, float]:
    vector = finite_vector("log_weights", log_weights)
    normalizer = logsumexp(vector)
    probabilities = tuple(math.exp(value - normalizer) for value in vector)
    total = compensated_sum(probabilities)
    if total <= 0.0:
        raise MathInvariantError(
            "log-weight normalization collapsed",
            reason="invalid_normalization",
            field="log_weights",
        )
    normalized = tuple(value / total for value in probabilities)
    return normalized, normalizer


def relative_error(reference: Real, candidate: Real, *, floor: Real = 1e-15) -> float:
    ref = finite_scalar("reference", reference)
    got = finite_scalar("candidate", candidate)
    denominator = max(abs(ref), positive_scalar("floor", floor))
    return abs(got - ref) / denominator


def almost_equal(
    reference: Real,
    candidate: Real,
    *,
    absolute_tolerance: Real = 1e-12,
    relative_tolerance: Real = 1e-9,
) -> bool:
    ref = finite_scalar("reference", reference)
    got = finite_scalar("candidate", candidate)
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    return abs(got - ref) <= max(abs_tol, rel_tol * max(abs(ref), abs(got)))
