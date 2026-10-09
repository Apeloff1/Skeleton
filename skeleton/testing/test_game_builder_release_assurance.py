"""Adversarial signed review and provenance tests. No real publisher licenses."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from skeleton.ai.game_builder.legal_paths import (
    CreativeMode, HardwareAccessFacts, HomebrewLegalRequest,
    Jurisdiction, MaterialKind, MaterialRecord, assess_homebrew,
)
from skeleton.ai.game_builder.plagiarism_guard import (
    AssetDeclaration, AssetDisposition, AttributionStatus, ExpressionSample,
    UseBasis, audit_game_originality,
)
from skeleton.ai.game_builder.release_assurance import (
    ReleaseCandidate, ReleaseChannel, ReleaseReadiness, ReleaseReviewError,
    ReviewAttestation, ReviewDecision, ReviewDomain, ReviewRole, TrustedReviewer,
    evaluate_independent_review,
)


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def base_evidence():
    project = "fresh-authored"
    artifact = digest("new-game-world")
    proof = digest("creator-confirmed-assets")
    categories = (
        "artwork", "characters", "interface_appearance", "level_maps",
        "marketing_brand", "music_audio", "source_code", "story_dialogue",
    )
    assets = tuple(AssetDeclaration(
        modality=c,
        disposition=AssetDisposition.INCLUDED if c == "story_dialogue" else AssetDisposition.NOT_USED,
        basis=UseBasis.OWN_CREATION if c == "story_dialogue" else None,
        provenance_sha256=proof if c == "story_dialogue" else None,
        author_identity="game-author" if c == "story_dialogue" else None,
        attribution=AttributionStatus.NOT_REQUIRED,
    ) for c in categories)
    authored = "The amber ship explored unknown caves below a violet horizon and met a clever moth"
    unrelated = "A round green apple fell from the old stone bridge as three hikers passed by"
    originality = audit_game_originality(
        project_id=project, assets=assets,
        candidate_samples=(ExpressionSample("mine", "story_dialogue", authored, proof),),
        references=(ExpressionSample("reference", "story_dialogue", unrelated),),
        artifact_sha256=artifact,
    )
    assert originality.design_admissible
    legal = assess_homebrew(HomebrewLegalRequest(
        project_id=project,
        source_platform_id="sega_dreamcast",
        target_platform_id="windows_modern",
        mode=CreativeMode.ORIGINAL,
        jurisdictions=(Jurisdiction.NO, Jurisdiction.EU_EEA),
        materials=(MaterialRecord("original-story", "story_dialogue",
                                  MaterialKind.ORIGINAL_EXPRESSION, proof),),
        hardware=HardwareAccessFacts(),
        originality_report=originality,
        rights_packet_sha256=digest("rights-file"),
    ))
    assert legal.design_admissible
    candidate = ReleaseCandidate(
        project_id=project,
        target_platform_id="windows_modern",
        world_sha256=artifact,
        native_source_sha256=digest("actual-c11-source"),
        native_binary_sha256=digest("compiled-executable"),
        rights_evidence_sha256=digest("rights-file"),
        legal_assessment_sha256=legal.assessment_digest,
        originality_screen_sha256=originality.screen_digest,
        credits_bundle_sha256=digest("reviewed-license-notices"),
        channel=ReleaseChannel.DIRECT_DOWNLOAD,
        jurisdictions=("NO", "EU_EEA"),
        author_ids=("game-author",), builder_ids=("build-agent",),
        native_build_evidence_sha256=digest("native-binary-test"),
        native_gameplay_evidence_sha256=digest("replay"),
    )
    return candidate, legal, originality


def signer(role: ReviewRole):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    from skeleton.ai.game_builder.release_assurance import _ROLE_BY_DOMAIN
    allowed = frozenset(d for d, owner in _ROLE_BY_DOMAIN.items() if owner is role)
    person = {
        ReviewRole.CREATIVE:"outside-creative-reviewer",
        ReviewRole.LEGAL:"outside-legal-reviewer",
        ReviewRole.TECHNICAL:"outside-hardware-reviewer",
    }[role]
    return key, TrustedReviewer(
        reviewer_id=person, key_id=person+"-key",
        public_key_hex=public, role=role, allowed_domains=allowed,
        valid_from_utc="2026-01-01T00:00:00Z",
        expires_utc="2028-01-01T00:00:00Z",
    )


def sign(key, reviewer: TrustedReviewer, candidate: ReleaseCandidate, domain: ReviewDomain,
         *, decision: ReviewDecision=ReviewDecision.ACCEPTED):
    att = ReviewAttestation(
        key_id=reviewer.key_id, reviewer_id=reviewer.reviewer_id,
        domain=domain, candidate_sha256=candidate.digest,
        review_evidence_sha256=digest("review-note-"+domain.value),
        decision=decision, issued_utc="2026-10-10T00:00:00Z",
        expires_utc="2027-01-01T00:00:00Z", signature_hex="00"*64,
    )
    return replace(att, signature_hex=key.sign(att.signed_bytes).hex())


def signed_panel(candidate):
    pairs = [signer(role) for role in ReviewRole]
    reg = tuple(row[1] for row in pairs)
    keys = {row[1].role:row[0] for row in pairs}
    reviewers = {r.role:r for r in reg}
    from skeleton.ai.game_builder.release_assurance import _ROLE_BY_DOMAIN
    signatures = tuple(
        sign(keys[role], reviewers[role], candidate, domain)
        for domain,role in _ROLE_BY_DOMAIN.items()
    )
    return reg, signatures


def evaluate(candidate, legal, originality, reg, signatures, now="2026-10-11T12:00:00Z"):
    return evaluate_independent_review(
        candidate, legal, originality, trust_registry=reg,
        attestations=signatures, evaluation_utc=now,
    )


def test_three_independent_reviewers_can_complete_all_ten_signed_domains():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    report = evaluate(candidate, legal, originality, reg, signatures)
    assert report.status is ReleaseReadiness.REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING
    assert len(report.verified_attestations) == len(ReviewDomain)
    assert report.unsigned_or_missing_domains == ()
    assert "FINAL_HUMAN_PUBLISHER_DECISION_REQUIRED" in report.pending_reasons
    assert report.legal_noninfringement_certified is False
    assert report.release_authorized is False
    assert report.publisher_approval_granted is False
    assert report == evaluate(candidate, legal, originality, reg, signatures)
    assert len(report.public_receipt()["receipt_sha256"]) == 64


def test_missing_one_domain_retains_independent_review_hold():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    report = evaluate(candidate, legal, originality, reg, signatures[:-1])
    assert report.status is ReleaseReadiness.INDEPENDENT_REVIEW_PENDING
    assert len(report.unsigned_or_missing_domains) == 1
    assert report.release_authorized is False


def test_changed_game_binary_invalidates_every_prior_review_signature():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    changed = replace(candidate, native_binary_sha256=digest("new-build"))
    report = evaluate(changed, legal, originality, reg, signatures)
    assert report.status is ReleaseReadiness.BLOCKED
    assert report.blocking_reasons
    assert report.unsigned_or_missing_domains


@pytest.mark.parametrize("change", [
    {"native_source_sha256":digest("new-source")},
    {"rights_evidence_sha256":digest("changed-rights")},
    {"credits_bundle_sha256":digest("updated-credits")},
    {"native_gameplay_evidence_sha256":digest("new-replay")},
    {"jurisdictions":("NO",)},
    {"channel":ReleaseChannel.PRIVATE_HOMEBREW},
])
def test_revisions_to_source_rights_replay_region_or_channel_revoke_old_signatures(change):
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    changed = replace(candidate, **change)
    report = evaluate(changed, legal, originality, reg, signatures)
    assert report.status is ReleaseReadiness.BLOCKED
    assert any("STALE_OR_FOREIGN_ARTIFACT_SIGNATURE" in x for x in report.blocking_reasons)


def test_signature_tampering_invalidates_independent_review():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    first = signatures[0]
    bad = replace(first, signature_hex=("00" if first.signature_hex[:2] != "00" else "01") + first.signature_hex[2:])
    report = evaluate(candidate, legal, originality, reg, (bad, *signatures[1:]))
    assert report.status is ReleaseReadiness.BLOCKED
    assert "INVALID_REVIEW_SIGNATURE:"+first.domain.value in report.blocking_reasons


def test_self_review_cannot_pass_even_with_valid_signature():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    changed = replace(candidate, author_ids=(reg[0].reviewer_id,))
    new_att = signed_panel(changed)
    report = evaluate(changed, legal, originality, *new_att)
    assert report.status is ReleaseReadiness.BLOCKED
    assert any("NON_INDEPENDENT_SELF_REVIEW" in x for x in report.blocking_reasons)


def test_key_revocation_removes_authority_without_changing_signature():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    bad_reg = (replace(reg[0], revoked=True), *reg[1:])
    report = evaluate(candidate, legal, originality, bad_reg, signatures)
    assert report.status is ReleaseReadiness.BLOCKED
    assert any("REVOKED_REVIEWER_KEY" in x for x in report.blocking_reasons)


def test_expired_review_cannot_reopen_old_rights_packet():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    report = evaluate(candidate, legal, originality, reg, signatures, now="2027-02-01T00:00:00Z")
    assert report.status is ReleaseReadiness.BLOCKED
    assert any("REVIEW_TIMESTAMP_OUTSIDE_TRUST_WINDOW" in x for x in report.blocking_reasons)


def test_rejected_or_requested_changes_cannot_pass_even_with_valid_signatures():
    candidate, legal, originality = base_evidence()
    for decision, expected_state in (
        (ReviewDecision.REJECTED, ReleaseReadiness.BLOCKED),
        (ReviewDecision.NEEDS_CHANGES, ReleaseReadiness.INDEPENDENT_REVIEW_PENDING),
    ):
        reg, signatures = signed_panel(candidate)
        # Sign a new decision with the original private keys: use the fixture
        # to produce a fresh independent panel and override one decision.
        key, reviewer = signer(ReviewRole.CREATIVE)
        new_reg = (reviewer, *reg[1:])
        new_first = sign(key, reviewer, candidate, ReviewDomain.AUTHORSHIP, decision=decision)
        remaining_creative = tuple(
            sign(key, reviewer, candidate, a.domain)
            for a in signatures if a.domain not in {ReviewDomain.AUTHORSHIP}
            and a.domain in reviewer.allowed_domains
        )
        unrelated = tuple(a for a in signatures if a.domain not in reviewer.allowed_domains)
        report = evaluate(candidate, legal, originality, new_reg,
                          (new_first, *remaining_creative, *unrelated))
        assert report.status is expected_state


def test_duplicate_reviewer_domain_fails_closed():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    report = evaluate(candidate, legal, originality, reg, (*signatures, signatures[0]))
    assert report.status is ReleaseReadiness.BLOCKED
    assert any("DUPLICATE_OR_CONFLICTING_ATTESTATIONS" in x for x in report.blocking_reasons)


def test_untrusted_signer_is_not_silently_promoted():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    unknown = replace(signatures[0], key_id="unknown-signing-key")
    report = evaluate(candidate, legal, originality, reg, (unknown,*signatures[1:]))
    assert report.status is ReleaseReadiness.BLOCKED
    assert any("REVIEW_SIGNER_NOT_IN_EXTERNAL_TRUST_REGISTRY" in x for x in report.blocking_reasons)


def test_no_external_reviewer_trust_registry_keeps_gate_closed():
    candidate, legal, originality = base_evidence()
    report = evaluate(candidate, legal, originality, (), ())
    assert report.status is ReleaseReadiness.INDEPENDENT_REVIEW_PENDING
    assert "EXTERNALLY_PROVISIONED_REVIEWER_TRUST_ROOT_MISSING" in report.pending_reasons
    assert len(report.unsigned_or_missing_domains) == len(ReviewDomain)


def test_candidate_is_bound_to_originality_and_legal_assessment():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    changed = replace(candidate, legal_assessment_sha256=digest("other-legal-review"))
    result = evaluate(changed, legal, originality, reg, signatures)
    assert "REVIEW_EVIDENCE_DOES_NOT_BIND_TO_BUILT_GAME" in result.blocking_reasons
    changed = replace(candidate, world_sha256=digest("other-world"))
    result = evaluate(changed, legal, originality, reg, signatures)
    assert "REVIEW_EVIDENCE_DOES_NOT_BIND_TO_BUILT_GAME" in result.blocking_reasons


def test_false_autoclearance_flags_are_rejected_by_immutable_receipts():
    candidate, legal, originality = base_evidence()
    reg, signatures = signed_panel(candidate)
    result = evaluate(candidate, legal, originality, reg, signatures)
    for flag in ("legal_noninfringement_certified","release_authorized",
                 "publisher_approval_granted"):
        with pytest.raises(ReleaseReviewError):
            replace(result, **{flag:True})


def test_commercial_channel_requires_independent_distribution_provenance():
    candidate, _, _ = base_evidence()
    with pytest.raises(ReleaseReviewError):
        replace(candidate, channel=ReleaseChannel.CONSOLE_STOREFRONT)
    with pytest.raises(ReleaseReviewError):
        replace(candidate, channel=ReleaseChannel.COMMERCIAL_DISTRIBUTION)


def test_unauthorized_role_cross_domain_or_key_mismatch_is_rejected():
    key, reviewer = signer(ReviewRole.CREATIVE)
    with pytest.raises(ReleaseReviewError):
        replace(reviewer, allowed_domains=frozenset({ReviewDomain.DISTRIBUTION_RIGHTS}))
    with pytest.raises(ReleaseReviewError):
        replace(reviewer, public_key_hex="invalid")
    with pytest.raises(ReleaseReviewError):
        replace(reviewer, revoked="false")
    with pytest.raises(ReleaseReviewError):
        replace(reviewer, expires_utc=reviewer.valid_from_utc)
    assert key is not None


def test_review_expiry_and_unknown_jurisdictions_are_invalid():
    candidate, _, _ = base_evidence()
    with pytest.raises(ReleaseReviewError):
        replace(candidate, jurisdictions=("OTHER",))
    with pytest.raises(ReleaseReviewError):
        replace(candidate, native_binary_sha256="wrong")
    with pytest.raises(ReleaseReviewError):
        replace(candidate, channel="commercial")
    reg, signatures = signed_panel(candidate)
    with pytest.raises(ReleaseReviewError):
        replace(signatures[0], expires_utc=signatures[0].issued_utc)
    with pytest.raises(ReleaseReviewError):
        evaluate(candidate, *_evidence_for(candidate), reg, signatures, now="not-a-date")


def _evidence_for(candidate):
    _, legal, originality = base_evidence()
    return legal, originality



def test_new_signatures_cannot_authorize_unreviewed_new_territory():
    """Re-signing another jurisdiction must not recycle the old legal opinion."""
    candidate, legal, originality = base_evidence()
    forged_new_market = replace(candidate, jurisdictions=("US",))
    reviewers, new_signatures = signed_panel(forged_new_market)
    result = evaluate(forged_new_market, legal, originality, reviewers, new_signatures)
    assert result.status is ReleaseReadiness.BLOCKED
    assert "RELEASE_JURISDICTIONS_NOT_IN_LEGAL_ASSESSMENT" in result.blocking_reasons
    assert result.release_authorized is False


def test_review_signatures_cannot_reauthorize_a_different_credit_bundle():
    """All ten freshly signed domains must still refer to reviewed credit bytes."""
    candidate, legal, originality = base_evidence()
    replaced_notices = replace(candidate, credits_bundle_sha256=digest("other-credit-notices"))
    reviewers, signatures = signed_panel(replaced_notices)
    result = evaluate(replaced_notices, legal, originality, reviewers, signatures)
    assert result.status is ReleaseReadiness.REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING
    # This signature-only plane checks approval of a DECLARED credit digest.
    # The native byte-intake must separately verify the signed digest
    # actually matches the reviewed source/credits files.
    assert result.release_authorized is False
