"""Conservative one-dimensional finite-volume references with Rusanov flux."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .numerics import compensated_sum


Flux = Callable[[float], Real]
WaveSpeed = Callable[[float, float], Real]


@dataclass(frozen=True, slots=True)
class FiniteVolumeReport:
    history: tuple[Vector, ...]
    final_state: Vector
    initial_mass: float
    final_mass: float
    mass_drift: float
    maximum_cfl: float
    steps: int
    scheme: str


def rusanov_periodic(
    values: Sequence[Real],
    flux: Flux,
    max_wave_speed: WaveSpeed,
    *,
    spacing: Real,
    time_step: Real,
    steps: int,
) -> FiniteVolumeReport:
    state = finite_vector("values", values)
    dx = positive_scalar("spacing", spacing)
    dt = positive_scalar("time_step", time_step)
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise MathInvariantError(
            "finite-volume steps must be a positive integer",
            reason="invalid_iteration_limit",
            field="steps",
        )
    initial_mass = dx * compensated_sum(state)
    history = [state]
    maximum_cfl = 0.0
    current = state
    n = len(current)

    for _ in range(steps):
        interface_flux = []
        for i in range(n):
            left = current[i]
            right = current[(i + 1) % n]
            speed = finite_scalar("wave_speed", max_wave_speed(left, right))
            if speed < 0.0:
                raise MathInvariantError(
                    "maximum wave speed must be non-negative",
                    reason="negative_wave_speed",
                    field="max_wave_speed",
                )
            cfl = speed * dt / dx
            maximum_cfl = max(maximum_cfl, cfl)
            if cfl > 1.0 + 1e-15:
                raise MathInvariantError(
                    "Rusanov finite-volume step violates CFL <= 1",
                    reason="unstable_time_step",
                    field="time_step",
                )
            left_flux = finite_scalar("flux", flux(left))
            right_flux = finite_scalar("flux", flux(right))
            interface_flux.append(
                0.5 * (left_flux + right_flux) - 0.5 * speed * (right - left)
            )
        candidate = tuple(
            current[i]
            - (dt / dx) * (interface_flux[i] - interface_flux[(i - 1) % n])
            for i in range(n)
        )
        current = finite_vector("finite_volume_state", candidate)
        history.append(current)

    final_mass = dx * compensated_sum(current)
    return FiniteVolumeReport(
        history=tuple(history),
        final_state=current,
        initial_mass=initial_mass,
        final_mass=final_mass,
        mass_drift=final_mass - initial_mass,
        maximum_cfl=maximum_cfl,
        steps=steps,
        scheme="rusanov_periodic",
    )


def linear_advection_finite_volume(
    values: Sequence[Real],
    *,
    velocity: Real,
    spacing: Real,
    time_step: Real,
    steps: int,
) -> FiniteVolumeReport:
    speed = finite_scalar("velocity", velocity)
    return rusanov_periodic(
        values,
        lambda value: speed * value,
        lambda _left, _right: abs(speed),
        spacing=spacing,
        time_step=time_step,
        steps=steps,
    )


def burgers_finite_volume(
    values: Sequence[Real],
    *,
    spacing: Real,
    time_step: Real,
    steps: int,
) -> FiniteVolumeReport:
    return rusanov_periodic(
        values,
        lambda value: 0.5 * value * value,
        lambda left, right: max(abs(left), abs(right)),
        spacing=spacing,
        time_step=time_step,
        steps=steps,
    )
