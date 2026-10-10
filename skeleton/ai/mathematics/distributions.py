"""Dependency-free distribution density/CDF reference functions."""
from __future__ import annotations

import math
from numbers import Real
from statistics import NormalDist
from typing import Sequence

from .contracts import MathInvariantError, finite_scalar, finite_vector, positive_scalar
from .numerics import logsumexp
from .probability import normalize_distribution


_SQRT_TWO = math.sqrt(2.0)
_LOG_TWO_PI = math.log(2.0 * math.pi)


def _open_probability(name: str, value: Real) -> float:
    probability = finite_scalar(name, value)
    if not 0.0 < probability < 1.0:
        raise MathInvariantError(
            f"{name} must lie strictly inside (0, 1)",
            reason="invalid_probability",
            field=name,
        )
    return probability


def normal_log_pdf(
    value: Real,
    *,
    mean: Real = 0.0,
    standard_deviation: Real = 1.0,
) -> float:
    x = finite_scalar("value", value)
    mu = finite_scalar("mean", mean)
    sigma = positive_scalar("standard_deviation", standard_deviation)
    z = (x - mu) / sigma
    return -0.5 * (_LOG_TWO_PI + z * z) - math.log(sigma)


def normal_pdf(
    value: Real,
    *,
    mean: Real = 0.0,
    standard_deviation: Real = 1.0,
) -> float:
    return math.exp(normal_log_pdf(value, mean=mean, standard_deviation=standard_deviation))


def normal_cdf(
    value: Real,
    *,
    mean: Real = 0.0,
    standard_deviation: Real = 1.0,
) -> float:
    x = finite_scalar("value", value)
    mu = finite_scalar("mean", mean)
    sigma = positive_scalar("standard_deviation", standard_deviation)
    z = (x - mu) / (sigma * _SQRT_TWO)
    return 0.5 * math.erfc(-z)


def normal_quantile(
    probability: Real,
    *,
    mean: Real = 0.0,
    standard_deviation: Real = 1.0,
) -> float:
    p = _open_probability("probability", probability)
    mu = finite_scalar("mean", mean)
    sigma = positive_scalar("standard_deviation", standard_deviation)
    return finite_scalar(
        "normal_quantile",
        NormalDist(mu=mu, sigma=sigma).inv_cdf(p),
    )


def student_t_log_pdf(
    value: Real,
    *,
    degrees_of_freedom: Real,
    location: Real = 0.0,
    scale: Real = 1.0,
) -> float:
    x = finite_scalar("value", value)
    nu = positive_scalar("degrees_of_freedom", degrees_of_freedom)
    center = finite_scalar("location", location)
    width = positive_scalar("scale", scale)
    z = (x - center) / width
    return (
        math.lgamma((nu + 1.0) * 0.5)
        - math.lgamma(nu * 0.5)
        - 0.5 * math.log(nu * math.pi)
        - math.log(width)
        - 0.5 * (nu + 1.0) * math.log1p((z * z) / nu)
    )


def poisson_log_pmf(count: int, rate: Real) -> float:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise MathInvariantError(
            "Poisson count must be a non-negative integer",
            reason="invalid_count",
            field="count",
        )
    lam = positive_scalar("rate", rate)
    return count * math.log(lam) - lam - math.lgamma(count + 1.0)


def bernoulli_log_pmf(outcome: bool | int, probability: Real) -> float:
    if isinstance(outcome, bool):
        event = int(outcome)
    elif isinstance(outcome, int) and outcome in {0, 1}:
        event = outcome
    else:
        raise MathInvariantError(
            "Bernoulli outcome must be 0 or 1",
            reason="invalid_outcome",
            field="outcome",
        )
    p = finite_scalar("probability", probability)
    if not 0.0 <= p <= 1.0:
        raise MathInvariantError(
            "Bernoulli probability must lie in [0, 1]",
            reason="invalid_probability",
            field="probability",
        )
    if event == 1:
        if p == 0.0:
            return -math.inf
        return math.log(p)
    if p == 1.0:
        return -math.inf
    return math.log1p(-p)


def gaussian_mixture_log_density(
    value: Real,
    means: Sequence[Real],
    standard_deviations: Sequence[Real],
    weights: Sequence[Real],
) -> float:
    x = finite_scalar("value", value)
    mu = finite_vector("means", means)
    sigma = finite_vector("standard_deviations", standard_deviations)
    probabilities = normalize_distribution(weights)
    if not (len(mu) == len(sigma) == len(probabilities)):
        raise MathInvariantError(
            "mixture component arrays must have equal length",
            reason="dimension_mismatch",
            field="mixture",
        )
    terms = []
    for index, (center, width, weight) in enumerate(zip(mu, sigma, probabilities)):
        if width <= 0.0:
            raise MathInvariantError(
                "mixture standard deviations must be positive",
                reason="non_positive_scale",
                field=f"standard_deviations[{index}]",
            )
        if weight == 0.0:
            continue
        terms.append(math.log(weight) + normal_log_pdf(x, mean=center, standard_deviation=width))
    if not terms:
        raise MathInvariantError(
            "mixture has no positive-weight components",
            reason="zero_probability_mass",
            field="weights",
        )
    return logsumexp(terms)
