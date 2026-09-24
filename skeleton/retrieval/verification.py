"""Retrieval/citation adapters for canonical verification evidence."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from skeleton.contracts.verification import (
    EvidenceKind,
    EvidenceRelation,
    ProvenanceOrigin,
    VerificationClaim,
    VerificationEvidence,
)


def citation_verification_evidence(
    claim: VerificationClaim,
    *,
    source_id: str,
    origin_id: str,
    content_digest: str,
    observed_at: datetime,
    locator: str,
    provenance_refs: tuple[str, ...],
    supports: bool = True,
    origin_type: ProvenanceOrigin = ProvenanceOrigin.SECONDARY_SOURCE,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    population_scope: tuple[str, ...] = (),
    environment_scope: tuple[str, ...] = (),
    evidence_id: str | None = None,
) -> VerificationEvidence:
    """Bind one inspectable citation explicitly to one canonical claim."""

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    if not locator or not locator.strip():
        raise ValueError("citation locator must be non-empty")
    if not provenance_refs:
        raise ValueError("citation provenance_refs must not be empty")
    return VerificationEvidence(
        evidence_id=evidence_id or str(uuid4()),
        tenant_id=claim.tenant_id,
        kind=EvidenceKind.CITATION,
        origin_type=origin_type,
        source_id=source_id,
        origin_id=origin_id,
        content_digest=content_digest,
        observed_at=observed_at,
        locator=locator,
        valid_from=valid_from,
        valid_until=valid_until,
        population_scope=population_scope,
        environment_scope=environment_scope,
        provenance_refs=provenance_refs,
        bound_claim_ids=(claim.claim_id,),
        relation=(
            EvidenceRelation.SUPPORTS
            if supports
            else EvidenceRelation.CONTRADICTS
        ),
        data_class=claim.data_class,
    )


__all__ = ["citation_verification_evidence"]
