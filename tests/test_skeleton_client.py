"""Unit + ASGI integration tests for skeleton.client."""

from __future__ import annotations

import json

import httpx
import pytest

from skeleton.client import (
    GatewayClient,
    MemoryClient,
    ServicesClient,
    SkeletonHTTPError,
    SkeletonTimeoutError,
    SkeletonTransportError,
)
from skeleton.client.retry import RetryPolicy


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_retry_policy_bounds():
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=0.05, max_delay_seconds=0.4)
    assert policy.delay_for_attempt(0) == pytest.approx(0.05)
    assert policy.delay_for_attempt(1) == pytest.approx(0.1)
    assert policy.delay_for_attempt(3) == pytest.approx(0.4)
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def test_gateway_health_and_capabilities():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if path.endswith("/health"):
            return httpx.Response(200, json={"status": "ok"})
        if path.endswith("/health/live"):
            return httpx.Response(200, json={"live": True})
        if path.endswith("/capabilities"):
            return httpx.Response(200, json={"planes": ["memory", "forge"]})
        return httpx.Response(404, json={"detail": "missing"})

    gw = GatewayClient(
        "http://skel.test",
        client=httpx.Client(
            base_url="http://skel.test",
            transport=_mock_transport(handler),
            timeout=5.0,
        ),
    )
    try:
        assert gw.health()["status"] == "ok"
        assert gw.health_live()["live"] is True
        assert gw.capabilities()["planes"] == ["memory", "forge"]
    finally:
        gw.close()
    assert calls == [
        "GET /api/v1/health",
        "GET /api/v1/health/live",
        "GET /api/v1/capabilities",
    ]


def test_gateway_http_error_typed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "busy"})

    gw = GatewayClient(
        "http://skel.test",
        client=httpx.Client(
            base_url="http://skel.test",
            transport=_mock_transport(handler),
            timeout=5.0,
        ),
        retry=RetryPolicy(max_attempts=1),
    )
    try:
        with pytest.raises(SkeletonHTTPError) as ei:
            gw.retrieval_query({"q": "x"})
        assert ei.value.status_code == 503
        assert ei.value.body == {"detail": "busy"}
    finally:
        gw.close()


def test_gateway_retries_idempotent_get():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(502, json={"detail": "blip"})
        return httpx.Response(200, json={"ok": True})

    gw = GatewayClient(
        "http://skel.test",
        client=httpx.Client(
            base_url="http://skel.test",
            transport=_mock_transport(handler),
            timeout=5.0,
        ),
        retry=RetryPolicy(max_attempts=4, base_delay_seconds=0.01, max_delay_seconds=0.02),
    )
    try:
        assert gw.health() == {"ok": True}
    finally:
        gw.close()
    assert attempts["n"] == 3


def test_memory_and_services_clients():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/memory/query"):
            body = json.loads(request.content)
            return httpx.Response(200, json={"hits": [{"q": body["query"]}], "n": 1})
        if path.endswith("/commands/contracts"):
            return httpx.Response(200, json={"commands": ["ping"]})
        if "/commands/execute/" in path:
            return httpx.Response(200, json={"ok": True, "command": path.rsplit("/", 1)[-1]})
        return httpx.Response(404, json={"detail": "no"})

    gw = GatewayClient(
        "http://skel.test",
        client=httpx.Client(
            base_url="http://skel.test",
            transport=_mock_transport(handler),
            timeout=5.0,
        ),
    )
    mem = MemoryClient(gw)
    svc = ServicesClient(gw)
    try:
        hits = mem.query_unified("forge eras", limit=3)
        assert hits["n"] == 1
        assert hits["hits"][0]["q"] == "forge eras"
        assert svc.contracts()["commands"] == ["ping"]
        assert svc.execute("ping", {"x": 1})["command"] == "ping"
    finally:
        gw.close()


def test_timeout_maps_to_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    gw = GatewayClient(
        "http://skel.test",
        client=httpx.Client(
            base_url="http://skel.test",
            transport=_mock_transport(handler),
            timeout=5.0,
        ),
    )
    try:
        with pytest.raises(SkeletonTimeoutError):
            gw.health()
    finally:
        gw.close()


def test_transport_error_maps():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    gw = GatewayClient(
        "http://skel.test",
        client=httpx.Client(
            base_url="http://skel.test",
            transport=_mock_transport(handler),
            timeout=5.0,
        ),
    )
    try:
        with pytest.raises(SkeletonTransportError):
            gw.capabilities()
    finally:
        gw.close()


def test_gateway_request_raw_returns_status_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "missing"})

    gw = GatewayClient(
        "http://skel.test",
        client=httpx.Client(
            base_url="http://skel.test",
            transport=_mock_transport(handler),
            timeout=5.0,
        ),
        retry=RetryPolicy(max_attempts=1),
    )
    try:
        status, body = gw.request_raw("GET", "/api/v1/health")
        assert status == 404
        assert body == {"detail": "missing"}
    finally:
        gw.close()


def test_app_health_probe_uses_client(monkeypatch):
    from skeleton.app.health import probe_http

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, base, **kwargs):
            captured["base"] = base
            captured["headers"] = kwargs.get("headers")

        def request_raw(self, method, path, *, idempotent=True):
            captured["method"] = method
            captured["path"] = path
            return 200, {"status": "ok"}

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr("skeleton.app.health.GatewayClient", FakeClient)
    result = probe_http("backend", "http://127.0.0.1:8000/api/v1/health", timeout=1.5)
    assert result.ok is True
    assert result.status == 200
    assert captured["base"] == "http://127.0.0.1:8000"
    assert captured["path"] == "/api/v1/health"
    assert captured["closed"] is True
