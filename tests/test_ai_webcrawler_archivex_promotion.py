"""ArchiveX promotion gate adversarial regression suite."""
import sqlite3
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
from skeleton.ai.webcrawler.archivex_truth_gate import AnchoredVerification
from skeleton.ai.webcrawler.dragon_provenance_registry import ProvenanceReview
from skeleton.ai.webcrawler.dragon_truth_verifier import (
    VerificationResult, VerificationStatus,
)


def review(status=VerificationStatus.CORROBORATED):
    verification = VerificationResult(
        "claim-1", status, 1.8, 0.0, 2, 0, (), 0,
        "two independent archived sources", "a" * 64,
    )
    provenance = ProvenanceReview(
        verification, 2, 0, ("owner:a", "owner:b"), "b" * 64,
    )
    return AnchoredVerification(provenance, ("e1", "e2"), (), ())


def gate():
    return ArchiveXPromotionGate(sqlite3.connect(":memory:"))


def authorize(g, result=None, **overrides):
    arguments = dict(
        claim_id="claim-1", approval_id="review-1", now=100,
        consent=True, reviewer_approved=True,
    )
    arguments.update(overrides)
    return g.authorize("alice", result or review(), **arguments)


def test_single_use_receipt_and_replay_rejection():
    g = gate()
    receipt = authorize(g)
    assert g.consume(receipt, now=101, consent=True)
    assert not g.consume(receipt, now=102, consent=True)


def test_approval_and_consent_are_required():
    g = gate()
    with pytest.raises(PermissionError):
        authorize(g, reviewer_approved=False)
    with pytest.raises(PermissionError):
        authorize(g, consent=False)
    receipt = authorize(g)
    with pytest.raises(PermissionError):
        g.consume(receipt, now=101, consent=False)


def test_contested_or_unverified_claim_cannot_promote():
    for status in (
        VerificationStatus.CONTESTED,
        VerificationStatus.INSUFFICIENT,
        VerificationStatus.UNVERIFIED,
        VerificationStatus.REFUTED,
    ):
        with pytest.raises(ValueError, match="corroborated"):
            authorize(gate(), review(status))


def test_missing_or_invalid_anchors_fail_closed():
    with pytest.raises(ValueError, match="incomplete"):
        authorize(gate(), replace(review(), missing_anchor_ids=("e3",)))
    with pytest.raises(ValueError, match="incomplete"):
        authorize(gate(), replace(review(), invalid_anchor_ids=("e2",)))


def test_approval_cannot_be_replayed_for_other_claim():
    g = gate()
    with pytest.raises(ValueError, match="another claim"):
        authorize(g, claim_id="claim-2")


def test_conflicting_receipts_require_revocation():
    g = gate()
    first = authorize(g)
    assert authorize(g) == first
    with pytest.raises(ValueError, match="conflicting"):
        authorize(g, approval_id="different-review")
    assert g.revoke("alice", "claim-1") == 1
    assert authorize(g, approval_id="different-review")


def test_owner_scoped_revocation():
    g = gate()
    receipt = authorize(g)
    assert g.revoke("bob") == 0
    assert g.consume(receipt, now=101, consent=True)
    assert g.revoke("alice") == 1


def test_tampered_receipt_is_not_consumable():
    g = gate()
    receipt = authorize(g)
    modified = replace(receipt, registry_fingerprint="0" * 64)
    assert not g.consume(modified, now=101, consent=True)
    assert g.consume(receipt, now=102, consent=True)
