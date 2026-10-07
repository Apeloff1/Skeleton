"""Matched-input representation correspondence across authorized models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class CorrespondencePair:
    pair_id: str
    input_digest: str
    left_model: str
    right_model: str
    left_vector: tuple[float, ...]
    right_vector: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.pair_id or not self.left_model or not self.right_model:
            raise ReverseEngineeringError("correspondence pair identity is required")
        if self.left_model == self.right_model:
            raise ReverseEngineeringError("correspondence pair requires distinct model identities")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if not self.left_vector or len(self.left_vector) != len(self.right_vector):
            raise ReverseEngineeringError("correspondence vectors must be non-empty and aligned")
        if any(not isfinite(value) for value in self.left_vector + self.right_vector):
            raise ReverseEngineeringError("correspondence vectors must contain finite values")


@dataclass(frozen=True)
class ModelCorrespondenceReport:
    left_model: str
    right_model: str
    pair_count: int
    dimension: int
    mean_cosine_similarity: float | None
    min_cosine_similarity: float | None
    max_cosine_similarity: float | None
    mean_norm_ratio_right_over_left: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_model": self.left_model,
            "right_model": self.right_model,
            "pair_count": self.pair_count,
            "dimension": self.dimension,
            "mean_cosine_similarity": self.mean_cosine_similarity,
            "min_cosine_similarity": self.min_cosine_similarity,
            "max_cosine_similarity": self.max_cosine_similarity,
            "mean_norm_ratio_right_over_left": self.mean_norm_ratio_right_over_left,
            "digest": self.digest,
        }


def _norm(vector: tuple[float, ...]) -> float:
    return sqrt(sum(value * value for value in vector))


def analyze_model_correspondence(
    pairs: Sequence[CorrespondencePair],
) -> tuple[ModelCorrespondenceReport, ...]:
    if not pairs:
        raise ReverseEngineeringError("model correspondence requires pairs")
    grouped: dict[tuple[str, str], list[CorrespondencePair]] = {}
    for pair in pairs:
        key = tuple(sorted((pair.left_model, pair.right_model)))
        grouped.setdefault(key, []).append(pair)

    reports: list[ModelCorrespondenceReport] = []
    for (model_a, model_b), items in sorted(grouped.items()):
        canonical: list[CorrespondencePair] = []
        for item in items:
            if item.left_model == model_a:
                canonical.append(item)
            else:
                canonical.append(
                    CorrespondencePair(
                        pair_id=item.pair_id,
                        input_digest=item.input_digest,
                        left_model=item.right_model,
                        right_model=item.left_model,
                        left_vector=item.right_vector,
                        right_vector=item.left_vector,
                    )
                )
        ordered = sorted(canonical, key=lambda item: item.pair_id)
        dimension = len(ordered[0].left_vector)
        if any(len(item.left_vector) != dimension for item in ordered):
            raise ReverseEngineeringError("correspondence dimensions must match within a model pair")
        cosines: list[float] = []
        ratios: list[float] = []
        for item in ordered:
            left_norm = _norm(item.left_vector)
            right_norm = _norm(item.right_vector)
            if left_norm != 0.0 and right_norm != 0.0:
                dot = sum(a * b for a, b in zip(item.left_vector, item.right_vector))
                cosines.append(dot / (left_norm * right_norm))
            if left_norm != 0.0:
                ratios.append(right_norm / left_norm)
        payload = {
            "left_model": model_a,
            "right_model": model_b,
            "pairs": [
                {
                    "pair_id": item.pair_id,
                    "input_digest": item.input_digest,
                    "left_vector_digest": stable_digest(list(item.left_vector)),
                    "right_vector_digest": stable_digest(list(item.right_vector)),
                }
                for item in ordered
            ],
        }
        reports.append(
            ModelCorrespondenceReport(
                left_model=model_a,
                right_model=model_b,
                pair_count=len(ordered),
                dimension=dimension,
                mean_cosine_similarity=(sum(cosines) / len(cosines) if cosines else None),
                min_cosine_similarity=(min(cosines) if cosines else None),
                max_cosine_similarity=(max(cosines) if cosines else None),
                mean_norm_ratio_right_over_left=(sum(ratios) / len(ratios) if ratios else None),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
