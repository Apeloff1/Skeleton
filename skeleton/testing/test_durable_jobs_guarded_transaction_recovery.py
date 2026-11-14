"""Actual SQLite failure and replay regressions for recovered native AI packages."""
from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
from skeleton.ai.runtime.operational_ai.durable_jobs.transaction import TransactionGate
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied
from skeleton.ai.runtime.operational_ai.guarded_request.identities import Scope
from skeleton.ai.runtime.operational_ai.guarded_request.nonce_fence import NonceFence


DIGEST = "a" * 64


def test_deferred_constraint_commit_failure_releases_transaction():
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE child(pid INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)")
        gate = TransactionGate(db)
        with pytest.raises(sqlite3.IntegrityError):
            with gate.exclusive():
                db.execute("INSERT INTO child VALUES (9)")
        assert not db.in_transaction
        assert db.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0
        with gate.exclusive():
            db.execute("INSERT INTO parent VALUES (9)")
            db.execute("INSERT INTO child VALUES (9)")
        assert db.execute("SELECT pid FROM child").fetchone() == (9,)


def test_busy_reader_commit_rolls_back_and_allows_next_write(tmp_path):
    path = tmp_path / "jobs.sqlite"
    with closing(sqlite3.connect(path, isolation_level=None, timeout=0)) as writer:
        writer.execute("PRAGMA journal_mode=DELETE")
        writer.execute("CREATE TABLE jobs(id INTEGER)")
        gate = TransactionGate(writer)
        with closing(sqlite3.connect(path, isolation_level=None, timeout=0)) as reader:
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM jobs").fetchall()
            with pytest.raises(sqlite3.OperationalError):
                with gate.exclusive():
                    writer.execute("INSERT INTO jobs VALUES (1)")
            assert not writer.in_transaction
            reader.execute("ROLLBACK")
        with gate.exclusive():
            writer.execute("INSERT INTO jobs VALUES (2)")
        assert writer.execute("SELECT id FROM jobs").fetchall() == [(2,)]


class RollbackFailure(sqlite3.Connection):
    reject_rollback = False

    def execute(self, sql, parameters=()):
        if self.reject_rollback and sql == "ROLLBACK":
            raise sqlite3.OperationalError("injected rollback failure")
        return super().execute(sql, parameters)


def test_failed_rollback_quarantines_gate_even_after_external_recovery():
    with closing(sqlite3.connect(":memory:", isolation_level=None, factory=RollbackFailure)) as db:
        gate = TransactionGate(db)
        db.reject_rollback = True
        with pytest.raises(JobDenied, match="transaction-rollback"):
            with gate.exclusive():
                raise ValueError("work failed")
        db.reject_rollback = False
        db.execute("ROLLBACK")
        with pytest.raises(JobDenied, match="transaction-unavailable"):
            with gate.exclusive():
                pytest.fail("poisoned gate reused")


@pytest.mark.parametrize("row_factory", [None, sqlite3.Row])
def test_scope_replay_survives_row_factory_and_separates_principals(row_factory):
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = row_factory
        fence = NonceFence(db)
        a = Scope("tenant", "alice", "session", DIGEST)
        b = Scope("tenant", "bob", "session", DIGEST)
        assert fence.reserve(a, "nonce", 1, DIGEST) == "admitted"
        assert fence.reserve(a.key, "nonce", 1, DIGEST) == "replayed"
        assert fence.reserve(b, "nonce", 1, DIGEST) == "admitted"
        assert fence.reserve("legacy", "nonce", 1, DIGEST) == "admitted"
        with pytest.raises(GateDenied, match="nonce-collision"):
            fence.reserve(a, "nonce", 2, DIGEST)
        assert not db.in_transaction
        assert fence.head(a) == fence.head(b) == 1
        assert fence.reserve(a, "next", 2, DIGEST) == "admitted"
        assert fence.head(b) == 1


def test_nonce_begin_denial_does_not_rollback_foreign_transaction():
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        fence = NonceFence(db)
        db.execute("BEGIN")
        with pytest.raises(GateDenied, match="nonce-transaction-admission"):
            fence.reserve("scope", "nonce", 1, DIGEST)
        assert db.in_transaction
        db.execute("ROLLBACK")
        assert fence.reserve("scope", "nonce", 1, DIGEST) == "admitted"


def test_nonce_failed_rollback_quarantines_reads_and_writes():
    with closing(sqlite3.connect(":memory:", isolation_level=None, factory=RollbackFailure)) as db:
        fence = NonceFence(db)
        assert fence.reserve("scope", "nonce", 1, DIGEST) == "admitted"
        db.reject_rollback = True
        with pytest.raises(GateDenied, match="nonce-transaction-rollback"):
            fence.reserve("scope", "nonce", 2, DIGEST)
        db.reject_rollback = False
        db.execute("ROLLBACK")
        with pytest.raises(GateDenied, match="nonce-fence-unavailable"):
            fence.head("scope")
        with pytest.raises(GateDenied, match="nonce-fence-unavailable"):
            fence.reserve("scope", "next", 2, DIGEST)


def test_dispatch_parallel_quota_preserves_pending_work_and_recovers_after_failure():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from skeleton.ai.runtime.operational_ai.guarded_request.budgets import Quota
    from skeleton.ai.runtime.operational_ai.guarded_request.pressure import Pressure
    from skeleton.ai.runtime.operational_ai.guarded_request.workflow import GuardedDispatcher, NativeRequest

    entered, release = Event(), Event()
    calls = []
    scope = Scope("tenant", "alice", "session", DIGEST)

    def turn(**request):
        calls.append(request["request_id"])
        if request["request_id"] == "first":
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("test failed to release worker")
            raise RuntimeError("local generation failure")
        return request["request_id"]

    # Isolate scheduler behavior; this is not a native model qualification.
    service = SimpleNamespace(
        actor=SimpleNamespace(tenant="tenant", user="alice", model_digest=DIGEST),
        turn=turn,
    )
    dispatcher = GuardedDispatcher(service, quota=Quota(parallel_requests=1))
    for request_id in ("first", "second"):
        dispatcher.submit(NativeRequest(scope, request_id, "question"),
                          pressure=Pressure(0, 0, 0, 10), now_mono_ms=10)
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(dispatcher.drain_one)
        try:
            assert entered.wait(timeout=5)
            assert pool.submit(dispatcher.drain_one).result(timeout=3) is None
            assert dispatcher.queue.snapshot()["pending"] == 1
            assert dispatcher.queue.snapshot()["inflight"] == 1
        finally:
            release.set()
        with pytest.raises(RuntimeError, match="local generation failure"):
            active.result(timeout=5)
    assert dispatcher.drain_one() == "second"
    assert dispatcher.queue.snapshot()["total"] == 0
    assert calls == ["first", "second"]
