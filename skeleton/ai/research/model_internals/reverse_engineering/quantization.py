"""Numerical characterization for authorized reference/quantized samples."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class QuantizationPair:
    pair_id: str
    reference: tuple[float, ...]
    quantized: tuple[float, ...]
    provenance_receipt: str

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ReverseEngineeringError("quantization pair requires pair_id")
        if not self.reference or len(self.reference) != len(self.quantized):
            raise ReverseEngineeringError("reference and quantized samples must be non-empty and aligned")
        if len(self.provenance_receipt) != 64:
            raise ReverseEngineeringError("quantization pair requires a provenance receipt")


@dataclass(frozen=True)
class QuantizationReport:
    pair_count: int
    scalar_count: int
    mean_absolute_error: float
    root_mean_square_error: float
    max_absolute_error: float
    cosine_similarity: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "pair_count": self.pair_count,
            "scalar_count": self.scalar_count,
            "mean_absolute_error": self.mean_absolute_error,
            "root_mean_square_error": self.root_mean_square_error,
            "max_absolute_error": self.max_absolute_error,
            "cosine_similarity": self.cosine_similarity,
            "digest": self.digest,
        }


def analyze_quantization(pairs: Sequence[QuantizationPair]) -> QuantizationReport:
    if not pairs:
        raise ReverseEngineeringError("quantization analysis requires pairs")
    reference: list[float] = []
    quantized: list[float] = []
    for pair in sorted(pairs, key=lambda item: item.pair_id):
        reference.extend(pair.reference)
        quantized.extend(pair.quantized)
    errors = [abs(a - b) for a, b in zip(reference, quantized)]
    squared = [(a - b) ** 2 for a, b in zip(reference, quantized)]
    dot = sum(a * b for a, b in zip(reference, quantized))
    norm_a = sqrt(sum(a * a for a in reference))
    norm_b = sqrt(sum(b * b for b in quantized))
    cosine = None if norm_a == 0.0 or norm_b == 0.0 else dot / (norm_a * norm_b)
    payload = {
        "pairs": [
            {
                "pair_id": pair.pair_id,
                "provenance_receipt": pair.provenance_receipt,
                "reference_digest": stable_digest(list(pair.reference)),
                "quantized_digest": stable_digest(list(pair.quantized)),
            }
            for pair in sorted(pairs, key=lambda item: item.pair_id)
        ]
    }
    return QuantizationReport(
        pair_count=len(pairs),
        scalar_count=len(errors),
        mean_absolute_error=sum(errors) / len(errors),
        root_mean_square_error=sqrt(sum(squared) / len(squared)),
        max_absolute_error=max(errors),
        cosine_similarity=cosine,
        digest=stable_digest(payload),
    )
