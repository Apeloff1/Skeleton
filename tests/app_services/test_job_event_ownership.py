"""Job event envelopes carry top-level actor_id/tenant_id (realtime S1-1, #4139).

The hub sink binds owner/tenant ONLY from top-level envelope fields, never from
payload. These tests pin the producer side and the end-to-end delivery rules.
"""
from __future__ import annotations

import pytest

from skeleton.app_services.events import make_envelope
from skeleton.app_services.job_api import JobService, JobWorker
from skeleton.app_services.jobs import BuildJobRunner, BuildService, SqliteJobQueue
from skeleton.persistence.app_foundation.db import Database
from skeleton.realtime import RealtimeHub, sealed_principal_authorizer
from skeleton.realtime.envelope import RealtimeEvent
from skeleton.realtime.sinks import HubJobEventSink

OWNERSHIP = ("actor_id", "tenant_id", "owner", "principal", "tenant")


class Sink:
    def __init__(self):
        self.events = []

    def publish(self, e):
        self.events.append(e)


def _hub():
    return RealtimeHub(id_seed=1000, authorizer=sealed_principal_authorizer)


def _events(sub):
    return [f for f in sub.drain() if isinstance(f, RealtimeEvent) and f.type != "presence.snapshot"]


def _db():
    db = Database()
    db.migrate()
    return db


# -- envelope shape -----------------------------------------------------------

def test_make_envelope_top_level_ownership_and_stripped_payload():
    env = make_envelope("build", "build.progress",
                        {"n": 1, "actor_id": "mallory", "tenant_id": "evil", "owner": "x", "principal": "y", "tenant": "z"},
                        job_id="j1", actor_id="alice", tenant_id="t1")
    assert env["actor_id"] == "alice" and env["tenant_id"] == "t1"
    assert env["payload"] == {"n": 1}
    assert {"v", "id", "ts", "channel", "type", "payload", "job_id"} <= set(env)


def test_make_envelope_v1_compatible_without_ownership():
    env = make_envelope("build", "build.log", {"line": "x"})
    assert set(env) == {"v", "id", "ts", "channel", "type", "payload"}


def test_job_service_envelopes_carry_submitter_not_in_payload():
    svc = JobService(_db(), publisher=Sink(), visibility_timeout_s=30)
    svc.register_handler("echo", lambda ctx, p: (ctx.progress(0.5, "half"), {"ok": True})[1])
    h = svc.enqueue("echo", {"x": 1, "actor_id": "mallory"}, actor_id="alice", tenant_id="t1")
    JobWorker(svc, worker_id="w").drain()
    evs = svc.publisher.events
    assert [e["type"] for e in evs] == ["build.started", "build.progress", "build.completed"]
    for e in evs:
        assert e["actor_id"] == "alice" and e["tenant_id"] == "t1" and e["job_id"] == h.job_id
        assert not set(OWNERSHIP) & set(e["payload"])


def test_build_job_runner_envelopes_carry_submitter():
    db = _db()
    from skeleton.persistence.app_foundation.repositories import SqliteBuildRepository
    builds = SqliteBuildRepository(db)
    queue = SqliteJobQueue(db)
    sink = Sink()
    pid = _project(db)
    BuildService(builds, queue).submit(pid, target="web", actor_id="alice", tenant_id="t1")
    BuildJobRunner(queue, builds, lambda ctx: (ctx.log("hi"), {"ok": 1})[1], publisher=sink).drain()
    assert [e["type"] for e in sink.events] == ["build.started", "build.log", "build.completed"]
    for e in sink.events:
        assert (e["actor_id"], e["tenant_id"]) == ("alice", "t1")
        assert not set(OWNERSHIP) & set(e["payload"])


def _project(db):
    from skeleton.persistence.app_foundation.repositories import SqliteProjectRepository, SqliteUserRepository
    user = SqliteUserRepository(db).create_user("o@example.test", "Owner", "x")
    return SqliteProjectRepository(db).create_project(user.user_id, "p").project_id


# -- end to end through the hub ----------------------------------------------

def _run_through_hub(hub, *, actor_id, tenant_id):
    svc = JobService(_db(), publisher=HubJobEventSink(hub), visibility_timeout_s=30)
    svc.register_handler("game.build", lambda ctx, p: (ctx.progress(0.5), {"ok": True})[1])
    h = svc.enqueue("game.build", {}, actor_id=actor_id, tenant_id=tenant_id)
    JobWorker(svc, worker_id="w").drain()
    return h.job_id


def test_hub_binds_owner_and_tenant_from_job_envelopes():
    hub = _hub()
    _run_through_hub(hub, actor_id="alice", tenant_id="t1")
    access = set(hub._access.values())
    assert {(a.owner, a.tenant) for a in access} == {("alice", "t1")}


def test_owner_without_tenant_receives_own_builds_on_plain_subscription():
    hub = _hub()
    alice = hub.subscribe(["build"], principal="alice")
    bob = hub.subscribe(["build"], principal="bob")
    # JobService requires tenant_id; BuildService may submit actor-only builds.
    sink = HubJobEventSink(hub)
    sink.publish(make_envelope("build", "build.progress", {"n": 1}, job_id="j1", actor_id="alice"))
    assert [e.type for e in _events(alice)] == ["build.progress"]
    assert _events(bob) == []


def test_tenant_scoped_builds_need_job_grant_and_never_cross():
    hub = _hub()
    plain_alice = hub.subscribe(["build"], principal="alice")
    job_id = _run_through_hub(hub, actor_id="alice", tenant_id="t1")
    granted = hub.subscribe(["build"], principal="alice", job_id=job_id, job_grant=job_id, cursor=1000)
    other_tenant = hub.subscribe(["build"], principal="alice", job_id="other-job", job_grant="other-job", cursor=1000)
    other_actor = hub.subscribe(["build"], principal="bob", cursor=1000)
    got = _events(granted)
    assert [e.type for e in got] == ["build.started", "build.progress", "build.completed"]
    assert all(e.job_id == job_id for e in got)
    # #4139 policy: tenant-scoped events are not delivered on an unfiltered stream.
    assert _events(plain_alice) == []
    assert _events(other_tenant) == []
    assert _events(other_actor) == []


fastapi = pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import skeleton.api.engine_routes as engine_routes  # noqa: E402
from skeleton.api.realtime_routes import router  # noqa: E402


@pytest.fixture()
def app(monkeypatch):
    def fake_authorize(request, execution_id, *, actor_id, tenant_id, service=None, service_token=None):
        if (actor_id, tenant_id) != ("alice", "t1"):
            raise HTTPException(status_code=403, detail="different actor or tenant")
        return request.headers["x-zaibatsu-attester"], {"events": []}

    monkeypatch.setattr(engine_routes, "authorize_execution_events", fake_authorize)
    a = fastapi.FastAPI()
    a.include_router(router, prefix="/api/v1")
    a.state.realtime_hub = _hub()
    return a


def test_http_job_grant_stream_delivers_owner_build_events(app):
    job_id = _run_through_hub(app.state.realtime_hub, actor_id="alice", tenant_id="t1")
    client = TestClient(app)
    ok = client.get(f"/api/v1/events?channels=build&job_id={job_id}&actor_id=alice&tenant_id=t1&cursor=1000&max_events=3",
                    headers={"x-zaibatsu-attester": "alice"})
    assert ok.status_code == 200
    assert "build.started" in ok.text and "build.completed" in ok.text
    cross = client.get(f"/api/v1/events?channels=build&job_id={job_id}&actor_id=bob&tenant_id=t2&cursor=1000&max_events=1",
                       headers={"x-zaibatsu-attester": "bob"})
    assert cross.status_code == 403


def test_http_plain_stream_other_actor_sees_nothing(app):
    hub = app.state.realtime_hub
    HubJobEventSink(hub).publish(make_envelope("build", "build.progress", {"n": 7}, job_id="j9", actor_id="alice"))
    HubJobEventSink(hub).publish(make_envelope("build", "build.progress", {"n": 8}, job_id="j8", actor_id="bob"))
    r = TestClient(app).get("/api/v1/events?channels=build&cursor=1000&max_events=1",
                            headers={"x-zaibatsu-attester": "alice"})
    assert r.status_code == 200 and '"n":7' in r.text and '"n":8' not in r.text


# -- follow-ups: owner cache, same-tx ownership, agent.* ownership -----------

def test_build_job_runner_caches_owner_per_job(monkeypatch):
    db = _db()
    from skeleton.persistence.app_foundation.repositories import SqliteBuildRepository
    builds, queue, sink = SqliteBuildRepository(db), SqliteJobQueue(db), Sink()
    BuildService(builds, queue).submit(_project(db), actor_id="alice", tenant_id="t1")
    runner = BuildJobRunner(queue, builds, lambda ctx: ([ctx.log(str(i)) for i in range(5)], {})[1], publisher=sink)
    selects = []
    real = db.query
    monkeypatch.setattr(db, "query", lambda sql, args=(): (selects.append(sql) if "actor_id, tenant_id" in sql else None, real(sql, args))[1])
    runner.drain()
    assert len(sink.events) == 7 and len(selects) == 1


def test_build_submit_records_owner_atomically_with_enqueue():
    db = _db()
    queue = SqliteJobQueue(db)
    job = queue.enqueue("game.build", {}, actor_id="alice", tenant_id="t1")
    row = db.query("SELECT actor_id, tenant_id FROM jobs WHERE job_id=?", (job.job_id,))[0]
    assert (row["actor_id"], row["tenant_id"]) == ("alice", "t1")


def test_agent_envelopes_carry_owner_top_level_not_payload():
    from skeleton.app_services.jobs import AgentEventEmitter
    sink = Sink()
    ag = AgentEventEmitter(sink, actor_id="alice", tenant_id="t1", job_id="j1")
    ag.started("coder")
    ag.step("coder", "plan", {"actor_id": "mallory", "tenant": "evil"})
    ag.completed("coder")
    assert [e["type"] for e in sink.events] == ["agent.started", "agent.step", "agent.completed"]
    for e in sink.events:
        assert (e["actor_id"], e["tenant_id"], e["job_id"]) == ("alice", "t1", "j1")
        assert not set(OWNERSHIP) & set(e["payload"])


def test_agent_emitter_unowned_default_keeps_v1_shape():
    from skeleton.app_services.jobs import AgentEventEmitter
    sink = Sink()
    AgentEventEmitter(sink).started("coder")
    assert set(sink.events[0]) == {"v", "id", "ts", "channel", "type", "payload"}


def test_job_context_agent_events_delivered_to_grant_holder_only():
    hub = _hub()
    svc = JobService(_db(), publisher=HubJobEventSink(hub), visibility_timeout_s=30)

    def handler(ctx, p):
        ag = ctx.agent_events()
        ag.started("coder")
        ag.step("coder", "plan")
        ag.completed("coder")
        return {}

    svc.register_handler("game.build", handler)
    h = svc.enqueue("game.build", {}, actor_id="alice", tenant_id="t1")
    JobWorker(svc, worker_id="w").drain()
    agent_access = {(a.owner, a.tenant) for seq, a in hub._access.items()}
    assert agent_access == {("alice", "t1")}
    granted = hub.subscribe(["agent"], principal="alice", job_id=h.job_id, job_grant=h.job_id, cursor=1000)
    other_job = hub.subscribe(["agent"], principal="alice", job_id="j-other", job_grant="j-other", cursor=1000)
    other_actor = hub.subscribe(["agent"], principal="bob", cursor=1000)
    got = _events(granted)
    assert [e.type for e in got] == ["agent.started", "agent.step", "agent.completed"]
    assert all(e.job_id == h.job_id for e in got)
    assert _events(other_job) == [] and _events(other_actor) == []


def test_build_context_agent_events_owned_and_cross_tenant_denied_over_http(app):
    hub = app.state.realtime_hub
    db = _db()
    from skeleton.persistence.app_foundation.repositories import SqliteBuildRepository
    builds, queue = SqliteBuildRepository(db), SqliteJobQueue(db)
    b = BuildService(builds, queue).submit(_project(db), actor_id="alice", tenant_id="t1")
    BuildJobRunner(queue, builds, lambda ctx: (ctx.agent_events().started("coder"), {})[1],
                   publisher=HubJobEventSink(hub)).drain()
    client = TestClient(app)
    ok = client.get(f"/api/v1/events?channels=agent&job_id={b.job_id}&actor_id=alice&tenant_id=t1&cursor=1000&max_events=1",
                    headers={"x-zaibatsu-attester": "alice"})
    assert ok.status_code == 200 and "agent.started" in ok.text
    cross = client.get(f"/api/v1/events?channels=agent&job_id={b.job_id}&actor_id=bob&tenant_id=t2&cursor=1000&max_events=1",
                       headers={"x-zaibatsu-attester": "bob"})
    assert cross.status_code == 403
