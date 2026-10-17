import pytest

from skeleton.app_services import job_api
from skeleton.app_services.job_api import IdempotencyMismatch, JobService, JobWorker
from skeleton.persistence.app_foundation.db import Database


class Sink:
    def __init__(self):
        self.events = []

    def publish(self, e):
        self.events.append(e)


@pytest.fixture
def clock():
    return [1000.0]


@pytest.fixture
def svc(clock):
    db = Database()
    db.migrate()
    s = JobService(db, publisher=Sink(), visibility_timeout_s=30, clock=lambda: clock[0])
    return s


def test_enqueue_status_result(svc):
    svc.register_handler("echo", lambda ctx, p: (ctx.progress(0.5, "half"), {"echo": p["x"]})[1])
    h = svc.enqueue("echo", {"x": 1}, actor_id="u1", tenant_id="t1", correlation_id="c1")
    assert h.status == "queued" and h.execution_id == h.job_id and not h.replayed
    st = svc.get_status(h.job_id)
    assert st.status == "queued" and st.attempts == 0 and st.started_at is None
    assert svc.get_result(h.job_id).result is None
    assert JobWorker(svc, worker_id="w").drain() == 1
    st = svc.get_status(h.job_id)
    assert st.status == "succeeded" and st.progress == 1.0 and st.message == "half" and st.started_at
    r = svc.get_result(h.job_id)
    assert r.status == "succeeded" and r.result == {"echo": 1} and r.error is None
    types = [e["type"] for e in svc.publisher.events]
    assert types == ["build.started", "build.progress", "build.completed"]
    assert all(e["job_id"] == h.job_id and e["correlation_id"] == "c1" for e in svc.publisher.events)


def test_long_job_with_heartbeats_survives_past_lease(svc, clock):
    seen = {}

    def long(ctx, p):
        # Lease = max(visibility 30, timeout 60 + grace 120) = 180s. Run ~540s with heartbeats.
        for _ in range(9):
            clock[0] += 60
            ctx.heartbeat()
            # another worker must not be able to steal it mid-run
            seen.setdefault("steal", []).append(svc.queue.claim("thief", kinds=["long"], lease_s=1))
        return {"ok": True}

    svc.register_handler("long", long)
    h = svc.enqueue("long", {}, actor_id="u", tenant_id="t", timeout_s=600)
    JobWorker(svc, worker_id="w1").drain()
    assert all(x is None for x in seen["steal"])
    assert svc.get_result(h.job_id).result == {"ok": True}
    assert svc.get_status(h.job_id).attempts == 1


def test_job_without_heartbeat_past_lease_is_reclaimable(svc, clock):
    h = svc.enqueue("k", {}, actor_id="u", tenant_id="t", timeout_s=10)
    svc.register_handler("k", lambda ctx, p: {})
    job = svc.queue.claim("dead-worker", kinds=["k"], lease_s=20)
    clock[0] += 21
    assert svc.queue.claim("w2", kinds=["k"], lease_s=20).job_id == job.job_id == h.job_id


def test_timeout_and_failure_give_error_results(svc, clock):
    def slow(ctx, p):
        clock[0] += 11
        ctx.heartbeat()
        return {}

    svc.register_handler("slow", slow)
    svc.register_handler("boom", lambda ctx, p: 1 / 0)
    t = svc.enqueue("slow", {}, actor_id="u", tenant_id="t", timeout_s=10)
    b = svc.enqueue("boom", {}, actor_id="u", tenant_id="t")
    JobWorker(svc).drain()
    rt, rb = svc.get_result(t.job_id), svc.get_result(b.job_id)
    assert rt.status == "failed" and rt.error["code"] == "timeout" and rt.result is None
    assert rb.status == "failed" and rb.error["code"] == "handler_error" and "ZeroDivisionError" in rb.error["message"]
    assert "build.failed" in [e["type"] for e in svc.publisher.events]


def test_idempotency_replay_and_mismatch(svc):
    a = svc.enqueue("k", {"t": 1}, actor_id="u", tenant_id="t", idempotency_key="key")
    b = svc.enqueue("k", {"t": 1}, actor_id="u", tenant_id="t", idempotency_key="key")
    assert b.job_id == a.job_id and b.replayed
    with pytest.raises(IdempotencyMismatch):
        svc.enqueue("k", {"t": 2}, actor_id="u", tenant_id="t", idempotency_key="key")
    c = svc.enqueue("k", {"t": 1}, actor_id="other", tenant_id="t", idempotency_key="key")
    assert c.job_id != a.job_id  # scoped per tenant/actor/kind


def test_cancel_and_validation(svc):
    h = svc.enqueue("k", {}, actor_id="u", tenant_id="t")
    assert svc.cancel(h.job_id) and svc.get_status(h.job_id).status == "cancelled"
    assert svc.get_result(h.job_id).error["code"] == "cancelled"
    with pytest.raises(ValueError):
        svc.enqueue("k", {}, actor_id="", tenant_id="t")
    with pytest.raises(KeyError):
        svc.get_status("nope")


def test_module_level_api_and_background_worker(svc):
    import time as _t
    real = JobService(svc.db)
    job_api.set_job_service(real)
    try:
        job_api.register_handler("bg", lambda ctx, p: {"done": True})
        h = job_api.enqueue("bg", {}, actor_id="u", tenant_id="t")
        w = job_api.start_worker(poll_s=0.05)
        assert job_api.start_worker() is w and w.running
        deadline = _t.time() + 5
        while job_api.get_status(h.job_id).status != "succeeded" and _t.time() < deadline:
            _t.sleep(0.05)
        assert job_api.get_result(h.job_id).result == {"done": True}
    finally:
        job_api.set_job_service(None)
