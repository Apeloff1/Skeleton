"""ArchiveX reverse-dependency integration and adversarial tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_lineage import ArchiveXEvidenceLineage
from skeleton.ai.webcrawler.archivex_dependencies import (
    ArchiveXDependencyIndex, DependencyPolicy,
)
from skeleton.ai.webcrawler.archivex_knowledge import ArchiveXKnowledgeStore
from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
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
    knowledge = ArchiveXKnowledgeStore(gate)
    index = ArchiveXDependencyIndex(lineage, knowledge)
    claim = Claim("c1", "An observation",
                  "https://video.example.org/watch?v=1")
    snapshots = []
    for number in (1, 2):
        url = f"https://source-{number}.example.org/article"
        excerpt = f"finding number {number}"
        snapshot = archive.capture(
            "alice", source_url=url, body=excerpt.encode(),
            observed_at=100, now=100, license_note="Authorized",
            authorized=True,
        )
        snapshots.append(snapshot)
        evidence = Evidence(
            f"e{number}", "c1", url, f"owner-{number}",
            EvidenceStance.SUPPORTS, excerpt, 100, 0.9,
        )
        lineage.anchor(
            "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
            start_byte=0, end_byte=len(excerpt), authorized=True,
        )
    verification = VerificationResult(
        "c1", VerificationStatus.CORROBORATED, 1.8, 0, 2, 0,
        (), 0, "independent", "a" * 64,
    )
    result = AnchoredVerification(
        ProvenanceReview(verification, 2, 0, ("owner:a", "owner:b"),
                         "b" * 64),
        ("e1", "e2"), (), (),
    )
    token = gate.authorize(
        "alice", result, claim_id="c1", approval_id="approval-1",
        now=100, consent=True, reviewer_approved=True,
    )
    knowledge.persist(
        token, summary="Supported observation",
        evidence_ids=("e1", "e2"), now=101, consent=True,
        authorized=True,
    )
    return index, knowledge, snapshots


def test_dependency_index_tracks_each_evidence_source():
    index, knowledge, snapshots = setup()
    assert index.index_claim("alice", "c1", authorized=True) == 2
    for snapshot in snapshots:
        assert index.impacted(
            "alice", snapshot.snapshot_id, authorized=True,
        ) == ("c1",)


def test_invalidation_is_targeted_and_idempotent():
    index, knowledge, snapshots = setup()
    index.index_claim("alice", "c1", authorized=True)
    receipt = index.invalidate_snapshot(
        "alice", snapshots[0].snapshot_id,
        reason="source retracted", authorized=True,
    )
    assert receipt.invalidated == 1
    assert receipt.affected_claims == ("c1",)
    assert knowledge.read("alice", "c1", authorized=True) is None
    again = index.invalidate_snapshot(
        "alice", snapshots[0].snapshot_id,
        reason="source retracted", authorized=True,
    )
    assert again.invalidated == 0
    assert again.fingerprint == receipt.fingerprint


def test_owner_isolation():
    index, knowledge, snapshots = setup()
    index.index_claim("alice", "c1", authorized=True)
    assert index.impacted(
        "bob", snapshots[0].snapshot_id, authorized=True,
    ) == ()
    assert index.erase("bob", authorized=True) == 0
    assert knowledge.read("alice", "c1", authorized=True) is not None


def test_indexing_without_authorization_fails():
    index, _, _ = setup()
    with pytest.raises(PermissionError):
        index.index_claim("alice", "c1", authorized=False)


def test_indexing_is_repeatable():
    index, _, snapshots = setup()
    assert index.index_claim("alice", "c1", authorized=True) == 2
    assert index.index_claim("alice", "c1", authorized=True) == 2
    assert index.erase("alice", authorized=True) == 2
    assert index.impacted(
        "alice", snapshots[0].snapshot_id, authorized=True,
    ) == ()


def test_bounded_invalidation_fails_closed():
    index, _, snapshots = setup()
    index.index_claim("alice", "c1", authorized=True)
    with pytest.raises(ValueError, match="limit"):
        index.impacted(
            "alice", snapshots[0].snapshot_id, authorized=True,
            limit=1000000,
        )
