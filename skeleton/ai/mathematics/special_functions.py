"""Numerically stable scalar transforms used across AI math references."""
from __future__ import annotations

import math
from numbers import Real

from .contracts import MathInvariantError, finite_scalar


_LOG_TWO = math.log(2.0)


def logaddexp(left: Real, right: Real) -> float:
    a = finite_scalar("left", left)
    b = finite_scalar("right", right)
    maximum = max(a, b)
    return maximum + math.log1p(math.exp(-abs(a - b)))


def logsubexp(log_left: Real, log_right: Real) -> float:
    a = finite_scalar("log_left", log_left)
    b = finite_scalar("log_right", log_right)
    if b >= a:
        raise MathInvariantError(
            "logsubexp requires log_left > log_right",
            reason="invalid_log_difference",
            field="log_right",
        )
    difference = b - a
    if difference < -_LOG_TWO:
        return a + math.log1p(-math.exp(difference))
    return a + math.log(-math.expm1(difference))


def log1mexp(log_probability: Real) -> float:
    value = finite_scalar("log_probability", log_probability)
    if value >= 0.0:
        raise MathInvariantError(
            "log1mexp requires a strictly negative log-probability",
            reason="invalid_log_probability",
            field="log_probability",
        )
    if value < -_LOG_TWO:
        return math.log1p(-math.exp(value))
    return math.log(-math.expm1(value))


def stable_sigmoid(value: Real) -> float:
    x = finite_scalar("value", value)
    if x >= 0.0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def stable_logit(probability: Real) -> float:
    p = finite_scalar("probability", probability)
    if not 0.0 < p < 1.0:
        raise MathInvariantError(
            "logit probability must lie strictly inside (0, 1)",
            reason="invalid_probability",
            field="probability",
        )
    return math.log(p) - math.log1p(-p)


def stable_softplus(value: Real) -> float:
    x = finite_scalar("value", value)
    if x > 36.0:
        return x
    if x < -36.0:
        return math.exp(x)
    return math.log1p(math.exp(x))


def inverse_softplus(value: Real) -> float:
    y = finite_scalar("value", value)
    if y <= 0.0:
        raise MathInvariantError(
            "inverse softplus requires a positive value",
            reason="domain_error",
            field="value",
        )
    if y > 36.0:
        return y
    return y + math.log(-math.expm1(-y))


def log_cosh(value: Real) -> float:
    x = finite_scalar("value", value)
    absolute = abs(x)
    return absolute + math.log1p(math.exp(-2.0 * absolute)) - _LOG_TWO
