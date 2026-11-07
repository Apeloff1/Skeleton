import json

import pytest
from starlette.testclient import TestClient

from skeleton.api.v1_edge.auth import ApiKeyStore, EdgeAuthenticator, SessionVerifier
from skeleton.api.v1_edge.edge import EdgeConfig, build_v1_edge
from skeleton.api.v1_edge.health import HealthRegistry
from skeleton.api.v1_edge.quota_store import (DistributedQuotas, InMemoryCounterStore, Limit,
                                              QuotaPlan, QuotaTelemetry, RemoteCounterStore)
from skeleton.api.v1_edge.quota_store.testing import FakeRemoteClient
from skeleton.api.v1_edge.quotas import QuotaPolicy, TenantQuotas
from skeleton.api.v1_edge.registry import RouteRegistry, RouteSpec

NOW = [1000.0]


async def downstream(scope, receive, send):
    while True:
        m = await receive()
        if not m.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": b'{"ok":true}'})


def make_app(store, legacy=None, tel=None):
    reg = RouteRegistry()
    reg.register(RouteSpec("GET", "/items/{iid}"))
    reg.register(RouteSpec("POST", "/items", quota_class="writes"))
    keys = ApiKeyStore()
    tok1 = keys.add("k1", "test-only-key-1", subject="svc", tenant="t1", scopes=set())
    tok2 = keys.add("k2", "test-only-key-2", subject="svc", tenant="t2", scopes=set())
    plan = QuotaPlan({"default": Limit(1, 3), "writes": Limit(1, 2)},
                     tenant_route_limits={"GET /items/{iid}": Limit(1, 2)})
    tel = tel or QuotaTelemetry()
    quotas = DistributedQuotas(plan, store=store, legacy=legacy, telemetry=tel)
    health = HealthRegistry()
    health.add("quota_store", quotas.health_check)
    cfg = EdgeConfig(registry=reg, auth=EdgeAuthenticator(keys, SessionVerifier(b"q" * 32)),
                     quotas=quotas, health=health)
    return TestClient(build_v1_edge(downstream, cfg)), tok1, tok2, tel


def auth(tok):
    return {"authorization": f"Bearer {tok}"}


@pytest.fixture
def mem():
    NOW[0] = 1000.0
    return make_app(InMemoryCounterStore(clock=lambda: NOW[0]))


def test_headers_on_success(mem):
    c, t1, _, _ = mem
    r = c.get("/api/v1/items/1", headers=auth(t1))
    assert r.status_code == 200
    assert r.headers["ratelimit-limit"] == "2" and r.headers["ratelimit-remaining"] == "1"
    assert r.headers["ratelimit-reset"] == "1"
    assert '"tenant_route";q=2' in r.headers["ratelimit-policy"]
    assert "x-request-id" in r.headers


def test_route_template_bucket_shared_across_ids_and_429_envelope(mem):
    c, t1, t2, tel = mem
    c.get("/api/v1/items/1", headers=auth(t1))
    c.get("/api/v1/items/2", headers=auth(t1))
    r = c.get("/api/v1/items/3", headers=auth(t1))
    assert r.status_code == 429
    body = r.json()["error"]
    assert body["code"] == "EDGE.RATE.LIMITED" and body["context"]["scope"] == "tenant_route"
    assert r.headers["retry-after"] == "1" and r.headers["ratelimit-remaining"] == "0"
    assert body["request_id"] == r.headers["x-request-id"]
    assert c.get("/api/v1/items/1", headers=auth(t2)).status_code == 200
    assert tel.recent("quota.denied")
    NOW[0] += 1
    assert c.get("/api/v1/items/1", headers=auth(t1)).status_code == 200


def test_store_down_returns_503_envelope_and_unready():
    NOW[0] = 0.0
    client = FakeRemoteClient()
    c, t1, _, tel = make_app(RemoteCounterStore(client, clock=lambda: NOW[0]))
    assert c.get("/api/v1/items/1", headers=auth(t1)).status_code == 200
    assert c.get("/api/v1/health/ready").status_code == 200
    client.down = True
    r = c.get("/api/v1/items/1", headers=auth(t1))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "EDGE.QUOTA.STORE_UNAVAILABLE"
    assert r.headers["retry-after"] == "1"
    assert c.get("/api/v1/health/ready").status_code == 503
    assert tel.recent("quota.store_unavailable")


def test_legacy_window_quota_still_applies_through_edge():
    NOW[0] = 0.0
    legacy = TenantQuotas({"default": QuotaPolicy(100, 100), "writes": QuotaPolicy(100, 100, window_s=60,
                                                                                   window_limit=1)},
                          clock=lambda: NOW[0])
    c, t1, _, _ = make_app(InMemoryCounterStore(clock=lambda: NOW[0]), legacy=legacy)
    r = c.post("/api/v1/items", headers=auth(t1), content=b"{}")
    assert r.status_code == 200 and r.headers["x-quota-remaining"] == "0"
    r = c.post("/api/v1/items", headers=auth(t1), content=b"{}")
    assert r.status_code == 429 and r.json()["error"]["code"] == "EDGE.QUOTA.EXHAUSTED"


def test_unauthenticated_requests_never_touch_store(mem):
    c, _, _, tel = mem
    r = c.get("/api/v1/items/1")
    assert r.status_code == 401
    assert tel.recent() == []
    assert c.get("/outside/v1").status_code == 200
