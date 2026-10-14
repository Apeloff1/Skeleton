"""Strict independently corroborated path into existing Dragon shadow custody.

Fact witnesses must be signed by different trusted publisher-group reviewers,
then a separate adjudicator must accept the exact signed observation set.
The original 100-matrix wrapper rechecks every signed scrutiny receipt and
retains all existing idle scheduling, consent, Wiki and shadow-weight gates.
"""
from __future__ import annotations

from .dragon_cross_source_factchecking import (
    ClaimSubject, SourceWitness, SignedClaimAdjudication,
    verify_cross_source_claims,
)
from .dragon_mother_hundred_handoff import run_hundred_matrix_mother_to_shadow


def run_correlated_mother_to_shadow(
    *,
    claims: tuple[ClaimSubject, ...],
    witnesses: tuple[SourceWitness, ...],
    adjudications: tuple[SignedClaimAdjudication, ...],
    trusted_publisher_reviewers: dict[str, tuple[str, str, bytes]],
    adjudicator_public_key: bytes,
    adjudicator: str,
    adjudicator_key_id: str,
    **handoff_kwargs,
):
    """Non-bypassable fact gate, then unchanged signed mother->shadow gate.

    This opt-in entry point is intentionally more demanding than the legacy
    worker. It does not itself schedule a worker, issue rights or change any
    retrieval/neural weight. Caller-provided signer trust is server config.
    """
    plan = handoff_kwargs.get("plan")
    owner = getattr(plan, "owner", None)
    knowledge_digest = handoff_kwargs.get("knowledge_digest")
    now = handoff_kwargs.get("review_at")
    if (handoff_kwargs.get("owner_authorized") is not True
        or handoff_kwargs.get("consented") is not True
        or handoff_kwargs.get("background_allowed") is not True
        or handoff_kwargs.get("privacy_clear") is not True):
        raise PermissionError("idle mother and source-consent authority required")
    report = verify_cross_source_claims(
        owner, knowledge_digest, claims, witnesses, adjudications,
        trusted_publisher_reviewers=trusted_publisher_reviewers,
        adjudicator_public_key=adjudicator_public_key,
        adjudicator=adjudicator,
        adjudicator_key_id=adjudicator_key_id,
        now=now,
    )
    if not report["all_claims_review_eligible"]:
        raise PermissionError("unresolved cross-source contradiction or missing review")
    # The original entry point verifies all one-hundred matrix signatures and
    # worker resource admission again, not merely this summary digest.
    return run_hundred_matrix_mother_to_shadow(**handoff_kwargs)
