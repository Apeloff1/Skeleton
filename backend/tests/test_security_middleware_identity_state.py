"""Adversarial regressions for middleware.security identity and state boundaries."""

from __future__ import annotations

import asyncio
from collections import OrderedDict

import pytest
from starlette.requests import Request
from starlette.responses import Response

from middleware import security


def _request(
    path: str = "/api/test",
    *,
    client: str | None = "198.51.100.10",
    xff: str | list[str] | None = None,
    request_id: str | list[str] | None = None,
    content_length: str | list[str] | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    for name, value in (
        (b"x-forwarded-for", xff),
        (b"x-request-id", request_id),
        (b"content-length", content_length),
    ):
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        headers.extend((name, item.encode("latin-1")) for item in values)
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": (client, 12345) if client is not None else None,
            "server": ("test", 80),
            "scheme": "http",
        }
    )


@pytest.fixture(autouse=True)
def _reset_shared_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CODEDOCK_TRUSTED_PROXY_CIDRS", raising=False)
    security.RateLimitMiddleware._buckets = OrderedDict()
    security.RateLimitMiddleware._lock = asyncio.Lock()
    security.RateLimitMiddleware._rps = 2.0
    security.RateLimitMiddleware._burst = 120
    security.RateLimitMiddleware._max_buckets = 10_000
    security.RateLimitMiddleware._bucket_ttl = 300.0
    security.RateLimitMiddleware._capacity_rejections = 0
    security.RateLimitMiddleware._expired_prunes = 0
    security.AuditMiddleware._buf.clear()
    yield


def test_route_boundary_never_matches_prefix_lookalikes() -> None:
    assert security._matches_path_prefix("/api", "/api")
    assert security._matches_path_prefix("/api/jobs", "/api")
    assert not security._matches_path_prefix("/apiary", "/api")
    assert not security._matches_path_prefix("/api-v2", "/api")
    assert not security._matches_path_prefix("/api/health-check", "/api/health")


def test_untrusted_peer_cannot_select_identity_with_xff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(client="198.51.100.10", xff="203.0.113.77")
    assert security._request_client_ip(request) == "198.51.100.10"


def test_trusted_chain_uses_nearest_untrusted_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(
        client="10.0.0.10",
        xff="203.0.113.77, 10.0.0.8, 10.0.0.9",
    )
    assert security._request_client_ip(request) == "203.0.113.77"


def test_ambiguous_malformed_and_overlong_xff_fail_closed_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    duplicate = _request(
        client="10.0.0.10",
        xff=["203.0.113.1", "203.0.113.2"],
    )
    malformed = _request(client="10.0.0.10", xff="203.0.113.1, ,10.0.0.9")
    invalid = _request(client="10.0.0.10", xff="not-an-ip")
    overlong = _request(
        client="10.0.0.10",
        xff=",".join(f"192.0.2.{index % 250 + 1}" for index in range(33)),
    )
    for request in (duplicate, malformed, invalid, overlong):
        assert security._request_client_ip(request) == "10.0.0.10"


def test_malformed_proxy_configuration_disables_forwarded_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CODEDOCK_TRUSTED_PROXY_CIDRS",
        "10.0.0.0/8,definitely-not-a-cidr",
    )
    request = _request(client="10.0.0.10", xff="203.0.113.77")
    assert security._trusted_proxy_networks() == ()
    assert security._request_client_ip(request) == "10.0.0.10"


def test_all_trusted_forwarded_hops_do_not_create_fake_client_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(client="10.0.0.10", xff="10.0.0.7,10.0.0.8")
    assert security._request_client_ip(request) == "10.0.0.10"


def test_audit_content_length_parser_never_raises_on_hostile_headers() -> None:
    assert security._safe_content_length(_request(content_length="123")) == 123
    assert security._safe_content_length(_request(content_length=" 00123\t")) == 123
    assert security._safe_content_length(_request(content_length="-1")) == 0
    assert security._safe_content_length(_request(content_length="1,2")) == 0
    assert security._safe_content_length(_request(content_length="9" * 10000)) == 0
    assert security._safe_content_length(_request(content_length=["1", "1"])) == 0


def test_audit_request_id_rejects_duplicates_controls_and_oversize() -> None:
    valid = _request(request_id="trace-2026.09:abc")
    assert security._safe_request_id(valid) == "trace-2026.09:abc"

    unsafe_requests = [
        _request(request_id=["one", "two"]),
        _request(request_id="bad id"),
        _request(request_id="a" * 65),
    ]
    generated = {security._safe_request_id(request) for request in unsafe_requests}
    assert len(generated) == len(unsafe_requests)
    for request_id in generated:
        assert len(request_id) == 16
        int(request_id, 16)


def test_audit_redacts_exception_text_and_uses_boundary_matching() -> None:
    middleware = security.AuditMiddleware(object(), max_entries=5000)

    async def fail(_request: Request) -> Response:
        raise RuntimeError("secret-token-must-not-be-persisted")

    with pytest.raises(RuntimeError):
        asyncio.run(middleware.dispatch(_request(), fail))
    assert security.AuditMiddleware._buf[-1]["error"] == "RuntimeError"
    assert "secret-token" not in repr(security.AuditMiddleware._buf[-1])

    before = len(security.AuditMiddleware._buf)

    async def ok(_request: Request) -> Response:
        return Response(status_code=204)

    response = asyncio.run(middleware.dispatch(_request(path="/apiary"), ok))
    assert response.status_code == 204
    assert len(security.AuditMiddleware._buf) == before


def test_rate_limiter_rejects_invalid_configuration() -> None:
    cases = [
        {"rps": 0},
        {"rps": float("nan")},
        {"rps": float("inf")},
        {"burst": 0},
        {"max_buckets": 0},
        {"bucket_ttl": 0},
        {"bucket_ttl": float("inf")},
    ]
    for kwargs in cases:
        with pytest.raises(ValueError):
            security.RateLimitMiddleware(object(), **kwargs)


def test_whitelist_uses_exact_or_child_boundaries() -> None:
    middleware = security.RateLimitMiddleware(object())
    assert middleware._is_whitelisted("/api/telemetry/event")
    assert not middleware._is_whitelisted("/api/telemetry/eventual")
    assert middleware._is_whitelisted("/api/health")
    assert middleware._is_whitelisted("/api/health/live")
    assert not middleware._is_whitelisted("/api/health-check")


def test_rate_state_saturation_rejects_new_identity_without_evicting_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([100.0, 100.0, 100.0, 100.0])
    monkeypatch.setattr(security, "_monotonic", lambda: next(times))
    middleware = security.RateLimitMiddleware(
        object(), rps=1, burst=1, max_buckets=1, bucket_ttl=300
    )

    async def ok(_request: Request) -> Response:
        return Response(status_code=204)

    first = asyncio.run(middleware.dispatch(_request(client="198.51.100.1"), ok))
    exhausted = asyncio.run(middleware.dispatch(_request(client="198.51.100.1"), ok))
    newcomer = asyncio.run(middleware.dispatch(_request(client="198.51.100.2"), ok))

    assert first.status_code == 204
    assert exhausted.status_code == 429
    assert newcomer.status_code == 429
    assert list(security.RateLimitMiddleware._buckets) == [
        ("198.51.100.1", "/api/test")
    ]
    assert security.RateLimitMiddleware._capacity_rejections == 1


def test_expired_bucket_is_pruned_before_new_identity_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([100.0, 111.0])
    monkeypatch.setattr(security, "_monotonic", lambda: next(times))
    middleware = security.RateLimitMiddleware(
        object(), rps=1, burst=1, max_buckets=1, bucket_ttl=10
    )

    async def ok(_request: Request) -> Response:
        return Response(status_code=204)

    first = asyncio.run(middleware.dispatch(_request(client="198.51.100.1"), ok))
    second = asyncio.run(middleware.dispatch(_request(client="198.51.100.2"), ok))
    assert first.status_code == second.status_code == 204
    assert list(security.RateLimitMiddleware._buckets) == [
        ("198.51.100.2", "/api/test")
    ]
    assert security.RateLimitMiddleware._expired_prunes == 1


def test_monotonic_clock_regression_cannot_mint_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([100.0, 90.0])
    monkeypatch.setattr(security, "_monotonic", lambda: next(times))
    middleware = security.RateLimitMiddleware(
        object(), rps=100, burst=1, max_buckets=4, bucket_ttl=300
    )

    async def ok(_request: Request) -> Response:
        return Response(status_code=204)

    first = asyncio.run(middleware.dispatch(_request(), ok))
    second = asyncio.run(middleware.dispatch(_request(), ok))
    assert first.status_code == 204
    assert second.status_code == 429
    bucket = security.RateLimitMiddleware._buckets[("198.51.100.10", "/api/test")]
    assert bucket.last_refill == 100.0


def test_missing_client_identity_shares_bounded_rate_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([100.0, 100.0])
    monkeypatch.setattr(security, "_monotonic", lambda: next(times))
    middleware = security.RateLimitMiddleware(
        object(), rps=1, burst=1, max_buckets=4, bucket_ttl=300
    )

    async def ok(_request: Request) -> Response:
        return Response(status_code=204)

    first = asyncio.run(middleware.dispatch(_request(client=None), ok))
    second = asyncio.run(middleware.dispatch(_request(client=None), ok))
    assert first.status_code == 204
    assert second.status_code == 429
    assert ("unknown", "/api/test") in security.RateLimitMiddleware._buckets
