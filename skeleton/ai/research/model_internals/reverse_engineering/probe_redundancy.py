"""Probe redundancy estimates from binary outcome agreement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ProbeOutcomeVector:
    probe_id: str
    outcomes: tuple[bool, ...]

    def __post_init__(self) -> None:
        if not self.probe_id:
            raise ReverseEngineeringError("probe outcome vector requires probe_id")
        if not self.outcomes:
            raise ReverseEngineeringError("probe outcome vector must be non-empty")


@dataclass(frozen=True)
class RedundantProbePair:
    probe_a: str
    probe_b: str
    agreement_ratio: float


@dataclass(frozen=True)
class ProbeRedundancyReport:
    probe_count: int
    observation_count: int
    pair_count: int
    redundant_pairs: tuple[RedundantProbePair, ...]
    suggested_drop_ids: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_count": self.probe_count,
            "observation_count": self.observation_count,
            "pair_count": self.pair_count,
            "redundant_pairs": [
                {
                    "probe_a": pair.probe_a,
                    "probe_b": pair.probe_b,
                    "agreement_ratio": pair.agreement_ratio,
                }
                for pair in self.redundant_pairs
            ],
            "suggested_drop_ids": list(self.suggested_drop_ids),
            "digest": self.digest,
        }


def analyze_probe_redundancy(
    vectors: Sequence[ProbeOutcomeVector],
    *,
    redundancy_threshold: float = 0.95,
) -> ProbeRedundancyReport:
    if len(vectors) < 2:
        raise ReverseEngineeringError("probe redundancy requires at least two probes")
    if not 0.0 <= redundancy_threshold <= 1.0:
        raise ReverseEngineeringError("redundancy_threshold must be within [0, 1]")
    ids = [vector.probe_id for vector in vectors]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("probe ids must be unique")
    length = len(vectors[0].outcomes)
    if any(len(vector.outcomes) != length for vector in vectors):
        raise ReverseEngineeringError("probe outcome vectors must be aligned")

    redundant: list[RedundantProbePair] = []
    drop: set[str] = set()
    ordered = sorted(vectors, key=lambda vector: vector.probe_id)
    pair_count = 0
    for i, left in enumerate(ordered):
        for right in ordered[i + 1:]:
            pair_count += 1
            agreement = sum(a == b for a, b in zip(left.outcomes, right.outcomes)) / length
            if agreement >= redundancy_threshold:
                redundant.append(RedundantProbePair(left.probe_id, right.probe_id, agreement))
                drop.add(right.probe_id)

    payload = {
        "redundancy_threshold": redundancy_threshold,
        "vectors": [
            {"probe_id": vector.probe_id, "outcomes": list(vector.outcomes)}
            for vector in ordered
        ],
    }
    return ProbeRedundancyReport(
        probe_count=len(ordered),
        observation_count=length,
        pair_count=pair_count,
        redundant_pairs=tuple(redundant),
        suggested_drop_ids=tuple(sorted(drop)),
        digest=stable_digest(payload),
    )
