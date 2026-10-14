"""Positional-sensitivity characterization from controlled offset trials."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class PositionTrial:
    trial_id: str
    probe_id: str
    content_digest: str
    offset: int
    similarity_to_anchor: float
    output_digest: str

    def __post_init__(self) -> None:
        if not self.trial_id or not self.probe_id:
            raise ReverseEngineeringError("position trial identity is required")
        if not is_sha256_digest(self.content_digest) or not is_sha256_digest(self.output_digest):
            raise ReverseEngineeringError("position trial digests must be sha256 hex digests")
        if self.offset < 0:
            raise ReverseEngineeringError("offset must be non-negative")
        if not isfinite(self.similarity_to_anchor) or not 0.0 <= self.similarity_to_anchor <= 1.0:
            raise ReverseEngineeringError("similarity_to_anchor must be finite and within [0, 1]")


@dataclass(frozen=True)
class PositionSensitivityReport:
    probe_id: str
    trial_count: int
    anchor_offset: int
    max_offset: int
    mean_similarity: float
    min_similarity: float
    similarity_drop: float
    monotonicity_violations: int
    invariant_above_095_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "trial_count": self.trial_count,
            "anchor_offset": self.anchor_offset,
            "max_offset": self.max_offset,
            "mean_similarity": self.mean_similarity,
            "min_similarity": self.min_similarity,
            "similarity_drop": self.similarity_drop,
            "monotonicity_violations": self.monotonicity_violations,
            "invariant_above_095_ratio": self.invariant_above_095_ratio,
            "digest": self.digest,
        }


def analyze_position_sensitivity(
    trials: Sequence[PositionTrial],
) -> tuple[PositionSensitivityReport, ...]:
    if not trials:
        raise ReverseEngineeringError("position sensitivity requires trials")
    grouped: dict[str, list[PositionTrial]] = {}
    for trial in trials:
        grouped.setdefault(trial.probe_id, []).append(trial)

    reports: list[PositionSensitivityReport] = []
    for probe_id, items in sorted(grouped.items()):
        digests = {item.content_digest for item in items}
        if len(digests) != 1:
            raise ReverseEngineeringError("position trials for a probe must share content_digest")
        ordered = sorted(items, key=lambda item: (item.offset, item.trial_id))
        offsets = [item.offset for item in ordered]
        if len(offsets) != len(set(offsets)):
            raise ReverseEngineeringError("position offsets must be unique within a probe")
        similarities = [item.similarity_to_anchor for item in ordered]
        violations = sum(
            right > left + 1e-12
            for left, right in zip(similarities, similarities[1:])
        )
        payload = {
            "probe_id": probe_id,
            "content_digest": ordered[0].content_digest,
            "trials": [
                {
                    "trial_id": item.trial_id,
                    "offset": item.offset,
                    "similarity_to_anchor": item.similarity_to_anchor,
                    "output_digest": item.output_digest,
                }
                for item in ordered
            ],
        }
        reports.append(
            PositionSensitivityReport(
                probe_id=probe_id,
                trial_count=len(ordered),
                anchor_offset=ordered[0].offset,
                max_offset=ordered[-1].offset,
                mean_similarity=sum(similarities) / len(similarities),
                min_similarity=min(similarities),
                similarity_drop=similarities[0] - similarities[-1],
                monotonicity_violations=violations,
                invariant_above_095_ratio=sum(value >= 0.95 for value in similarities) / len(similarities),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
