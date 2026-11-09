"""Bounded, truthful process-local swarm job admission and persistence contracts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import databases
from core import swarm_scheduler as scheduler
from routes import swarm_planner as api


@pytest.fixture(autouse=True)
def isolated_job_registry(monkeypatch):
    monkeypatch.setattr(scheduler, "_JOBS", {})
    monkeypatch.setattr(scheduler, "_ACTIVE_JOBS", set())


def _fake_thread_factory(*, target, daemon):
    class FakeThread:
        def start(self):
            target()
    return FakeThread()


def _fake_result(**_kwargs):
    return {
        "plan_hash": "receipt",
        "coverage": {"all_covered": True},
        "verification": {"valid": True},
        "execution": {"execution_complete": True},
        "participation": {"total_seats": 2},
    }


def test_ephemeral_job_runs_without_database_and_finishes(monkeypatch):
    monkeypatch.setattr(databases, "get_sync_db",
                        lambda: (_ for _ in ()).throw(AssertionError("unexpected DB")))
    monkeypatch.setattr(scheduler, "execute_schedule", _fake_result)
    monkeypatch.setattr(scheduler.threading, "Thread", _fake_thread_factory)
    job_id = scheduler.start_async("execute", build_id="b", phases=["a"], persist=False)
    assert len(job_id) == 16
    assert scheduler.get_job(job_id)["status"] == "done"
    assert scheduler.get_job(job_id)["result"]["execution"]["execution_complete"] is True
    assert not scheduler._ACTIVE_JOBS


def test_durable_job_requires_acknowledged_status_for_acceptance(monkeypatch):
    writes = []
    class Collection:
        def update_one(self, query, update, *, upsert):
            writes.append((query, update, upsert))
            return SimpleNamespace(acknowledged=True)

    monkeypatch.setattr(databases, "get_sync_db",
                        lambda: {"swarm_schedule_jobs": Collection()})
    monkeypatch.setattr(scheduler, "execute_schedule", _fake_result)
    monkeypatch.setattr(scheduler.threading, "Thread", _fake_thread_factory)
    job_id = scheduler.start_async("execute", build_id="b", phases=["a"], persist=True)
    assert scheduler.get_job(job_id)["status"] == "done"
    assert len(writes) == 2
    assert writes[0][1]["$set"]["status"] == "running"
    assert writes[1][1]["$set"]["status"] == "done"
    assert not scheduler._ACTIVE_JOBS


def test_unacknowledged_admission_never_starts_a_background_job(monkeypatch):
    class Collection:
        def update_one(self, *_args, **_kwargs):
            return SimpleNamespace(acknowledged=False)

    monkeypatch.setattr(databases, "get_sync_db",
                        lambda: {"swarm_schedule_jobs": Collection()})
    monkeypatch.setattr(scheduler.threading, "Thread", lambda **_kw:
                        (_ for _ in ()).throw(AssertionError("worker was started")))
    with pytest.raises(RuntimeError, match="not durably recorded"):
        scheduler.start_async("execute", build_id="b", phases=["a"], persist=True)
    assert not scheduler._ACTIVE_JOBS
    assert all(row["status"] == "error" for row in scheduler._JOBS.values())


def test_unknown_job_kind_does_not_fallback_to_execute():
    with pytest.raises(ValueError, match="unsupported"):
        scheduler.start_async("dangerous-future-kind", build_id="b", persist=False)
    assert not scheduler._ACTIVE_JOBS


@pytest.mark.parametrize("rounds", [-1, 0, True, 11, float("nan")])
def test_invalid_rounds_rejected_before_admission(rounds):
    with pytest.raises(ValueError, match="rounds"):
        scheduler.start_async("execute", build_id="b", rounds=rounds, persist=False)
    assert not scheduler._ACTIVE_JOBS


def test_concurrency_limit_fences_unbounded_threads():
    scheduler._ACTIVE_JOBS.update(f"{number:016x}" for number in range(scheduler.MAX_PARALLEL_ASYNC_JOBS))
    with pytest.raises(RuntimeError, match="capacity"):
        scheduler.start_async("execute", build_id="b", persist=False)
    assert len(scheduler._ACTIVE_JOBS) == scheduler.MAX_PARALLEL_ASYNC_JOBS


def test_thread_start_failure_releases_capacity(monkeypatch):
    class BrokenThread:
        def __init__(self, *, target, daemon):
            pass
        def start(self):
            raise RuntimeError("thread limit")

    monkeypatch.setattr(scheduler.threading, "Thread", BrokenThread)
    with pytest.raises(RuntimeError, match="could not start"):
        scheduler.start_async("execute", build_id="b", persist=False)
    assert not scheduler._ACTIVE_JOBS
    assert all(row["status"] == "error" for row in scheduler._JOBS.values())


def test_job_snapshots_have_a_bounded_retention_policy():
    scheduler._JOBS.update({
        f"{i:016x}": {"job_id": f"{i:016x}", "status": "done", "finished_at": float(i)}
        for i in range(280)
    })
    scheduler._set_job("ffffffffffffffff", status="done", durable=False, finished_at=300)
    assert len(scheduler._JOBS) <= scheduler.MAX_RETAINED_JOB_SNAPSHOTS


def test_history_outage_is_not_confused_with_unknown_job(monkeypatch):
    monkeypatch.setattr(databases, "get_sync_db",
                        lambda: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(RuntimeError, match="history unavailable"):
        scheduler.get_job("abcdef0123456789")
    assert scheduler.get_job("not-a-hex-id") is None


def test_async_api_propagates_admission_outage_as_503(monkeypatch):
    monkeypatch.setattr(scheduler, "start_async", lambda *_a, **_kw:
                        (_ for _ in ()).throw(RuntimeError("storage unavailable")))
    with pytest.raises(HTTPException) as error:
        api.execute_async(api.ExecuteReq(build_id="b", persist=True))
    assert error.value.status_code == 503
    with pytest.raises(HTTPException) as error:
        api.execute_build_async(api.BuildReq(build_id="b"))
    assert error.value.status_code == 503
