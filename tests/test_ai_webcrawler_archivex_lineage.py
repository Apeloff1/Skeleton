"""ArchiveX lineage adversarial tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_lineage import ArchiveXEvidenceLineage
from skeleton.ai.webcrawler.dragon_truth_verifier import Claim, Evidence, EvidenceStance


URL = "https://research.example.org/study"


def fixture():
    archive = ArchiveX(sqlite3.connect(":memory:"))
    lineage = ArchiveXEvidenceLineage(archive)
    snapshot = archive.capture(
        "alice", source_url=URL, body=b"Claim supported by archived evidence.",
        observed_at=100, now=100, license_note="Authorized quotation",
        authorized=True,
    )
    claim = Claim("c1", "Claim supported", "https://video.example.org/watch?v=1")
    evidence = Evidence(
        "e1", "c1", URL, "research", EvidenceStance.SUPPORTS,
        "Claim supported", 100, 0.9,
    )
    return archive, lineage, snapshot, claim, evidence


def test_anchor_exact_bytes_and_revalidate():
    _, lineage, snapshot, claim, evidence = fixture()
    anchor = lineage.anchor(
        "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
        start_byte=0, end_byte=15, authorized=True,
    )
    assert lineage.validate("alice", anchor, authorized=True).valid
    assert lineage.anchor(
        "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
        start_byte=0, end_byte=15, authorized=True,
    ) == anchor


def test_mismatched_excerpt_rejected():
    _, lineage, snapshot, claim, evidence = fixture()
    with pytest.raises(ValueError, match="excerpt"):
        lineage.anchor(
            "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
            start_byte=0, end_byte=10, authorized=True,
        )


def test_other_owner_cannot_anchor_snapshot():
    _, lineage, snapshot, claim, evidence = fixture()
    with pytest.raises(ValueError, match="unknown snapshot"):
        lineage.anchor(
            "bob", claim, evidence, snapshot_id=snapshot.snapshot_id,
            start_byte=0, end_byte=15, authorized=True,
        )


def test_tampered_snapshot_invalidates_anchor():
    archive, lineage, snapshot, claim, evidence = fixture()
    anchor = lineage.anchor(
        "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
        start_byte=0, end_byte=15, authorized=True,
    )
    archive.db.execute(
        "UPDATE archivex_snapshots SET body=? WHERE owner=? AND snapshot_id=?",
        (b"modified", "alice", snapshot.snapshot_id),
    )
    archive.db.commit()
    assert not lineage.validate("alice", anchor, authorized=True).valid


def test_revoked_authorization_denies_validation():
    _, lineage, snapshot, claim, evidence = fixture()
    anchor = lineage.anchor(
        "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
        start_byte=0, end_byte=15, authorized=True,
    )
    with pytest.raises(PermissionError):
        lineage.validate("alice", anchor, authorized=False)


def test_anchor_erasure_is_owner_scoped():
    _, lineage, snapshot, claim, evidence = fixture()
    anchor = lineage.anchor(
        "alice", claim, evidence, snapshot_id=snapshot.snapshot_id,
        start_byte=0, end_byte=15, authorized=True,
    )
    assert lineage.erase("bob") == 0
    assert lineage.erase("alice") == 1
    assert not lineage.validate("alice", anchor, authorized=True).valid
