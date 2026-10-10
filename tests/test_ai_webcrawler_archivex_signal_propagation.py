"""ArchiveX source propagation regression tests."""
import sqlite3
from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_dependencies import ArchiveXDependencyIndex
from skeleton.ai.webcrawler.archivex_knowledge import ArchiveXKnowledgeStore
from skeleton.ai.webcrawler.archivex_lineage import ArchiveXEvidenceLineage
from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
from skeleton.ai.webcrawler.archivex_signal_index import ArchiveXSignalIndex, SignalKind
from skeleton.ai.webcrawler.archivex_signal_propagation import ArchiveXSignalPropagator


def setup():
    db = sqlite3.connect(":memory:")
    archive = ArchiveX(db)
    lineage = ArchiveXEvidenceLineage(archive)
    knowledge = ArchiveXKnowledgeStore(ArchiveXPromotionGate(db))
    dependencies = ArchiveXDependencyIndex(lineage, knowledge)
    signals = ArchiveXSignalIndex(db)
    propagation = ArchiveXSignalPropagator(archive, dependencies, signals)
    return db, archive, knowledge, signals, propagation


def capture(archive, body, observed_at):
    return archive.capture(
        "alice", source_url="https://journal.example.org/paper",
        body=body, observed_at=observed_at, now=observed_at,
        license_note="authorized", authorized=True,
    )


def test_changed_source_creates_review_pending_signal():
    _, archive, _, signals, propagation = setup()
    a = capture(archive, b"first result", 100)
    b = capture(archive, b"corrected result", 200)
    result = propagation.propagate(
        "alice", earlier_snapshot_id=a.snapshot_id,
        later_snapshot_id=b.snapshot_id, now=200, authorized=True,
    )
    assert result.signal.kind is SignalKind.REVISION
    assert result.signal.review_required
    assert signals.query("alice", now=200, authorized=True) == ()
    assert len(signals.query(
        "alice", now=200, authorized=True,
        include_review_pending=True,
    )) == 1


def test_unchanged_source_creates_low_strength_signal():
    _, archive, _, _, propagation = setup()
    a = capture(archive, b"same result", 100)
    b = capture(archive, b"same result", 200)
    result = propagation.propagate(
        "alice", earlier_snapshot_id=a.snapshot_id,
        later_snapshot_id=b.snapshot_id, now=200, authorized=True,
    )
    assert result.signal.kind is SignalKind.CORROBORATION
    assert result.signal.strength == 0.1


def test_cross_source_propagation_rejected():
    from dataclasses import replace
    import pytest
    _, archive, _, _, propagation = setup()
    a = capture(archive, b"first result", 100)
    b = capture(archive, b"second result", 200)
    archive.db.execute("""
        UPDATE archivex_snapshots SET source_url=?
        WHERE owner=? AND snapshot_id=?
    """, ("https://unrelated.example.org", "alice", b.snapshot_id))
    archive.db.commit()
    with pytest.raises(ValueError):
        propagation.propagate(
            "alice", earlier_snapshot_id=a.snapshot_id,
            later_snapshot_id=b.snapshot_id, now=200, authorized=True,
        )


def test_propagation_requires_authorization():
    import pytest
    _, archive, _, _, propagation = setup()
    a = capture(archive, b"first result", 100)
    b = capture(archive, b"second result", 200)
    with pytest.raises(PermissionError):
        propagation.propagate(
            "alice", earlier_snapshot_id=a.snapshot_id,
            later_snapshot_id=b.snapshot_id, now=200, authorized=False,
        )


def test_owner_isolation():
    _, archive, _, signals, propagation = setup()
    a = capture(archive, b"first result", 100)
    b = capture(archive, b"second result", 200)
    import pytest
    with pytest.raises(ValueError):
        propagation.propagate(
            "bob", earlier_snapshot_id=a.snapshot_id,
            later_snapshot_id=b.snapshot_id, now=200, authorized=True,
        )
    assert signals.query(
        "bob", now=200, authorized=True, include_review_pending=True,
    ) == ()
