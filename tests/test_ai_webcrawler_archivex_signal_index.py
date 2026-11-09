"""ArchiveX temporal research signal index tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.archivex_signal_index import (
    ArchiveXSignalIndex, SignalIndexPolicy, SignalKind,
)


SNAPSHOT = "a" * 64


def store(**policy):
    return ArchiveXSignalIndex(
        sqlite3.connect(":memory:"), policy=SignalIndexPolicy(**policy),
    )


def record(index, owner="alice", **kwargs):
    args = dict(
        kind=SignalKind.DISCOVERY, subject="Machine Learning",
        source_snapshot_id=SNAPSHOT, observed_at=100, now=100,
        strength=0.8, review_required=False, authorized=True,
    )
    args.update(kwargs)
    return index.record(owner, **args)


def test_record_and_query_are_deterministic():
    index = store()
    first = record(index)
    second = record(index)
    assert first == second
    results = index.query("alice", now=100, authorized=True)
    assert len(results) == 1
    assert results[0].signal.subject == "machine learning"
    assert results[0].decayed_strength == 0.8


def test_owner_isolation():
    index = store()
    record(index)
    assert index.query("bob", now=100, authorized=True) == ()
    assert index.erase("bob", authorized=True) == 0
    assert index.query("alice", now=100, authorized=True)


def test_review_pending_is_hidden_by_default():
    index = store()
    record(index, review_required=True)
    assert index.query("alice", now=100, authorized=True) == ()
    assert len(index.query(
        "alice", now=100, authorized=True,
        include_review_pending=True,
    )) == 1


def test_temporal_decay_reduces_strength():
    index = store(half_life_days=1)
    record(index, observed_at=0, now=0, strength=1)
    results = index.query("alice", now=86400, authorized=True)
    assert len(results) == 1
    assert abs(results[0].decayed_strength - 0.5) < 0.00001


def test_subject_filter():
    index = store()
    record(index)
    record(index, subject="Biology")
    results = index.query(
        "alice", now=100, authorized=True, subject="BIOLOGY",
    )
    assert len(results) == 1
    assert results[0].signal.subject == "biology"


def test_capacity_enforced_without_blocking_duplicates():
    index = store(max_signals_per_owner=1)
    record(index)
    record(index)
    with pytest.raises(ValueError, match="capacity"):
        record(index, subject="biology")


def test_invalid_strength_and_source_rejected():
    index = store()
    with pytest.raises(ValueError, match="strength"):
        record(index, strength=float("nan"))
    with pytest.raises(ValueError, match="source"):
        record(index, source_snapshot_id="not-a-digest")


def test_consent_gate():
    index = store()
    with pytest.raises(PermissionError):
        record(index, authorized=False)
    with pytest.raises(PermissionError):
        index.query("alice", now=100, authorized=False)


def test_retention_pruning():
    index = store(max_signal_age_days=1)
    record(index, observed_at=0, now=0)
    assert index.prune("alice", now=86401, authorized=True) == 1
    assert index.query("alice", now=86401, authorized=True) == ()


def test_retraction_is_not_mistaken_for_positive_corroboration():
    index = store()
    record(index, kind=SignalKind.RETRACTION, strength=1)
    results = index.query("alice", now=100, authorized=True)
    assert results[0].signal.kind is SignalKind.RETRACTION
