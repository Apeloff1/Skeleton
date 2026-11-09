"""Subspace/circuit overlap summaries for authorized local-model representations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class SubspaceBasis:
    basis_id: str
    layer_id: str
    feature_digest: str
    vectors: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if not self.basis_id or not self.layer_id:
            raise ReverseEngineeringError("subspace basis identity is required")
        if not is_sha256_digest(self.feature_digest):
            raise ReverseEngineeringError("feature_digest must be a sha256 hex digest")
        if not self.vectors:
            raise ReverseEngineeringError("subspace basis requires vectors")
        dimension = len(self.vectors[0])
        if dimension <= 0 or any(len(vector) != dimension for vector in self.vectors):
            raise ReverseEngineeringError("subspace vectors must be non-empty and dimension-aligned")
        if any(not isfinite(value) for vector in self.vectors for value in vector):
            raise ReverseEngineeringError("subspace vectors must contain finite values")
        if any(_norm(vector) == 0.0 for vector in self.vectors):
            raise ReverseEngineeringError("subspace vectors must have non-zero norm")


@dataclass(frozen=True)
class SubspaceOverlapReport:
    left_basis_id: str
    right_basis_id: str
    dimension: int
    left_rank: int
    right_rank: int
    max_absolute_cosine: float
    mean_best_match_cosine: float
    symmetric_overlap_score: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_basis_id": self.left_basis_id,
            "right_basis_id": self.right_basis_id,
            "dimension": self.dimension,
            "left_rank": self.left_rank,
            "right_rank": self.right_rank,
            "max_absolute_cosine": self.max_absolute_cosine,
            "mean_best_match_cosine": self.mean_best_match_cosine,
            "symmetric_overlap_score": self.symmetric_overlap_score,
            "digest": self.digest,
        }


def _norm(vector: Sequence[float]) -> float:
    return sqrt(sum(value * value for value in vector))


def _abs_cosine(left: Sequence[float], right: Sequence[float]) -> float:
    return abs(sum(a * b for a, b in zip(left, right)) / (_norm(left) * _norm(right)))


def analyze_subspace_overlap(
    left: SubspaceBasis,
    right: SubspaceBasis,
) -> SubspaceOverlapReport:
    dimension = len(left.vectors[0])
    if len(right.vectors[0]) != dimension:
        raise ReverseEngineeringError("subspace dimensions must match")

    matrix = [
        [_abs_cosine(lv, rv) for rv in right.vectors]
        for lv in left.vectors
    ]
    left_best = [max(row) for row in matrix]
    right_best = [max(matrix[i][j] for i in range(len(matrix))) for j in range(len(matrix[0]))]
    all_values = [value for row in matrix for value in row]
    symmetric = (
        (sum(left_best) / len(left_best)) + (sum(right_best) / len(right_best))
    ) / 2.0
    payload = {
        "left": {
            "basis_id": left.basis_id,
            "layer_id": left.layer_id,
            "feature_digest": left.feature_digest,
            "vector_digests": [stable_digest(list(vector)) for vector in left.vectors],
        },
        "right": {
            "basis_id": right.basis_id,
            "layer_id": right.layer_id,
            "feature_digest": right.feature_digest,
            "vector_digests": [stable_digest(list(vector)) for vector in right.vectors],
        },
    }
    return SubspaceOverlapReport(
        left_basis_id=left.basis_id,
        right_basis_id=right.basis_id,
        dimension=dimension,
        left_rank=len(left.vectors),
        right_rank=len(right.vectors),
        max_absolute_cosine=max(all_values),
        mean_best_match_cosine=sum(left_best) / len(left_best),
        symmetric_overlap_score=symmetric,
        digest=stable_digest(payload),
    )
