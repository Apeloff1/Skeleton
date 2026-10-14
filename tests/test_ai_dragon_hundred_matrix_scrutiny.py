"""100 externally signed findings are advisory, never model promotion authority."""
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.webcrawler.dragon_hundred_matrix_scrutiny import (
    AXES, MATRIX_IDS, SignedMatrixFinding, scrutinize_one_hundred,
)

OWNER = "reviewed-dragon"
KNOWLEDGE = "a" * 64
EVIDENCE = "b" * 64
GROUPS = ("1" * 64, "2" * 64)
REVIEWER = "independent-human-reviewer"
KEY = "reviewer-key-v1"
NOW = 1_800_000_000


def _sign(key: Ed25519PrivateKey, matrix_id: str, **changes) -> SignedMatrixFinding:
    item = SignedMatrixFinding(
        matrix_id=matrix_id, owner=OWNER,
        knowledge_digest=KNOWLEDGE,
        evidence_digest=EVIDENCE,
        independent_group_digests=GROUPS,
        reviewer=REVIEWER, key_id=KEY,
        issued_at=NOW - 100, expires_at=NOW + 100,
        verdict="pass", signature_hex="",
    )
    if changes:
        item = replace(item, **changes)
    return replace(item, signature_hex=key.sign(canonical_json(item.body()).encode()).hex())


def _review(key: Ed25519PrivateKey, findings: tuple[SignedMatrixFinding, ...], **override):
    args = dict(
        public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
        trusted_reviewer=REVIEWER, key_id=KEY, now=NOW,
    )
    args.update(override)
    return scrutinize_one_hundred(OWNER, KNOWLEDGE, findings, **args)


def test_complete_signed_100_matrix_review_is_only_a_shadow_proposal() -> None:
    key = Ed25519PrivateKey.generate()
    findings = tuple(_sign(key, name) for name in MATRIX_IDS)
    result = _review(key, findings)
    assert len(MATRIX_IDS) == 100
    assert len(AXES) == 10
    assert result["passed_matrix_count"] == 100
    assert result["shadow_review_proposal_eligible"] is True
    assert not result["normal_weight_promotion_authorized"]
    assert not result["hyperweight_promotion_authorized"]
    assert not result["neural_training_authorized"]
    assert all(count == 10 for count in result["axis_pass_counts"].values())
    assert len(result["report_digest"]) == 64
    assert result == _review(key, findings)


def test_missing_failed_and_expired_finding_never_pass_shadow_review() -> None:
    key = Ed25519PrivateKey.generate()
    all_findings = tuple(_sign(key, name) for name in MATRIX_IDS)
    missing = _review(key, all_findings[:-1])
    assert missing["attested_matrix_count"] == 99
    assert missing["missing_matrix_ids"] == (MATRIX_IDS[-1],)
    assert missing["shadow_review_proposal_eligible"] is False

    rejected = _review(key, all_findings[:-1] + (_sign(key, MATRIX_IDS[-1], verdict="reject"),))
    assert not rejected["shadow_review_proposal_eligible"]
    assert rejected["failed_matrix_ids"] == (MATRIX_IDS[-1],)

    expired = _review(key, all_findings[:-1] + (_sign(key, MATRIX_IDS[-1], expires_at=NOW),))
    assert not expired["shadow_review_proposal_eligible"]
    assert expired["failed_matrix_ids"] == (MATRIX_IDS[-1],)


def test_signature_replay_and_identity_substitution_fail_closed() -> None:
    key = Ed25519PrivateKey.generate()
    entry = _sign(key, MATRIX_IDS[0])
    with pytest.raises(PermissionError, match="signature"):
        _review(key, (replace(entry, verdict="reject"),))
    with pytest.raises(PermissionError, match="signature"):
        _review(Ed25519PrivateKey.generate(), (entry,))
    with pytest.raises(PermissionError, match="identity"):
        _review(key, (replace(entry, reviewer="forged-reviewer"),))
    with pytest.raises(PermissionError, match="identity"):
        _review(key, (replace(entry, knowledge_digest="f" * 64),))


def test_bounded_unique_independent_source_groups_required() -> None:
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="distinct"):
        _review(key, (_sign(key, MATRIX_IDS[0], independent_group_digests=(GROUPS[0], GROUPS[0])),))
    with pytest.raises(ValueError, match="distinct"):
        _review(key, (_sign(key, MATRIX_IDS[0], independent_group_digests=(GROUPS[0],)),))
    with pytest.raises(ValueError, match="attestation"):
        _review(key, (_sign(key, MATRIX_IDS[0], issued_at=-1),))
    with pytest.raises(ValueError, match="trusted"):
        _review(key, (), trusted_reviewer="x" * 129)


def test_duplicate_unknown_or_untyped_receipts_rejected() -> None:
    key = Ed25519PrivateKey.generate()
    good = _sign(key, MATRIX_IDS[0])
    with pytest.raises(ValueError, match="duplicate"):
        _review(key, (good, good))
    with pytest.raises(ValueError, match="unknown"):
        _review(key, (_sign(key, "unknown.question"),))
    with pytest.raises(TypeError):
        _review(key, (object(),))
    with pytest.raises(ValueError, match="bounded"):
        _review(key, (), require_groups=1)
    with pytest.raises(ValueError, match="trusted"):
        _review(key, (), key_id="k" * 129)
