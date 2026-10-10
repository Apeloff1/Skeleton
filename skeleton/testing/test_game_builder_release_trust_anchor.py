"""Adversarial pinned reviewer registry and independent authorization tests.

All cryptographic keys in this test are synthetic and generated in memory.
The real policy authority public key must be pinned *outside* the repository.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from skeleton.ai.game_builder.release_assurance import (
    ReleaseReviewError, ReleaseReadiness, ReviewRole,
    TrustedReviewer, evaluate_independent_review,
)
from skeleton.ai.game_builder.release_trust_anchor import (
    SignedReviewerRegistry, evaluate_pinned_independent_review,
)
from skeleton.testing.test_game_builder_release_assurance import (
    base_evidence, signed_panel, sign, signer,
)


def signed_root(candidate, reviewers=None):
    if reviewers is None:
        reviewers, _ = signed_panel(candidate)
    root_key = Ed25519PrivateKey.generate()
    root_public = root_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    envelope = SignedReviewerRegistry(
        project_id=candidate.project_id,
        target_platform_id=candidate.target_platform_id,
        channel=candidate.channel,
        jurisdictions=candidate.jurisdictions,
        policy_epoch=45,
        issued_utc="2026-10-01T00:00:00Z",
        expires_utc="2027-01-01T00:00:00Z",
        root_public_key_hex=root_public,
        reviewers=reviewers,
        root_signature_hex="00"*64,
    )
    return (
        replace(envelope, root_signature_hex=root_key.sign(envelope.signed_bytes).hex()),
        sha256(bytes.fromhex(root_public)).hexdigest(),
    )


def pinned(candidate, legal, original, root, pin, signatures, *, epoch=45, clock="2026-10-11T12:00:00Z"):
    return evaluate_pinned_independent_review(
        candidate,legal,original,registry=root,attestations=signatures,
        evaluation_utc=clock, expected_root_key_sha256=pin, minimum_policy_epoch=epoch,
    )


def test_fully_independent_review_requires_a_signed_and_pinned_policy_root():
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    root,pin = signed_root(candidate,reviewers)
    result = pinned(candidate,legal,original,root,pin,signatures)
    assert result.review.status is ReleaseReadiness.REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING
    assert result.externally_root_key_pinned
    assert result.trusted_policy_epoch == 45
    assert len(result.public_receipt()["evaluation_sha256"]) == 64
    assert result.public_receipt()["release_authorized"] is False
    assert result.public_receipt()["legal_infringement_certified"] is False
    assert result == pinned(candidate,legal,original,root,pin,signatures)


def test_self_supplied_reviewer_root_cannot_replace_external_pinned_admin_key():
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    root,pin = signed_root(candidate,reviewers)
    another_root,another_pin = signed_root(candidate,reviewers)
    assert another_pin != pin
    with pytest.raises(ReleaseReviewError,match="pinned"):
        pinned(candidate,legal,original,another_root,pin,signatures)


@pytest.mark.parametrize("change",[
    {"policy_epoch":46},
    {"project_id":"other-owned-game"},
    {"expires_utc":"2028-01-01T00:00:00Z"},
    {"issued_utc":"2026-10-02T00:00:00Z"},
    {"root_signature_hex":"0"*128},
])
def test_manifest_mutations_invalidate_root_signature_or_scope(change):
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    root,pin = signed_root(candidate,reviewers)
    tampered = replace(root,**change)
    with pytest.raises(ReleaseReviewError):
        pinned(candidate,legal,original,tampered,pin,signatures)


def test_signature_covers_reviewer_revocation_and_role_permissions():
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    root,pin = signed_root(candidate,reviewers)
    tampered = replace(root,reviewers=(replace(reviewers[0],revoked=True),*reviewers[1:]))
    with pytest.raises(ReleaseReviewError,match="forged|modified"):
        pinned(candidate,legal,original,tampered,pin,signatures)


@pytest.mark.parametrize("minimum", [46,99,9999])
def test_monotonic_policy_epoch_prevents_old_keyset_replay(minimum):
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    root,pin = signed_root(candidate,reviewers)
    with pytest.raises(ReleaseReviewError,match="rolled back"):
        pinned(candidate,legal,original,root,pin,signatures,epoch=minimum)


@pytest.mark.parametrize("clock",["2026-09-30T23:59:59Z","2027-01-01T00:00:01Z"])
def test_signed_reviewer_registry_cannot_be_used_outside_trust_window(clock):
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    root,pin = signed_root(candidate,reviewers)
    with pytest.raises(ReleaseReviewError,match="not started|expired"):
        pinned(candidate,legal,original,root,pin,signatures,clock=clock)


@pytest.mark.parametrize("field,wrong",[
    ("target_platform_id","gameboy_color"),
    ("jurisdictions",("US",)),
])
def test_valid_signatures_from_another_market_or_platform_do_not_transfer(field,wrong):
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    root,pin = signed_root(candidate,reviewers)
    mismatch = replace(root,**{field:wrong})
    with pytest.raises(ReleaseReviewError):
        pinned(candidate,legal,original,mismatch,pin,signatures)


def test_one_private_key_cannot_masquerade_as_multiple_separate_reviewers():
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    cloned = replace(reviewers[1],public_key_hex=reviewers[0].public_key_hex)
    with pytest.raises(ReleaseReviewError,match="shared"):
        signed_root(candidate,(reviewers[0],cloned,reviewers[2]))
    with pytest.raises(ReleaseReviewError,match="key"):
        evaluate_independent_review(
            candidate,legal,original,
            trust_registry=(reviewers[0],cloned,reviewers[2]),
            attestations=signatures,evaluation_utc="2026-10-11T12:00:00Z",
        )


def test_author_identity_case_alias_cannot_self_approve_creative_review():
    candidate,legal,original=base_evidence()
    reviewers,signatures=signed_panel(candidate)
    disguised=replace(candidate,author_ids=(reviewers[0].reviewer_id.upper(),))
    # Sign fresh data with a genuinely independent panel first. Then assert a
    # reviewer with the same identity in another letter case cannot qualify.
    _,new_signatures=signed_panel(disguised)
    # Each fresh signer is independent. For the signers in reviewers, the old
    # signatures also become stale and fail (not a viable alias attack).
    review=evaluate_independent_review(
        disguised,legal,original,trust_registry=reviewers,
        attestations=new_signatures,evaluation_utc="2026-10-11T12:00:00Z",
    )
    assert review.status is ReleaseReadiness.BLOCKED
    assert any("NON_INDEPENDENT_SELF_REVIEW" in reason for reason in review.blocking_reasons)


def test_signed_registry_revoked_reviewer_results_in_blocked_review_not_success():
    candidate,legal,original = base_evidence()
    reviewers,signatures = signed_panel(candidate)
    revoked = (replace(reviewers[0],revoked=True),*reviewers[1:])
    root,pin=signed_root(candidate,revoked)
    review=pinned(candidate,legal,original,root,pin,signatures)
    assert review.review.status is ReleaseReadiness.BLOCKED
    assert review.release_authorized is False


def test_unpinned_admin_policy_missing_or_invalid_inputs_refused():
    candidate,legal,original=base_evidence()
    reviewers,signatures=signed_panel(candidate)
    root,pin=signed_root(candidate,reviewers)
    with pytest.raises(ReleaseReviewError):
        pinned(candidate,legal,original,root,"unknown",signatures)
    with pytest.raises(ReleaseReviewError):
        pinned(candidate,legal,original,root,pin,signatures,epoch=0)
    with pytest.raises(ReleaseReviewError):
        pinned(candidate,legal,original,root,pin,signatures,epoch=True)


def test_trust_policy_supports_only_explicit_scoped_territories():
    candidate,_,_ = base_evidence()
    reviewers,_=signed_panel(candidate)
    root,pin=signed_root(candidate,reviewers)
    assert pin == root.trust_root_sha256
    with pytest.raises(ReleaseReviewError):
        replace(root,jurisdictions=("NO","no"))
    with pytest.raises(ReleaseReviewError):
        replace(root,policy_epoch=0)
    with pytest.raises(ReleaseReviewError):
        replace(root,reviewers=())
