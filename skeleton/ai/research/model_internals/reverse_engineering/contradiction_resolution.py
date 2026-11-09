"""Deterministic contradiction adjudication across independent evidence domains."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ContradictionEvidence:
    evidence_id: str
    claim_id: str
    domain: str
    report_digest: str
    supports: bool
    confidence: float

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.claim_id or not self.domain:
            raise ReverseEngineeringError("contradiction evidence identity is required")
        if not is_sha256_digest(self.report_digest):
            raise ReverseEngineeringError("report_digest must be sha256 hex")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ReverseEngineeringError("confidence must be finite and within [0, 1]")


@dataclass(frozen=True)
class ContradictionResolution:
    claim_id: str
    domain_count: int
    supporting_domain_count: int
    contradicting_domain_count: int
    mean_support: float
    mean_contradiction: float
    margin: float
    status: str
    unresolved_domains: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "domain_count": self.domain_count,
            "supporting_domain_count": self.supporting_domain_count,
            "contradicting_domain_count": self.contradicting_domain_count,
            "mean_support": self.mean_support,
            "mean_contradiction": self.mean_contradiction,
            "margin": self.margin,
            "status": self.status,
            "unresolved_domains": list(self.unresolved_domains),
            "digest": self.digest,
        }


def resolve_contradictions(
    evidence: Sequence[ContradictionEvidence],
    *,
    minimum_domains: int = 2,
    decisive_margin: float = 0.25,
) -> tuple[ContradictionResolution, ...]:
    if not evidence:
        raise ReverseEngineeringError("contradiction resolution requires evidence")
    if minimum_domains < 1:
        raise ReverseEngineeringError("minimum_domains must be positive")
    if not isfinite(decisive_margin) or not 0.0 <= decisive_margin <= 1.0:
        raise ReverseEngineeringError("decisive_margin must be within [0, 1]")
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("contradiction evidence ids must be unique")

    grouped: dict[str, list[ContradictionEvidence]] = {}
    for item in evidence:
        grouped.setdefault(item.claim_id, []).append(item)

    reports: list[ContradictionResolution] = []
    for claim_id, items in sorted(grouped.items()):
        by_domain: dict[str, list[ContradictionEvidence]] = {}
        for item in items:
            by_domain.setdefault(item.domain, []).append(item)

        support_scores: list[float] = []
        contradiction_scores: list[float] = []
        support_domains = 0
        contradiction_domains = 0
        unresolved: list[str] = []
        for domain, domain_items in sorted(by_domain.items()):
            support = max((item.confidence for item in domain_items if item.supports), default=0.0)
            contradiction = max((item.confidence for item in domain_items if not item.supports), default=0.0)
            support_scores.append(support)
            contradiction_scores.append(contradiction)
            if support > contradiction:
                support_domains += 1
            elif contradiction > support:
                contradiction_domains += 1
            else:
                unresolved.append(domain)

        mean_support = sum(support_scores) / len(support_scores)
        mean_contradiction = sum(contradiction_scores) / len(contradiction_scores)
        margin = mean_support - mean_contradiction

        status = "insufficient"
        if len(by_domain) >= minimum_domains:
            if support_domains and contradiction_domains and abs(margin) < decisive_margin:
                status = "conflicted"
            elif margin >= decisive_margin and support_domains >= minimum_domains:
                status = "supported"
            elif margin <= -decisive_margin and contradiction_domains >= minimum_domains:
                status = "rejected"
            elif support_domains and contradiction_domains:
                status = "conflicted"

        payload = {
            "claim_id": claim_id,
            "minimum_domains": minimum_domains,
            "decisive_margin": decisive_margin,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "domain": item.domain,
                    "report_digest": item.report_digest,
                    "supports": item.supports,
                    "confidence": item.confidence,
                }
                for item in sorted(items, key=lambda value: value.evidence_id)
            ],
        }
        reports.append(
            ContradictionResolution(
                claim_id=claim_id,
                domain_count=len(by_domain),
                supporting_domain_count=support_domains,
                contradicting_domain_count=contradiction_domains,
                mean_support=mean_support,
                mean_contradiction=mean_contradiction,
                margin=margin,
                status=status,
                unresolved_domains=tuple(unresolved),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
