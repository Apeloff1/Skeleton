"""Probability and information-theory primitives with strict evidence semantics."""
from __future__ import annotations

import math
from numbers import Real
from typing import Iterable, Sequence

from .contracts import MathInvariantError, Vector, finite_vector, same_length
from .numerics import compensated_sum


def normalize_distribution(values: Sequence[Real] | Iterable[Real]) -> Vector:
    vector = finite_vector("values", values)
    if any(value < 0.0 for value in vector):
        raise MathInvariantError(
            "probability weights must be non-negative",
            reason="negative_probability",
            field="values",
        )
    total = compensated_sum(vector)
    if total <= 0.0:
        raise MathInvariantError(
            "probability mass must be positive",
            reason="zero_probability_mass",
            field="values",
        )
    normalized = tuple(value / total for value in vector)
    correction = 1.0 - compensated_sum(normalized)
    if correction:
        index = max(range(len(normalized)), key=normalized.__getitem__)
        mutable = list(normalized)
        mutable[index] += correction
        normalized = tuple(mutable)
    return normalized


def entropy(values: Sequence[Real] | Iterable[Real]) -> float:
    probabilities = normalize_distribution(values)
    return -compensated_sum(p * math.log(p) for p in probabilities if p > 0.0)


def cross_entropy(
    expected: Sequence[Real] | Iterable[Real],
    candidate: Sequence[Real] | Iterable[Real],
) -> float:
    p = normalize_distribution(expected)
    q = normalize_distribution(candidate)
    same_length("cross_entropy", p, q)
    terms: list[float] = []
    for left, right in zip(p, q):
        if left == 0.0:
            continue
        if right == 0.0:
            raise MathInvariantError(
                "candidate assigns zero mass where expected mass is positive",
                reason="zero_support_probability",
                field="candidate",
            )
        terms.append(-left * math.log(right))
    return compensated_sum(terms)


def kl_divergence(
    expected: Sequence[Real] | Iterable[Real],
    candidate: Sequence[Real] | Iterable[Real],
) -> float:
    p = normalize_distribution(expected)
    q = normalize_distribution(candidate)
    same_length("kl_divergence", p, q)
    terms: list[float] = []
    for left, right in zip(p, q):
        if left == 0.0:
            continue
        if right == 0.0:
            raise MathInvariantError(
                "KL divergence is infinite because candidate support is missing",
                reason="infinite_divergence",
                field="candidate",
            )
        terms.append(left * math.log(left / right))
    value = compensated_sum(terms)
    if value < 0.0 and abs(value) <= 1e-14:
        return 0.0
    if value < 0.0:
        raise MathInvariantError(
            "KL divergence violated non-negativity",
            reason="numerical_invariant_failure",
            field="kl_divergence",
        )
    return value


def jensen_shannon_divergence(
    left: Sequence[Real] | Iterable[Real],
    right: Sequence[Real] | Iterable[Real],
) -> float:
    p = normalize_distribution(left)
    q = normalize_distribution(right)
    same_length("jensen_shannon_divergence", p, q)
    midpoint = tuple((a + b) * 0.5 for a, b in zip(p, q))
    return 0.5 * kl_divergence(p, midpoint) + 0.5 * kl_divergence(q, midpoint)


def effective_sample_size(weights: Sequence[Real] | Iterable[Real]) -> float:
    probabilities = normalize_distribution(weights)
    concentration = compensated_sum(value * value for value in probabilities)
    if concentration <= 0.0:
        raise MathInvariantError(
            "effective sample size concentration is invalid",
            reason="invalid_normalization",
            field="weights",
        )
    return 1.0 / concentration


def weighted_moments(
    values: Sequence[Real] | Iterable[Real],
    weights: Sequence[Real] | Iterable[Real],
) -> tuple[float, float]:
    observations = finite_vector("values", values)
    probabilities = normalize_distribution(weights)
    same_length("weighted_moments", observations, probabilities)
    mean = compensated_sum(value * weight for value, weight in zip(observations, probabilities))
    variance = compensated_sum(
        weight * (value - mean) * (value - mean)
        for value, weight in zip(observations, probabilities)
    )
    if variance < 0.0 and abs(variance) <= 1e-14:
        variance = 0.0
    if variance < 0.0:
        raise MathInvariantError(
            "weighted variance violated non-negativity",
            reason="numerical_invariant_failure",
            field="variance",
        )
    return mean, variance
