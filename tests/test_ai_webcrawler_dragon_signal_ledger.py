"""Transactional signal-ledger regression tests."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_signal_ledger import (
    DragonSignalLedger, SignalLedgerPolicy,
)
from skeleton.ai.webcrawler.dragon_interest_signals import InterestSignal, SignalKind


def signal(key, topic="science", *, consent=True, observed_at=100.0):
    return InterestSignal(key, SignalKind.LIKE, (topic,), observed_at,
                          consent=consent)


def test_ledger_owner_isolation_and_erasure():
    ledger = DragonSignalLedger(sqlite3.connect(":memory:"))
    assert ledger.append("alice", (signal("one"),), now=100) == 1
    assert ledger.append("bob", (signal("one", "art"),), now=100) == 1
    assert [s.tags for s in ledger.recent("alice")] == [("science",)]
    assert [s.tags for s in ledger.recent("bob")] == [("art",)]
    assert ledger.erase("alice") == 1
    assert ledger.recent("alice") == ()
    assert len(ledger.recent("bob")) == 1


def test_idempotent_append_and_profile_reconstruction():
    ledger = DragonSignalLedger(sqlite3.connect(":memory:"))
    batch = (signal("a"), signal("b", "animation"))
    assert ledger.append("alice", batch, now=100) == 2
    assert ledger.append("alice", batch, now=100) == 0
    profile = ledger.profile("alice", now=100)
    assert profile.accepted_signals == 2
    assert {topic.tag for topic in profile.topics} == {"science", "animation"}


def test_invalid_batch_is_atomic():
    ledger = DragonSignalLedger(sqlite3.connect(":memory:"))
    with pytest.raises(PermissionError):
        ledger.append("alice", (signal("ok"), signal("denied", consent=False)),
                      now=100)
    assert ledger.recent("alice") == ()


def test_capacity_is_checked_before_writes():
    ledger = DragonSignalLedger(
        sqlite3.connect(":memory:"),
        policy=SignalLedgerPolicy(max_per_owner=2),
    )
    ledger.append("alice", (signal("one"),), now=100)
    with pytest.raises(ValueError, match="budget"):
        ledger.append("alice", (signal("two"), signal("three")), now=100)
    assert len(ledger.recent("alice")) == 1


def test_retention_pruning():
    ledger = DragonSignalLedger(
        sqlite3.connect(":memory:"),
        policy=SignalLedgerPolicy(retention_seconds=100),
    )
    ledger.append("alice", (signal("old", observed_at=100),), now=100)
    ledger.append("alice", (signal("new", observed_at=200),), now=200)
    assert ledger.prune("alice", now=250) == 1
    assert [s.signal_id for s in ledger.recent("alice")] == ["new"]


def test_rejects_expired_signal_and_invalid_owner():
    ledger = DragonSignalLedger(
        sqlite3.connect(":memory:"),
        policy=SignalLedgerPolicy(retention_seconds=100),
    )
    with pytest.raises(ValueError):
        ledger.append("alice", (signal("expired", observed_at=100),), now=300)
    with pytest.raises(ValueError):
        ledger.recent("")


def test_default_query_limit_respects_smaller_owner_capacity():
    ledger=DragonSignalLedger(sqlite3.connect(":memory:"),
                              policy=SignalLedgerPolicy(max_per_owner=2))
    ledger.append("alice",(signal("one"),signal("two")),now=100)
    assert len(ledger.recent("alice"))==2
    with pytest.raises(ValueError,match="limit"):
        ledger.recent("alice",limit=3)
