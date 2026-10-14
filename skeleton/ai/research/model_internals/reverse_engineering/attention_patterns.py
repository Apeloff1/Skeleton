"""Aggregate attention-pattern characterization for authorized local models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class AttentionPatternSample:
    sample_id: str
    input_digest: str
    layer_index: int
    head_index: int
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.sample_id:
            raise ReverseEngineeringError("attention-pattern sample requires sample_id")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if self.layer_index < 0 or self.head_index < 0:
            raise ReverseEngineeringError("layer_index and head_index must be non-negative")
        if not self.weights:
            raise ReverseEngineeringError("attention weights must be non-empty")
        if any(not isfinite(weight) or weight < 0.0 for weight in self.weights):
            raise ReverseEngineeringError("attention weights must be finite and non-negative")
        total = sum(self.weights)
        if total <= 0.0:
            raise ReverseEngineeringError("attention weights must have positive mass")


@dataclass(frozen=True)
class AttentionPatternReport:
    layer_index: int
    head_index: int
    sample_count: int
    mean_peak_weight: float
    mean_first_position_weight: float
    mean_last_position_weight: float
    mean_effective_support: float
    sink_candidate_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_index": self.layer_index,
            "head_index": self.head_index,
            "sample_count": self.sample_count,
            "mean_peak_weight": self.mean_peak_weight,
            "mean_first_position_weight": self.mean_first_position_weight,
            "mean_last_position_weight": self.mean_last_position_weight,
            "mean_effective_support": self.mean_effective_support,
            "sink_candidate_ratio": self.sink_candidate_ratio,
            "digest": self.digest,
        }


def _normalized(weights: tuple[float, ...]) -> tuple[float, ...]:
    total = sum(weights)
    return tuple(weight / total for weight in weights)


def _effective_support(weights: tuple[float, ...]) -> float:
    concentration = sum(weight * weight for weight in weights)
    return 1.0 / concentration if concentration > 0.0 else 0.0


def analyze_attention_patterns(
    samples: Sequence[AttentionPatternSample],
    *,
    sink_threshold: float = 0.25,
) -> tuple[AttentionPatternReport, ...]:
    if not samples:
        raise ReverseEngineeringError("attention-pattern analysis requires samples")
    if not 0.0 <= sink_threshold <= 1.0:
        raise ReverseEngineeringError("sink_threshold must be within [0, 1]")
    grouped: dict[tuple[int, int], list[AttentionPatternSample]] = {}
    for sample in samples:
        grouped.setdefault((sample.layer_index, sample.head_index), []).append(sample)

    reports: list[AttentionPatternReport] = []
    for (layer_index, head_index), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: (item.sample_id, item.input_digest))
        normalized = [_normalized(item.weights) for item in ordered]
        first = [weights[0] for weights in normalized]
        last = [weights[-1] for weights in normalized]
        peaks = [max(weights) for weights in normalized]
        supports = [_effective_support(weights) for weights in normalized]
        payload = {
            "layer_index": layer_index,
            "head_index": head_index,
            "samples": [
                {
                    "sample_id": item.sample_id,
                    "input_digest": item.input_digest,
                    "weights_digest": stable_digest(list(item.weights)),
                    "length": len(item.weights),
                }
                for item in ordered
            ],
            "sink_threshold": sink_threshold,
        }
        reports.append(
            AttentionPatternReport(
                layer_index=layer_index,
                head_index=head_index,
                sample_count=len(ordered),
                mean_peak_weight=sum(peaks) / len(peaks),
                mean_first_position_weight=sum(first) / len(first),
                mean_last_position_weight=sum(last) / len(last),
                mean_effective_support=sum(supports) / len(supports),
                sink_candidate_ratio=sum(value >= sink_threshold for value in first) / len(first),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
