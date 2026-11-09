"""Distribution-free and categorical hypothesis-test reference diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector
from .probability import normalize_distribution


@dataclass(frozen=True, slots=True)
class TwoSampleKSReport:
    statistic: float
    left_count: int
    right_count: int
    effective_count: float
    asymptotic_p_value: float


def two_sample_ks(
    left: Sequence[Real],
    right: Sequence[Real],
) -> TwoSampleKSReport:
    a = sorted(finite_vector("left", left))
    b = sorted(finite_vector("right", right))
    n = len(a)
    m = len(b)
    i = j = 0
    cdf_a = 0.0
    cdf_b = 0.0
    statistic = 0.0

    while i < n or j < m:
        if j >= m or (i < n and a[i] < b[j]):
            value = a[i]
        elif i >= n or b[j] < a[i]:
            value = b[j]
        else:
            value = a[i]
        while i < n and a[i] <= value:
            i += 1
        while j < m and b[j] <= value:
            j += 1
        cdf_a = i / n
        cdf_b = j / m
        statistic = max(statistic, abs(cdf_a - cdf_b))

    effective = n * m / (n + m)
    if statistic == 0.0:
        p_value = 1.0
    else:
        root = math.sqrt(effective)
        lam = (root + 0.12 + 0.11 / root) * statistic
        series = 0.0
        for k in range(1, 101):
            term = math.exp(-2.0 * k * k * lam * lam)
            series += term if k % 2 else -term
            if term < 1e-15:
                break
        p_value = max(0.0, min(1.0, 2.0 * series))
    return TwoSampleKSReport(
        statistic=statistic,
        left_count=n,
        right_count=m,
        effective_count=effective,
        asymptotic_p_value=p_value,
    )


def _regularized_gamma_q(shape: float, x: float) -> float:
    if shape <= 0.0 or x < 0.0:
        raise MathInvariantError(
            "regularized gamma requires shape > 0 and x >= 0",
            reason="domain_error",
            field="gamma",
        )
    if x == 0.0:
        return 1.0
    gln = math.lgamma(shape)
    if x < shape + 1.0:
        term = 1.0 / shape
        total = term
        ap = shape
        for _ in range(1, 1001):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) <= abs(total) * 1e-15:
                break
        p = total * math.exp(-x + shape * math.log(x) - gln)
        return max(0.0, min(1.0, 1.0 - p))

    tiny = 1e-300
    b = x + 1.0 - shape
    c = 1.0 / tiny
    d = 1.0 / b if abs(b) > tiny else 1.0 / tiny
    h = d
    for i in range(1, 1001):
        an = -i * (i - shape)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) <= 1e-15:
            break
    q = math.exp(-x + shape * math.log(x) - gln) * h
    return max(0.0, min(1.0, q))


@dataclass(frozen=True, slots=True)
class ChiSquareReport:
    statistic: float
    degrees_of_freedom: int
    p_value: float
    observed_total: float
    expected_counts: Vector


def chi_square_goodness_of_fit(
    observed: Sequence[Real],
    expected_probabilities: Sequence[Real],
) -> ChiSquareReport:
    counts = finite_vector("observed", observed)
    if any(value < 0.0 for value in counts):
        raise MathInvariantError(
            "observed counts must be non-negative",
            reason="negative_count",
            field="observed",
        )
    total = sum(counts)
    if total <= 0.0:
        raise MathInvariantError(
            "observed counts must have positive total",
            reason="zero_count_mass",
            field="observed",
        )
    probabilities = normalize_distribution(expected_probabilities)
    if len(probabilities) != len(counts):
        raise MathInvariantError(
            "expected probabilities must match observed categories",
            reason="dimension_mismatch",
            field="expected_probabilities",
        )
    if len(counts) < 2:
        raise MathInvariantError(
            "chi-square test requires at least two categories",
            reason="insufficient_observations",
            field="observed",
        )
    expected = tuple(total * probability for probability in probabilities)
    if any(value <= 0.0 for value in expected):
        raise MathInvariantError(
            "chi-square expected counts must all be positive",
            reason="zero_support_probability",
            field="expected_probabilities",
        )
    statistic = sum(
        (observed_value - expected_value) ** 2 / expected_value
        for observed_value, expected_value in zip(counts, expected)
    )
    dof = len(counts) - 1
    p_value = _regularized_gamma_q(0.5 * dof, 0.5 * statistic)
    return ChiSquareReport(
        statistic=statistic,
        degrees_of_freedom=dof,
        p_value=p_value,
        observed_total=total,
        expected_counts=expected,
    )
