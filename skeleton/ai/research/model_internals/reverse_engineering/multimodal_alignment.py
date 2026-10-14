"""Cross-modal alignment drift for authorized paired representations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class MultimodalAlignmentPair:
    pair_id: str
    semantic_digest: str
    layer_index: int
    modality_a: str
    modality_b: str
    vector_a: tuple[float, ...]
    vector_b: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.pair_id or not self.modality_a or not self.modality_b:
            raise ReverseEngineeringError("multimodal alignment identity is required")
        if self.modality_a == self.modality_b:
            raise ReverseEngineeringError("alignment pair requires distinct modalities")
        if not is_sha256_digest(self.semantic_digest):
            raise ReverseEngineeringError("semantic_digest must be a sha256 hex digest")
        if self.layer_index < 0:
            raise ReverseEngineeringError("layer_index must be non-negative")
        if not self.vector_a or len(self.vector_a) != len(self.vector_b):
            raise ReverseEngineeringError("alignment vectors must be non-empty and aligned")
        if any(not isfinite(value) for value in self.vector_a + self.vector_b):
            raise ReverseEngineeringError("alignment vectors must contain finite values")


@dataclass(frozen=True)
class MultimodalAlignmentReport:
    modality_a: str
    modality_b: str
    layer_index: int
    pair_count: int
    dimension: int
    mean_cosine_similarity: float | None
    min_cosine_similarity: float | None
    mean_norm_ratio_b_over_a: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "modality_a": self.modality_a,
            "modality_b": self.modality_b,
            "layer_index": self.layer_index,
            "pair_count": self.pair_count,
            "dimension": self.dimension,
            "mean_cosine_similarity": self.mean_cosine_similarity,
            "min_cosine_similarity": self.min_cosine_similarity,
            "mean_norm_ratio_b_over_a": self.mean_norm_ratio_b_over_a,
            "digest": self.digest,
        }


def _norm(vector: Sequence[float]) -> float:
    return sqrt(sum(value * value for value in vector))


def analyze_multimodal_alignment(
    pairs: Sequence[MultimodalAlignmentPair],
) -> tuple[MultimodalAlignmentReport, ...]:
    if not pairs:
        raise ReverseEngineeringError("multimodal alignment requires pairs")
    grouped: dict[tuple[str, str, int], list[MultimodalAlignmentPair]] = {}
    for pair in pairs:
        modalities = tuple(sorted((pair.modality_a, pair.modality_b)))
        if pair.modality_a == modalities[0]:
            canonical = pair
        else:
            canonical = MultimodalAlignmentPair(
                pair_id=pair.pair_id,
                semantic_digest=pair.semantic_digest,
                layer_index=pair.layer_index,
                modality_a=pair.modality_b,
                modality_b=pair.modality_a,
                vector_a=pair.vector_b,
                vector_b=pair.vector_a,
            )
        grouped.setdefault((modalities[0], modalities[1], pair.layer_index), []).append(canonical)

    reports: list[MultimodalAlignmentReport] = []
    for (modality_a, modality_b, layer_index), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.pair_id)
        dimension = len(ordered[0].vector_a)
        if any(len(item.vector_a) != dimension for item in ordered):
            raise ReverseEngineeringError("alignment dimensions must match within a group")
        cosines: list[float] = []
        ratios: list[float] = []
        for item in ordered:
            norm_a = _norm(item.vector_a)
            norm_b = _norm(item.vector_b)
            if norm_a and norm_b:
                cosines.append(
                    sum(a * b for a, b in zip(item.vector_a, item.vector_b)) / (norm_a * norm_b)
                )
            if norm_a:
                ratios.append(norm_b / norm_a)
        payload = {
            "modality_a": modality_a,
            "modality_b": modality_b,
            "layer_index": layer_index,
            "pairs": [
                {
                    "pair_id": item.pair_id,
                    "semantic_digest": item.semantic_digest,
                    "vector_a_digest": stable_digest(list(item.vector_a)),
                    "vector_b_digest": stable_digest(list(item.vector_b)),
                }
                for item in ordered
            ],
        }
        reports.append(
            MultimodalAlignmentReport(
                modality_a=modality_a,
                modality_b=modality_b,
                layer_index=layer_index,
                pair_count=len(ordered),
                dimension=dimension,
                mean_cosine_similarity=(sum(cosines) / len(cosines) if cosines else None),
                min_cosine_similarity=(min(cosines) if cosines else None),
                mean_norm_ratio_b_over_a=(sum(ratios) / len(ratios) if ratios else None),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
