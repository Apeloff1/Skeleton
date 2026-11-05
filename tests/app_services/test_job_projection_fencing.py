"""Interleavings that must not resurrect cancelled or superseded builds."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.app_services.container import AppServices
from skeleton.contracts.projects import ProjectBrief
from skeleton.persistence.app_foundation.projects_v1 import ProjectsV1Store


def _project_job(service, *, max_attempts=1):
    actor = service.auth.register("projection@example.test", "a-strong-test-password").user_id
    project, _ = ProjectsV1Store(service.db).create(actor, "tenant", ProjectBrief(title="Projection game"))
    handle = service.jobs.enqueue("game.build", {"brief": "test"}, actor_id=actor, tenant_id="tenant",
                                  project_id=project.project_id, max_attempts=max_attempts)
    return handle


def test_cancel_between_claim_and_projection_never_starts_handler(tmp_path, monkeypatch):
    service = AppServices.open(tmp_path)
    try:
        handle = _project_job(service)
        observed = []
        service.jobs.register_handler("game.build", lambda ctx, payload: observed.append(True) or {})
        original_claim = service.jobs.queue.claim
        def cancel_after_claim(*args, **kwargs):
            job = original_claim(*args, **kwargs)
            assert service.jobs.cancel(job.job_id)
            return job
        monkeypatch.setattr(service.jobs.queue, "claim", cancel_after_claim)
        assert service.jobs.run_once("worker") == handle.job_id
        assert observed == []
        assert service.jobs.get_status(handle.job_id).status == "cancelled"
        assert service.builds.get_build(handle.execution_id).status == "cancelled"
    finally:
        service.close()


def test_stale_failed_attempt_cannot_overwrite_new_worker_projection(tmp_path):
    service = AppServices.open(tmp_path)
    try:
        clock = [1000.0]
        service.jobs.clock = service.jobs.queue.clock = lambda: clock[0]
        handle = _project_job(service, max_attempts=2)
        assert service.jobs.queue.claim("worker-1", kinds=["game.build"], lease_s=100)
        old = service.jobs._row(handle.job_id)
        assert service.jobs._sync_build(old, "running", worker_id="worker-1")
        service.jobs.queue.fail(handle.job_id, "worker-1", "first attempt failed")
        clock[0] += 10
        assert service.jobs.queue.claim("worker-2", kinds=["game.build"], lease_s=100)
        assert not service.jobs._sync_build(old, "queued", error="first attempt failed")
        assert service.jobs.get_status(handle.job_id).status == "running"
        assert service.builds.get_build(handle.execution_id).status == "running"
        current = service.jobs._row(handle.job_id)
        assert service.jobs._sync_build(current, "running", worker_id="worker-2")
        service.jobs.queue.complete(handle.job_id, "worker-2", {"ok": True})
        assert service.jobs._sync_build(current, "succeeded", result={"ok": True})
        assert service.builds.get_build(handle.execution_id).status == "succeeded"
    finally:
        service.close()


@pytest.mark.parametrize("fails", [False, True])
def test_terminal_queue_and_build_projection_commit_or_roll_back_together(tmp_path, fails):
    service = AppServices.open(tmp_path)
    try:
        clock = [1000.0]
        service.jobs.clock = service.jobs.queue.clock = lambda: clock[0]
        handle = _project_job(service)
        def run(ctx, payload):
            if fails:
                raise ValueError("build failed")
            return {"ok": True}
        service.jobs.register_handler("game.build", run)
        target = "failed" if fails else "succeeded"
        with service.db.tx() as c:
            c.execute("CREATE TRIGGER fail_projection BEFORE UPDATE OF status ON builds "
                      f"WHEN NEW.status='{target}' BEGIN SELECT RAISE(ABORT, 'injected fault'); END")
        with pytest.raises(sqlite3.IntegrityError, match="injected fault"):
            service.jobs.run_once("worker-1")
        assert service.jobs.get_status(handle.job_id).status == "running"
        assert service.builds.get_build(handle.execution_id).status == "running"
        assert service.jobs.get_result(handle.job_id).result is None
        assert service.db.query("SELECT error_code FROM jobs WHERE job_id=?", (handle.job_id,))[0][0] == ""

        # The interrupted worker's lease can be recovered after the storage
        # fault clears. Both authoritative records reach the same terminal state.
        with service.db.tx() as c:
            c.execute("DROP TRIGGER fail_projection")
        clock[0] += 3000
        assert service.jobs.run_once("worker-2") == handle.job_id
        expected = "failed" if fails else "succeeded"
        assert service.jobs.get_status(handle.job_id).status == expected
        assert service.builds.get_build(handle.execution_id).status == expected
        if fails:
            assert service.jobs.get_result(handle.job_id).error["code"] == "handler_error"
        else:
            assert service.jobs.get_result(handle.job_id).result == {"ok": True}
    finally:
        service.close()


def test_cancel_fences_work_even_if_build_projection_disappeared(tmp_path):
    service = AppServices.open(tmp_path)
    try:
        handle = _project_job(service)
        # Simulate a damaged or administratively removed projection: the user
        # must still be able to stop execution without updating another build.
        with service.db.tx() as c:
            c.execute("DELETE FROM builds WHERE build_id=?", (handle.execution_id,))
        assert service.jobs.cancel(handle.job_id)
        assert service.jobs.get_status(handle.job_id).status == "cancelled"
    finally:
        service.close()
