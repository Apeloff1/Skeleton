"""Explicit finite-difference time integrators with CFL-governed contracts."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar


@dataclass(frozen=True, slots=True)
class PDETimeReport:
    history: tuple[Vector, ...]
    final_state: Vector
    steps: int
    cfl_number: float
    stable_under_reference_bound: bool
    scheme: str


def _steps(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MathInvariantError(
            "time integrator steps must be a positive integer",
            reason="invalid_iteration_limit",
            field="steps",
        )
    return value


def advection_upwind_periodic(
    values: Sequence[Real],
    *,
    velocity: Real,
    spacing: Real,
    time_step: Real,
    steps: int,
) -> PDETimeReport:
    state = finite_vector("values", values)
    speed = finite_scalar("velocity", velocity)
    dx = positive_scalar("spacing", spacing)
    dt = positive_scalar("time_step", time_step)
    count = _steps(steps)
    cfl = abs(speed) * dt / dx
    if cfl > 1.0 + 1e-15:
        raise MathInvariantError(
            "upwind advection violates CFL <= 1",
            reason="unstable_time_step",
            field="time_step",
        )
    history = [state]
    current = state
    n = len(current)
    for _ in range(count):
        if speed >= 0.0:
            candidate = tuple(
                current[i] - (speed * dt / dx) * (current[i] - current[(i - 1) % n])
                for i in range(n)
            )
        else:
            candidate = tuple(
                current[i] - (speed * dt / dx) * (current[(i + 1) % n] - current[i])
                for i in range(n)
            )
        current = finite_vector("advection_state", candidate)
        history.append(current)
    return PDETimeReport(tuple(history), current, count, cfl, True, "upwind_periodic")


def diffusion_explicit_periodic(
    values: Sequence[Real],
    *,
    diffusivity: Real,
    spacing: Real,
    time_step: Real,
    steps: int,
) -> PDETimeReport:
    state = finite_vector("values", values)
    coefficient = positive_scalar("diffusivity", diffusivity)
    dx = positive_scalar("spacing", spacing)
    dt = positive_scalar("time_step", time_step)
    count = _steps(steps)
    ratio = coefficient * dt / (dx * dx)
    if ratio > 0.5 + 1e-15:
        raise MathInvariantError(
            "explicit 1-D diffusion violates mu <= 1/2",
            reason="unstable_time_step",
            field="time_step",
        )
    history = [state]
    current = state
    n = len(current)
    for _ in range(count):
        candidate = tuple(
            current[i]
            + ratio * (current[(i - 1) % n] - 2.0 * current[i] + current[(i + 1) % n])
            for i in range(n)
        )
        current = finite_vector("diffusion_state", candidate)
        history.append(current)
    return PDETimeReport(tuple(history), current, count, ratio, True, "diffusion_explicit_periodic")


def wave_leapfrog_periodic(
    displacement: Sequence[Real],
    velocity: Sequence[Real],
    *,
    wave_speed: Real,
    spacing: Real,
    time_step: Real,
    steps: int,
) -> PDETimeReport:
    initial = finite_vector("displacement", displacement)
    initial_velocity = finite_vector("velocity", velocity)
    if len(initial_velocity) != len(initial):
        raise MathInvariantError(
            "wave displacement and velocity dimensions must match",
            reason="dimension_mismatch",
            field="velocity",
        )
    speed = positive_scalar("wave_speed", wave_speed)
    dx = positive_scalar("spacing", spacing)
    dt = positive_scalar("time_step", time_step)
    count = _steps(steps)
    courant = speed * dt / dx
    if courant > 1.0 + 1e-15:
        raise MathInvariantError(
            "leapfrog wave scheme violates CFL <= 1",
            reason="unstable_time_step",
            field="time_step",
        )
    n = len(initial)
    c2 = courant * courant
    first = tuple(
        initial[i]
        + dt * initial_velocity[i]
        + 0.5 * c2 * (initial[(i - 1) % n] - 2.0 * initial[i] + initial[(i + 1) % n])
        for i in range(n)
    )
    first = finite_vector("wave_state", first)
    history = [initial, first]
    if count == 1:
        return PDETimeReport(tuple(history), first, count, courant, True, "wave_leapfrog_periodic")

    previous = initial
    current = first
    for _ in range(1, count):
        candidate = tuple(
            2.0 * current[i]
            - previous[i]
            + c2 * (current[(i - 1) % n] - 2.0 * current[i] + current[(i + 1) % n])
            for i in range(n)
        )
        previous, current = current, finite_vector("wave_state", candidate)
        history.append(current)
    return PDETimeReport(tuple(history), current, count, courant, True, "wave_leapfrog_periodic")
