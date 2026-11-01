"""HTTP contract for /api/v1/core delivery log, DLQ, retry policy, secrets admin."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.core_v1.clock import FakeClock
from core.core_v1.keys import StaticKeyProvider
from core.core_v1.ports import TransportResult
from core.core_v1.transport import AllowAllPolicy, RecordingTransport
from core.core_v1_webhooks import build_runtime, set_runtime
from routes import core_v1_delivery_ops as ops_mod
from routes import core_v1_webhooks as mod
from routes.gameforge_auth import get_current_user

ADMIN = {"email": "a@example.com", "tenant_id": "t1", "role": "admin"}
VIEWER = {"email": "v@example.com", "tenant_id": "t1", "role": "viewer"}
OTHER = {"email": "o@example.com", "tenant_id": "t2", "role": "admin"}
TEST_PROVIDER = StaticKeyProvider({"k1": b"\x01" * 32}, "k1")


def _client(tmp_path, provider):
    clock, transport = FakeClock(), RecordingTransport()
    rt = build_runtime(str(tmp_path / "r.db"), clock=clock, transport=transport,
                       url_policy=AllowAllPolicy(), cursor_key=b"k" * 32, key_provider=provider)
    set_runtime(rt)
    app = FastAPI()
    mod.install_error_handler(app)
    app.include_router(mod.router)
    app.include_router(ops_mod.router)
    state = {"user": dict(ADMIN)}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = TestClient(app)
    c.state, c.rt, c.clock, c.transport = state, rt, clock, transport
    return c


@pytest.fixture
def client(tmp_path):
    yield _client(tmp_path, TEST_PROVIDER)
    set_runtime(None)


@pytest.fixture
def plain_client(tmp_path):
    yield _client(tmp_path, None)
    set_runtime(None)


def _hook(c, max_attempts=1):
    r = c.post("/api/v1/core/webhooks", json={"url": "https://h.example.com/x", "max_attempts": max_attempts})
    assert r.status_code == 201
    return r.json()["id"]


def _dead(c, n=2):
    wid = _hook(c)
    for i in range(n):
        assert c.post("/api/v1/core/events", json={"type": "a.b", "data": {"i": i}}).status_code == 202
    c.transport.responder = lambda call: TransportResult(500)
    c.rt.webhooks.dispatch_due()
    c.transport.responder = None
    return wid


def test_requires_auth(client):
    client.state["user"] = {"dev_mode": True}
    for path in ("/api/v1/core/deliveries", "/api/v1/core/dlq", "/api/v1/core/attempts",
                 "/api/v1/core/admin/secrets/status"):
        r = client.get(path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "CORE.AUTH.UNAUTHENTICATED"


def test_delivery_log_and_attempts(client):
    wid = _dead(client, 3)
    r = client.get("/api/v1/core/deliveries", params={"limit": 2, "status": "dead"})
    body = r.json()
    assert r.status_code == 200 and len(body["items"]) == 2 and body["has_more"]
    r2 = client.get("/api/v1/core/deliveries", params={"limit": 2, "status": "dead",
                                                       "cursor": body["next_cursor"]})
    assert len(r2.json()["items"]) == 1 and r2.json()["next_cursor"] is None
    tampered = body["next_cursor"][:-1] + ("0" if body["next_cursor"][-1] != "0" else "1")
    assert client.get("/api/v1/core/deliveries", params={"cursor": tampered, "status": "dead"}).status_code == 400
    ev = body["items"][0]["event_id"]
    r = client.get(f"/api/v1/core/events/{ev}/deliveries")
    assert [d["event_id"] for d in r.json()["items"]] == [ev]
    a = client.get(f"/api/v1/core/webhooks/{wid}/attempts").json()
    assert len(a["items"]) == 3 and a["items"][0]["object"] == "delivery_attempt"
    assert a["items"][0]["outcome"] == "dead" and a["items"][0]["webhook_id"] == wid
    bad = client.get("/api/v1/core/deliveries", params={"since": "not-a-time"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "CORE.DELIVERY_LOG.INVALID_FILTER"
    assert client.get("/api/v1/core/attempts", params={"outcome": "dead"}).json()["items"]
    client.state["user"] = OTHER
    assert client.get("/api/v1/core/deliveries").json()["items"] == []
    assert client.get(f"/api/v1/core/webhooks/{wid}/attempts").status_code == 404
    assert client.get(f"/api/v1/core/events/{ev}/deliveries").status_code == 404


def test_dlq_redrive_purge(client):
    _dead(client, 2)
    dead = client.get("/api/v1/core/dlq").json()["items"]
    assert len(dead) == 2
    client.state["user"] = VIEWER
    assert client.post("/api/v1/core/dlq/redrive", json={"delivery_ids": [dead[0]["id"]]}).status_code == 403
    client.state["user"] = ADMIN
    r = client.post("/api/v1/core/dlq/redrive", json={"delivery_ids": [dead[0]["id"]]})
    assert r.status_code == 202 and r.json()["redriven"][0]["delivery_id"] == dead[0]["id"]
    r = client.post("/api/v1/core/dlq/redrive", json={"delivery_ids": "x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "CORE.DLQ.INVALID"
    client.clock.advance(2 * 86400)
    r = client.post("/api/v1/core/dlq/purge", json={"older_than_seconds": 86400})
    assert r.status_code == 200 and r.json()["purged"] == 2
    assert client.get("/api/v1/core/dlq").json()["items"] == []
    assert client.post("/api/v1/core/dlq/purge", json={}).status_code == 400


def test_retry_policy_routes(client):
    wid = _hook(client)
    base = f"/api/v1/core/webhooks/{wid}/retry-policy"
    g = client.get(base).json()
    assert g["override"] is False and g["object"] == "retry_policy"
    p = client.put(base, json={"base_seconds": 2, "max_age_seconds": 3600})
    assert p.status_code == 200 and p.json()["base_seconds"] == 2 and p.json()["override"]
    assert client.get(base).json()["max_age_seconds"] == 3600
    bad = client.put(base, json={"factor": 99})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "CORE.RETRY_POLICY.INVALID"
    client.state["user"] = VIEWER
    assert client.put(base, json={"base_seconds": 2}).status_code == 403
    assert client.get(base).status_code == 200
    client.state["user"] = OTHER
    assert client.get(base).status_code == 404
    client.state["user"] = ADMIN
    assert client.delete(base).status_code == 204
    r = client.delete(base)
    assert r.status_code == 404 and r.json()["error"]["code"] == "CORE.RETRY_POLICY.NOT_FOUND"


def test_secrets_admin(client):
    _hook(client)
    st = client.get("/api/v1/core/admin/secrets/status").json()
    assert st["active_key_id"] == "k1" and st["rows_by_key"] == {"k1": 1} and st["plaintext_rows"] == 0
    r = client.post("/api/v1/core/admin/secrets/encrypt")
    assert r.status_code == 200 and r.json()["done"] and r.json()["changed"] == 0
    r = client.post("/api/v1/core/admin/secrets/rewrap", json={"batch_size": 10, "force": True})
    assert r.status_code == 200 and r.json()["done"]
    assert client.post("/api/v1/core/admin/secrets/rewrap", json={"batch_size": 0}).status_code == 400
    client.state["user"] = {"email": "e@example.com", "tenant_id": "t1", "role": "editor"}
    assert client.get("/api/v1/core/admin/secrets/status").status_code == 403


def test_secrets_admin_without_keyring_is_409(plain_client):
    r = plain_client.get("/api/v1/core/admin/secrets/status")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CORE.SECRETS.NO_KEYRING"
    assert plain_client.post("/api/v1/core/admin/secrets/encrypt").status_code == 409


def test_secret_never_rendered_and_encrypted_at_rest(client):
    r = client.post("/api/v1/core/webhooks", json={"url": "https://h.example.com/x"})
    secret = r.json()["secret"].encode()
    rows = client.rt.webhooks.secrets.store.scan("", 10)
    assert rows and all(secret not in row.blob for row in rows)
    for path in ("/api/v1/core/deliveries", "/api/v1/core/admin/secrets/status"):
        assert secret.decode() not in client.get(path).text


def test_build_runtime_reads_keyring_from_env(tmp_path, monkeypatch):
    from core.core_v1.keys import KeyProviderError, encode_key
    monkeypatch.delenv("SKELETON_BACKEND_CORE_KEKS", raising=False)
    monkeypatch.delenv("SKELETON_BACKEND_CORE_REQUIRE_KEK", raising=False)
    # Default composition must never silently persist signing secrets in cleartext.
    with pytest.raises(KeyProviderError, match="required"):
        build_runtime(str(tmp_path / "no-key.db"), url_policy=AllowAllPolicy(), cursor_key=b"k" * 32)
    assert not (tmp_path / "no-key.db").exists()  # no side effects on missing custody
    # Explicit test-only plaintext mode remains available for migration fixtures.
    dev = build_runtime(str(tmp_path / "dev.db"), url_policy=AllowAllPolicy(),
                        cursor_key=b"k" * 32, key_provider=None)
    assert dev.ops.secrets_admin is None
    monkeypatch.setenv("SKELETON_BACKEND_CORE_REQUIRE_KEK", "1")
    with pytest.raises(KeyProviderError):
        build_runtime(str(tmp_path / "a.db"), url_policy=AllowAllPolicy(), cursor_key=b"k" * 32)
    test_key = encode_key(bytes([3]) * 32)
    monkeypatch.setenv("SKELETON_BACKEND_CORE_KEKS", "envk:" + test_key)
    rt = build_runtime(str(tmp_path / "b.db"), url_policy=AllowAllPolicy(), cursor_key=b"k" * 32)
    assert rt.ops.secrets_admin is not None and rt.webhooks.secrets.provider.active_key_id() == "envk"
