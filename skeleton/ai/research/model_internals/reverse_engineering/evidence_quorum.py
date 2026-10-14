"""Evidence-quorum enforcement across independent research domains."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class DomainEvidence:
    evidence_id: str
    domain: str
    report_digest: str
    confidence: float
    supports: bool

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.domain:
            raise ReverseEngineeringError("domain evidence identity is required")
        if not is_sha256_digest(self.report_digest):
            raise ReverseEngineeringError("report_digest must be a sha256 hex digest")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ReverseEngineeringError("confidence must be finite and within [0, 1]")


@dataclass(frozen=True)
class EvidenceQuorumReport:
    evidence_count: int
    domain_count: int
    supporting_domain_count: int
    contradicting_domain_count: int
    weighted_support: float
    weighted_contradiction: float
    quorum_met: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_count": self.evidence_count,
            "domain_count": self.domain_count,
            "supporting_domain_count": self.supporting_domain_count,
            "contradicting_domain_count": self.contradicting_domain_count,
            "weighted_support": self.weighted_support,
            "weighted_contradiction": self.weighted_contradiction,
            "quorum_met": self.quorum_met,
            "digest": self.digest,
        }


def evaluate_evidence_quorum(
    evidence: Sequence[DomainEvidence],
    *,
    minimum_supporting_domains: int = 3,
    minimum_weighted_support: float = 0.75,
    maximum_weighted_contradiction: float = 0.25,
) -> EvidenceQuorumReport:
    if not evidence:
        raise ReverseEngineeringError("evidence quorum requires evidence")
    if minimum_supporting_domains < 1:
        raise ReverseEngineeringError("minimum_supporting_domains must be positive")
    for value, name in (
        (minimum_weighted_support, "minimum_weighted_support"),
        (maximum_weighted_contradiction, "maximum_weighted_contradiction"),
    ):
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ReverseEngineeringError(f"{name} must be within [0, 1]")
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("domain evidence ids must be unique")

    by_domain: dict[str, list[DomainEvidence]] = {}
    for item in evidence:
        by_domain.setdefault(item.domain, []).append(item)
    supporting_domains = 0
    contradicting_domains = 0
    domain_support_scores: list[float] = []
    domain_contradiction_scores: list[float] = []
    for items in by_domain.values():
        supports = [item.confidence for item in items if item.supports]
        contradictions = [item.confidence for item in items if not item.supports]
        support_score = max(supports) if supports else 0.0
        contradiction_score = max(contradictions) if contradictions else 0.0
        domain_support_scores.append(support_score)
        domain_contradiction_scores.append(contradiction_score)
        if support_score > contradiction_score:
            supporting_domains += 1
        elif contradiction_score > support_score:
            contradicting_domains += 1

    weighted_support = sum(domain_support_scores) / len(domain_support_scores)
    weighted_contradiction = sum(domain_contradiction_scores) / len(domain_contradiction_scores)
    quorum = (
        supporting_domains >= minimum_supporting_domains
        and weighted_support >= minimum_weighted_support
        and weighted_contradiction <= maximum_weighted_contradiction
    )
    payload = {
        "minimum_supporting_domains": minimum_supporting_domains,
        "minimum_weighted_support": minimum_weighted_support,
        "maximum_weighted_contradiction": maximum_weighted_contradiction,
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "domain": item.domain,
                "report_digest": item.report_digest,
                "confidence": item.confidence,
                "supports": item.supports,
            }
            for item in sorted(evidence, key=lambda value: value.evidence_id)
        ],
    }
    return EvidenceQuorumReport(
        evidence_count=len(evidence),
        domain_count=len(by_domain),
        supporting_domain_count=supporting_domains,
        contradicting_domain_count=contradicting_domains,
        weighted_support=weighted_support,
        weighted_contradiction=weighted_contradiction,
        quorum_met=quorum,
        digest=stable_digest(payload),
    )
