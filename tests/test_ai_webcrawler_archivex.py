"""ArchiveX integrity, isolation, retention and temporal signal tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.archivex import ArchiveX, ArchiveXPolicy
from skeleton.ai.webcrawler.archivex_signals import (
    ArchiveSignalKind, compare_snapshots, source_drift_timeline,
)


URL = "https://research.example.org/study"


def archive():
    return ArchiveX(sqlite3.connect(":memory:"))


def capture(store, body, observed=100, owner="alice"):
    return store.capture(
        owner, source_url=URL, body=body, observed_at=observed,
        now=observed, license_note="Authorized excerpt", authorized=True,
    )


def test_content_addressing_is_idempotent_and_owner_isolated():
    store = archive()
    first = capture(store, b"evidence", owner="alice")
    again = capture(store, b"evidence", owner="alice")
    other = capture(store, b"evidence", owner="bob")
    assert first.snapshot_id == again.snapshot_id == other.snapshot_id
    assert len(store.timeline("alice", URL, authorized=True)) == 1
    assert store.read("bob", first.snapshot_id, authorized=True)[1] == b"evidence"
    assert store.read("carol", first.snapshot_id, authorized=True) is None


def test_archive_requires_authorization_and_license():
    store = archive()
    with pytest.raises(PermissionError):
        store.capture(
            "alice", source_url=URL, body=b"x", observed_at=1, now=1,
            license_note="ok", authorized=False,
        )
    with pytest.raises(ValueError, match="license"):
        store.capture(
            "alice", source_url=URL, body=b"x", observed_at=1, now=1,
            license_note="", authorized=True,
        )
    with pytest.raises(PermissionError):
        store.timeline("alice", URL, authorized=False)


def test_tampering_fails_integrity_check():
    store = archive()
    item = capture(store, b"original")
    store.db.execute(
        "UPDATE archivex_snapshots SET body=? WHERE owner=? AND snapshot_id=?",
        (b"tampered", "alice", item.snapshot_id),
    )
    store.db.commit()
    with pytest.raises(ValueError, match="integrity"):
        store.read("alice", item.snapshot_id, authorized=True)


def test_archive_capacity_and_retention():
    store = ArchiveX(
        sqlite3.connect(":memory:"),
        policy=ArchiveXPolicy(max_snapshots_per_owner=1, max_age_seconds=100),
    )
    capture(store, b"first", observed=100)
    with pytest.raises(ValueError, match="capacity"):
        capture(store, b"second", observed=101)
    assert store.prune("alice", now=201) == 1
    assert capture(store, b"second", observed=201)


def test_temporal_signals_detect_revisions_and_deletions():
    store = archive()
    capture(store, b"the original study showed a large effect", observed=100)
    capture(store, b"the study showed an effect", observed=200)
    capture(store, b"the study showed an effect", observed=300)
    signals = source_drift_timeline(store, "alice", URL, authorized=True)
    assert len(signals) == 3
    assert signals[0].kind is ArchiveSignalKind.FIRST_SEEN
    assert signals[1].kind in (ArchiveSignalKind.REMOVED, ArchiveSignalKind.REVISED)
    assert signals[2].kind is ArchiveSignalKind.UNCHANGED


def test_unrelated_sources_cannot_be_compared():
    store = archive()
    first = capture(store, b"first")
    second = store.capture(
        "alice", source_url="https://other.example.org/study",
        body=b"second", observed_at=200, now=200,
        license_note="Authorized excerpt", authorized=True,
    )
    with pytest.raises(ValueError, match="unrelated"):
        compare_snapshots(
            store.read("alice", first.snapshot_id, authorized=True),
            store.read("alice", second.snapshot_id, authorized=True),
        )
