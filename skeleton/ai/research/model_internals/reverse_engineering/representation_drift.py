"""Cross-layer representation drift for authorized local-model activations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class LayerRepresentation:
    sample_id: str
    input_digest: str
    layer_index: int
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.sample_id:
            raise ReverseEngineeringError("representation sample requires sample_id")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if self.layer_index < 0:
            raise ReverseEngineeringError("layer_index must be non-negative")
        if not self.vector:
            raise ReverseEngineeringError("representation vector must be non-empty")
        if any(not isfinite(value) for value in self.vector):
            raise ReverseEngineeringError("representation vector must contain finite values")


@dataclass(frozen=True)
class RepresentationTransition:
    from_layer: int
    to_layer: int
    pair_count: int
    mean_cosine_similarity: float | None
    mean_cosine_drift: float | None
    mean_norm_ratio: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_layer": self.from_layer,
            "to_layer": self.to_layer,
            "pair_count": self.pair_count,
            "mean_cosine_similarity": self.mean_cosine_similarity,
            "mean_cosine_drift": self.mean_cosine_drift,
            "mean_norm_ratio": self.mean_norm_ratio,
            "digest": self.digest,
        }


def _norm(vector: tuple[float, ...]) -> float:
    return sqrt(sum(value * value for value in vector))


def analyze_representation_drift(
    samples: Sequence[LayerRepresentation],
) -> tuple[RepresentationTransition, ...]:
    if not samples:
        raise ReverseEngineeringError("representation drift requires samples")
    by_sample: dict[tuple[str, str], list[LayerRepresentation]] = {}
    for sample in samples:
        by_sample.setdefault((sample.sample_id, sample.input_digest), []).append(sample)

    transition_pairs: dict[tuple[int, int], list[tuple[float | None, float | None]]] = {}
    transition_evidence: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for (sample_id, input_digest), items in sorted(by_sample.items()):
        ordered = sorted(items, key=lambda item: item.layer_index)
        indices = [item.layer_index for item in ordered]
        if len(indices) != len(set(indices)):
            raise ReverseEngineeringError("layer indices must be unique within each sample")
        dimension = len(ordered[0].vector)
        if any(len(item.vector) != dimension for item in ordered):
            raise ReverseEngineeringError("representation dimensions must match within each sample")
        for left, right in zip(ordered, ordered[1:]):
            left_norm = _norm(left.vector)
            right_norm = _norm(right.vector)
            cosine = None
            if left_norm != 0.0 and right_norm != 0.0:
                cosine = sum(a * b for a, b in zip(left.vector, right.vector)) / (left_norm * right_norm)
            norm_ratio = None if left_norm == 0.0 else right_norm / left_norm
            key = (left.layer_index, right.layer_index)
            transition_pairs.setdefault(key, []).append((cosine, norm_ratio))
            transition_evidence.setdefault(key, []).append(
                {
                    "sample_id": sample_id,
                    "input_digest": input_digest,
                    "left_vector_digest": stable_digest(list(left.vector)),
                    "right_vector_digest": stable_digest(list(right.vector)),
                }
            )

    reports: list[RepresentationTransition] = []
    for key in sorted(transition_pairs):
        values = transition_pairs[key]
        cosines = [cosine for cosine, _ in values if cosine is not None]
        ratios = [ratio for _, ratio in values if ratio is not None]
        mean_cosine = sum(cosines) / len(cosines) if cosines else None
        reports.append(
            RepresentationTransition(
                from_layer=key[0],
                to_layer=key[1],
                pair_count=len(values),
                mean_cosine_similarity=mean_cosine,
                mean_cosine_drift=(1.0 - mean_cosine if mean_cosine is not None else None),
                mean_norm_ratio=(sum(ratios) / len(ratios) if ratios else None),
                digest=stable_digest(
                    {
                        "from_layer": key[0],
                        "to_layer": key[1],
                        "evidence": transition_evidence[key],
                    }
                ),
            )
        )
    return tuple(reports)
