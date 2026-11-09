"""ArchiveX anchored cross-reference verification gate.

Only evidence with a valid, exact archived excerpt is admitted. Provenance
attestations then determine independent source families. Unanchored material
is retained as a review gap, never silently counted as corroboration.
"""
from __future__ import annotations

from dataclasses import dataclass

from .archivex_lineage import ArchiveXEvidenceLineage, EvidenceAnchor
from .dragon_provenance_registry import ProvenanceRegistry, ProvenanceReview
from .dragon_truth_verifier import Claim, Evidence, VerificationPolicy


@dataclass(frozen=True)
class AnchoredVerification:
    provenance: ProvenanceReview
    accepted_evidence_ids: tuple[str, ...]
    missing_anchor_ids: tuple[str, ...]
    invalid_anchor_ids: tuple[str, ...]
    archive_checked: bool = True


def verify_anchored_claim(
    *,
    owner: str,
    claim: Claim,
    evidence: tuple[Evidence, ...],
    anchors: tuple[EvidenceAnchor, ...],
    lineage: ArchiveXEvidenceLineage,
    provenance: ProvenanceRegistry,
    now: float,
    authorized: bool,
    policy: VerificationPolicy = VerificationPolicy(),
) -> AnchoredVerification:
    if not authorized:
        raise PermissionError("anchored verification requires archive authorization")
    if len(evidence) > policy.max_evidence or len(anchors) > policy.max_evidence:
        raise ValueError("anchored verification budget exceeded")
    anchor_by_id: dict[str, EvidenceAnchor] = {}
    for anchor in anchors:
        if anchor.claim_id != claim.claim_id:
            raise ValueError("anchor references another claim")
        if anchor.evidence_id in anchor_by_id:
            raise ValueError("duplicate evidence anchor")
        anchor_by_id[anchor.evidence_id] = anchor

    accepted = []
    missing = []
    invalid = []
    for item in evidence:
        if item.claim_id != claim.claim_id:
            raise ValueError("evidence references another claim")
        anchor = anchor_by_id.get(item.evidence_id)
        if anchor is None:
            missing.append(item.evidence_id)
            continue
        validation = lineage.validate(owner, anchor, authorized=True)
        if not validation.valid:
            invalid.append(item.evidence_id)
            continue
        # Re-check source URL and excerpt bytes against current evidence:
        # a valid anchor for a different excerpt must not be reused.
        archived = lineage.archive.read(owner, anchor.snapshot_id, authorized=True)
        if archived is None or archived[0].source_url != item.source_url:
            invalid.append(item.evidence_id)
            continue
        body = archived[1]
        try:
            excerpt = body[anchor.start_byte:anchor.end_byte].decode("utf-8")
        except UnicodeDecodeError:
            invalid.append(item.evidence_id)
            continue
        if excerpt != item.excerpt:
            invalid.append(item.evidence_id)
            continue
        accepted.append(item)

    reviewed = provenance.verify(
        claim, tuple(accepted), now=now, verification_policy=policy,
    )
    return AnchoredVerification(
        reviewed,
        tuple(sorted(item.evidence_id for item in accepted)),
        tuple(sorted(missing)),
        tuple(sorted(invalid)),
    )
