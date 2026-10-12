"""Adversarial cross-source verification for Dragon mother-to-shadow admission."""
from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.webcrawler.dragon_cross_source_factchecking import (
    ClaimSubject, SourceWitness, SignedClaimAdjudication,
    witness_set_digest, verify_cross_source_claims,
)
from skeleton.ai.webcrawler.dragon_correlated_mother_handoff import (
    run_correlated_mother_to_shadow,
)


def _sign(key, packet):
    return key.sign(canonical_json(packet).encode()).hex()


def _keys():
    keys = [Ed25519PrivateKey.generate() for _ in range(3)]
    public = [k.public_key().public_bytes_raw() for k in keys]
    trust = {
        "publisher-one": ("auditor-one", "k1", public[0]),
        "publisher-two": ("auditor-two", "k2", public[1]),
    }
    return keys, public, trust


def _evidence(relations=("supports", "supports"), *, owner="studio"):
    keys, public, trust = _keys()
    subject = ClaimSubject("a"*64, "b"*64, "game-physics")
    witnesses = []
    for i, relation in enumerate(relations):
        group = ("publisher-one", "publisher-two")[i]
        w = SourceWitness(
            owner, "c"*64, subject.claim_digest, subject.context_digest,
            "source-" + str(i+1)*64, str(i+4)*64,
            group, relation, trust[group][0], trust[group][1],
            100, 800, "")
        witnesses.append(replace(w, signature_hex=_sign(keys[i], w.body())))
    adj = SignedClaimAdjudication(
        owner, "c"*64, subject.claim_digest, subject.context_digest,
        witness_set_digest(tuple(witnesses)), "accept",
        "independent-reviewer", "review-key", 110, 700, "")
    adj = replace(adj, signature_hex=_sign(keys[2], adj.body()))
    opts = {
        "trusted_publisher_reviewers": trust,
        "adjudicator_public_key": public[2],
        "adjudicator": "independent-reviewer",
        "adjudicator_key_id": "review-key",
        "now": 150,
    }
    return subject, tuple(witnesses), adj, opts, keys


def test_article_claim_corroboration_requires_distinct_signed_publishers():
    claim, witnesses, adjudication, opts, _ = _evidence()
    review = verify_cross_source_claims(
        "studio", "c"*64, (claim,), witnesses, (adjudication,), **opts)
    assert review["schema"] == "skeleton.dragon.signed_cross_source_fact_review.v1"
    assert review["all_claims_review_eligible"] is True
    assert review["corroborated_claim_count"] == 1
    assert review["claims"][0]["distinct_reviewed_publisher_groups"] == 2
    assert review["claims"][0]["contradicting_source_count"] == 0
    assert review["claims"][0]["source_independence_externally_attested_not_proved"]
    assert not review["neural_training_authorized"]
    assert not review["shadow_weight_promotion_authorized"]
    again = verify_cross_source_claims(
        "studio", "c"*64, (claim,), tuple(reversed(witnesses)),
        (adjudication,), **opts)
    assert again == review


def test_contradiction_uncertainty_or_missing_final_review_blocks():
    for relations in (("supports", "contradicts"),
                      ("supports", "uncertain")):
        claim, witnesses, adj, opts, _ = _evidence(relations)
        review = verify_cross_source_claims(
            "studio", "c"*64, (claim,), witnesses, (adj,), **opts)
        assert review["all_claims_review_eligible"] is False
        assert review["corroborated_claim_count"] == 0
        assert review["claims"][0]["supporting_source_count"] == 1
    claim, witnesses, adj, opts, _ = _evidence()
    review = verify_cross_source_claims(
        "studio", "c"*64, (claim,), witnesses, (), **opts)
    assert not review["all_claims_review_eligible"]
    with pytest.raises(PermissionError, match="not bound"):
        verify_cross_source_claims(
            "studio", "c"*64, (claim,), witnesses[:1], (adj,), **opts)


def test_forged_source_claims_and_cross_tenant_signatures_fail_closed():
    claim, witnesses, adj, opts, _ = _evidence()
    with pytest.raises(PermissionError, match="cross-tenant"):
        verify_cross_source_claims(
            "different-tenant", "c"*64, (claim,), witnesses, (adj,), **opts)
    with pytest.raises(PermissionError, match="signed factual"):
        verify_cross_source_claims(
            "studio", "c"*64, (claim,),
            (replace(witnesses[0], relation="supports",
                     source_revision_digest="f"*64), witnesses[1]),
            (adj,), **opts)
    with pytest.raises(ValueError, match="duplicate source"):
        verify_cross_source_claims(
            "studio", "c"*64, (claim,),
            (witnesses[0], witnesses[0]), (adj,), **opts)
    with pytest.raises(PermissionError, match="key reused"):
        trust = dict(opts["trusted_publisher_reviewers"])
        trust["publisher-two"] = ("auditor-two", "k2",
                                   trust["publisher-one"][2])
        verify_cross_source_claims(
            "studio", "c"*64, (claim,), witnesses, (adj,),
            **{**opts, "trusted_publisher_reviewers": trust})
    with pytest.raises(ValueError, match="stale"):
        verify_cross_source_claims(
            "studio", "c"*64, (claim,), witnesses, (adj,),
            **{**opts, "now": 800})


def test_final_adjudicator_cannot_sign_away_an_incomplete_claim():
    claim, witnesses, adj, opts, keys = _evidence()
    unknown = replace(adj, verdict="needs_research", signature_hex="")
    unknown = replace(unknown, signature_hex=_sign(keys[2], unknown.body()))
    review = verify_cross_source_claims(
        "studio", "c"*64, (claim,), witnesses, (unknown,), **opts)
    assert not review["all_claims_review_eligible"]
    with pytest.raises(PermissionError, match="signed factual"):
        verify_cross_source_claims(
            "studio", "c"*64, (claim,), witnesses,
            (replace(adj, verdict="accept", issued_at=130),), **opts)


def test_strict_mother_dispatch_requires_complete_article_fact_review():
    claim, witnesses, adj, opts, _ = _evidence()
    args = {
        "claims": (claim,), "witnesses": witnesses, "adjudications": (adj,),
        "trusted_publisher_reviewers": opts["trusted_publisher_reviewers"],
        "adjudicator_public_key": opts["adjudicator_public_key"],
        "adjudicator": opts["adjudicator"],
        "adjudicator_key_id": opts["adjudicator_key_id"],
        "plan": SimpleNamespace(owner="studio"),
        "knowledge_digest": "c"*64, "review_at": 150,
        "owner_authorized": True, "consented": True,
        "background_allowed": True, "privacy_clear": True,
    }
    with patch(
        "skeleton.ai.webcrawler.dragon_correlated_mother_handoff."
        "run_hundred_matrix_mother_to_shadow",
        return_value="still-must-pass-existing-100-matrix-worker"
    ) as worker:
        assert run_correlated_mother_to_shadow(**args) == (
            "still-must-pass-existing-100-matrix-worker")
        worker.assert_called_once()
        worker.reset_mock()
        with pytest.raises(PermissionError, match="contradiction"):
            run_correlated_mother_to_shadow(
                **{**args, "adjudications": ()})
        worker.assert_not_called()
        with pytest.raises(PermissionError, match="idle"):
            run_correlated_mother_to_shadow(
                **{**args, "background_allowed": False})
        worker.assert_not_called()
