"""External source signatures prove attestations, not independent factual truth."""
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.webcrawler.dragon_cross_source_factchecking import (
    ClaimSubject, SourceWitness, SignedClaimAdjudication,
    verify_cross_source_claims, witness_set_digest,
)

OWNER = "studio"
KNOW = "a" * 64
CLAIM = ClaimSubject("b" * 64, "c" * 64, "gameplay")
NOW = 1000


def _public(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _signed_witness(key, *, group, source, revision, relation="supports"):
    item = SourceWitness(
        OWNER, KNOW, CLAIM.claim_digest, CLAIM.context_digest,
        "source-" + source * 64, revision * 64, group, relation,
        "reviewer-" + group, "key-" + group, NOW - 100, NOW + 100, "",
    )
    return replace(item, signature_hex=key.sign(canonical_json(item.body()).encode()).hex())


def _setup(relation2="supports", *, same_group=False):
    first = Ed25519PrivateKey.generate()
    second = Ed25519PrivateKey.generate()
    judge = Ed25519PrivateKey.generate()
    group2 = "lab-one" if same_group else "lab-two"
    witnesses = (
        _signed_witness(first, group="lab-one", source="d", revision="e"),
        _signed_witness(first if same_group else second,
                        group=group2, source="e", revision="f",
                        relation=relation2),
    )
    policy = {
        "lab-one": ("reviewer-lab-one", "key-lab-one", _public(first)),
    }
    if not same_group:
        policy["lab-two"] = ("reviewer-lab-two", "key-lab-two", _public(second))
    else:
        # Trust-map minimum is two distinct configured independent reviewers,
        # even when the actual evidence happens to come from one group.
        policy["lab-two"] = ("reviewer-lab-two", "key-lab-two", _public(second))
    body = SignedClaimAdjudication(
        OWNER, KNOW, CLAIM.claim_digest, CLAIM.context_digest,
        witness_set_digest(witnesses), "accept",
        "independent-judge", "judge-key", NOW - 50, NOW + 50, "",
    )
    final = replace(body, signature_hex=judge.sign(canonical_json(body.body()).encode()).hex())
    args = dict(
        trusted_publisher_reviewers=policy,
        adjudicator_public_key=_public(judge),
        adjudicator="independent-judge", adjudicator_key_id="judge-key",
        now=NOW,
    )
    return witnesses, final, args


def test_two_signed_independent_source_groups_admit_review_not_training():
    witnesses, adjudication, options = _setup()
    result = verify_cross_source_claims(
        OWNER, KNOW, (CLAIM,), witnesses, (adjudication,), **options,
    )
    assert result["all_claims_review_eligible"]
    assert result["corroborated_claim_count"] == 1
    assert result["claims"][0]["distinct_reviewed_publisher_groups"] == 2
    assert result["claims"][0]["supporting_source_count"] == 2
    assert result["independent_source_rights_still_required"]
    assert not result["neural_training_authorized"]
    assert not result["shadow_weight_promotion_authorized"]
    assert not result["normal_weight_promotion_authorized"]
    assert not result["hyperweight_promotion_authorized"]
    assert result == verify_cross_source_claims(
        OWNER, KNOW, (CLAIM,), tuple(reversed(witnesses)),
        (adjudication,), **options,
    )


def test_independent_contradiction_always_blocks_corroboration():
    witnesses, adjudication, options = _setup(relation2="contradicts")
    report = verify_cross_source_claims(
        OWNER, KNOW, (CLAIM,), witnesses, (adjudication,), **options,
    )
    assert not report["all_claims_review_eligible"]
    assert report["claims"][0]["contradicting_source_count"] == 1


def test_same_publisher_group_cannot_fake_independent_corroboration():
    witnesses, adjudication, options = _setup(same_group=True)
    report = verify_cross_source_claims(
        OWNER, KNOW, (CLAIM,), witnesses, (adjudication,), **options,
    )
    assert not report["all_claims_review_eligible"]
    assert report["claims"][0]["distinct_reviewed_publisher_groups"] == 1


def test_tampered_signature_missing_review_or_spoofed_owner_fail_closed():
    witnesses, adjudication, options = _setup()
    with pytest.raises(PermissionError, match="factual evidence"):
        verify_cross_source_claims(
            OWNER, KNOW, (CLAIM,),
            (replace(witnesses[0], relation="contradicts"), witnesses[1]),
            (adjudication,), **options,
        )
    with pytest.raises(PermissionError, match="cross-tenant"):
        verify_cross_source_claims(
            OWNER, KNOW, (CLAIM,),
            (replace(witnesses[0], owner="other"), witnesses[1]),
            (adjudication,), **options,
        )
    without_review = verify_cross_source_claims(
        OWNER, KNOW, (CLAIM,), witnesses, (), **options,
    )
    assert not without_review["all_claims_review_eligible"]
    with pytest.raises(PermissionError, match="signed witness set"):
        verify_cross_source_claims(
            OWNER, KNOW, (CLAIM,), witnesses,
            (replace(adjudication, witness_set_digest="0" * 64),),
            **options,
        )


def test_reused_keys_and_duplicates_do_not_count_as_two_reviews():
    witnesses, adjudication, options = _setup()
    tampered = dict(options)
    tampered["trusted_publisher_reviewers"] = {
        **options["trusted_publisher_reviewers"],
        "lab-two": ("reviewer-lab-two", "key-lab-two",
                    options["trusted_publisher_reviewers"]["lab-one"][2]),
    }
    with pytest.raises(PermissionError, match="key reused"):
        verify_cross_source_claims(
            OWNER, KNOW, (CLAIM,), witnesses, (adjudication,), **tampered,
        )
    with pytest.raises(ValueError, match="duplicate source identity"):
        verify_cross_source_claims(
            OWNER, KNOW, (CLAIM,), (witnesses[0], witnesses[0]),
            (adjudication,), **options,
        )
