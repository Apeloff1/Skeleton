"""Multimodal adapter geometry from authorized projection metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class AdapterProjection:
    projection_id: str
    source_modality: str
    target_space: str
    input_dim: int
    output_dim: int
    rank: int | None
    provenance_receipt: str
    weight_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.projection_id or not self.source_modality or not self.target_space:
            raise ReverseEngineeringError("adapter projection identity fields are required")
        if self.input_dim <= 0 or self.output_dim <= 0:
            raise ReverseEngineeringError("adapter dimensions must be positive")
        if self.rank is not None and (self.rank <= 0 or self.rank > min(self.input_dim, self.output_dim)):
            raise ReverseEngineeringError("adapter rank must be positive and bounded by dimensions")
        if not is_sha256_digest(self.provenance_receipt):
            raise ReverseEngineeringError("provenance_receipt must be a sha256 hex digest")
        if self.weight_digest is not None and not is_sha256_digest(self.weight_digest):
            raise ReverseEngineeringError("weight_digest must be a sha256 hex digest")


@dataclass(frozen=True)
class MultimodalAdapterReport:
    projection_count: int
    source_modalities: tuple[str, ...]
    target_spaces: tuple[str, ...]
    dimension_pairs: tuple[tuple[int, int], ...]
    low_rank_projection_count: int
    expansion_count: int
    contraction_count: int
    square_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "projection_count": self.projection_count,
            "source_modalities": list(self.source_modalities),
            "target_spaces": list(self.target_spaces),
            "dimension_pairs": [list(pair) for pair in self.dimension_pairs],
            "low_rank_projection_count": self.low_rank_projection_count,
            "expansion_count": self.expansion_count,
            "contraction_count": self.contraction_count,
            "square_count": self.square_count,
            "digest": self.digest,
        }


def analyze_multimodal_adapters(
    projections: Sequence[AdapterProjection],
) -> MultimodalAdapterReport:
    if not projections:
        raise ReverseEngineeringError("multimodal adapter analysis requires projections")
    ids = [projection.projection_id for projection in projections]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("projection_id values must be unique")
    ordered = sorted(projections, key=lambda item: item.projection_id)
    payload = {
        "projections": [
            {
                "projection_id": item.projection_id,
                "source_modality": item.source_modality,
                "target_space": item.target_space,
                "input_dim": item.input_dim,
                "output_dim": item.output_dim,
                "rank": item.rank,
                "provenance_receipt": item.provenance_receipt,
                "weight_digest": item.weight_digest,
            }
            for item in ordered
        ]
    }
    return MultimodalAdapterReport(
        projection_count=len(ordered),
        source_modalities=tuple(sorted({item.source_modality for item in ordered})),
        target_spaces=tuple(sorted({item.target_space for item in ordered})),
        dimension_pairs=tuple(sorted({(item.input_dim, item.output_dim) for item in ordered})),
        low_rank_projection_count=sum(
            item.rank is not None and item.rank < min(item.input_dim, item.output_dim)
            for item in ordered
        ),
        expansion_count=sum(item.output_dim > item.input_dim for item in ordered),
        contraction_count=sum(item.output_dim < item.input_dim for item in ordered),
        square_count=sum(item.output_dim == item.input_dim for item in ordered),
        digest=stable_digest(payload),
    )
