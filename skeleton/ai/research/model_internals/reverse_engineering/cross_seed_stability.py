"""Cross-seed stability for stochastic local-model measurements."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class SeedMeasurement:
    measurement_id: str
    probe_digest: str
    seed: int
    metric: float

    def __post_init__(self) -> None:
        if not self.measurement_id:
            raise ReverseEngineeringError("seed measurement requires identity")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if self.seed < 0:
            raise ReverseEngineeringError("seed must be non-negative")
        if not isfinite(self.metric):
            raise ReverseEngineeringError("seed metric must be finite")


@dataclass(frozen=True)
class CrossSeedStabilityReport:
    seed_count: int
    measurement_count: int
    mean_metric: float
    min_metric: float
    max_metric: float
    metric_range: float
    mean_absolute_deviation: float
    within_tolerance_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed_count": self.seed_count,
            "measurement_count": self.measurement_count,
            "mean_metric": self.mean_metric,
            "min_metric": self.min_metric,
            "max_metric": self.max_metric,
            "metric_range": self.metric_range,
            "mean_absolute_deviation": self.mean_absolute_deviation,
            "within_tolerance_ratio": self.within_tolerance_ratio,
            "digest": self.digest,
        }


def analyze_cross_seed_stability(
    measurements: Sequence[SeedMeasurement],
    *,
    tolerance: float = 0.1,
) -> CrossSeedStabilityReport:
    if len(measurements) < 2:
        raise ReverseEngineeringError("cross-seed stability requires at least two measurements")
    if not isfinite(tolerance) or tolerance < 0.0:
        raise ReverseEngineeringError("tolerance must be finite and non-negative")
    probe_digests = {item.probe_digest for item in measurements}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("seed measurements must share probe_digest")
    seeds = [item.seed for item in measurements]
    if len(seeds) != len(set(seeds)):
        raise ReverseEngineeringError("seed values must be unique")
    metrics = [item.metric for item in measurements]
    mean = sum(metrics) / len(metrics)
    deviations = [abs(value - mean) for value in metrics]
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "tolerance": tolerance,
        "measurements": [
            {
                "measurement_id": item.measurement_id,
                "seed": item.seed,
                "metric": item.metric,
            }
            for item in sorted(measurements, key=lambda value: value.seed)
        ],
    }
    return CrossSeedStabilityReport(
        seed_count=len(set(seeds)),
        measurement_count=len(measurements),
        mean_metric=mean,
        min_metric=min(metrics),
        max_metric=max(metrics),
        metric_range=max(metrics) - min(metrics),
        mean_absolute_deviation=sum(deviations) / len(deviations),
        within_tolerance_ratio=sum(value <= tolerance for value in deviations) / len(deviations),
        digest=stable_digest(payload),
    )
