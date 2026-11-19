"""Durable work custody and plan-to-admission verification, no live workers."""
from dataclasses import replace
import sqlite3

import pytest

from skeleton.frontier.durable_work import (
    DurableWorkJournal, WorkCapacity, WorkConflict, WorkIntegrityError, WorkOrder, work_identity,
)
from skeleton.prood.admission import admit_build


def open_journal(path, scope="owner", **kwargs):
    connection = sqlite3.connect(path)
    return connection, DurableWorkJournal(connection, scope=scope, custody_key=b"w" * 32, **kwargs)


def order(scope, identity, deps=(), payload=None):
    return WorkOrder(work_identity(scope, "test", identity), "test",
                     {"identity": identity} if payload is None else payload, tuple(deps))


def test_ordered_batch_and_claim_receipt(tmp_path):
    db, journal = open_journal(tmp_path / "work.sqlite")
    first = order("owner", "first")
    second = order("owner", "second", (first.work_id,))
    assert [r.state for r in journal.submit([first, second])] == ["pending", "pending"]
    with pytest.raises(WorkConflict):
        journal.claim(second.work_id, owner="worker2")
    claim = journal.claim(first.work_id, owner="worker1")
    assert claim.token not in repr(claim)
    with pytest.raises(WorkConflict):
        journal.claim(first.work_id, owner="worker2")
    with pytest.raises(WorkConflict):
        journal.finish(replace(claim, token="0" * 64), succeeded=True, receipt_digest="a" * 64)
    result = journal.finish(claim, succeeded=True, receipt_digest="a" * 64)
    assert result.state == "succeeded"
    assert journal.finish(claim, succeeded=True, receipt_digest="a" * 64) == result
    with pytest.raises(WorkConflict):
        journal.finish(claim, succeeded=False, receipt_digest="a" * 64)
    assert journal.claim(second.work_id, owner="worker2").payload["identity"] == "second"
    db.close()


def test_reopen_never_reexecutes_uncertain_claim(tmp_path):
    path = tmp_path / "work.sqlite"
    db, journal = open_journal(path)
    work = order("owner", "once")
    journal.submit([work])
    claim = journal.claim(work.work_id, owner="worker")
    journal.close()
    db.close()
    db, recovered = open_journal(path)
    assert recovered.list_status(state="claimed")[0].work_id == work.work_id
    assert recovered.submit([work])[0].state == "claimed"
    with pytest.raises(WorkConflict):
        recovered.claim(work.work_id, owner="new")
    assert recovered.mark_uncertain(claim, receipt_digest="b" * 64).state == "uncertain"
    with pytest.raises(WorkConflict):
        recovered.claim(work.work_id, owner="new")
    db.close()


def test_scope_separation_and_atomic_conflict(tmp_path):
    path = tmp_path / "work.sqlite"
    db, journal = open_journal(path)
    first = order("owner", "existing")
    journal.submit([first])
    fresh = order("owner", "fresh")
    with pytest.raises(WorkConflict):
        journal.submit([fresh, replace(first, payload={"different": True})])
    with pytest.raises(KeyError):
        journal.status(fresh.work_id)
    other_db, other = open_journal(path, scope="other")
    assert other.list_status() == ()
    with pytest.raises(KeyError):
        other.claim(first.work_id, owner="other")
    other_db.close()
    db.close()


def test_capacity_batch_is_atomic_and_cycles_denied(tmp_path):
    db, journal = open_journal(tmp_path / "work.sqlite", max_rows=1)
    a = order("owner", "a")
    b = order("owner", "b", (a.work_id,))
    with pytest.raises(WorkCapacity):
        journal.submit([a, b])
    assert journal.list_status() == ()
    with pytest.raises(WorkConflict):
        journal.submit([b, a])
    assert journal.list_status() == ()
    db.close()


def test_tamper_state_cannot_hide_from_recovery_scan(tmp_path):
    db, journal = open_journal(tmp_path / "work.sqlite")
    work = order("owner", "a")
    journal.submit([work])
    db.execute("UPDATE frontier_work_orders_v1 SET state='failed'")
    db.commit()
    with pytest.raises(WorkIntegrityError):
        journal.list_status(state="claimed")
    with pytest.raises(WorkIntegrityError):
        journal.claim(work.work_id, owner="worker")
    db.close()


def test_cancelled_dependency_blocks_followers(tmp_path):
    db, journal = open_journal(tmp_path / "work.sqlite")
    a = order("owner", "a")
    b = order("owner", "b", (a.work_id,))
    journal.submit([a, b])
    assert journal.cancel_pending(a.work_id, receipt_digest="c" * 64).state == "cancelled"
    with pytest.raises(WorkConflict):
        journal.claim(b.work_id, owner="worker")
    db.close()


def test_prood_is_deterministically_admitted_not_executed(tmp_path):
    db, journal = open_journal(tmp_path / "work.sqlite")
    a = admit_build(journal, build_id="game", phases=["world", "mechanics"], platoon_size=3)
    b = admit_build(journal, build_id="game", phases=["world", "mechanics"], platoon_size=3)
    assert a == b and a.worker_count == 6 and not a.execution_verified
    assert all(item.state == "pending" for item in a.work)
    assert all(len(item.dependencies) == 3 for item in a.work[3:])
    with pytest.raises(WorkConflict):
        journal.claim(a.work[3].work_id, owner="worker")
    for index, item in enumerate(a.work[:3]):
        claim = journal.claim(item.work_id, owner=f"worker{index}")
        journal.finish(claim, succeeded=True, receipt_digest="d" * 64)
    assert journal.claim(a.work[3].work_id, owner="worker3").payload["phase"] == "mechanics"
    db.close()
