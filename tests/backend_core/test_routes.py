import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.core_v1.clock import FakeClock
from core.core_v1.transport import AllowAllPolicy, RecordingTransport
from core.core_v1_webhooks import build_runtime, set_runtime
from routes import core_v1_webhooks as mod
from routes.gameforge_auth import get_current_user

USER = {"email": "a@example.com", "tenant_id": "t1", "role": "admin"}


@pytest.fixture
def client(tmp_path):
    rt = build_runtime(str(tmp_path / "r.db"), clock=FakeClock(), transport=RecordingTransport(),
                       url_policy=AllowAllPolicy(), cursor_key=b"k" * 32)
    set_runtime(rt)
    app = FastAPI()
    mod.install_error_handler(app)
    app.include_router(mod.router)
    state = {"user": dict(USER)}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = TestClient(app)
    c.state = state
    c.rt = rt
    yield c
    set_runtime(None)


def _create(client, **headers):
    return client.post("/api/v1/core/webhooks", json={"url": "https://h.example.com/x",
                                                      "event_filters": ["a.*"]}, headers=headers)


def test_create_get_etag(client):
    r = _create(client)
    assert r.status_code == 201 and r.json()["secret"].startswith("whsec_")
    wid = r.json()["id"]
    g = client.get(f"/api/v1/core/webhooks/{wid}")
    assert g.status_code == 200 and "secret" not in g.json() and g.headers["ETag"] == r.json()["etag"]


def test_idempotent_create(client):
    r1 = _create(client, **{"Idempotency-Key": "create-0001"})
    r2 = _create(client, **{"Idempotency-Key": "create-0001"})
    assert r1.json() == r2.json() and r2.headers.get("Idempotent-Replayed") == "true"
    r3 = client.post("/api/v1/core/webhooks", json={"url": "https://other.example.com/"},
                     headers={"Idempotency-Key": "create-0001"})
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "CORE.IDEMPOTENCY.KEY_REUSED"


def test_patch_concurrency(client):
    wid = _create(client).json()["id"]
    assert client.patch(f"/api/v1/core/webhooks/{wid}", json={"description": "x"}).status_code == 428
    tag = client.get(f"/api/v1/core/webhooks/{wid}").headers["ETag"]
    ok = client.patch(f"/api/v1/core/webhooks/{wid}", json={"description": "x"}, headers={"If-Match": tag})
    assert ok.status_code == 200 and ok.json()["version"] == 2
    stale = client.patch(f"/api/v1/core/webhooks/{wid}", json={"description": "y"}, headers={"If-Match": tag})
    assert stale.status_code == 412 and stale.headers["ETag"] == ok.headers["ETag"]


def test_errors_and_auth(client):
    r = client.post("/api/v1/core/webhooks", json={"url": "https://h.example.com/", "bogus": 1})
    assert r.status_code == 400 and set(r.json()["error"]) == {"type", "code", "message", "context"}
    assert client.get("/api/v1/core/webhooks/whk_nope").status_code == 404
    assert client.get("/api/v1/core/webhooks?limit=0").json()["error"]["code"] == "CORE.PAGINATION.INVALID_LIMIT"
    assert client.get("/api/v1/core/webhooks?cursor=junk").status_code == 400
    client.state["user"] = {"email": "v@example.com", "tenant_id": "t1", "role": "viewer"}
    assert _create(client).status_code == 403
    client.state["user"] = None
    assert client.get("/api/v1/core/webhooks").status_code == 401
    client.state["user"] = {"email": "anonymous", "role": "admin", "dev_mode": True}
    assert client.get("/api/v1/core/webhooks").status_code == 401


def test_events_deliveries_replay_flow(client):
    wid = _create(client).json()["id"]
    e = client.post("/api/v1/core/events", json={"type": "a.b", "data": {"x": 1}, "dedupe_key": "d1"})
    assert e.status_code == 202 and e.json()["deliveries_created"] == 1
    dup = client.post("/api/v1/core/events", json={"type": "a.b", "data": {"x": 1}, "dedupe_key": "d1"})
    assert dup.status_code == 200 and dup.json()["duplicate"] is True
    client.rt.webhooks.dispatch_due()
    lst = client.get(f"/api/v1/core/webhooks/{wid}/deliveries?status=succeeded").json()
    did = lst["items"][0]["id"]
    detail = client.get(f"/api/v1/core/deliveries/{did}").json()
    assert detail["attempt_log"][0]["outcome"] == "success"
    rep = client.post(f"/api/v1/core/deliveries/{did}/replay")
    assert rep.status_code == 202 and rep.json()["replay_of"] == did


def test_tenant_isolation_over_http(client):
    wid = _create(client).json()["id"]
    client.state["user"] = {"email": "b@example.com", "tenant_id": "t2", "role": "admin"}
    assert client.get(f"/api/v1/core/webhooks/{wid}").status_code == 404
    assert client.get("/api/v1/core/webhooks").json()["items"] == []
