"""Aggregate embedding geometry for authorized local/open models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class EmbeddingSample:
    sample_id: str
    input_digest: str
    vector: tuple[float, ...]
    condition: str = "default"

    def __post_init__(self) -> None:
        if not self.sample_id or not self.condition:
            raise ReverseEngineeringError("embedding sample identity is required")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if not self.vector:
            raise ReverseEngineeringError("embedding vector must be non-empty")
        if any(not isfinite(value) for value in self.vector):
            raise ReverseEngineeringError("embedding vector must contain finite values")


@dataclass(frozen=True)
class EmbeddingGeometryReport:
    condition: str
    sample_count: int
    dimension: int
    zero_norm_count: int
    mean_norm: float
    min_norm: float
    max_norm: float
    mean_pairwise_cosine: float | None
    mean_absolute_pairwise_cosine: float | None
    centroid_norm: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "sample_count": self.sample_count,
            "dimension": self.dimension,
            "zero_norm_count": self.zero_norm_count,
            "mean_norm": self.mean_norm,
            "min_norm": self.min_norm,
            "max_norm": self.max_norm,
            "mean_pairwise_cosine": self.mean_pairwise_cosine,
            "mean_absolute_pairwise_cosine": self.mean_absolute_pairwise_cosine,
            "centroid_norm": self.centroid_norm,
            "digest": self.digest,
        }


def _norm(vector: tuple[float, ...]) -> float:
    return sqrt(sum(value * value for value in vector))


def analyze_embedding_geometry(
    samples: Sequence[EmbeddingSample],
) -> tuple[EmbeddingGeometryReport, ...]:
    if not samples:
        raise ReverseEngineeringError("embedding geometry requires samples")
    grouped: dict[str, list[EmbeddingSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.condition, []).append(sample)

    reports: list[EmbeddingGeometryReport] = []
    for condition, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.sample_id)
        dimension = len(ordered[0].vector)
        if any(len(item.vector) != dimension for item in ordered):
            raise ReverseEngineeringError("embedding dimensions must match within a condition")
        norms = [_norm(item.vector) for item in ordered]
        cosines: list[float] = []
        for left_index, left in enumerate(ordered):
            left_norm = norms[left_index]
            if left_norm == 0.0:
                continue
            for right_index in range(left_index + 1, len(ordered)):
                right_norm = norms[right_index]
                if right_norm == 0.0:
                    continue
                dot = sum(a * b for a, b in zip(left.vector, ordered[right_index].vector))
                cosines.append(dot / (left_norm * right_norm))

        centroid = tuple(
            sum(item.vector[index] for item in ordered) / len(ordered)
            for index in range(dimension)
        )
        payload = {
            "condition": condition,
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
            EmbeddingGeometryReport(
                condition=condition,
                sample_count=len(ordered),
                dimension=dimension,
                zero_norm_count=sum(1 for norm in norms if norm == 0.0),
                mean_norm=sum(norms) / len(norms),
                min_norm=min(norms),
                max_norm=max(norms),
                mean_pairwise_cosine=(sum(cosines) / len(cosines) if cosines else None),
                mean_absolute_pairwise_cosine=(
                    sum(abs(value) for value in cosines) / len(cosines) if cosines else None
                ),
                centroid_norm=_norm(centroid),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
