"""SQLite qualification of durable native scheduling authority (no model fixtures as evidence)."""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace
import sqlite3

import pytest

from skeleton.ai.runtime.operational_ai.durable_jobs.bridge import NativeJobBridge
from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_result, make_spec, make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.canonical import encode
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
from skeleton.ai.runtime.operational_ai.durable_jobs.spec import JobIdentity, WorkLimits
from skeleton.ai.runtime.operational_ai.durable_jobs.store import JobStore


def test_direct_store_enforces_configured_deadline_without_admission_adapter():
    store = make_store(WorkLimits(deadline_ms=900))
    with closing(store.db):
        with pytest.raises(JobDenied, match="submit-deadline-budget"):
            store.submit(make_spec(expires_ms=1901), now_ms=1000)
        assert store.submit(make_spec(expires_ms=1900), now_ms=1000) == "admitted"
        assert len(store.audit("job_1", OWNER)) == 1


def test_clock_regression_after_heartbeat_cannot_commit_fail_or_cancel():
    store = make_store()
    with closing(store.db):
        spec = make_spec()
        store.submit(spec, now_ms=1000)
        claim = store.claim("worker", now_ms=1000, lease_ms=500)
        assert store.heartbeat(claim, now_ms=1200, extend_ms=800) == 2000
        operations = (
            lambda: store.heartbeat(claim, now_ms=1199, extend_ms=1000),
            lambda: store.finish(claim, make_result(spec), now_ms=1199),
            lambda: store.fail(claim, now_ms=1199, code="ambiguous", ambiguous=True),
            lambda: store.cancel(spec.job_id, OWNER, now_ms=1199),
            lambda: store.submit(spec, now_ms=1199),
        )
        for operation in operations:
            with pytest.raises(JobDenied, match="job-clock-regressed"):
                operation()
            assert store.inspect(spec.job_id, OWNER)["state"] == "running"
        assert len(store.audit(spec.job_id, OWNER)) == 3
        assert store.finish(claim, make_result(spec), now_ms=1300) == "committed"


def test_replay_requires_original_request_prompt_worker_attempt_and_audit():
    store = make_store()
    with closing(store.db):
        spec = make_spec()
        store.submit(spec, now_ms=1000)
        claim = store.claim("worker", now_ms=1000)
        result = make_result(spec)
        assert store.finish(claim, result, now_ms=1001) == "committed"
        for forged in (
            replace(claim, request_id="other"),
            replace(claim, question="other"),
            replace(claim, worker_id="other"),
            replace(claim, attempt=2),
        ):
            with pytest.raises(JobDenied, match="claim"):
                store.finish(forged, result, now_ms=1002)
        assert store.finish(claim, result, now_ms=1002) == "replayed"
        assert len(store.audit(spec.job_id, OWNER)) == 3
        # Rehashing a receipt is insufficient without the recorded completion.
        altered = make_result(spec, text="Different result.")
        store.db.execute(
            "UPDATE ai_durable_jobs SET result_json=?,terminal_sha=? WHERE job_id=?",
            (encode(altered.to_record()), altered.digest, spec.job_id),
        )
        with pytest.raises(JobDenied, match="result-audit-binding"):
            store.receipt(spec.job_id, OWNER)
        with pytest.raises(JobDenied, match="job-audit-state-binding"):
            store.finish(claim, altered, now_ms=1002)


def test_rehashed_admitted_prompt_does_not_become_authoritative():
    store = make_store()
    with closing(store.db):
        spec = make_spec()
        store.submit(spec, now_ms=1000)
        altered = replace(spec, question="Unadmitted prompt.")
        store.db.execute(
            "UPDATE ai_durable_jobs SET payload_json=?,spec_sha=? WHERE job_id=?",
            (encode(altered.to_record()), altered.digest, spec.job_id),
        )
        for operation in (
            lambda: store.load_spec(spec.job_id, OWNER),
            lambda: store.claim("worker", now_ms=1000),
        ):
            with pytest.raises(JobDenied, match="job-admission-binding"):
                operation()


def test_deleted_dependency_edges_cannot_admit_child():
    store = make_store()
    with closing(store.db):
        parent = make_spec(name="parent")
        child = make_spec(name="child", dependencies=("parent",))
        store.submit(parent, now_ms=1000)
        store.submit(child, now_ms=1000)
        assert store.claim("worker", now_ms=1000, target_job_id="child") is None
        store.db.execute("DELETE FROM ai_job_deps WHERE job_id='child'")
        with pytest.raises(JobDenied, match="dependency-inventory-corrupt"):
            store.dependencies("child", OWNER)
        with pytest.raises(JobDenied, match="dependency-inventory-corrupt"):
            store.claim("worker", now_ms=1000, target_job_id="child")
        assert store.inspect("child", OWNER)["state"] == "pending"


def test_scoped_native_worker_never_claims_unrelated_job():
    store = make_store()
    with closing(store.db):
        outside = JobIdentity("alpha", "other", "session", "c"*64, "d"*64)
        store.submit(make_spec(name="outside", owner=outside), now_ms=1000)
        store.submit(make_spec(name="local"), now_ms=1000)
        calls = []

        def turn(**request):
            calls.append(request)
            return SimpleNamespace(
                session_id=request["session"], request_id=request["request_id"],
                model_digest=OWNER.model_sha256, tokenizer_digest=OWNER.tokenizer_sha256,
                text="Interface receipt only", prompt_tokens=2, generated_tokens=3,
            )

        service = SimpleNamespace(
            actor=SimpleNamespace(
                tenant=OWNER.tenant, user=OWNER.user,
                model_digest=OWNER.model_sha256, tokenizer_digest=OWNER.tokenizer_sha256,
            ),
            turn=turn,
        )
        bridge = NativeJobBridge(service, store)
        assert bridge.run_one("worker", clock_ms=lambda: 1000, target_job_id="outside") is None
        assert calls == []
        times = iter((1000, 1001))
        assert bridge.run_one("worker", clock_ms=lambda: next(times)) is not None
        assert [row["request_id"] for row in calls] == ["local"]
        assert store.inspect("outside", outside)["state"] == "pending"
        assert store.inspect("local", OWNER)["state"] == "completed"


def test_target_and_round_robin_reach_beyond_previous_candidate_limit():
    store = make_store(WorkLimits(queue_depth=2048, tenant_depth=1536, active_per_tenant=1))
    with closing(store.db):
        # Build a valid admitted inventory using the production transaction and
        # audit primitives. This deliberately crosses the former 1024-row cap.
        alpha = JobIdentity("alpha", "user", "session", "a"*64, "b"*64)
        zeta = JobIdentity("zeta", "user", "session", "a"*64, "b"*64)
        from skeleton.ai.runtime.operational_ai.durable_jobs.audit import append_event
        with store.tx.exclusive() as db:
            for index in range(1025):
                spec = make_spec(name=f"job_{index:04}", owner=alpha)
                db.execute(
                    """INSERT INTO ai_durable_jobs(
                    job_id,tenant,user_id,session_id,request_id,model_sha,tokenizer_sha,
                    payload_json,spec_sha,created_ms,expires_ms,next_eligible_ms,priority,
                    state,attempt,updated_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',0,?)""",
                    (spec.job_id, alpha.tenant, alpha.user, alpha.session, spec.request_id,
                     alpha.model_sha256, alpha.tokenizer_sha256, encode(spec.to_record()),
                     spec.digest, spec.created_ms, spec.expires_ms, spec.created_ms, 0, 1000),
                )
                append_event(db, spec.job_id, "submitted", {"spec_sha": spec.digest, "at": 1000})
        store.submit(make_spec(name="target", owner=zeta), now_ms=1000)
        db = store.db
        db.execute("UPDATE ai_job_state SET rr_tenant='alpha' WHERE singleton=1")
        assert store.claim("worker", now_ms=1000).job_id == "target"
        assert store.claim("worker2", now_ms=1000, target_job_id="job_1024").job_id == "job_1024"


def test_sqlite_row_factory_and_invalid_claim_input_fail_closed():
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        store = JobStore(db)
        spec = make_spec()
        assert store.submit(spec, now_ms=1000) == "admitted"
        claim = store.claim("worker", now_ms=1000)
        with pytest.raises(JobDenied, match="claim-token-format"):
            replace(claim, token="é" * 40)
        with pytest.raises(JobDenied, match="claim-type"):
            store.finish(object(), make_result(spec), now_ms=1001)
        assert store.finish(claim, make_result(spec), now_ms=1001) == "committed"
        assert store.receipt(spec.job_id, OWNER) == make_result(spec)
