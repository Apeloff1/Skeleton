"""Deterministic bootstrap confidence intervals for bounded research metrics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from random import Random
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class BootstrapConfig:
    resamples: int = 2000
    confidence: float = 0.95
    seed: int = 0

    def __post_init__(self) -> None:
        if self.resamples < 100:
            raise ReverseEngineeringError("bootstrap resamples must be at least 100")
        if not isfinite(self.confidence) or not 0.0 < self.confidence < 1.0:
            raise ReverseEngineeringError("bootstrap confidence must be within (0, 1)")


@dataclass(frozen=True)
class BootstrapInterval:
    sample_count: int
    mean: float
    lower: float
    upper: float
    confidence: float
    resamples: int
    seed: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "mean": self.mean,
            "lower": self.lower,
            "upper": self.upper,
            "confidence": self.confidence,
            "resamples": self.resamples,
            "seed": self.seed,
            "digest": self.digest,
        }


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ReverseEngineeringError("percentile requires values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = probability * (len(sorted_values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = position - lower_index
    return (
        sorted_values[lower_index] * (1.0 - weight)
        + sorted_values[upper_index] * weight
    )


def bootstrap_mean_interval(
    values: Sequence[float],
    *,
    config: BootstrapConfig = BootstrapConfig(),
) -> BootstrapInterval:
    if not values:
        raise ReverseEngineeringError("bootstrap requires values")
    if any(not isfinite(value) for value in values):
        raise ReverseEngineeringError("bootstrap values must be finite")

    source = tuple(float(value) for value in values)
    rng = Random(config.seed)
    resampled_means: list[float] = []
    n = len(source)
    for _ in range(config.resamples):
        total = 0.0
        for _ in range(n):
            total += source[rng.randrange(n)]
        resampled_means.append(total / n)
    resampled_means.sort()

    alpha = (1.0 - config.confidence) / 2.0
    lower = _percentile(resampled_means, alpha)
    upper = _percentile(resampled_means, 1.0 - alpha)
    mean = sum(source) / n
    payload = {
        "values": list(source),
        "config": {
            "resamples": config.resamples,
            "confidence": config.confidence,
            "seed": config.seed,
        },
    }
    return BootstrapInterval(
        sample_count=n,
        mean=mean,
        lower=lower,
        upper=upper,
        confidence=config.confidence,
        resamples=config.resamples,
        seed=config.seed,
        digest=stable_digest(payload),
    )
