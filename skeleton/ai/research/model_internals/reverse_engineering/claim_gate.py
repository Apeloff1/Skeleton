"""Fail-closed quality gate for reverse-engineering claims."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ClaimQualityEvidence:
    claim_id: str
    evidence_digest: str
    balanced_accuracy: float | None
    attribution_stability: float | None
    standardized_effect: float | None
    independent_domains: int
    replication_ratio: float | None
    contradiction_weight: float

    def __post_init__(self) -> None:
        if not self.claim_id:
            raise ReverseEngineeringError("claim quality evidence requires claim_id")
        if not is_sha256_digest(self.evidence_digest):
            raise ReverseEngineeringError("evidence_digest must be a sha256 hex digest")
        for value, name in (
            (self.balanced_accuracy, "balanced_accuracy"),
            (self.attribution_stability, "attribution_stability"),
            (self.replication_ratio, "replication_ratio"),
        ):
            if value is not None and (not isfinite(value) or not 0.0 <= value <= 1.0):
                raise ReverseEngineeringError(f"{name} must be finite and within [0, 1]")
        if self.standardized_effect is not None and not isfinite(self.standardized_effect):
            raise ReverseEngineeringError("standardized_effect must be finite")
        if self.independent_domains < 0:
            raise ReverseEngineeringError("independent_domains must be non-negative")
        if not isfinite(self.contradiction_weight) or not 0.0 <= self.contradiction_weight <= 1.0:
            raise ReverseEngineeringError("contradiction_weight must be finite and within [0, 1]")


@dataclass(frozen=True)
class ClaimQualityGate:
    minimum_balanced_accuracy: float = 0.75
    minimum_attribution_stability: float = 0.5
    minimum_absolute_effect: float = 0.5
    minimum_independent_domains: int = 2
    minimum_replication_ratio: float = 0.75
    maximum_contradiction_weight: float = 0.25

    def __post_init__(self) -> None:
        for value, name in (
            (self.minimum_balanced_accuracy, "minimum_balanced_accuracy"),
            (self.minimum_attribution_stability, "minimum_attribution_stability"),
            (self.minimum_replication_ratio, "minimum_replication_ratio"),
            (self.maximum_contradiction_weight, "maximum_contradiction_weight"),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ReverseEngineeringError(f"{name} must be finite and within [0, 1]")
        if not isfinite(self.minimum_absolute_effect) or self.minimum_absolute_effect < 0.0:
            raise ReverseEngineeringError("minimum_absolute_effect must be finite and non-negative")
        if self.minimum_independent_domains < 1:
            raise ReverseEngineeringError("minimum_independent_domains must be positive")


@dataclass(frozen=True)
class ClaimGateDecision:
    claim_id: str
    status: str
    passed_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]
    digest: str

    @property
    def promotable(self) -> bool:
        return self.status == "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "status": self.status,
            "passed_checks": list(self.passed_checks),
            "failed_checks": list(self.failed_checks),
            "digest": self.digest,
        }


def evaluate_claim_quality(
    evidence: ClaimQualityEvidence,
    *,
    gate: ClaimQualityGate = ClaimQualityGate(),
) -> ClaimGateDecision:
    checks: dict[str, bool] = {
        "balanced_accuracy": (
            evidence.balanced_accuracy is not None
            and evidence.balanced_accuracy >= gate.minimum_balanced_accuracy
        ),
        "attribution_stability": (
            evidence.attribution_stability is not None
            and evidence.attribution_stability >= gate.minimum_attribution_stability
        ),
        "effect_size": (
            evidence.standardized_effect is not None
            and abs(evidence.standardized_effect) >= gate.minimum_absolute_effect
        ),
        "independent_domains": evidence.independent_domains >= gate.minimum_independent_domains,
        "replication": (
            evidence.replication_ratio is not None
            and evidence.replication_ratio >= gate.minimum_replication_ratio
        ),
        "contradiction": evidence.contradiction_weight <= gate.maximum_contradiction_weight,
    }
    passed = tuple(sorted(name for name, ok in checks.items() if ok))
    failed = tuple(sorted(name for name, ok in checks.items() if not ok))
    status = "pass" if not failed else "hold"
    if evidence.contradiction_weight > 0.5:
        status = "reject"
    payload = {
        "claim_id": evidence.claim_id,
        "evidence_digest": evidence.evidence_digest,
        "checks": checks,
        "gate": {
            "minimum_balanced_accuracy": gate.minimum_balanced_accuracy,
            "minimum_attribution_stability": gate.minimum_attribution_stability,
            "minimum_absolute_effect": gate.minimum_absolute_effect,
            "minimum_independent_domains": gate.minimum_independent_domains,
            "minimum_replication_ratio": gate.minimum_replication_ratio,
            "maximum_contradiction_weight": gate.maximum_contradiction_weight,
        },
    }
    return ClaimGateDecision(
        claim_id=evidence.claim_id,
        status=status,
        passed_checks=passed,
        failed_checks=failed,
        digest=stable_digest(payload),
    )
