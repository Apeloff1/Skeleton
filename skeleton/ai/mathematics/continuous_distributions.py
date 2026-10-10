"""Continuous-distribution special functions and density/CDF references."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, finite_scalar, finite_vector, positive_scalar
from .numerics import compensated_sum


def log_beta(alpha: Real, beta: Real) -> float:
    a = positive_scalar("alpha", alpha)
    b = positive_scalar("beta", beta)
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations = 400
    epsilon = 3e-14
    tiny = 1e-300

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d

    for iteration in range(1, maximum_iterations + 1):
        m2 = 2 * iteration
        aa = iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c

        aa = -(a + iteration) * (qab + iteration) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) <= epsilon:
            return h
    raise MathInvariantError(
        "regularized beta continued fraction did not converge",
        reason="special_function_non_convergence",
        field="x",
    )


def regularized_beta(x: Real, alpha: Real, beta: Real) -> float:
    point = finite_scalar("x", x)
    a = positive_scalar("alpha", alpha)
    b = positive_scalar("beta", beta)
    if not 0.0 <= point <= 1.0:
        raise MathInvariantError(
            "regularized beta x must lie in [0, 1]",
            reason="domain_error",
            field="x",
        )
    if point == 0.0:
        return 0.0
    if point == 1.0:
        return 1.0
    front = math.exp(
        a * math.log(point)
        + b * math.log1p(-point)
        - log_beta(a, b)
    )
    threshold = (a + 1.0) / (a + b + 2.0)
    if point < threshold:
        value = front * _beta_continued_fraction(a, b, point) / a
    else:
        value = 1.0 - front * _beta_continued_fraction(b, a, 1.0 - point) / b
    return max(0.0, min(1.0, value))


def beta_log_pdf(x: Real, alpha: Real, beta: Real) -> float:
    point = finite_scalar("x", x)
    a = positive_scalar("alpha", alpha)
    b = positive_scalar("beta", beta)
    if not 0.0 < point < 1.0:
        raise MathInvariantError(
            "beta log density requires x strictly inside (0, 1)",
            reason="domain_error",
            field="x",
        )
    return (a - 1.0) * math.log(point) + (b - 1.0) * math.log1p(-point) - log_beta(a, b)


def beta_cdf(x: Real, alpha: Real, beta: Real) -> float:
    return regularized_beta(x, alpha, beta)


def regularized_gamma_p(shape: Real, x: Real) -> float:
    a = positive_scalar("shape", shape)
    point = finite_scalar("x", x)
    if point < 0.0:
        raise MathInvariantError(
            "regularized gamma x must be non-negative",
            reason="domain_error",
            field="x",
        )
    if point == 0.0:
        return 0.0
    gln = math.lgamma(a)
    if point < a + 1.0:
        term = 1.0 / a
        total = term
        ap = a
        for _ in range(1, 1001):
            ap += 1.0
            term *= point / ap
            total += term
            if abs(term) <= abs(total) * 1e-15:
                result = total * math.exp(-point + a * math.log(point) - gln)
                return max(0.0, min(1.0, result))
        raise MathInvariantError(
            "regularized gamma series did not converge",
            reason="special_function_non_convergence",
            field="x",
        )

    tiny = 1e-300
    b = point + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if abs(b) > tiny else 1.0 / tiny
    h = d
    for iteration in range(1, 1001):
        an = -iteration * (iteration - a)
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
            q = math.exp(-point + a * math.log(point) - gln) * h
            return max(0.0, min(1.0, 1.0 - q))
    raise MathInvariantError(
        "regularized gamma continued fraction did not converge",
        reason="special_function_non_convergence",
        field="x",
    )


def gamma_log_pdf(x: Real, shape: Real, *, scale: Real = 1.0) -> float:
    point = finite_scalar("x", x)
    a = positive_scalar("shape", shape)
    theta = positive_scalar("scale", scale)
    if point <= 0.0:
        raise MathInvariantError(
            "gamma log density requires x > 0",
            reason="domain_error",
            field="x",
        )
    return (
        (a - 1.0) * math.log(point)
        - point / theta
        - math.lgamma(a)
        - a * math.log(theta)
    )


def gamma_cdf(x: Real, shape: Real, *, scale: Real = 1.0) -> float:
    point = finite_scalar("x", x)
    theta = positive_scalar("scale", scale)
    if point < 0.0:
        return 0.0
    return regularized_gamma_p(shape, point / theta)


def dirichlet_log_pdf(
    probabilities: Sequence[Real],
    alpha: Sequence[Real],
) -> float:
    values = finite_vector("probabilities", probabilities)
    concentrations = finite_vector("alpha", alpha)
    if len(values) != len(concentrations):
        raise MathInvariantError(
            "Dirichlet probabilities and alpha must align",
            reason="dimension_mismatch",
            field="dirichlet",
        )
    if any(value <= 0.0 for value in concentrations):
        raise MathInvariantError(
            "Dirichlet concentrations must be positive",
            reason="non_positive_concentration",
            field="alpha",
        )
    if any(value <= 0.0 for value in values):
        raise MathInvariantError(
            "Dirichlet log density requires strictly positive simplex coordinates",
            reason="domain_error",
            field="probabilities",
        )
    total_probability = compensated_sum(values)
    if abs(total_probability - 1.0) > 1e-12:
        raise MathInvariantError(
            "Dirichlet probabilities must sum to one",
            reason="not_normalized",
            field="probabilities",
        )
    alpha_total = compensated_sum(concentrations)
    log_normalizer = compensated_sum(math.lgamma(value) for value in concentrations) - math.lgamma(alpha_total)
    return -log_normalizer + compensated_sum(
        (concentration - 1.0) * math.log(probability)
        for concentration, probability in zip(concentrations, values)
    )
