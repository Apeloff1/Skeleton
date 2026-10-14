"""Ordinal evidence staleness for long-running research campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class EvidenceAge:
    evidence_id: str
    evidence_digest: str
    produced_epoch: int
    current_epoch: int
    maximum_age: int

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ReverseEngineeringError("evidence age requires identity")
        if not is_sha256_digest(self.evidence_digest):
            raise ReverseEngineeringError("evidence_digest must be sha256 hex")
        if self.produced_epoch < 0 or self.current_epoch < 0 or self.maximum_age < 0:
            raise ReverseEngineeringError("evidence epochs and maximum_age must be non-negative")
        if self.current_epoch < self.produced_epoch:
            raise ReverseEngineeringError("current_epoch cannot precede produced_epoch")

    @property
    def age(self) -> int:
        return self.current_epoch - self.produced_epoch

    @property
    def stale(self) -> bool:
        return self.age > self.maximum_age


@dataclass(frozen=True)
class EvidenceStalenessReport:
    evidence_count: int
    stale_count: int
    stale_ratio: float
    maximum_age_observed: int
    stale_ids: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_count": self.evidence_count,
            "stale_count": self.stale_count,
            "stale_ratio": self.stale_ratio,
            "maximum_age_observed": self.maximum_age_observed,
            "stale_ids": list(self.stale_ids),
            "digest": self.digest,
        }


def analyze_evidence_staleness(
    evidence: Sequence[EvidenceAge],
) -> EvidenceStalenessReport:
    if not evidence:
        raise ReverseEngineeringError("evidence staleness requires evidence")
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("evidence ids must be unique")
    stale = [item for item in evidence if item.stale]
    payload = {
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "evidence_digest": item.evidence_digest,
                "produced_epoch": item.produced_epoch,
                "current_epoch": item.current_epoch,
                "maximum_age": item.maximum_age,
            }
            for item in sorted(evidence, key=lambda value: value.evidence_id)
        ]
    }
    return EvidenceStalenessReport(
        evidence_count=len(evidence),
        stale_count=len(stale),
        stale_ratio=len(stale) / len(evidence),
        maximum_age_observed=max(item.age for item in evidence),
        stale_ids=tuple(sorted(item.evidence_id for item in stale)),
        digest=stable_digest(payload),
    )
