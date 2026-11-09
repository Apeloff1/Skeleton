"""Jenkins S1-1 (#4128 review): deny-by-default realtime authorization.

Covers live delivery, ring replay, the ``job_id`` stream and the engine
execution-events filtered view.
"""

from __future__ import annotations

import pytest

from skeleton.realtime import RealtimeAuthError, RealtimeHub, sealed_principal_authorizer
from skeleton.realtime.envelope import RealtimeEvent
from skeleton.realtime.sinks import HubJobEventSink


def _hub(**kw):
    kw.setdefault("id_seed", 1000)
    kw.setdefault("authorizer", sealed_principal_authorizer)
    return RealtimeHub(**kw)


def _events(sub):
    return [f for f in sub.drain() if isinstance(f, RealtimeEvent) and f.type != "presence.snapshot"]


def test_default_authorizer_denies_everyone():
    hub = RealtimeHub(id_seed=1)
    with pytest.raises(RealtimeAuthError):
        hub.subscribe(["build"], principal="alice")
    with pytest.raises(RealtimeAuthError):
        hub.presence("join", client_id="tab", principal="alice")


def test_empty_principal_denied_even_with_permissive_authorizer():
    hub = RealtimeHub(id_seed=1, authorizer=lambda p, c: True)
    with pytest.raises(RealtimeAuthError):
        hub.subscribe(["build"], principal="")


def test_cross_tenant_live_events_are_not_delivered():
    hub = _hub()
    alice = hub.subscribe(["build", "agent"], principal="alice")
    bob = hub.subscribe(["build", "agent"], principal="bob")
    hub.publish("build", "build.progress", {"n": 1}, job_id="job-a", owner="alice", tenant="t1")
    hub.publish("agent", "agent.step", {"n": 2}, job_id="job-b", owner="bob", tenant="t2")
    # Raw actor identity does not establish the tenant. Tenant-scoped events
    # require a separately authorized execution/job grant.
    assert _events(alice) == []
    assert _events(bob) == []


def test_same_actor_in_multiple_tenants_requires_execution_grant_live_and_replay():
    hub = _hub()
    shared = hub.subscribe(["build"], principal="shared-actor")
    hub.publish("build", "build.progress", {"n": 1}, job_id="job-t1", owner="shared-actor", tenant="tenant-1")
    hub.publish("build", "build.progress", {"n": 2}, job_id="job-t2", owner="shared-actor", tenant="tenant-2")
    # Neither event is safe merely because the actor name matches.
    assert _events(shared) == []
    resumed = hub.subscribe(["build"], principal="shared-actor", cursor=1000)
    assert _events(resumed) == []
    # Only the separately authorized execution ID gives its scoped data back.
    granted = hub.subscribe(["build"], principal="service", job_id="job-t1", job_grant="job-t1", cursor=1000)
    assert [e.payload["n"] for e in _events(granted)] == [1]
    hub.publish("build", "build.progress", {"n": 3}, job_id="job-t1", owner="shared-actor", tenant="tenant-1")
    hub.publish("build", "build.progress", {"n": 4}, job_id="job-t2", owner="shared-actor", tenant="tenant-2")
    assert [e.payload["n"] for e in _events(granted)] == [3]
    assert _events(resumed) == []


def test_unscoped_owner_events_still_reach_matching_principal():
    hub = _hub()
    subscriber = hub.subscribe(["agent"], principal="alice", cursor=1000)
    hub.publish("agent", "agent.step", {"n": 1}, owner="alice")
    hub.publish("agent", "agent.step", {"n": 2}, owner="bob")
    assert [e.payload["n"] for e in _events(subscriber)] == [1]


def test_unowned_events_are_delivered_to_nobody_without_a_grant():
    hub = _hub()
    sub = hub.subscribe(["build"], principal="alice")
    hub.publish("build", "build.progress", {}, job_id="job-a")
    assert _events(sub) == []


def test_payload_cannot_spoof_owner():
    hub = _hub()
    mallory = hub.subscribe(["build"], principal="mallory")
    hub.publish("build", "build.progress", {"owner": "mallory", "actor_id": "mallory"}, owner="alice")
    assert _events(mallory) == []


def test_cross_tenant_replay_is_filtered():
    hub = _hub()
    hub.publish("build", "build.progress", {"n": 1}, owner="alice")
    hub.publish("build", "build.progress", {"n": 2}, owner="bob")
    hub.publish("build", "build.progress", {"n": 3}, owner="alice")
    bob = hub.subscribe(["build"], principal="bob", cursor=1000)
    alice = hub.subscribe(["build"], principal="alice", cursor=1000)
    assert [e.payload["n"] for e in _events(bob)] == [2]
    assert [e.payload["n"] for e in _events(alice)] == [1, 3]


def test_cross_tenant_job_id_stream_without_grant_sees_nothing():
    hub = _hub()
    hub.publish("build", "build.progress", {"n": 1}, job_id="job-a", owner="alice")
    snoop = hub.subscribe(["build"], principal="bob", job_id="job-a", cursor=1000)
    hub.publish("build", "build.progress", {"n": 2}, job_id="job-a", owner="alice")
    assert _events(snoop) == []


def test_job_grant_sees_job_events_live_and_replay_only_for_that_job():
    hub = _hub()
    hub.publish("build", "build.progress", {"n": 1}, job_id="job-a", owner="alice")
    hub.publish("build", "build.progress", {"n": 9}, job_id="job-z", owner="alice")
    svc = hub.subscribe(["build", "agent"], principal="backend-service", job_id="job-a", job_grant="job-a", cursor=1000)
    hub.publish("agent", "agent.step", {"n": 2}, job_id="job-a")
    hub.publish("agent", "agent.step", {"n": 8}, job_id="job-z")
    assert [e.payload["n"] for e in _events(svc)] == [1, 2]


def test_job_grant_must_match_job_id():
    hub = _hub()
    with pytest.raises(RealtimeAuthError):
        hub.subscribe(["build"], principal="svc", job_id="job-b", job_grant="job-a")


def test_access_metadata_is_pruned_with_the_ring():
    hub = _hub(replay_capacity=2)
    for i in range(5):
        hub.publish("build", "build.progress", {"i": i}, owner="alice")
    assert len(hub._access) == 2


def test_sink_binds_owner_from_envelope_not_payload():
    hub = _hub()
    alice = hub.subscribe(["build"], principal="alice")
    mallory = hub.subscribe(["build"], principal="mallory")
    sink = HubJobEventSink(hub)
    sink.publish({"type": "build.progress", "actor_id": "alice", "tenant_id": "t1", "payload": {"actor_id": "mallory"}})
    sink.publish({"type": "build.progress", "payload": {"owner": "mallory"}})
    # The scoped producer envelope cannot grant unfiltered tenant access.
    assert _events(alice) == []
    assert _events(mallory) == []


def test_presence_subscribers_and_snapshots_are_principal_private():
    hub = _hub()
    alice = hub.subscribe(["presence"], principal="alice")
    bob = hub.subscribe(["presence"], principal="bob")
    hub.presence("join", client_id="tab-a", principal="alice", meta={"private": "alice"})
    hub.presence("join", client_id="tab-b", principal="bob", meta={"private": "bob"})
    assert [e.payload["client_id"] for e in _events(alice)] == ["tab-a"]
    assert [e.payload["client_id"] for e in _events(bob)] == ["tab-b"]
    later = hub.subscribe(["presence"], principal="alice")
    snapshot = [e for e in later.drain() if e.type == "presence.snapshot"]
    assert len(snapshot) == 1
    assert [m["client_id"] for m in snapshot[0].payload["members"]] == ["tab-a"]
    assert [m["client_id"] for m in hub.presence_snapshot(principal="bob")["members"]] == ["tab-b"]
    hub.presence("leave", client_id="tab-b", principal="bob")
    assert _events(alice) == []


# -- HTTP layer --------------------------------------------------------------

fastapi = pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import skeleton.api.engine_routes as engine_routes  # noqa: E402
from skeleton.api.realtime_routes import router  # noqa: E402


@pytest.fixture()
def app_and_calls(monkeypatch):
    calls = []

    def fake_authorize(request, execution_id, *, actor_id, tenant_id, service=None, service_token=None):
        calls.append((execution_id, actor_id, tenant_id))
        if request.headers.get("authorization") != "Bearer svc-token":
            raise HTTPException(status_code=401, detail="engine service authentication failed")
        if (actor_id, tenant_id) != ("alice", "t1"):
            raise HTTPException(status_code=403, detail="engine execution belongs to a different actor or tenant")
        return request.headers["x-zaibatsu-attester"], {"events": []}

    monkeypatch.setattr(engine_routes, "authorize_execution_events", fake_authorize)
    app = fastapi.FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.realtime_hub = _hub()
    return app, calls



def test_presence_http_snapshot_is_scoped_to_verified_attester(app_and_calls):
    app, _calls = app_and_calls
    hub = app.state.realtime_hub
    hub.presence("join", client_id="private-a", principal="alice", meta={"note": "alice"})
    hub.presence("join", client_id="private-b", principal="bob", meta={"note": "bob"})
    client = TestClient(app)
    alice = client.get("/api/v1/presence?scope=app", headers={"x-zaibatsu-attester": "alice"})
    bob = client.get("/api/v1/presence?scope=app", headers={"x-zaibatsu-attester": "bob"})
    missing = client.get("/api/v1/presence?scope=app")
    assert alice.status_code == bob.status_code == 200
    assert [m["client_id"] for m in alice.json()["members"]] == ["private-a"]
    assert [m["client_id"] for m in bob.json()["members"]] == ["private-b"]
    assert missing.status_code == 401



def test_job_id_stream_requires_actor_and_tenant(app_and_calls):
    app, calls = app_and_calls
    r = TestClient(app).get("/api/v1/events?job_id=job-a", headers={"x-zaibatsu-attester": "bob"})
    assert r.status_code == 422 and calls == []


def test_job_id_stream_runs_engine_checks_and_denies_cross_tenant(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    no_token = client.get("/api/v1/events?job_id=job-a&actor_id=alice&tenant_id=t1", headers={"x-zaibatsu-attester": "bob"})
    assert no_token.status_code == 401
    wrong = client.get(
        "/api/v1/events?job_id=job-a&actor_id=bob&tenant_id=t2",
        headers={"x-zaibatsu-attester": "backend-service", "authorization": "Bearer svc-token"},
    )
    assert wrong.status_code == 403
    assert calls[-1] == ("job-a", "bob", "t2")
    assert app.state.realtime_hub._subs == {}


def test_job_id_stream_service_identity_following_engine_rules_gets_job_events(app_and_calls):
    app, _calls = app_and_calls
    hub = app.state.realtime_hub
    hub.publish("build", "build.progress", {"n": 1}, job_id="job-a", owner="alice")
    hub.publish("build", "build.progress", {"n": 2}, job_id="job-b", owner="alice")
    r = TestClient(app).get(
        "/api/v1/events?channels=build&job_id=job-a&actor_id=alice&tenant_id=t1&cursor=1000&max_events=1",
        headers={"x-zaibatsu-attester": "backend-service", "authorization": "Bearer svc-token"},
    )
    assert r.status_code == 200
    assert '"n":1' in r.text and '"n":2' not in r.text


def test_events_without_job_id_only_stream_own_events(app_and_calls):
    app, _calls = app_and_calls
    hub = app.state.realtime_hub
    hub.publish("build", "build.progress", {"n": 1}, owner="bob")
    hub.publish("build", "build.progress", {"n": 2}, owner="alice")
    r = TestClient(app).get(
        "/api/v1/events?channels=build&cursor=1000&max_events=1",
        headers={"x-zaibatsu-attester": "alice"},
    )
    assert r.status_code == 200
    assert '"n":2' in r.text and '"n":1' not in r.text


def test_execution_view_denies_empty_principal(app_and_calls):
    from starlette.requests import Request

    from skeleton.api.realtime_routes import execution_stream_or_none

    app, _ = app_and_calls
    scope = {"type": "http", "method": "GET", "path": "/x", "headers": [(b"accept", b"text/event-stream")], "query_string": b"", "app": app}
    with pytest.raises(HTTPException) as exc:
        execution_stream_or_none(Request(scope), "exec-1", principal="")
    assert exc.value.status_code == 401
