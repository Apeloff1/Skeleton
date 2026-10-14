"""Deterministic seeded scalar stochastic-differential-equation references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable

from .contracts import MathInvariantError, Vector, finite_scalar, positive_scalar
from .sampling import SplitMix64


ScalarField = Callable[[float, float], Real]


@dataclass(frozen=True, slots=True)
class SDEPathReport:
    times: Vector
    states: Vector
    brownian_increments: Vector
    steps: int
    time_step: float
    seed: int
    scheme: str
    terminal_state: float


def _step_count(steps: int) -> int:
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise MathInvariantError(
            "SDE steps must be a positive integer",
            reason="invalid_iteration_limit",
            field="steps",
        )
    return steps


def _field(name: str, function: ScalarField, time: float, state: float) -> float:
    return finite_scalar(name, function(time, state))


def euler_maruyama(
    drift: ScalarField,
    diffusion: ScalarField,
    *,
    initial_state: Real,
    start_time: Real = 0.0,
    time_step: Real = 0.01,
    steps: int = 100,
    seed: int = 0,
) -> SDEPathReport:
    x = finite_scalar("initial_state", initial_state)
    t = finite_scalar("start_time", start_time)
    dt = positive_scalar("time_step", time_step)
    count = _step_count(steps)
    rng = SplitMix64(seed)
    root_dt = math.sqrt(dt)
    times = [t]
    states = [x]
    increments = []
    for _ in range(count):
        d_w = root_dt * rng.normal()
        a = _field("drift", drift, t, x)
        b = _field("diffusion", diffusion, t, x)
        x = finite_scalar("sde_state", x + a * dt + b * d_w)
        t = finite_scalar("sde_time", t + dt)
        increments.append(d_w)
        times.append(t)
        states.append(x)
    return SDEPathReport(
        times=tuple(times),
        states=tuple(states),
        brownian_increments=tuple(increments),
        steps=count,
        time_step=dt,
        seed=seed,
        scheme="euler_maruyama",
        terminal_state=x,
    )


def milstein_scalar(
    drift: ScalarField,
    diffusion: ScalarField,
    diffusion_derivative: ScalarField,
    *,
    initial_state: Real,
    start_time: Real = 0.0,
    time_step: Real = 0.01,
    steps: int = 100,
    seed: int = 0,
) -> SDEPathReport:
    x = finite_scalar("initial_state", initial_state)
    t = finite_scalar("start_time", start_time)
    dt = positive_scalar("time_step", time_step)
    count = _step_count(steps)
    rng = SplitMix64(seed)
    root_dt = math.sqrt(dt)
    times = [t]
    states = [x]
    increments = []
    for _ in range(count):
        d_w = root_dt * rng.normal()
        a = _field("drift", drift, t, x)
        b = _field("diffusion", diffusion, t, x)
        derivative = _field("diffusion_derivative", diffusion_derivative, t, x)
        correction = 0.5 * b * derivative * (d_w * d_w - dt)
        x = finite_scalar("sde_state", x + a * dt + b * d_w + correction)
        t = finite_scalar("sde_time", t + dt)
        increments.append(d_w)
        times.append(t)
        states.append(x)
    return SDEPathReport(
        times=tuple(times),
        states=tuple(states),
        brownian_increments=tuple(increments),
        steps=count,
        time_step=dt,
        seed=seed,
        scheme="milstein_scalar",
        terminal_state=x,
    )


@dataclass(frozen=True, slots=True)
class GBMMomentReport:
    time: float
    mean: float
    variance: float
    second_moment: float


def geometric_brownian_moments(
    initial_state: Real,
    drift: Real,
    volatility: Real,
    time: Real,
) -> GBMMomentReport:
    x0 = finite_scalar("initial_state", initial_state)
    mu = finite_scalar("drift", drift)
    sigma = finite_scalar("volatility", volatility)
    horizon = finite_scalar("time", time)
    if horizon < 0.0:
        raise MathInvariantError(
            "GBM time must be non-negative",
            reason="domain_error",
            field="time",
        )
    mean = x0 * math.exp(mu * horizon)
    second = x0 * x0 * math.exp((2.0 * mu + sigma * sigma) * horizon)
    variance = max(0.0, second - mean * mean)
    return GBMMomentReport(horizon, mean, variance, second)
