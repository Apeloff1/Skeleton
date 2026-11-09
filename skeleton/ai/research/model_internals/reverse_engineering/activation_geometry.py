"""Aggregate activation geometry without persisting raw activation tensors."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ActivationSample:
    sample_id: str
    layer_id: str
    input_digest: str
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.sample_id or not self.layer_id:
            raise ReverseEngineeringError("activation sample identity is required")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if not self.vector:
            raise ReverseEngineeringError("activation vector must be non-empty")
        if any(not isfinite(value) for value in self.vector):
            raise ReverseEngineeringError("activation vector must contain finite values")


@dataclass(frozen=True)
class ActivationLayerReport:
    layer_id: str
    sample_count: int
    dimension: int
    mean_norm: float
    zero_fraction: float
    mean_pairwise_cosine: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "sample_count": self.sample_count,
            "dimension": self.dimension,
            "mean_norm": self.mean_norm,
            "zero_fraction": self.zero_fraction,
            "mean_pairwise_cosine": self.mean_pairwise_cosine,
            "digest": self.digest,
        }


def _norm(vector: tuple[float, ...]) -> float:
    return sqrt(sum(value * value for value in vector))


def analyze_activation_geometry(
    samples: Sequence[ActivationSample],
) -> tuple[ActivationLayerReport, ...]:
    if not samples:
        raise ReverseEngineeringError("activation geometry requires samples")
    grouped: dict[str, list[ActivationSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.layer_id, []).append(sample)

    reports: list[ActivationLayerReport] = []
    for layer_id, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.sample_id)
        dimension = len(ordered[0].vector)
        if any(len(item.vector) != dimension for item in ordered):
            raise ReverseEngineeringError("activation dimensions must match within a layer")
        norms = [_norm(item.vector) for item in ordered]
        cosine_values: list[float] = []
        for left_index, left in enumerate(ordered):
            if norms[left_index] == 0.0:
                continue
            for right_index in range(left_index + 1, len(ordered)):
                if norms[right_index] == 0.0:
                    continue
                dot = sum(a * b for a, b in zip(left.vector, ordered[right_index].vector))
                cosine_values.append(dot / (norms[left_index] * norms[right_index]))
        scalar_count = len(ordered) * dimension
        zero_count = sum(
            1 for item in ordered for value in item.vector if value == 0.0
        )
        payload = {
            "layer_id": layer_id,
            "samples": [
                {
                    "sample_id": item.sample_id,
                    "input_digest": item.input_digest,
                    "vector_digest": stable_digest(list(item.vector)),
                }
                for item in ordered
            ],
        }
        reports.append(
            ActivationLayerReport(
                layer_id=layer_id,
                sample_count=len(ordered),
                dimension=dimension,
                mean_norm=sum(norms) / len(norms),
                zero_fraction=zero_count / scalar_count,
                mean_pairwise_cosine=(
                    sum(cosine_values) / len(cosine_values) if cosine_values else None
                ),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
