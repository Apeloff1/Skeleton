"""Black-box decoding variability signatures without logit access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class DecodeSample:
    sample_id: str
    condition_id: str
    output_digest: str
    output_units: int
    stop_reason: str = "unknown"

    def __post_init__(self) -> None:
        if not self.sample_id or not self.condition_id:
            raise ReverseEngineeringError("decode sample identity is required")
        if len(self.output_digest) != 64:
            raise ReverseEngineeringError("output_digest must be sha256 length")
        if self.output_units < 0:
            raise ReverseEngineeringError("output_units must be non-negative")


@dataclass(frozen=True)
class DecodingSignature:
    condition_id: str
    sample_count: int
    unique_output_count: int
    diversity_ratio: float
    collision_ratio: float
    min_output_units: int
    max_output_units: int
    mean_output_units: float
    stop_reason_counts: tuple[tuple[str, int], ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "sample_count": self.sample_count,
            "unique_output_count": self.unique_output_count,
            "diversity_ratio": self.diversity_ratio,
            "collision_ratio": self.collision_ratio,
            "min_output_units": self.min_output_units,
            "max_output_units": self.max_output_units,
            "mean_output_units": self.mean_output_units,
            "stop_reason_counts": [list(item) for item in self.stop_reason_counts],
            "digest": self.digest,
        }


def decoding_signatures(samples: Sequence[DecodeSample]) -> tuple[DecodingSignature, ...]:
    if not samples:
        raise ReverseEngineeringError("decoding analysis requires samples")
    grouped: dict[str, list[DecodeSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.condition_id, []).append(sample)

    result: list[DecodingSignature] = []
    for condition, items in sorted(grouped.items()):
        outputs = {item.output_digest for item in items}
        total = len(items)
        diversity = len(outputs) / total
        stops: dict[str, int] = {}
        for item in items:
            stops[item.stop_reason] = stops.get(item.stop_reason, 0) + 1
        units = [item.output_units for item in items]
        payload = {
            "condition": condition,
            "samples": [
                {
                    "sample_id": item.sample_id,
                    "output_digest": item.output_digest,
                    "output_units": item.output_units,
                    "stop_reason": item.stop_reason,
                }
                for item in sorted(items, key=lambda value: value.sample_id)
            ],
        }
        result.append(
            DecodingSignature(
                condition_id=condition,
                sample_count=total,
                unique_output_count=len(outputs),
                diversity_ratio=diversity,
                collision_ratio=1.0 - diversity,
                min_output_units=min(units),
                max_output_units=max(units),
                mean_output_units=sum(units) / total,
                stop_reason_counts=tuple(sorted(stops.items())),
                digest=stable_digest(payload),
            )
        )
    return tuple(result)
