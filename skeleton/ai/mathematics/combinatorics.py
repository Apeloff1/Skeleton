"""Exact combinatorial counts and stable discrete probability mass references."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, finite_scalar
from .numerics import compensated_sum
from .probability import normalize_distribution


def _non_negative_integer(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MathInvariantError(
            f"{name} must be a non-negative integer",
            reason="invalid_count",
            field=name,
        )
    return value


def log_factorial(n: int) -> float:
    count = _non_negative_integer("n", n)
    return math.lgamma(count + 1.0)


def binomial_coefficient(n: int, k: int) -> int:
    total = _non_negative_integer("n", n)
    chosen = _non_negative_integer("k", k)
    if chosen > total:
        raise MathInvariantError(
            "k must not exceed n",
            reason="invalid_count",
            field="k",
        )
    return math.comb(total, chosen)


def log_binomial_coefficient(n: int, k: int) -> float:
    total = _non_negative_integer("n", n)
    chosen = _non_negative_integer("k", k)
    if chosen > total:
        raise MathInvariantError(
            "k must not exceed n",
            reason="invalid_count",
            field="k",
        )
    return log_factorial(total) - log_factorial(chosen) - log_factorial(total - chosen)


def binomial_log_pmf(successes: int, trials: int, probability: Real) -> float:
    k = _non_negative_integer("successes", successes)
    n = _non_negative_integer("trials", trials)
    if k > n:
        raise MathInvariantError(
            "successes must not exceed trials",
            reason="invalid_count",
            field="successes",
        )
    p = finite_scalar("probability", probability)
    if not 0.0 <= p <= 1.0:
        raise MathInvariantError(
            "probability must lie in [0, 1]",
            reason="invalid_probability",
            field="probability",
        )
    if p == 0.0:
        if k == 0:
            return 0.0
        raise MathInvariantError(
            "positive successes have zero support at probability zero",
            reason="zero_support_probability",
            field="probability",
        )
    if p == 1.0:
        if k == n:
            return 0.0
        raise MathInvariantError(
            "failures have zero support at probability one",
            reason="zero_support_probability",
            field="probability",
        )
    return (
        log_binomial_coefficient(n, k)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def hypergeometric_log_pmf(
    successes: int,
    *,
    population_successes: int,
    population_failures: int,
    draws: int,
) -> float:
    k = _non_negative_integer("successes", successes)
    good = _non_negative_integer("population_successes", population_successes)
    bad = _non_negative_integer("population_failures", population_failures)
    sample = _non_negative_integer("draws", draws)
    population = good + bad
    if sample > population:
        raise MathInvariantError(
            "draws must not exceed population size",
            reason="invalid_count",
            field="draws",
        )
    minimum = max(0, sample - bad)
    maximum = min(sample, good)
    if not minimum <= k <= maximum:
        raise MathInvariantError(
            "success count lies outside hypergeometric support",
            reason="zero_support_probability",
            field="successes",
        )
    return (
        log_binomial_coefficient(good, k)
        + log_binomial_coefficient(bad, sample - k)
        - log_binomial_coefficient(population, sample)
    )


def multinomial_log_pmf(
    counts: Sequence[int],
    probabilities: Sequence[Real],
) -> float:
    if not counts:
        raise MathInvariantError(
            "multinomial counts must not be empty",
            reason="empty_vector",
            field="counts",
        )
    clean_counts = tuple(_non_negative_integer(f"counts[{i}]", value) for i, value in enumerate(counts))
    probs = normalize_distribution(probabilities)
    if len(clean_counts) != len(probs):
        raise MathInvariantError(
            "multinomial counts and probabilities must align",
            reason="dimension_mismatch",
            field="multinomial",
        )
    total = sum(clean_counts)
    value = log_factorial(total) - compensated_sum(log_factorial(count) for count in clean_counts)
    terms = []
    for index, (count, probability) in enumerate(zip(clean_counts, probs)):
        if count == 0:
            continue
        if probability == 0.0:
            raise MathInvariantError(
                "positive multinomial count has zero probability support",
                reason="zero_support_probability",
                field=f"probabilities[{index}]",
            )
        terms.append(count * math.log(probability))
    return value + compensated_sum(terms)
