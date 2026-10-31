"""HTTP-level hardening: verified-tenant streams, presence limits, engine-token fallback, /metrics."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api import engine_routes  # noqa: E402
from skeleton.api.realtime_routes import router  # noqa: E402
from skeleton.realtime import RealtimeHub  # noqa: E402
from skeleton.realtime.hub import sealed_principal_authorizer  # noqa: E402

SVC = {"x-zaibatsu-attester": "backend-service", "authorization": "Bearer svc-token"}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(engine_routes, "_engine_service_token", lambda: "svc-token")
    a = fastapi.FastAPI()
    a.include_router(router, prefix="/api/v1")
    a.state.realtime_hub = RealtimeHub(id_seed=1000, authorizer=sealed_principal_authorizer)
    return a


def test_verified_tenant_plain_stream_gets_own_tenant_builds(app):
    hub = app.state.realtime_hub
    hub.publish("build", "build.progress", {"n": 1}, owner="alice", tenant="t1")
    hub.publish("build", "build.progress", {"n": 2}, owner="alice", tenant="t2")
    r = TestClient(app).get("/api/v1/events?channels=build&actor_id=alice&tenant_id=t1&cursor=1000&max_events=1", headers=SVC)
    assert r.status_code == 200 and '"n":1' in r.text and '"n":2' not in r.text


def test_tenant_claim_without_service_token_is_401(app):
    r = TestClient(app).get("/api/v1/events?channels=build&actor_id=alice&tenant_id=t1", headers={"x-zaibatsu-attester": "alice"})
    assert r.status_code == 401 and app.state.realtime_hub._subs == {}


def test_tenant_claim_needs_both_actor_and_tenant(app):
    r = TestClient(app).get("/api/v1/events?channels=build&tenant_id=t1", headers=SVC)
    assert r.status_code == 422


def test_engine_service_fallback_without_configured_token_denies(monkeypatch):
    def unconfigured():
        raise HTTPException(status_code=503, detail="engine service authentication is not configured")

    monkeypatch.setattr(engine_routes, "_engine_service_token", unconfigured)
    a = fastapi.FastAPI()
    a.include_router(router, prefix="/api/v1")
    a.state.realtime_hub = RealtimeHub(id_seed=1000, authorizer=sealed_principal_authorizer)
    client = TestClient(a)
    for url in ("/api/v1/events?actor_id=alice&tenant_id=t1", "/api/v1/events?job_id=j&actor_id=alice&tenant_id=t1"):
        r = client.get(url, headers=SVC)
        assert r.status_code in (401, 403, 503), url
    assert a.state.realtime_hub._subs == {}


def test_presence_http_rejects_2mb_meta_with_413(app):
    r = TestClient(app).post(
        "/api/v1/presence",
        json={"action": "join", "client_id": "c1", "meta": {"blob": "x" * (2 * 1024 * 1024)}},
        headers={"x-zaibatsu-attester": "alice"},
    )
    assert r.status_code == 413 and app.state.realtime_hub._presence == {}


def test_public_metrics_surface_hides_realtime_series(monkeypatch):
    from skeleton.api.routes import _without_public_realtime

    snap = {"counters": {"realtime.connect_attempts": 1, "http.requests": 2}, "gauges": {}, "histograms": {}}
    monkeypatch.delenv("SKELETON_PUBLIC_DEV_SURFACES", raising=False)
    assert _without_public_realtime(snap) == snap
    monkeypatch.setenv("SKELETON_PUBLIC_DEV_SURFACES", "1")
    assert _without_public_realtime(snap)["counters"] == {"http.requests": 2}
