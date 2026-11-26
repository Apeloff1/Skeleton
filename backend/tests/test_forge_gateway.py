"""Forge gateway BFF: app users reach sealed engine routes without ever holding the seal."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import forge_gateway as gw

SECRET = "0123456789abcdef" * 4
ALICE = {"email": "alice@example.com", "role": "editor", "tenant_id": "default"}
BOB = {"email": "bob@example.com", "role": "editor", "tenant_id": "default"}


class _Recorder(httpx.AsyncBaseTransport):
    """Wrap a transport and keep every outbound request for assertions."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner
        self.requests: List[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return await self.inner.handle_async_request(request)


class _LifespanBridge(httpx.AsyncBaseTransport):
    """Forward to a started engine (TestClient keeps its lifespan running)."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        response = await asyncio.to_thread(
            self.client.request, request.method, request.url.raw_path.decode(), content=body, headers=dict(request.headers),
        )
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)


def _app(user: Dict[str, Any] | None) -> FastAPI:
    app = FastAPI()
    app.include_router(gw.router)

    def current() -> Dict[str, Any]:
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Authentication required")
        return user

    app.dependency_overrides[gw.require_builder] = current
    app.dependency_overrides[gw.require_reader] = current
    return app


@pytest.fixture()
def engine(monkeypatch: pytest.MonkeyPatch):
    """The real Skeleton engine app as the upstream (sealed, charter-gated)."""
    from skeleton.api.server import create_app

    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    with TestClient(create_app(), base_url="http://engine.internal") as engine_client:  # runs the lifespan
        recorder = _Recorder(_LifespanBridge(engine_client))
        gw.configure_for_tests(config=gw.GatewayConfig(engine_url="http://engine.internal", builds_per_minute=50), transport=recorder)
        yield recorder
    gw.configure_for_tests(config=None, transport=None)


def _poll(client: TestClient, ref: str, timeout_s: float = 90.0) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = client.get(ref)
        assert response.status_code == 200, response.text
        view = response.json()
        if view.get("status") in {"succeeded", "failed", "cancelled", "dead_letter"}:
            return view
        time.sleep(0.2)
    raise AssertionError("build did not finish")


def test_build_through_gateway_against_real_engine(engine: _Recorder) -> None:
    client = TestClient(_app(ALICE))
    started = client.post("/api/forge-gateway/game/build", json={"brief": "A small platformer. Core loop: jump to the gate.", "playtest": "off"},
                          headers={"Idempotency-Key": "alice-build-0001", "x-request-id": "rid-1"})
    assert started.status_code == 202, started.text
    ack = started.json()
    assert ack["status_ref"] == f"/api/forge-gateway/game/build/{ack['execution_id']}"
    assert ack["gateway"]["schema"] == gw.SCHEMA
    assert int(started.headers["content-length"]) == len(started.content)  # rewritten body, fresh length
    assert started.headers["x-request-id"] == "rid-1"
    view = _poll(client, ack["status_ref"])
    assert view["status"] == "succeeded", view

    outbound = engine.requests[0]
    seal = outbound.headers["x-gf-seal"]
    principal, actor, expiry, mac = seal.split(".")
    assert principal == "forge-gateway" and actor.startswith("app-") and len(mac) == 64
    assert 0 < int(expiry) - time.time() <= gw.SEAL_TTL_S
    assert outbound.headers["idempotency-key"] == "alice-build-0001"
    assert outbound.headers["x-request-id"] == "rid-1"
    assert "authorization" not in outbound.headers
    assert SECRET not in json.dumps(ack) and SECRET not in started.text
    # Nothing the client sent is forwarded beyond the allow-listed headers.
    assert set(outbound.headers) <= {"x-gf-seal", "x-skeleton-tenant", "x-request-id", "accept", "idempotency-key", "content-type", "content-length", "host", "accept-encoding", "connection", "user-agent"}


def test_builds_are_isolated_per_user(engine: _Recorder) -> None:
    alice = TestClient(_app(ALICE))
    bob = TestClient(_app(BOB))
    ack = alice.post("/api/forge-gateway/game/build", json={"brief": "A tiny top-down shooter.", "playtest": "off"}).json()
    assert bob.get(ack["status_ref"]).status_code == 404
    assert alice.get(ack["status_ref"]).status_code == 200


def test_unauthenticated_and_validation(engine: _Recorder) -> None:
    anon = TestClient(_app(None))
    assert anon.post("/api/forge-gateway/game/build", json={"brief": "x"}).status_code == 401
    client = TestClient(_app(ALICE))
    for body in ({"brief": "   "}, {"brief": "x" * (gw.MAX_BRIEF_CHARS + 1)}, {"brief": "ok", "playtest": "maybe"},
                 {"brief": "ok", "project_root": "/etc"}, {"brief": "ok", "actor_id": "someone-else"}):
        assert client.post("/api/forge-gateway/game/build", json=body).status_code == 422, body
    assert client.post("/api/forge-gateway/game/build", json={"brief": "ok"}, headers={"Idempotency-Key": "bad key!"}).status_code == 422
    assert client.get("/api/forge-gateway/game/build/..%2Fadmin").status_code == 404
    assert client.post("/api/forge-gateway/gameforge/run", json={"vision": "v", "out": "/tmp/x"}).status_code == 422
    assert engine.requests == []  # nothing invalid reached the engine


def test_rate_limit_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(202, json={"execution_id": f"exec-{len(calls)}", "status": "queued"})

    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    now = [1000.0]
    gw.configure_for_tests(config=gw.GatewayConfig(engine_url="http://engine.internal", builds_per_minute=2),
                           transport=httpx.MockTransport(handler), clock=lambda: now[0])
    try:
        alice = TestClient(_app(ALICE))
        bob = TestClient(_app(BOB))
        for _ in range(2):
            assert alice.post("/api/forge-gateway/game/build", json={"brief": "b"}).status_code == 202
        limited = alice.post("/api/forge-gateway/game/build", json={"brief": "b"})
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
        assert bob.post("/api/forge-gateway/game/build", json={"brief": "b"}).status_code == 202
        now[0] += 61
        assert alice.post("/api/forge-gateway/game/build", json={"brief": "b"}).status_code == 202
        assert len(calls) == 4
    finally:
        gw.configure_for_tests(config=None, transport=None)


@pytest.mark.parametrize("upstream_status,body,expected,fragment", [
    (401, {"detail": "invalid seal"}, 502, "credentials"),
    (500, {"detail": "Traceback: secret stuff"}, 502, "failed"),
    (503, {"error": "service_unavailable"}, 503, "Try again"),
    (422, {"detail": "brief must be a string"}, 422, "brief must be"),
    (403, {"detail": {"error": "charter_denied", "reason": "paused"}}, 403, "charter_denied"),
])
def test_engine_errors_are_mapped(monkeypatch: pytest.MonkeyPatch, upstream_status: int, body: Dict[str, Any], expected: int, fragment: str) -> None:
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    gw.configure_for_tests(config=gw.GatewayConfig(engine_url="http://engine.internal"),
                           transport=httpx.MockTransport(lambda r: httpx.Response(upstream_status, json=body)))
    try:
        response = TestClient(_app(ALICE)).post("/api/forge-gateway/game/build", json={"brief": "b"})
        assert response.status_code == expected
        assert fragment in response.text and "Traceback" not in response.text
    finally:
        gw.configure_for_tests(config=None, transport=None)


def test_engine_unreachable_and_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    gw.configure_for_tests(config=gw.GatewayConfig(engine_url="http://engine.internal"), transport=httpx.MockTransport(boom))
    try:
        assert TestClient(_app(ALICE)).post("/api/forge-gateway/game/build", json={"brief": "b"}).status_code == 502
    finally:
        gw.configure_for_tests(config=None, transport=None)
    monkeypatch.delenv("FORGE_GATEWAY_ENGINE_URL", raising=False)
    monkeypatch.delenv("SKELETON_INTERNAL_URL", raising=False)
    client = TestClient(_app(ALICE))
    assert client.post("/api/forge-gateway/game/build", json={"brief": "b"}).status_code == 503
    status = client.get("/api/forge-gateway/status").json()
    assert status["engine_configured"] is False and status["seal_configured"] is True
    assert SECRET not in json.dumps(status)


def test_missing_seal_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    gw.configure_for_tests(config=gw.GatewayConfig(engine_url="http://engine.internal"),
                           transport=httpx.MockTransport(lambda r: httpx.Response(202, json={})))
    try:
        assert TestClient(_app(ALICE)).post("/api/forge-gateway/game/build", json={"brief": "b"}).status_code == 503
    finally:
        gw.configure_for_tests(config=None, transport=None)


@pytest.mark.parametrize("url", ["ftp://x", "http://u:p@x", "http://x/path", "http://x?q=1", "http://x#f", "not a url"])
def test_engine_url_must_be_plain_origin(url: str) -> None:
    with pytest.raises(gw.GatewayConfigError):
        gw.normalise_engine_url(url)


def test_actor_is_stable_pseudonymous_and_tenant_scoped() -> None:
    a1 = gw.caller_from_user(ALICE)
    a2 = gw.caller_from_user({**ALICE, "email": "ALICE@example.com"})
    other_tenant = gw.caller_from_user({**ALICE, "tenant_id": "acme"})
    assert a1.actor == a2.actor and a1.actor != other_tenant.actor
    assert "alice" not in a1.actor and len(a1.actor) <= 128
    with pytest.raises(Exception):
        gw.caller_from_user({"role": "editor"})


def test_registered_in_route_registry() -> None:
    from core.routes_registry import KNOWN_ROUTES

    assert ("routes.forge_gateway", "router") in KNOWN_ROUTES
