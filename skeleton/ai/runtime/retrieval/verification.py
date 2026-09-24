"""Deterministic citation integrity and claim-grounding adapters."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.contracts.verification import (
    ClaimScope,
    EvidenceProducer,
    EvidenceReference,
    EvidenceRelation,
    VerificationClaim,
)


@dataclass(frozen=True, slots=True)
class CitationIntegrityResult:
    evidence_id: str
    accepted: bool
    authoritative: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroundingAssessment:
    citation_results: tuple[CitationIntegrityResult, ...]
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    supporting_origin_ids: tuple[str, ...]
    rejected_evidence_ids: tuple[str, ...]

    @property
    def has_authoritative_support(self) -> bool:
        return bool(self.supporting_evidence_ids)

    @property
    def has_authoritative_contradiction(self) -> bool:
        return bool(self.contradicting_evidence_ids)


def _scope_reasons(claim_scope: ClaimScope, evidence: EvidenceReference) -> tuple[str, ...]:
    reasons: list[str] = []
    evidence_scope = evidence.scope
    for field in ("population", "environment", "jurisdiction"):
        required = getattr(claim_scope, field)
        actual = getattr(evidence_scope, field)
        if required is not None and actual != required:
            reasons.append(field + "_scope_mismatch")

    if claim_scope.valid_from is not None:
        evidence_end = evidence_scope.valid_to or evidence.observed_at
        if evidence_end < claim_scope.valid_from:
            reasons.append("temporal_scope_stale")
    if claim_scope.valid_to is not None:
        evidence_start = evidence_scope.valid_from or evidence.observed_at
        if evidence_start > claim_scope.valid_to:
            reasons.append("temporal_scope_future")
    return tuple(reasons)


def validate_citation(
    claim: VerificationClaim,
    evidence: EvidenceReference,
) -> CitationIntegrityResult:
    """Validate that one evidence reference is structurally bound to one claim."""

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    if not isinstance(evidence, EvidenceReference):
        raise TypeError("evidence must be EvidenceReference")

    reasons: list[str] = []
    if evidence.claim_id != claim.claim_id:
        reasons.append("claim_id_mismatch")
    if evidence.tenant_id != claim.tenant_id:
        reasons.append("tenant_mismatch")
    reasons.extend(_scope_reasons(claim.scope, evidence))

    accepted = not reasons
    authoritative = accepted and evidence.producer is not EvidenceProducer.MODEL
    if accepted and not authoritative:
        reasons.append("model_evidence_non_authoritative")
    return CitationIntegrityResult(
        evidence_id=evidence.evidence_id,
        accepted=accepted,
        authoritative=authoritative,
        reasons=tuple(reasons),
    )


def ground_claim(
    claim: VerificationClaim,
    evidence: tuple[EvidenceReference, ...] | list[EvidenceReference],
) -> GroundingAssessment:
    """Ground a claim without double-counting correlated source origins."""

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    results: list[CitationIntegrityResult] = []
    supporting_ids: list[str] = []
    contradicting_ids: list[str] = []
    supporting_origins: list[str] = []
    rejected_ids: list[str] = []

    for item in evidence:
        result = validate_citation(claim, item)
        results.append(result)
        if not result.accepted:
            rejected_ids.append(item.evidence_id)
            continue
        if not result.authoritative:
            continue
        if item.relation is EvidenceRelation.SUPPORTS:
            supporting_ids.append(item.evidence_id)
            if item.origin_id not in supporting_origins:
                supporting_origins.append(item.origin_id)
        elif item.relation is EvidenceRelation.CONTRADICTS:
            contradicting_ids.append(item.evidence_id)

    return GroundingAssessment(
        citation_results=tuple(results),
        supporting_evidence_ids=tuple(supporting_ids),
        contradicting_evidence_ids=tuple(contradicting_ids),
        supporting_origin_ids=tuple(supporting_origins),
        rejected_evidence_ids=tuple(rejected_ids),
    )


__all__ = [
    "CitationIntegrityResult",
    "GroundingAssessment",
    "ground_claim",
    "validate_citation",
]
