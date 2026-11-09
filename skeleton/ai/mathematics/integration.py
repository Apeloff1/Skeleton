"""Adaptive quadrature and RK4 ODE integration reference routines."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar


ScalarFunction = Callable[[float], Real]
ODEFunction = Callable[[float, Vector], Sequence[Real]]


@dataclass(frozen=True, slots=True)
class QuadratureReport:
    integral: float
    absolute_error_estimate: float
    evaluations: int
    converged: bool
    max_depth_reached: int


@dataclass(frozen=True, slots=True)
class ODEPoint:
    time: float
    state: Vector


@dataclass(frozen=True, slots=True)
class ODEReport:
    points: tuple[ODEPoint, ...]
    steps: int
    step_size: float


def _evaluate(function: ScalarFunction, x: float) -> float:
    return finite_scalar("integrand", function(x))


def adaptive_simpson(
    function: ScalarFunction,
    start: Real,
    end: Real,
    *,
    absolute_tolerance: Real = 1e-10,
    relative_tolerance: Real = 1e-10,
    max_depth: int = 20,
) -> QuadratureReport:
    a = finite_scalar("start", start)
    b = finite_scalar("end", end)
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 1:
        raise MathInvariantError(
            "max_depth must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_depth",
        )
    if a == b:
        return QuadratureReport(0.0, 0.0, 0, True, 0)
    sign = 1.0
    if b < a:
        a, b = b, a
        sign = -1.0

    evaluations = 0

    def f(x: float) -> float:
        nonlocal evaluations
        evaluations += 1
        return _evaluate(function, x)

    fa = f(a)
    fb = f(b)
    middle = (a + b) * 0.5
    fm = f(middle)
    whole = (b - a) * (fa + 4.0 * fm + fb) / 6.0
    error_total = 0.0
    deepest = 0
    converged = True

    def recurse(
        left: float,
        right: float,
        f_left: float,
        f_middle: float,
        f_right: float,
        estimate: float,
        depth: int,
        local_abs_tol: float,
    ) -> float:
        nonlocal error_total, deepest, converged
        deepest = max(deepest, depth)
        midpoint = (left + right) * 0.5
        left_midpoint = (left + midpoint) * 0.5
        right_midpoint = (midpoint + right) * 0.5
        f_left_midpoint = f(left_midpoint)
        f_right_midpoint = f(right_midpoint)
        left_estimate = (midpoint - left) * (
            f_left + 4.0 * f_left_midpoint + f_middle
        ) / 6.0
        right_estimate = (right - midpoint) * (
            f_middle + 4.0 * f_right_midpoint + f_right
        ) / 6.0
        refined = left_estimate + right_estimate
        correction = (refined - estimate) / 15.0
        error = abs(correction)
        local_tolerance = max(local_abs_tol, rel_tol * abs(refined))
        if error <= local_tolerance:
            error_total += error
            return refined + correction
        if depth >= max_depth:
            converged = False
            error_total += error
            return refined + correction
        return recurse(
            left,
            midpoint,
            f_left,
            f_left_midpoint,
            f_middle,
            left_estimate,
            depth + 1,
            local_abs_tol * 0.5,
        ) + recurse(
            midpoint,
            right,
            f_middle,
            f_right_midpoint,
            f_right,
            right_estimate,
            depth + 1,
            local_abs_tol * 0.5,
        )

    integral = recurse(a, b, fa, fm, fb, whole, 1, abs_tol)
    return QuadratureReport(
        integral=sign * finite_scalar("integral", integral),
        absolute_error_estimate=finite_scalar("absolute_error_estimate", error_total),
        evaluations=evaluations,
        converged=converged,
        max_depth_reached=deepest,
    )


def _derivative(function: ODEFunction, time: float, state: Vector) -> Vector:
    output = finite_vector("derivative", function(time, state))
    if len(output) != len(state):
        raise MathInvariantError(
            "ODE derivative dimension mismatch",
            reason="dimension_mismatch",
            field="derivative",
        )
    return output


def _combine(state: Vector, derivative: Vector, scale: float) -> Vector:
    return tuple(value + scale * delta for value, delta in zip(state, derivative))


def rk4_step(
    function: ODEFunction,
    time: Real,
    state: Sequence[Real],
    step_size: Real,
) -> Vector:
    t = finite_scalar("time", time)
    y = finite_vector("state", state)
    h = finite_scalar("step_size", step_size)
    if h == 0.0:
        raise MathInvariantError(
            "RK4 step size must be non-zero",
            reason="zero_step_size",
            field="step_size",
        )
    k1 = _derivative(function, t, y)
    k2 = _derivative(function, t + h * 0.5, _combine(y, k1, h * 0.5))
    k3 = _derivative(function, t + h * 0.5, _combine(y, k2, h * 0.5))
    k4 = _derivative(function, t + h, _combine(y, k3, h))
    output = tuple(
        value + h * (a + 2.0 * b + 2.0 * c + d) / 6.0
        for value, a, b, c, d in zip(y, k1, k2, k3, k4)
    )
    return finite_vector("rk4_state", output)


def rk4_integrate(
    function: ODEFunction,
    start_time: Real,
    end_time: Real,
    initial_state: Sequence[Real],
    *,
    steps: int,
) -> ODEReport:
    start = finite_scalar("start_time", start_time)
    end = finite_scalar("end_time", end_time)
    state = finite_vector("initial_state", initial_state)
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 1_000_000:
        raise MathInvariantError(
            "steps must be an integer in [1, 1000000]",
            reason="invalid_iteration_limit",
            field="steps",
        )
    h = (end - start) / steps
    if h == 0.0:
        raise MathInvariantError(
            "ODE interval must have non-zero duration",
            reason="zero_interval",
            field="end_time",
        )
    points = [ODEPoint(start, state)]
    time = start
    for index in range(steps):
        state = rk4_step(function, time, state, h)
        time = end if index == steps - 1 else start + (index + 1) * h
        if not math.isfinite(time):
            raise MathInvariantError(
                "ODE integration produced non-finite time",
                reason="non_finite_result",
                field="time",
            )
        points.append(ODEPoint(time, state))
    return ODEReport(points=tuple(points), steps=steps, step_size=h)
