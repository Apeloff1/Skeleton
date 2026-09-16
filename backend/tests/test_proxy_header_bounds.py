"""Focused bounds and disclosure tests for trusted proxy and request metadata."""

from __future__ import annotations

import asyncio
import ipaddress
import json
from pathlib import Path

import pytest
from starlette.requests import Request

import api_middleware
import middleware.security as legacy_security
from middleware.header_bounds import HeaderBoundMiddleware, measure_headers


def _request(client_host: str, xff: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", xff.encode("ascii"))],
            "client": (client_host, 43210),
            "server": ("testserver", 80),
        }
    )


def _trusted_test_networks():
    return (ipaddress.ip_network("10.0.0.0/8"),)


def _trust_test_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        _trusted_test_networks(),
    )


def test_xff_chain_has_hard_hop_bound(monkeypatch) -> None:
    _trust_test_proxy(monkeypatch)
    trusted = _trusted_test_networks()
    peer = "10.0.0.5"
    within_bound = ",".join(f"198.51.100.{index}" for index in range(1, 33))
    over_bound = within_bound + ",198.51.100.33"

    request = _request(peer, within_bound)
    assert api_middleware._client_ip(request) == "198.51.100.32"
    assert legacy_security._client_ip(request, trusted) == "198.51.100.32"

    request = _request(peer, over_bound)
    assert api_middleware._client_ip(request) == peer
    assert legacy_security._client_ip(request, trusted) == peer


def test_xff_value_has_hard_character_bound_before_ip_parsing(monkeypatch) -> None:
    _trust_test_proxy(monkeypatch)
    trusted = _trusted_test_networks()
    peer = "10.0.0.5"
    original_primary = api_middleware._canonical_ip
    original_legacy = legacy_security._canonical_ip

    def guarded_primary_canonical_ip(value: str):
        if len(value) > 1000:
            raise AssertionError("oversized forwarded value reached the primary IP parser")
        return original_primary(value)

    def guarded_legacy_canonical_ip(value: str):
        if len(value) > 1000:
            raise AssertionError("oversized forwarded value reached the legacy IP parser")
        return original_legacy(value)

    monkeypatch.setattr(api_middleware, "_canonical_ip", guarded_primary_canonical_ip)
    monkeypatch.setattr(legacy_security, "_canonical_ip", guarded_legacy_canonical_ip)
    oversized = "1" * (api_middleware._MAX_XFF_CHARS + 1)

    request = _request(peer, oversized)
    assert api_middleware._client_ip(request) == peer
    assert legacy_security._client_ip(request, trusted) == peer


def test_proxy_bounds_stay_aligned_between_active_security_stacks() -> None:
    assert legacy_security._MAX_XFF_HOPS == api_middleware._MAX_XFF_HOPS
    assert legacy_security._MAX_XFF_CHARS == api_middleware._MAX_XFF_CHARS


def test_malformed_proxy_cidr_disables_trust_in_both_active_stacks() -> None:
    raw = "10.0.0.0/8, definitely-not-a-cidr, 2001:db8::/32"

    assert api_middleware._parse_trusted_proxy_networks(raw) == ()
    assert legacy_security._parse_trusted_proxy_networks(raw) == ()


def test_telemetry_reports_proxy_count_without_disclosing_networks(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("2001:db8::/32"),
        ),
    )
    stats = api_middleware.get_stats()["rate_limit"]

    assert stats["trusted_proxy_count"] == 2
    assert "trusted_proxy_cidrs" not in stats
    assert "10.0.0.0/8" not in repr(stats)
    assert "2001:db8::/32" not in repr(stats)


def _header_scope(headers):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/health",
        "raw_path": b"/api/health",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _run_header_middleware(middleware, scope):
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(middleware(scope, _empty_receive, send))
    return messages


def _response_body(messages):
    chunks = [
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ]
    return json.loads(b"".join(chunks))


def test_header_measurement_counts_raw_asgi_name_and_value_bytes() -> None:
    headers = [(b"host", b"example.test"), (b"x-test", b"abc")]
    assert measure_headers(headers) == (2, 4 + 12 + 6 + 3)


def test_header_byte_limit_rejects_before_application_dispatch() -> None:
    called = []

    async def app(scope, receive, send):
        called.append(scope["path"])

    middleware = HeaderBoundMiddleware(
        app,
        max_header_bytes=8,
        max_header_count=10,
    )
    messages = _run_header_middleware(
        middleware,
        _header_scope([(b"x", b"12345678")]),
    )

    assert called == []
    assert messages[0]["status"] == 431
    body = _response_body(messages)
    assert body["reason"] == "header_bytes"
    assert "12345678" not in repr(body)
    assert (b"cache-control", b"no-store") in messages[0]["headers"]


def test_header_count_limit_rejects_before_application_dispatch() -> None:
    called = []

    async def app(scope, receive, send):
        called.append(True)

    middleware = HeaderBoundMiddleware(
        app,
        max_header_bytes=1024,
        max_header_count=2,
    )
    messages = _run_header_middleware(
        middleware,
        _header_scope([(b"a", b"1"), (b"b", b"2"), (b"c", b"3")]),
    )

    assert called == []
    assert messages[0]["status"] == 431
    assert _response_body(messages)["reason"] == "header_count"


def test_malformed_asgi_header_shape_fails_closed() -> None:
    called = []

    async def app(scope, receive, send):
        called.append(True)

    middleware = HeaderBoundMiddleware(app)
    messages = _run_header_middleware(
        middleware,
        _header_scope([(b"valid", b"ok"), (b"broken", "not-bytes")]),
    )

    assert called == []
    assert messages[0]["status"] == 431
    assert _response_body(messages)["reason"] == "malformed_headers"


def test_header_environment_limits_override_constructor(monkeypatch) -> None:
    monkeypatch.setenv("CODEDOCK_MAX_HEADER_BYTES", "64")
    monkeypatch.setenv("CODEDOCK_MAX_HEADER_COUNT", "7")

    async def app(scope, receive, send):
        return None

    middleware = HeaderBoundMiddleware(
        app,
        max_header_bytes=4096,
        max_header_count=99,
    )
    assert middleware.max_header_bytes == 64
    assert middleware.max_header_count == 7


def test_invalid_header_limit_configuration_fails_startup(monkeypatch) -> None:
    async def app(scope, receive, send):
        return None

    monkeypatch.setenv("CODEDOCK_MAX_HEADER_BYTES", "not-an-int")
    with pytest.raises(ValueError, match="must be an integer"):
        HeaderBoundMiddleware(app)

    monkeypatch.delenv("CODEDOCK_MAX_HEADER_BYTES")
    with pytest.raises(ValueError, match="must be positive"):
        HeaderBoundMiddleware(app, max_header_count=0)


def test_non_http_scope_passes_through_header_guard() -> None:
    called = []

    async def app(scope, receive, send):
        called.append(scope["type"])

    middleware = HeaderBoundMiddleware(
        app,
        max_header_bytes=1,
        max_header_count=1,
    )
    _run_header_middleware(middleware, {"type": "lifespan"})
    assert called == ["lifespan"]


def test_container_entrypoints_use_outer_header_boundary_wrapper() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    dockerfile = (backend_root / "Dockerfile").read_text(encoding="utf-8")
    wrapper = (backend_root / "security_app.py").read_text(encoding="utf-8")

    cmd_lines = [line for line in dockerfile.splitlines() if line.startswith("CMD [")]
    assert len(cmd_lines) == 2
    assert all('"security_app:app"' in line for line in cmd_lines)
    assert all('"server:app"' not in line for line in cmd_lines)

    assert "from server import app as _backend_app" in wrapper
    assert "app = HeaderBoundMiddleware(_backend_app)" in wrapper
    assert wrapper.index("from server import app as _backend_app") < wrapper.index(
        "app = HeaderBoundMiddleware(_backend_app)"
    )
