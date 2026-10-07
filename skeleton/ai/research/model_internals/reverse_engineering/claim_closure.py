"""Final fail-closed closure decision for a reverse-engineering claim."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ClaimClosureEvidence:
    claim_id: str
    claim_digest: str
    quality_gate_passed: bool
    quorum_met: bool
    lineage_closed: bool
    falsification_status: str
    replication_quality: float | None
    stale_evidence_ratio: float
    contradiction_weight: float

    def __post_init__(self) -> None:
        if not self.claim_id:
            raise ReverseEngineeringError("claim closure evidence requires claim_id")
        if not is_sha256_digest(self.claim_digest):
            raise ReverseEngineeringError("claim_digest must be sha256 hex")
        if self.falsification_status not in {"incomplete", "survived", "falsified"}:
            raise ReverseEngineeringError("invalid falsification_status")
        if self.replication_quality is not None and (
            not isfinite(self.replication_quality)
            or not 0.0 <= self.replication_quality <= 1.0
        ):
            raise ReverseEngineeringError("replication_quality must be within [0, 1]")
        for value, name in (
            (self.stale_evidence_ratio, "stale_evidence_ratio"),
            (self.contradiction_weight, "contradiction_weight"),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ReverseEngineeringError(f"{name} must be within [0, 1]")


@dataclass(frozen=True)
class ClaimClosurePolicy:
    minimum_replication_quality: float = 0.75
    maximum_stale_evidence_ratio: float = 0.0
    maximum_contradiction_weight: float = 0.25


@dataclass(frozen=True)
class ClaimClosureDecision:
    claim_id: str
    status: str
    failed_requirements: tuple[str, ...]
    digest: str

    @property
    def closed(self) -> bool:
        return self.status == "closed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "status": self.status,
            "failed_requirements": list(self.failed_requirements),
            "digest": self.digest,
        }


def evaluate_claim_closure(
    evidence: ClaimClosureEvidence,
    *,
    policy: ClaimClosurePolicy = ClaimClosurePolicy(),
) -> ClaimClosureDecision:
    for value, name in (
        (policy.minimum_replication_quality, "minimum_replication_quality"),
        (policy.maximum_stale_evidence_ratio, "maximum_stale_evidence_ratio"),
        (policy.maximum_contradiction_weight, "maximum_contradiction_weight"),
    ):
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ReverseEngineeringError(f"{name} must be within [0, 1]")

    checks = {
        "quality_gate": evidence.quality_gate_passed,
        "quorum": evidence.quorum_met,
        "lineage": evidence.lineage_closed,
        "falsification": evidence.falsification_status == "survived",
        "replication": (
            evidence.replication_quality is not None
            and evidence.replication_quality >= policy.minimum_replication_quality
        ),
        "freshness": evidence.stale_evidence_ratio <= policy.maximum_stale_evidence_ratio,
        "contradiction": evidence.contradiction_weight <= policy.maximum_contradiction_weight,
    }
    failed = tuple(sorted(name for name, passed in checks.items() if not passed))
    if evidence.falsification_status == "falsified":
        status = "rejected"
    elif failed:
        status = "hold"
    else:
        status = "closed"
    payload = {
        "claim_id": evidence.claim_id,
        "claim_digest": evidence.claim_digest,
        "checks": checks,
        "policy": {
            "minimum_replication_quality": policy.minimum_replication_quality,
            "maximum_stale_evidence_ratio": policy.maximum_stale_evidence_ratio,
            "maximum_contradiction_weight": policy.maximum_contradiction_weight,
        },
        "status": status,
    }
    return ClaimClosureDecision(
        claim_id=evidence.claim_id,
        status=status,
        failed_requirements=failed,
        digest=stable_digest(payload),
    )
