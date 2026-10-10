"""ArchiveX evidence revalidation integration tests."""
import sqlite3

from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_lineage import ArchiveXEvidenceLineage
from skeleton.ai.webcrawler.archivex_knowledge import ArchiveXKnowledgeStore
from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
from skeleton.ai.webcrawler.archivex_revalidation import ArchiveXRevalidator
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
    claim = Claim("c1", "A supported claim",
                  "https://videos.example.org/watch?v=1")
    sources = (
        ("e1", "https://a.example.org/study", "first finding"),
        ("e2", "https://b.example.org/study", "second finding"),
    )
    for evidence_id, url, excerpt in sources:
        snapshot = archive.capture(
            "alice", source_url=url, body=excerpt.encode(),
            observed_at=100, now=100, license_note="Authorized",
            authorized=True,
        )
        evidence = Evidence(
            evidence_id, "c1", url, "publisher-" + evidence_id,
            EvidenceStance.SUPPORTS, excerpt, 100, 0.9,
        )
        lineage.anchor(
            "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
            start_byte=0, end_byte=len(excerpt), authorized=True,
        )
    verification = VerificationResult(
        "c1", VerificationStatus.CORROBORATED, 1.8, 0, 2, 0,
        (), 0, "corroborated", "a" * 64,
    )
    review = AnchoredVerification(
        ProvenanceReview(verification, 2, 0, ("owner:a", "owner:b"),
                         "b" * 64),
        ("e1", "e2"), (), (),
    )
    receipt = gate.authorize(
        "alice", review, claim_id="c1", approval_id="review-1",
        now=100, consent=True, reviewer_approved=True,
    )
    memory.persist(
        receipt, summary="Evidence-supported finding",
        evidence_ids=("e1", "e2"), now=101, consent=True,
        authorized=True,
    )
    return archive, lineage, memory


def test_unchanged_archive_keeps_knowledge_active():
    archive, lineage, memory = setup()
    report = ArchiveXRevalidator(archive, lineage, memory).run(
        "alice", authorized=True,
    )
    assert report.inspected == 1
    assert report.invalidated == 0
    assert memory.read("alice", "c1", authorized=True).active


def test_source_revision_invalidates_knowledge():
    archive, lineage, memory = setup()
    archive.capture(
        "alice", source_url="https://a.example.org/study",
        body=b"corrected finding", observed_at=200, now=200,
        license_note="Authorized", authorized=True,
    )
    report = ArchiveXRevalidator(archive, lineage, memory).run(
        "alice", authorized=True,
    )
    assert report.invalidated == 1
    assert report.events[0].reason == "newer source snapshot changed"
    assert memory.read("alice", "c1", authorized=True) is None


def test_missing_anchor_invalidates_knowledge():
    archive, lineage, memory = setup()
    lineage.db.execute("""
        DELETE FROM archivex_evidence_anchors
        WHERE owner='alice' AND evidence_id='e1'
    """)
    lineage.db.commit()
    report = ArchiveXRevalidator(archive, lineage, memory).run(
        "alice", authorized=True,
    )
    assert report.invalidated == 1
    assert "anchor missing" in report.events[0].reason


def test_owner_isolation():
    archive, lineage, memory = setup()
    report = ArchiveXRevalidator(archive, lineage, memory).run(
        "bob", authorized=True,
    )
    assert report.inspected == 0
    assert report.invalidated == 0
    assert memory.read("alice", "c1", authorized=True) is not None
