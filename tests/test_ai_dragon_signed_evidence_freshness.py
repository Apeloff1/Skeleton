"""Bounded externally signed freshness fences; no inference or weight promotion."""
from dataclasses import replace
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.webcrawler.dragon_evidence_freshness_ledger import (
    SignedKnowledgeFreshness, DragonKnowledgeFreshnessLedger,
)

OWNER = "studio"
KNOWLEDGE = "a" * 64
SOURCES = "b" * 64
INDEX = "c" * 64
KEY = b"operator-owned-freshness-secret-at-least-32-bytes"


def setup():
    private = Ed25519PrivateKey.generate()
    pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    db = sqlite3.connect(":memory:")
    ledger = DragonKnowledgeFreshnessLedger(
        db, owner=OWNER, signing_key=KEY, reviewer_public_key=pub,
        reviewer="independent-reviewer", key_id="review-key-1",
    )
    return db, private, ledger


def signed(private, *, owner=OWNER, source=SOURCES, index=INDEX, status="fresh",
           reason="independent_review", reviewed=100, expires=500):
    receipt = SignedKnowledgeFreshness(
        owner, KNOWLEDGE, source, index, status, reason,
        "independent-reviewer", "review-key-1", reviewed, expires, "",
    )
    signature = private.sign(canonical_json(receipt.body()).encode("utf-8")).hex()
    return replace(receipt, signature_hex=signature)


def test_signed_fresh_evidence_is_bound_to_source_index_and_expires():
    db, private, ledger = setup()
    try:
        unknown = ledger.state(KNOWLEDGE, now=150, index_digest=INDEX,
                               source_set_digest=SOURCES)
        assert unknown["state"] == "unreviewed"
        assert not unknown["serve_permitted"]
        result = ledger.record(signed(private), now=150,
                               expected_revision=0, authorized=True)
        assert result["revision"] == 1
        assert result["weights_modified"] is False
        accepted = ledger.require_current(KNOWLEDGE, now=150,
                                          index_digest=INDEX, source_set_digest=SOURCES)
        assert accepted["serve_permitted"]
        assert accepted["read_only"]
        assert accepted["weights_modified"] is False
        with pytest.raises(PermissionError, match="wrong_source_or_index"):
            ledger.require_current(KNOWLEDGE, now=150, index_digest="d" * 64,
                                   source_set_digest=SOURCES)
        with pytest.raises(PermissionError, match="expired_or_future"):
            ledger.require_current(KNOWLEDGE, now=500, index_digest=INDEX,
                                   source_set_digest=SOURCES)
    finally:
        db.close()


def test_stale_evidence_requires_revised_sources_and_revocation_is_terminal():
    db, private, ledger = setup()
    try:
        ledger.record(signed(private), now=150, expected_revision=0, authorized=True)
        ledger.record(signed(private, status="stale", reason="source_changed",
                             reviewed=151), now=151, expected_revision=1, authorized=True)
        with pytest.raises(PermissionError, match="stale"):
            ledger.require_current(KNOWLEDGE, now=151, index_digest=INDEX,
                                   source_set_digest=SOURCES)
        with pytest.raises(PermissionError, match="unchanged stale"):
            ledger.record(signed(private, reviewed=152), now=152,
                          expected_revision=2, authorized=True)
        ledger.record(signed(private, source="e" * 64, reviewed=153),
                      now=153, expected_revision=2, authorized=True)
        assert ledger.require_current(KNOWLEDGE, now=153, index_digest=INDEX,
                                      source_set_digest="e" * 64)["revision"] == 3
        ledger.record(signed(private, source="e" * 64, reviewed=154,
                             status="revoked", reason="rights_revoked"),
                      now=154, expected_revision=3, authorized=True)
        with pytest.raises(PermissionError, match="revoked"):
            ledger.require_current(KNOWLEDGE, now=155, index_digest=INDEX,
                                   source_set_digest="e" * 64)
        with pytest.raises(PermissionError, match="revoked knowledge"):
            ledger.record(signed(private, source="f" * 64, reviewed=156),
                          now=156, expected_revision=4, authorized=True)
    finally:
        db.close()


def test_signer_forgeries_owner_substitutions_and_stale_revisions_are_denied():
    db, private, ledger = setup()
    try:
        stranger = Ed25519PrivateKey.generate()
        with pytest.raises(PermissionError, match="signature"):
            ledger.record(signed(stranger), now=150, expected_revision=0, authorized=True)
        with pytest.raises(PermissionError, match="policy"):
            ledger.record(signed(private, owner="other"), now=150,
                          expected_revision=0, authorized=True)
        with pytest.raises(PermissionError, match="operator-side"):
            ledger.record(signed(private), now=150, expected_revision=0, authorized=False)
        ledger.record(signed(private), now=150, expected_revision=0, authorized=True)
        with pytest.raises(PermissionError, match="stale knowledge"):
            ledger.record(signed(private), now=150, expected_revision=0, authorized=True)
        with pytest.raises(PermissionError, match="signature"):
            ledger.record(replace(signed(private), status="revoked"), now=150,
                          expected_revision=1, authorized=True)
    finally:
        db.close()


def test_full_replay_detects_tampered_row_and_missing_independent_head():
    db, private, ledger = setup()
    try:
        ledger.record(signed(private), now=150, expected_revision=0, authorized=True)
        db.execute(
            "UPDATE dragon_knowledge_freshness_v1 SET payload=? WHERE owner=?",
            ("{}", OWNER),
        )
        with pytest.raises(ValueError, match="corruption"):
            ledger.state(KNOWLEDGE, now=150, index_digest=INDEX,
                         source_set_digest=SOURCES)
    finally:
        db.close()

    db, private, ledger = setup()
    try:
        ledger.record(signed(private), now=150, expected_revision=0, authorized=True)
        db.execute("DELETE FROM dragon_knowledge_freshness_heads_v1 WHERE owner=?",
                   (OWNER,))
        with pytest.raises(ValueError, match="truncated"):
            ledger.state(KNOWLEDGE, now=150, index_digest=INDEX,
                         source_set_digest=SOURCES)
    finally:
        db.close()
