"""Reproducibility scoring across repeated protocol executions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ReproductionRun:
    run_id: str
    protocol_digest: str
    environment_digest: str
    output_digest: str
    metric: float

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ReverseEngineeringError("reproduction run requires identity")
        for digest in (
            self.protocol_digest,
            self.environment_digest,
            self.output_digest,
        ):
            if not is_sha256_digest(digest):
                raise ReverseEngineeringError("reproduction digests must be sha256 hex")
        if not isfinite(self.metric):
            raise ReverseEngineeringError("reproduction metric must be finite")


@dataclass(frozen=True)
class ReproducibilityReport:
    run_count: int
    environment_count: int
    dominant_output_ratio: float
    metric_mean: float
    metric_standard_deviation: float
    metric_range: float
    normalized_metric_dispersion: float
    reproducibility_score: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_count": self.run_count,
            "environment_count": self.environment_count,
            "dominant_output_ratio": self.dominant_output_ratio,
            "metric_mean": self.metric_mean,
            "metric_standard_deviation": self.metric_standard_deviation,
            "metric_range": self.metric_range,
            "normalized_metric_dispersion": self.normalized_metric_dispersion,
            "reproducibility_score": self.reproducibility_score,
            "digest": self.digest,
        }


def analyze_reproducibility(
    runs: Sequence[ReproductionRun],
) -> ReproducibilityReport:
    if len(runs) < 2:
        raise ReverseEngineeringError("reproducibility requires at least two runs")
    ids = [run.run_id for run in runs]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("reproduction run ids must be unique")
    protocols = {run.protocol_digest for run in runs}
    if len(protocols) != 1:
        raise ReverseEngineeringError("reproduction runs must share protocol_digest")

    output_counts: dict[str, int] = {}
    for run in runs:
        output_counts[run.output_digest] = output_counts.get(run.output_digest, 0) + 1
    dominant_ratio = max(output_counts.values()) / len(runs)

    metrics = [run.metric for run in runs]
    mean = sum(metrics) / len(metrics)
    variance = sum((value - mean) ** 2 for value in metrics) / (len(metrics) - 1)
    standard_deviation = sqrt(variance)
    scale = max(abs(mean), max(abs(value) for value in metrics), 1e-12)
    normalized_dispersion = min(1.0, standard_deviation / scale)
    metric_consistency = 1.0 - normalized_dispersion
    score = (dominant_ratio + metric_consistency) / 2.0

    payload = {
        "protocol_digest": next(iter(protocols)),
        "runs": [
            {
                "run_id": run.run_id,
                "environment_digest": run.environment_digest,
                "output_digest": run.output_digest,
                "metric": run.metric,
            }
            for run in sorted(runs, key=lambda value: value.run_id)
        ],
    }
    return ReproducibilityReport(
        run_count=len(runs),
        environment_count=len({run.environment_digest for run in runs}),
        dominant_output_ratio=dominant_ratio,
        metric_mean=mean,
        metric_standard_deviation=standard_deviation,
        metric_range=max(metrics) - min(metrics),
        normalized_metric_dispersion=normalized_dispersion,
        reproducibility_score=score,
        digest=stable_digest(payload),
    )
