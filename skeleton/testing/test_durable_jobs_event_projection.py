"""Independent restart and hostile-row tests for durable audit replay."""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.runtime.operational_ai.durable_jobs.audit import append_event
from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_result, make_spec, make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.canonical import decode, encode, sha256
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
from skeleton.ai.runtime.operational_ai.durable_jobs.invariants import verify_store
from skeleton.ai.runtime.operational_ai.durable_jobs.store import JobStore


@pytest.mark.parametrize("row_factory", [None, sqlite3.Row])
def test_schema_bootstrap_is_atomic_even_with_default_isolation(row_factory):
    with closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = row_factory
        store = JobStore(db)
        assert not db.in_transaction
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        store.submit(make_spec(), now_ms=1000)
        assert not db.in_transaction
        assert verify_store(store)["verified"]


def test_schema_never_commits_or_rolls_back_caller_transaction():
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE unrelated(id INTEGER)")
        db.execute("INSERT INTO unrelated VALUES (3)")
        with pytest.raises(JobDenied, match="schema-foreign-transaction"):
            JobStore(db)
        assert db.in_transaction
        assert db.execute("SELECT id FROM unrelated").fetchone() == (3,)
        db.rollback()
        assert db.execute("SELECT id FROM unrelated").fetchone() is None
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0


def test_tampered_terminal_state_cannot_authorize_dependent_dispatch():
    store = make_store()
    with closing(store.db):
        parent = make_spec(name="parent")
        child = make_spec(name="child", dependencies=("parent",))
        store.submit(parent, now_ms=1000)
        store.submit(child, now_ms=1000)
        store.db.execute("UPDATE ai_durable_jobs SET state='completed' WHERE job_id='parent'")
        for operation in (
            lambda: store.inspect("parent", OWNER),
            lambda: store.claim("worker", now_ms=1000, target_job_id="child"),
            lambda: verify_store(store),
        ):
            with pytest.raises(JobDenied, match="job-audit-state-binding"):
                operation()
        assert len(store.audit("parent", OWNER)) == 1


def test_token_row_rehash_cannot_replace_audit_bound_claim():
    store = make_store()
    with closing(store.db):
        spec = make_spec()
        store.submit(spec, now_ms=1000)
        claim = store.claim("worker", now_ms=1000)
        forged = replace(claim, token="x"*43)
        store.db.execute("UPDATE ai_durable_jobs SET lease_token_sha=? WHERE job_id=?",
                         (sha256(forged.token.encode("ascii")), spec.job_id))
        with pytest.raises(JobDenied, match="job-audit-token-binding"):
            store.finish(forged, make_result(spec), now_ms=1001)
        with pytest.raises(JobDenied, match="job-audit-token-binding"):
            verify_store(store)
        assert store.db.execute("SELECT state FROM ai_durable_jobs").fetchone()[0] == "running"


def test_legacy_unbound_running_claim_is_inspectable_but_requires_reconciliation():
    store = make_store()
    with closing(store.db):
        spec = make_spec()
        store.submit(spec, now_ms=1000)
        token = "l"*43
        from skeleton.ai.runtime.operational_ai.durable_jobs.store import ClaimedJob
        claim = ClaimedJob(spec.job_id, spec.request_id, OWNER, spec.question,
                           "legacy", token, 1500, 1)
        with store.tx.exclusive() as db:
            db.execute("""UPDATE ai_durable_jobs SET state='running',attempt=1,
                       lease_token_sha=?,worker_id='legacy',lease_expires_ms=1500,
                       updated_ms=1000 WHERE job_id=?""", (sha256(token.encode("ascii")), spec.job_id))
            append_event(db, spec.job_id, "claimed",
                         {"worker": "legacy", "at": 1000, "attempt": 1, "lease_expires_ms": 1500})
        report = verify_store(store)
        assert report["verified"] and not report["dispatch_qualified"]
        assert report["legacy_unbound_active_leases"] == 1
        with pytest.raises(JobDenied, match="claim-audit-unbound"):
            store.finish(claim, make_result(spec), now_ms=1200)
        assert store.sweep(now_ms=1500)["held_running"] == 1
        assert store.inspect(spec.job_id, OWNER)["state"] == "held"
        assert store.manual_resume(
            spec.job_id, OWNER, now_ms=1501, no_effect_proof_sha256="a"*64,
            operator_approved=True, proof_verifier=lambda original, proof: original == spec,
        ) == "pending"
        resumed = store.claim("new_worker", now_ms=1502)
        assert resumed.attempt == 2
        assert store.finish(resumed, make_result(spec), now_ms=1503) == "committed"
        assert verify_store(store)["dispatch_qualified"]


def test_complete_projection_survives_restart_cancellation_and_manual_recovery(tmp_path):
    path = tmp_path / "queue.sqlite3"
    spec = make_spec()
    with closing(sqlite3.connect(path, isolation_level=None)) as db:
        store = JobStore(db)
        store.submit(spec, now_ms=1000)
        first = store.claim("worker", now_ms=1000, lease_ms=500)
        store.heartbeat(first, now_ms=1100, extend_ms=500)
        store.cancel(spec.job_id, OWNER, now_ms=1200)
        assert store.sweep(now_ms=1600)["held_running"] == 1
        assert verify_store(store)["held"] == 1
    with closing(sqlite3.connect(path, isolation_level=None)) as db:
        store = JobStore(db)
        store.manual_resume(spec.job_id, OWNER, now_ms=1601,
                            no_effect_proof_sha256="a"*64, operator_approved=True,
                            proof_verifier=lambda original, proof: original == spec)
        second = store.claim("worker", now_ms=1602)
        assert second.attempt == 2
        with pytest.raises(JobDenied, match="claim-worker"):
            store.finish(first, make_result(spec), now_ms=1603)
        store.finish(second, make_result(spec), now_ms=1603)
        assert store.receipt(spec.job_id, OWNER) == make_result(spec)
        assert verify_store(store)["terminal"] == 1


def test_audit_projection_rejects_orphaned_job_events():
    store = make_store()
    with closing(store.db):
        store.submit(make_spec(), now_ms=1000)
        with store.tx.exclusive() as db:
            append_event(db, "unknown", "submitted", {"at": 1000, "spec_sha": "a"*64})
        with pytest.raises(JobDenied, match="invariants-orphan-audit"):
            verify_store(store)


def test_json_budget_is_aggregate_before_encoding_and_rejects_hostile_keys():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(JobDenied, match="json-cycle"):
        encode(cycle)
    # Each element is individually legal. Their aggregate is not.
    with pytest.raises(JobDenied, match="json-oversize"):
        encode(["x"*65536]*3)
    with pytest.raises(JobDenied, match="json-key"):
        encode({"\ud800": 1})
    with pytest.raises(JobDenied, match="json-key"):
        decode(b'{"\\ud800":1}')
    with pytest.raises(JobDenied, match="json-float-underflow"):
        decode(b'{"x":1e-99999}')
    assert decode(b'{"x":0e-99999}') == {"x": 0.0}
    assert decode(encode({"a": ["雪", 0.25, True], "b": None})) == {"a": ["雪", 0.25, True], "b": None}
