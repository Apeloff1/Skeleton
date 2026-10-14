"""Atomic ArchiveX knowledge persistence regression tests."""
import sqlite3
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
from skeleton.ai.webcrawler.archivex_knowledge import (
    ArchiveXKnowledgeStore, MemoryWritePolicy,
)
from skeleton.ai.webcrawler.archivex_truth_gate import AnchoredVerification
from skeleton.ai.webcrawler.dragon_provenance_registry import ProvenanceReview
from skeleton.ai.webcrawler.dragon_truth_verifier import (
    VerificationResult, VerificationStatus,
)


def setup():
    db = sqlite3.connect(":memory:")
    gate = ArchiveXPromotionGate(db)
    store = ArchiveXKnowledgeStore(gate)
    return db, gate, store


def receipt(gate, claim_id="claim-1"):
    verification = VerificationResult(
        claim_id, VerificationStatus.CORROBORATED, 1.8, 0, 2, 0,
        (), 0, "independent", "a" * 64,
    )
    result = AnchoredVerification(
        ProvenanceReview(verification, 2, 0, ("owner:a", "owner:b"),
                         "b" * 64),
        ("e1", "e2"), (), (),
    )
    return gate.authorize(
        "alice", result, claim_id=claim_id, approval_id="review-1",
        now=100, consent=True, reviewer_approved=True,
    )


def persist(store, token, **kwargs):
    args = dict(summary="Verified scientific observation",
                evidence_ids=("e1", "e2"), tags=("science",),
                now=101, consent=True, authorized=True)
    args.update(kwargs)
    return store.persist(token, **args)


def test_atomic_write_and_read_integrity():
    _, gate, store = setup()
    token = receipt(gate)
    memory = persist(store, token)
    assert memory.active
    assert store.read("alice", token.claim_id, authorized=True) == memory
    assert store.read("bob", token.claim_id, authorized=True) is None


def test_single_use_promotion_cannot_duplicate_memory():
    _, gate, store = setup()
    token = receipt(gate)
    persist(store, token)
    with pytest.raises(ValueError):
        persist(store, token)
    assert len(store.recent("alice", authorized=True)) == 1


def test_failed_memory_write_does_not_consume_receipt():
    db, gate, store = setup()
    token = receipt(gate)
    with pytest.raises(ValueError, match="summary"):
        persist(store, token, summary="")
    assert db.execute(
        "SELECT consumed_at FROM archivex_promotions WHERE owner='alice'"
    ).fetchone()[0] is None
    assert persist(store, token)


def test_database_insert_failure_rolls_back_receipt_consumption():
    db, gate, store = setup()
    token = receipt(gate)
    db.execute("""
        CREATE TRIGGER abort_memory_insert BEFORE INSERT ON archivex_knowledge
        BEGIN SELECT RAISE(ABORT, 'injected failure'); END
    """)
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        persist(store, token)
    assert db.execute(
        "SELECT consumed_at FROM archivex_promotions WHERE owner='alice'"
    ).fetchone()[0] is None
    db.execute("DROP TRIGGER abort_memory_insert")
    db.commit()
    assert persist(store, token)


def test_invalidated_memory_is_hidden_but_auditable():
    _, gate, store = setup()
    token = receipt(gate)
    persist(store, token)
    assert store.invalidate(
        "alice", token.claim_id, reason="source retracted",
        authorized=True,
    )
    assert store.read("alice", token.claim_id, authorized=True) is None
    archived = store.read(
        "alice", token.claim_id, authorized=True, include_inactive=True,
    )
    assert not archived.active
    assert archived.invalidation_reason == "source retracted"


def test_registry_rotation_invalidates_outdated_knowledge():
    _, gate, store = setup()
    token = receipt(gate)
    persist(store, token)
    assert store.invalidate_registry(
        "alice", current_fingerprint="c" * 64, authorized=True,
    ) == 1
    assert store.recent("alice", authorized=True) == ()


def test_tampering_with_stored_summary_detected():
    db, gate, store = setup()
    token = receipt(gate)
    persist(store, token)
    db.execute("""
        UPDATE archivex_knowledge SET summary='fabricated'
        WHERE owner='alice'
    """)
    db.commit()
    with pytest.raises(ValueError, match="integrity"):
        store.read("alice", token.claim_id, authorized=True)


def test_owner_erasure_does_not_touch_other_owner():
    _, gate, store = setup()
    token = receipt(gate)
    persist(store, token)
    assert store.erase("bob", authorized=True) == 0
    assert store.erase("alice", authorized=True) == 1
    assert store.read("alice", token.claim_id, authorized=True) is None


def test_consent_revocation_blocks_persistence():
    _, gate, store = setup()
    token = receipt(gate)
    with pytest.raises(PermissionError):
        persist(store, token, consent=False)
    with pytest.raises(PermissionError):
        persist(store, token, authorized=False)
    assert persist(store, token)


def test_evidence_references_must_be_distinct():
    _, gate, store = setup()
    token = receipt(gate)
    with pytest.raises(ValueError, match="duplicate"):
        persist(store, token, evidence_ids=("e1", "e1"))
    assert persist(store, token)


def test_capacity_limit_does_not_consume_receipt():
    db = sqlite3.connect(":memory:")
    gate = ArchiveXPromotionGate(db)
    store = ArchiveXKnowledgeStore(
        gate, policy=MemoryWritePolicy(max_memories_per_owner=1),
    )
    persist(store, receipt(gate, "claim-1"))
    second = receipt(gate, "claim-2")
    with pytest.raises(ValueError, match="capacity"):
        persist(store, second)
    assert db.execute("""
        SELECT consumed_at FROM archivex_promotions
        WHERE owner='alice' AND claim_id='claim-2'
    """).fetchone()[0] is None
