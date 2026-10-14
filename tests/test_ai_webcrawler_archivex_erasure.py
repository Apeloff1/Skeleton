"""ArchiveX complete owner-erasure regression tests."""
import sqlite3

from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_dependencies import ArchiveXDependencyIndex
from skeleton.ai.webcrawler.archivex_knowledge import ArchiveXKnowledgeStore
from skeleton.ai.webcrawler.archivex_lineage import ArchiveXEvidenceLineage
from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
from skeleton.ai.webcrawler.archivex_signal_index import ArchiveXSignalIndex, SignalKind


def setup():
    db = sqlite3.connect(":memory:")
    archive = ArchiveX(db)
    lineage = ArchiveXEvidenceLineage(archive)
    gate = ArchiveXPromotionGate(db)
    memory = ArchiveXKnowledgeStore(gate)
    ArchiveXDependencyIndex(lineage, memory)
    signals = ArchiveXSignalIndex(db)
    return db, archive, signals


def capture(archive, owner):
    return archive.capture(
        owner, source_url="https://research.example.org/study",
        body=b"licensed evidence", observed_at=100, now=100,
        license_note="authorized", authorized=True,
    )


def test_erasure_removes_owner_from_all_archive_related_tables():
    db, archive, signals = setup()
    snapshot = capture(archive, "alice")
    signals.record(
        "alice", kind=SignalKind.DISCOVERY, subject="biology",
        source_snapshot_id=snapshot.snapshot_id,
        observed_at=100, now=100, strength=0.7,
        authorized=True,
    )
    db.execute(
        "INSERT INTO archivex_evidence_anchors VALUES (?,?,?,?,?,?,?)",
        ("alice", "claim", "evidence", snapshot.snapshot_id,
         0, 5, "a" * 64),
    )
    db.execute(
        "INSERT INTO archivex_dependencies VALUES (?,?,?,?)",
        ("alice", snapshot.snapshot_id, "claim", "evidence"),
    )
    db.commit()
    assert archive.erase("alice") == 1
    for table in (
        "archivex_snapshots",
        "archivex_evidence_anchors",
        "archivex_dependencies",
        "archivex_research_signals",
    ):
        assert db.execute(
            "SELECT COUNT(*) FROM " + table + " WHERE owner='alice'"
        ).fetchone()[0] == 0


def test_erasure_preserves_other_owners():
    db, archive, _ = setup()
    capture(archive, "alice")
    other = capture(archive, "bob")
    assert archive.erase("alice") == 1
    assert archive.read("bob", other.snapshot_id, authorized=True)


def test_erasure_on_minimal_archive_without_optional_tables():
    db = sqlite3.connect(":memory:")
    archive = ArchiveX(db)
    capture(archive, "alice")
    assert archive.erase("alice") == 1
    assert archive.erase("alice") == 0
