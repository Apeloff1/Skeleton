"""Contract tests for the composed /api/v1 edge."""
import json

from skeleton.api.v1_edge.webhook_ingress import sign
from tests.api_v1_edge.conftest import SECRET, calls


def err(r):
    return r.json()["error"]["code"]


def test_passthrough_outside_v1(env):
    r = env["client"].get("/other")
    assert r.status_code == 200 and "x-request-id" not in r.headers


def test_public_route_security_headers_trace(env):
    r = env["client"].get("/api/v1/public/ping", headers={"x-request-id": "req-12345678"})
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-request-id"] == "req-12345678"
    assert r.headers["traceparent"].startswith("00-")
    assert env["traces"][-1]["status"] == 200


def test_404_405_envelope(env):
    r = env["client"].get("/api/v1/nope")
    assert r.status_code == 404 and err(r) == "EDGE.NOT_FOUND" and r.json()["error"]["request_id"]
    r = env["client"].delete("/api/v1/public/ping")
    assert r.status_code == 405 and r.headers["allow"] == "GET"


def test_auth_required_and_scopes(env):
    c = env["client"]
    assert c.get("/api/v1/projects/1").status_code == 401
    r = c.get("/api/v1/projects/7", headers={"x-api-key": env["ro"]})
    assert r.status_code == 200 and r.json()["tenant"] == "t2" and r.json()["params"] == {"pid": "7"}
    r = c.post("/api/v1/projects", headers={"x-api-key": env["ro"], "idempotency-key": "a"}, json={"name": "x"})
    assert r.status_code == 403 and err(r) == "EDGE.AUTH.SCOPE"


def test_session_route(env):
    cookie = env["sessions"].issue("u", "t9")
    r = env["client"].get("/api/v1/me", headers={"cookie": f"skl_session={cookie}"})
    assert r.status_code == 200 and r.json()["tenant"] == "t9"
    assert env["client"].get("/api/v1/me", headers={"x-api-key": env["token"]}).status_code == 403


def test_validation_and_media(env):
    h = {"x-api-key": env["token"], "idempotency-key": "v1"}
    c = env["client"]
    r = c.post("/api/v1/projects", headers=h, json={"name": ""})
    assert r.status_code == 422 and r.json()["error"]["context"]["errors"][0]["path"] == "$.name"
    r = c.post("/api/v1/projects", headers={**h, "content-type": "text/plain"}, content=b"x")
    assert r.status_code == 415
    r = c.post("/api/v1/projects", headers={**h, "content-type": "application/json"}, content=b"{bad")
    assert r.status_code == 400 and err(r) == "EDGE.MALFORMED_JSON"
    r = c.post("/api/v1/projects", headers={**h, "content-type": "application/json"}, content=b"x" * 2000)
    assert r.status_code == 413


def test_idempotency_replay_mismatch_and_required(env):
    c, h = env["client"], {"x-api-key": env["token"], "idempotency-key": "k-1"}
    r1 = c.post("/api/v1/projects", headers=h, json={"name": "a"})
    r2 = c.post("/api/v1/projects", headers=h, json={"name": "a"})
    assert r1.status_code == r2.status_code == 201
    assert r1.json() == r2.json() and r2.headers["idempotent-replayed"] == "true"
    assert calls.count("/api/v1/projects") == 1
    r3 = c.post("/api/v1/projects", headers=h, json={"name": "b"})
    assert r3.status_code == 422 and err(r3) == "EDGE.IDEMPOTENCY.MISMATCH"
    r4 = c.post("/api/v1/projects", headers={"x-api-key": env["token"]}, json={"name": "a"})
    assert r4.status_code == 400


def test_idempotency_does_not_pin_5xx(env):
    c, h = env["client"], {"x-api-key": env["token"], "idempotency-key": "b"}
    assert c.post("/api/v1/boom", headers=h).status_code == 500
    assert c.post("/api/v1/boom", headers=h).status_code == 500
    assert calls.count("/api/v1/boom") == 2


def test_rate_limit_writes(env):
    c = env["client"]
    codes = [c.post("/api/v1/projects", headers={"x-api-key": env["token"], "idempotency-key": f"r{i}"},
                    json={"name": "n"}).status_code for i in range(7)]
    assert codes[:6] == [201] * 6 and codes[6] == 429


def test_cors_preflight(env):
    c = env["client"]
    r = c.options("/api/v1/projects", headers={"origin": "https://app.example",
                                               "access-control-request-method": "POST",
                                               "access-control-request-headers": "content-type,idempotency-key"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "https://app.example"
    r = c.options("/api/v1/projects", headers={"origin": "https://evil", "access-control-request-method": "POST"})
    assert r.status_code == 403
    r = c.get("/api/v1/public/ping", headers={"origin": "https://evil"})
    assert "access-control-allow-origin" not in r.headers


def test_health(env):
    c = env["client"]
    assert c.get("/api/v1/health/live").json()["status"] == "ok"
    assert c.get("/api/v1/health/ready").status_code == 200
    env["health"].add("cache", lambda: False)
    r = c.get("/api/v1/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["cache"] == "fail"


def test_webhook_ingress(env):
    c, body = env["client"], b'{"e":1}'
    import time
    sig = sign(SECRET, int(time.time()), body)
    r = c.post("/api/v1/webhooks/gh", headers={"x-skeleton-signature": sig}, content=body)
    assert r.status_code == 201 and json.loads(r.json()["echo"]) == {"e": 1}
    r = c.post("/api/v1/webhooks/gh", headers={"x-skeleton-signature": sig}, content=body)
    assert r.status_code == 409
    r = c.post("/api/v1/webhooks/gh", content=body)
    assert r.status_code == 401
