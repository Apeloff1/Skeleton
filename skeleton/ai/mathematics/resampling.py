"""Deterministic jackknife and bootstrap uncertainty references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector
from .sampling import SplitMix64
from .statistics import quantile
from .numerics import compensated_sum


Statistic = Callable[[Vector], Real]


@dataclass(frozen=True, slots=True)
class JackknifeReport:
    estimate: float
    leave_one_out: Vector
    bias_estimate: float
    bias_corrected_estimate: float
    standard_error: float


def jackknife(
    values: Sequence[Real],
    statistic: Statistic,
) -> JackknifeReport:
    observations = finite_vector("values", values)
    n = len(observations)
    if n < 2:
        raise MathInvariantError(
            "jackknife requires at least two observations",
            reason="insufficient_observations",
            field="values",
        )
    estimate = finite_scalar("estimate", statistic(observations))
    leave_one_out = []
    for omitted in range(n):
        sample = observations[:omitted] + observations[omitted + 1:]
        leave_one_out.append(finite_scalar("jackknife_statistic", statistic(sample)))
    pseudo_mean = compensated_sum(leave_one_out) / n
    bias = (n - 1) * (pseudo_mean - estimate)
    corrected = estimate - bias
    variance = (n - 1) / n * compensated_sum(
        (value - pseudo_mean) ** 2 for value in leave_one_out
    )
    return JackknifeReport(
        estimate=estimate,
        leave_one_out=tuple(leave_one_out),
        bias_estimate=bias,
        bias_corrected_estimate=corrected,
        standard_error=math.sqrt(max(0.0, variance)),
    )


@dataclass(frozen=True, slots=True)
class BootstrapReport:
    estimate: float
    replicates: Vector
    mean: float
    standard_error: float
    confidence_interval: tuple[float, float]
    confidence_level: float
    seed: int


def bootstrap(
    values: Sequence[Real],
    statistic: Statistic,
    *,
    replicates: int = 1000,
    confidence_level: Real = 0.95,
    seed: int = 0,
) -> BootstrapReport:
    observations = finite_vector("values", values)
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < 2:
        raise MathInvariantError(
            "bootstrap replicates must be an integer >= 2",
            reason="invalid_sample_count",
            field="replicates",
        )
    level = finite_scalar("confidence_level", confidence_level)
    if not 0.0 < level < 1.0:
        raise MathInvariantError(
            "confidence_level must lie in (0, 1)",
            reason="invalid_probability",
            field="confidence_level",
        )
    rng = SplitMix64(seed)
    n = len(observations)
    estimate = finite_scalar("estimate", statistic(observations))
    generated: list[float] = []
    for _ in range(replicates):
        sample = tuple(observations[int(rng.uniform() * n)] for _ in range(n))
        generated.append(finite_scalar("bootstrap_statistic", statistic(sample)))
    mean = compensated_sum(generated) / replicates
    if replicates < 2:
        variance = 0.0
    else:
        variance = compensated_sum((value - mean) ** 2 for value in generated) / (replicates - 1)
    alpha = (1.0 - level) * 0.5
    interval = (
        quantile(generated, alpha),
        quantile(generated, 1.0 - alpha),
    )
    return BootstrapReport(
        estimate=estimate,
        replicates=tuple(generated),
        mean=mean,
        standard_error=math.sqrt(max(0.0, variance)),
        confidence_interval=interval,
        confidence_level=level,
        seed=seed,
    )
