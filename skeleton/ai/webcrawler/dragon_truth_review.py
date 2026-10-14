"""Bounded multi-claim verification and review gate for distilled knowledge.

Unverified and contested claims remain review material. Only corroborated
claims are eligible for a *proposal* to memory; this is not a persistence API.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_truth_verifier import (
    Claim, Evidence, VerificationPolicy, VerificationResult,
    VerificationStatus, verify_claim,
)


@dataclass(frozen=True)
class VerificationBatchPolicy:
    max_claims: int = 100
    max_evidence_total: int = 2000
    require_human_review: bool = True


@dataclass(frozen=True)
class ClaimReview:
    result: VerificationResult
    memory_eligible: bool
    requires_review: bool
    review_reason: str


@dataclass(frozen=True)
class VerificationBatch:
    reviews: tuple[ClaimReview, ...]
    corroborated: int
    contested: int
    unverified: int
    fingerprint: str


def verify_claim_batch(
    claims: tuple[Claim, ...],
    evidence: tuple[Evidence, ...],
    *,
    now: float,
    policy: VerificationBatchPolicy = VerificationBatchPolicy(),
    evidence_policy: VerificationPolicy = VerificationPolicy(),
) -> VerificationBatch:
    if not 1 <= policy.max_claims <= 10000:
        raise ValueError("invalid claim budget")
    if not 1 <= policy.max_evidence_total <= 100000:
        raise ValueError("invalid evidence budget")
    if len(claims) > policy.max_claims or len(evidence) > policy.max_evidence_total:
        raise ValueError("verification batch budget exceeded")
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise ValueError("duplicate claim identifiers")
    claim_ids = {claim.claim_id for claim in claims}
    if any(item.claim_id not in claim_ids for item in evidence):
        raise ValueError("orphan evidence cannot be silently ignored")

    grouped: dict[str, list[Evidence]] = {key: [] for key in claim_ids}
    for item in evidence:
        grouped[item.claim_id].append(item)

    reviews = []
    for claim in sorted(claims, key=lambda item: item.claim_id):
        result = verify_claim(
            claim, tuple(grouped[claim.claim_id]),
            now=now, policy=evidence_policy,
        )
        corroborated = result.status is VerificationStatus.CORROBORATED
        eligible = corroborated and not policy.require_human_review
        if result.status is VerificationStatus.CONTESTED:
            reason = "Conflicting independent evidence requires investigation"
        elif not corroborated:
            reason = "Insufficient independent corroboration for memory promotion"
        elif policy.require_human_review:
            reason = "Corroborated, awaiting explicit memory review"
        else:
            reason = "Corroborated and eligible for separate persistence authorization"
        reviews.append(ClaimReview(result, eligible, not eligible, reason))

    digest = sha256(json.dumps(
        [(r.result.claim_id, r.result.fingerprint, r.memory_eligible)
         for r in reviews],
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return VerificationBatch(
        tuple(reviews),
        sum(r.result.status is VerificationStatus.CORROBORATED for r in reviews),
        sum(r.result.status is VerificationStatus.CONTESTED for r in reviews),
        sum(r.result.status in (
            VerificationStatus.UNVERIFIED, VerificationStatus.INSUFFICIENT,
        ) for r in reviews),
        digest,
    )
