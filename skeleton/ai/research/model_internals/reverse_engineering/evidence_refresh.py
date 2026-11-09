"""Priority planning for stale or drift-sensitive research evidence."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class EvidenceRefreshCandidate:
    evidence_id: str
    evidence_digest: str
    age: int
    maximum_age: int
    criticality: float
    drift_score: float

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ReverseEngineeringError("refresh candidate requires identity")
        if not is_sha256_digest(self.evidence_digest):
            raise ReverseEngineeringError("evidence_digest must be sha256 hex")
        if self.age < 0 or self.maximum_age < 0:
            raise ReverseEngineeringError("evidence age values must be non-negative")
        for value, name in (
            (self.criticality, "criticality"),
            (self.drift_score, "drift_score"),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ReverseEngineeringError(f"{name} must be within [0, 1]")

    @property
    def stale(self) -> bool:
        return self.age > self.maximum_age

    @property
    def priority(self) -> float:
        age_ratio = (
            self.age / self.maximum_age
            if self.maximum_age > 0
            else (1.0 if self.age > 0 else 0.0)
        )
        return age_ratio * 0.4 + self.criticality * 0.35 + self.drift_score * 0.25


@dataclass(frozen=True)
class EvidenceRefreshPlan:
    candidate_count: int
    must_refresh_ids: tuple[str, ...]
    ordered_refresh_ids: tuple[str, ...]
    highest_priority: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "must_refresh_ids": list(self.must_refresh_ids),
            "ordered_refresh_ids": list(self.ordered_refresh_ids),
            "highest_priority": self.highest_priority,
            "digest": self.digest,
        }


def plan_evidence_refresh(
    candidates: Sequence[EvidenceRefreshCandidate],
    *,
    mandatory_criticality: float = 0.9,
    mandatory_drift: float = 0.75,
) -> EvidenceRefreshPlan:
    if not candidates:
        raise ReverseEngineeringError("evidence refresh planning requires candidates")
    for value, name in (
        (mandatory_criticality, "mandatory_criticality"),
        (mandatory_drift, "mandatory_drift"),
    ):
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ReverseEngineeringError(f"{name} must be within [0, 1]")
    ids = [item.evidence_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("refresh candidate ids must be unique")

    ordered = tuple(
        item.evidence_id
        for item in sorted(candidates, key=lambda item: (-item.priority, item.evidence_id))
    )
    must_refresh = tuple(
        sorted(
            item.evidence_id
            for item in candidates
            if item.stale
            or item.criticality >= mandatory_criticality
            or item.drift_score >= mandatory_drift
        )
    )
    payload = {
        "mandatory_criticality": mandatory_criticality,
        "mandatory_drift": mandatory_drift,
        "candidates": [
            {
                "evidence_id": item.evidence_id,
                "evidence_digest": item.evidence_digest,
                "age": item.age,
                "maximum_age": item.maximum_age,
                "criticality": item.criticality,
                "drift_score": item.drift_score,
            }
            for item in sorted(candidates, key=lambda value: value.evidence_id)
        ],
    }
    return EvidenceRefreshPlan(
        candidate_count=len(candidates),
        must_refresh_ids=must_refresh,
        ordered_refresh_ids=ordered,
        highest_priority=max(item.priority for item in candidates),
        digest=stable_digest(payload),
    )
