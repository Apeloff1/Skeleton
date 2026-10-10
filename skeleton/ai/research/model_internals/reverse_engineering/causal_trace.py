"""Causal tracing summaries for authorized corruption/restoration experiments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class CausalTraceObservation:
    observation_id: str
    input_digest: str
    layer_index: int
    clean_metric: float
    corrupted_metric: float
    restored_metric: float
    intervention_digest: str

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("causal-trace observation requires identity")
        if not is_sha256_digest(self.input_digest) or not is_sha256_digest(self.intervention_digest):
            raise ReverseEngineeringError("causal-trace digests must be sha256 hex digests")
        if self.layer_index < 0:
            raise ReverseEngineeringError("layer_index must be non-negative")
        if any(
            not isfinite(value)
            for value in (self.clean_metric, self.corrupted_metric, self.restored_metric)
        ):
            raise ReverseEngineeringError("causal-trace metrics must be finite")

    @property
    def corruption_effect(self) -> float:
        return self.clean_metric - self.corrupted_metric

    @property
    def restoration_gain(self) -> float:
        return self.restored_metric - self.corrupted_metric

    @property
    def restoration_fraction(self) -> float | None:
        effect = self.corruption_effect
        if effect == 0.0:
            return None
        return self.restoration_gain / effect


@dataclass(frozen=True)
class CausalTraceLayerReport:
    layer_index: int
    observation_count: int
    mean_corruption_effect: float
    mean_restoration_gain: float
    mean_restoration_fraction: float | None
    positive_restoration_ratio: float
    over_restoration_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_index": self.layer_index,
            "observation_count": self.observation_count,
            "mean_corruption_effect": self.mean_corruption_effect,
            "mean_restoration_gain": self.mean_restoration_gain,
            "mean_restoration_fraction": self.mean_restoration_fraction,
            "positive_restoration_ratio": self.positive_restoration_ratio,
            "over_restoration_ratio": self.over_restoration_ratio,
            "digest": self.digest,
        }


def analyze_causal_trace(
    observations: Sequence[CausalTraceObservation],
) -> tuple[CausalTraceLayerReport, ...]:
    if not observations:
        raise ReverseEngineeringError("causal tracing requires observations")
    grouped: dict[int, list[CausalTraceObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.layer_index, []).append(observation)

    reports: list[CausalTraceLayerReport] = []
    for layer_index, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.observation_id)
        fractions = [
            item.restoration_fraction
            for item in ordered
            if item.restoration_fraction is not None
        ]
        payload = {
            "layer_index": layer_index,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "input_digest": item.input_digest,
                    "clean_metric": item.clean_metric,
                    "corrupted_metric": item.corrupted_metric,
                    "restored_metric": item.restored_metric,
                    "intervention_digest": item.intervention_digest,
                }
                for item in ordered
            ],
        }
        reports.append(
            CausalTraceLayerReport(
                layer_index=layer_index,
                observation_count=len(ordered),
                mean_corruption_effect=sum(item.corruption_effect for item in ordered) / len(ordered),
                mean_restoration_gain=sum(item.restoration_gain for item in ordered) / len(ordered),
                mean_restoration_fraction=(
                    sum(fractions) / len(fractions) if fractions else None
                ),
                positive_restoration_ratio=sum(item.restoration_gain > 0.0 for item in ordered) / len(ordered),
                over_restoration_ratio=sum(
                    fraction is not None and fraction > 1.0
                    for fraction in (item.restoration_fraction for item in ordered)
                ) / len(ordered),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
