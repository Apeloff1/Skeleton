"""Adaptive Dormand-Prince RK45 reference integration."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar


ODEFunction = Callable[[float, Vector], Sequence[Real]]


@dataclass(frozen=True, slots=True)
class AdaptiveODEPoint:
    time: float
    state: Vector
    step_size: float
    error_norm: float


@dataclass(frozen=True, slots=True)
class AdaptiveODEReport:
    points: tuple[AdaptiveODEPoint, ...]
    accepted_steps: int
    rejected_steps: int
    function_evaluations: int
    converged: bool
    reason: str


def _derivative(function: ODEFunction, time: float, state: Vector) -> Vector:
    result = finite_vector("derivative", function(time, state))
    if len(result) != len(state):
        raise MathInvariantError(
            "ODE derivative dimension mismatch",
            reason="dimension_mismatch",
            field="derivative",
        )
    return result


def _combine(state: Vector, h: float, terms: Sequence[tuple[float, Vector]]) -> Vector:
    return tuple(
        state[i] + h * sum(coefficient * vector[i] for coefficient, vector in terms)
        for i in range(len(state))
    )


def adaptive_rk45(
    function: ODEFunction,
    start_time: Real,
    end_time: Real,
    initial_state: Sequence[Real],
    *,
    initial_step: Real | None = None,
    absolute_tolerance: Real = 1e-9,
    relative_tolerance: Real = 1e-7,
    minimum_step: Real = 1e-12,
    maximum_step: Real | None = None,
    max_steps: int = 100000,
) -> AdaptiveODEReport:
    start = finite_scalar("start_time", start_time)
    end = finite_scalar("end_time", end_time)
    state = finite_vector("initial_state", initial_state)
    if start == end:
        raise MathInvariantError(
            "adaptive ODE interval must have non-zero duration",
            reason="zero_interval",
            field="end_time",
        )
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    min_step = positive_scalar("minimum_step", minimum_step)
    interval = abs(end - start)
    max_step = interval if maximum_step is None else positive_scalar("maximum_step", maximum_step)
    if max_step < min_step:
        raise MathInvariantError(
            "maximum_step must be >= minimum_step",
            reason="invalid_step_bounds",
            field="maximum_step",
        )
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise MathInvariantError(
            "max_steps must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_steps",
        )
    direction = 1.0 if end > start else -1.0
    if initial_step is None:
        h = direction * min(max_step, max(min_step, interval / 100.0))
    else:
        h = direction * min(max_step, max(min_step, positive_scalar("initial_step", initial_step)))

    time = start
    accepted = 0
    rejected = 0
    evaluations = 0
    points = [AdaptiveODEPoint(time, state, 0.0, 0.0)]

    while direction * (end - time) > 0.0:
        if accepted + rejected >= max_steps:
            return AdaptiveODEReport(tuple(points), accepted, rejected, evaluations, False, "step_limit")
        remaining = end - time
        if direction * h > direction * remaining:
            h = remaining
        if abs(h) < min_step and abs(remaining) > min_step:
            return AdaptiveODEReport(tuple(points), accepted, rejected, evaluations, False, "minimum_step")

        k1 = _derivative(function, time, state)
        k2 = _derivative(function, time + h * (1/5), _combine(state, h, ((1/5, k1),)))
        k3 = _derivative(function, time + h * (3/10), _combine(state, h, ((3/40, k1), (9/40, k2))))
        k4 = _derivative(function, time + h * (4/5), _combine(state, h, ((44/45, k1), (-56/15, k2), (32/9, k3))))
        k5 = _derivative(function, time + h * (8/9), _combine(state, h, ((19372/6561, k1), (-25360/2187, k2), (64448/6561, k3), (-212/729, k4))))
        k6 = _derivative(function, time + h, _combine(state, h, ((9017/3168, k1), (-355/33, k2), (46732/5247, k3), (49/176, k4), (-5103/18656, k5))))
        fifth = _combine(state, h, ((35/384, k1), (500/1113, k3), (125/192, k4), (-2187/6784, k5), (11/84, k6)))
        k7 = _derivative(function, time + h, fifth)
        fourth = _combine(state, h, ((5179/57600, k1), (7571/16695, k3), (393/640, k4), (-92097/339200, k5), (187/2100, k6), (1/40, k7)))
        evaluations += 7

        error_components = []
        for old, candidate, low in zip(state, fifth, fourth):
            scale = abs_tol + rel_tol * max(abs(old), abs(candidate))
            error_components.append((candidate - low) / scale)
        error_norm = math.sqrt(sum(value * value for value in error_components) / len(error_components))
        if not math.isfinite(error_norm):
            raise MathInvariantError(
                "RK45 error estimate became non-finite",
                reason="non_finite_result",
                field="error_norm",
            )

        if error_norm <= 1.0:
            time = end if abs(end - (time + h)) <= min_step else time + h
            state = finite_vector("state", fifth)
            accepted += 1
            points.append(AdaptiveODEPoint(time, state, h, error_norm))
        else:
            rejected += 1
            if abs(h) <= min_step:
                return AdaptiveODEReport(
                    tuple(points),
                    accepted,
                    rejected,
                    evaluations,
                    False,
                    "minimum_step",
                )

        if error_norm == 0.0:
            factor = 5.0
        else:
            factor = 0.9 * error_norm ** (-0.2)
            factor = min(5.0, max(0.2, factor))
        next_magnitude = min(max_step, max(min_step, abs(h) * factor))
        h = direction * next_magnitude

    return AdaptiveODEReport(tuple(points), accepted, rejected, evaluations, True, "completed")
