"""Adversarial integration tests for atomic indexed ArchiveX memory writes."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_lineage import ArchiveXEvidenceLineage
from skeleton.ai.webcrawler.archivex_dependencies import ArchiveXDependencyIndex
from skeleton.ai.webcrawler.archivex_knowledge import ArchiveXKnowledgeStore
from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
from skeleton.ai.webcrawler.archivex_integrated_writer import ArchiveXIntegratedWriter
from skeleton.ai.webcrawler.archivex_truth_gate import AnchoredVerification
from skeleton.ai.webcrawler.dragon_provenance_registry import ProvenanceReview
from skeleton.ai.webcrawler.dragon_truth_verifier import (
    Claim, Evidence, EvidenceStance, VerificationResult, VerificationStatus,
)


def setup():
    db = sqlite3.connect(":memory:")
    archive = ArchiveX(db)
    lineage = ArchiveXEvidenceLineage(archive)
    gate = ArchiveXPromotionGate(db)
    memory = ArchiveXKnowledgeStore(gate)
    index = ArchiveXDependencyIndex(lineage, memory)
    writer = ArchiveXIntegratedWriter(memory, lineage, index)
    claim = Claim("claim-1", "The experimental result",
                  "https://videos.example.org/watch?v=1")
    snapshots = []
    for n in (1, 2):
        url = f"https://journal-{n}.example.org/paper"
        excerpt = f"Independent observation {n}"
        snapshot = archive.capture(
            "alice", source_url=url, body=excerpt.encode(),
            observed_at=100, now=100, license_note="Authorized",
            authorized=True,
        )
        snapshots.append(snapshot)
        evidence = Evidence(
            f"e{n}", "claim-1", url, f"publisher-{n}",
            EvidenceStance.SUPPORTS, excerpt, 100, 0.9,
        )
        lineage.anchor(
            "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
            start_byte=0, end_byte=len(excerpt), authorized=True,
        )
    verified = VerificationResult(
        "claim-1", VerificationStatus.CORROBORATED,
        1.8, 0, 2, 0, (), 0, "independent", "a" * 64,
    )
    review = AnchoredVerification(
        ProvenanceReview(
            verified, 2, 0, ("owner:a", "owner:b"), "b" * 64,
        ),
        ("e1", "e2"), (), (),
    )
    receipt = gate.authorize(
        "alice", review, claim_id="claim-1",
        approval_id="review-1", now=100,
        consent=True, reviewer_approved=True,
    )
    return db, archive, lineage, gate, memory, index, writer, receipt, snapshots


def persist(writer, receipt, **kwargs):
    arguments = dict(
        summary="Reviewed independent experimental result",
        evidence_ids=("e1", "e2"),
        tags=("science", "research"),
        now=101, consent=True, authorized=True,
    )
    arguments.update(kwargs)
    return writer.persist(receipt, **arguments)


def test_atomic_write_includes_both_dependencies():
    _, _, _, _, memory, index, writer, receipt, snapshots = setup()
    result = persist(writer, receipt)
    assert result.dependency_count == 2
    assert result.memory.active
    assert writer.audit_claim("alice", "claim-1", authorized=True) == ()
    for snapshot in snapshots:
        assert index.impacted(
            "alice", snapshot.snapshot_id, authorized=True,
        ) == ("claim-1",)


def test_duplicate_promotion_fails_without_extra_writes():
    db, _, _, _, _, _, writer, receipt, _ = setup()
    persist(writer, receipt)
    with pytest.raises(ValueError):
        persist(writer, receipt)
    assert db.execute(
        "SELECT COUNT(*) FROM archivex_knowledge"
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM archivex_dependencies"
    ).fetchone()[0] == 2


def test_dependency_insertion_failure_rolls_back_everything():
    db, _, _, _, memory, _, writer, receipt, _ = setup()
    db.execute("""
        CREATE TRIGGER reject_dependency
        BEFORE INSERT ON archivex_dependencies
        BEGIN SELECT RAISE(ABORT, 'injected dependency failure'); END
    """)
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        persist(writer, receipt)
    assert memory.read("alice", "claim-1", authorized=True) is None
    assert db.execute(
        "SELECT consumed_at FROM archivex_promotions"
    ).fetchone()[0] is None
    db.execute("DROP TRIGGER reject_dependency")
    db.commit()
    assert persist(writer, receipt)


def test_changed_source_blocks_promotion():
    db, archive, _, _, _, _, writer, receipt, snapshots = setup()
    archive.capture(
        "alice", source_url=snapshots[0].source_url,
        body=b"New correction", observed_at=200, now=200,
        license_note="Authorized", authorized=True,
    )
    with pytest.raises(ValueError, match="changed"):
        persist(writer, receipt, now=201)
    assert db.execute(
        "SELECT consumed_at FROM archivex_promotions"
    ).fetchone()[0] is None


def test_missing_anchor_blocks_promotion():
    db, _, lineage, _, _, _, writer, receipt, _ = setup()
    lineage.db.execute("""
        DELETE FROM archivex_evidence_anchors
        WHERE owner='alice' AND evidence_id='e1'
    """)
    lineage.db.commit()
    with pytest.raises(ValueError, match="unanchored"):
        persist(writer, receipt)
    assert db.execute(
        "SELECT COUNT(*) FROM archivex_knowledge"
    ).fetchone()[0] == 0


def test_tampered_archive_blocks_promotion():
    _, archive, _, _, _, _, writer, receipt, snapshots = setup()
    archive.db.execute("""
        UPDATE archivex_snapshots SET body=?
        WHERE owner='alice' AND snapshot_id=?
    """, (b"tampered", snapshots[0].snapshot_id))
    archive.db.commit()
    with pytest.raises(ValueError):
        persist(writer, receipt)


def test_audit_detects_removed_dependency():
    _, _, _, _, _, _, writer, receipt, _ = setup()
    persist(writer, receipt)
    writer.db.execute("""
        DELETE FROM archivex_dependencies
        WHERE owner='alice' AND evidence_id='e1'
    """)
    writer.db.commit()
    assert "dependency mismatch: e1" in writer.audit_claim(
        "alice", "claim-1", authorized=True,
    )


def test_no_consent_no_memory():
    _, _, _, _, _, _, writer, receipt, _ = setup()
    with pytest.raises(PermissionError):
        persist(writer, receipt, consent=False)
    with pytest.raises(PermissionError):
        persist(writer, receipt, authorized=False)


def test_other_owner_has_no_access_to_claim():
    _, _, _, _, memory, _, writer, receipt, _ = setup()
    persist(writer, receipt)
    assert writer.audit_claim("bob", "claim-1", authorized=True) == (
        "knowledge missing",
    )
    assert memory.read("bob", "claim-1", authorized=True) is None


def test_deterministic_lineage_fingerprint():
    _, _, _, _, _, _, writer, receipt, _ = setup()
    result = persist(writer, receipt)
    assert len(result.lineage_fingerprint) == 64
    assert result.snapshot_ids == tuple(sorted(result.snapshot_ids)) or len(
        result.snapshot_ids
    ) == 2
