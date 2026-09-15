"""Security regression tests for API middleware trust boundaries."""

from __future__ import annotations

import asyncio
import ipaddress

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from api_middleware import RateLimiterMiddleware


class _App:
    pass


def _request(
    client_host: str | None,
    *,
    path: str = "/api/test",
    xff: str | None = None,
    request_id: str | None = None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("latin-1")))
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("latin-1")))
    if extra_headers:
        headers.extend(extra_headers)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 43210) if client_host is not None else None,
        "server": ("testserver", 80),
    }
    return Request(scope)


def _trust(monkeypatch, *cidrs: str) -> None:
    networks = tuple(ipaddress.ip_network(value) for value in cidrs)
    monkeypatch.setattr(api_middleware, "_TRUSTED_PROXY_NETWORKS", networks)


def test_untrusted_peer_cannot_spoof_rate_limit_identity(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("198.51.100.24", xff="203.0.113.99")
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_trusted_proxy_uses_nearest_untrusted_forwarded_hop(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "203.0.113.0/24")
    request = _request("10.0.0.5", xff="198.51.100.24, 203.0.113.7")
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_leftmost_xff_spoof_does_not_override_nearest_client(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.5", xff="192.0.2.250, 198.51.100.24")
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_malformed_forwarded_chain_falls_back_to_peer(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.5", xff="198.51.100.24, not-an-ip")
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_empty_forwarded_hop_falls_back_to_peer(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.5", xff="198.51.100.24,,10.0.0.7")
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_duplicate_xff_field_lines_fail_closed_to_peer(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request(
        "10.0.0.5",
        extra_headers=[
            (b"x-forwarded-for", b"198.51.100.24"),
            (b"x-forwarded-for", b"203.0.113.7"),
        ],
    )
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_all_trusted_forwarded_hops_fail_closed_to_peer(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "203.0.113.0/24")
    request = _request("10.0.0.5", xff="203.0.113.7")
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_malformed_proxy_allowlist_disables_forwarded_trust_entirely() -> None:
    assert api_middleware._parse_trusted_proxy_networks(
        "10.0.0.0/8, definitely-not-a-cidr"
    ) == ()


def test_request_id_accepts_only_bounded_header_safe_values() -> None:
    accepted = _request("198.51.100.24", request_id="trace-01.prod:abc_123")
    rejected = _request("198.51.100.24", request_id="unsafe value with spaces")
    oversized = _request("198.51.100.24", request_id="a" * 129)

    assert api_middleware._request_id(accepted) == "trace-01.prod:abc_123"
    assert api_middleware._request_id(rejected) != "unsafe value with spaces"
    assert len(api_middleware._request_id(oversized)) == 32


def test_duplicate_request_id_headers_are_replaced() -> None:
    request = _request(
        "198.51.100.24",
        extra_headers=[
            (b"x-request-id", b"first"),
            (b"x-request-id", b"second"),
        ],
    )
    assert api_middleware._request_id(request) not in {"first", "second"}
    assert len(api_middleware._request_id(request)) == 32


def test_api_route_boundary_rejects_lookalike_prefixes() -> None:
    assert api_middleware._matches_path_prefix("/api")
    assert api_middleware._matches_path_prefix("/api/health")
    assert not api_middleware._matches_path_prefix("/apiary")
    assert not api_middleware._matches_path_prefix("/apis")
    assert not api_middleware._matches_path_prefix("/api-v2")


@pytest.mark.asyncio
async def test_rate_limiter_prunes_expired_state_and_stays_bounded() -> None:
    limiter = RateLimiterMiddleware(
        _App(), per_minute=60, burst=1, max_buckets=3, bucket_ttl=300
    )

    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        async with limiter._get_state_lock():
            bucket, retry = limiter._bucket_for(ip)
            assert bucket is not None
            assert retry == 0.0

    limiter._buckets["10.0.0.1"].last -= 301
    async with limiter._get_state_lock():
        bucket, retry = limiter._bucket_for("10.0.0.4")

    assert bucket is not None
    assert retry == 0.0
    assert len(limiter._buckets) == 3
    assert "10.0.0.1" not in limiter._buckets
    assert "10.0.0.4" in limiter._buckets
    assert limiter._expired_pruned == 1


@pytest.mark.asyncio
async def test_recent_consumption_reorders_bucket_for_constant_time_pruning() -> None:
    limiter = RateLimiterMiddleware(
        _App(), per_minute=60, burst=2, max_buckets=2, bucket_ttl=30
    )

    async def call_next(_request: Request) -> Response:
        return Response(status_code=204)

    assert (
        await limiter.dispatch(_request("198.51.100.1"), call_next)
    ).status_code == 204
    assert (
        await limiter.dispatch(_request("198.51.100.2"), call_next)
    ).status_code == 204
    assert (
        await limiter.dispatch(_request("198.51.100.1"), call_next)
    ).status_code == 204
    assert list(limiter._buckets) == ["198.51.100.2", "198.51.100.1"]

    limiter._buckets["198.51.100.2"].last -= 31
    assert (
        await limiter.dispatch(_request("198.51.100.3"), call_next)
    ).status_code == 204

    assert list(limiter._buckets) == ["198.51.100.1", "198.51.100.3"]
    assert limiter._expired_pruned == 1


@pytest.mark.asyncio
async def test_rate_limiter_hard_cap_rejects_concurrent_identity_churn() -> None:
    limiter = RateLimiterMiddleware(
        _App(), per_minute=600, burst=1, max_buckets=8, bucket_ttl=300
    )
    admitted = 0
    rejected = 0

    async def add_bucket(i: int) -> None:
        nonlocal admitted, rejected
        async with limiter._get_state_lock():
            bucket, retry = limiter._bucket_for(f"192.0.2.{i}")
            if bucket is None:
                rejected += 1
                assert retry > 0
            else:
                admitted += 1
                assert retry == 0.0

    await asyncio.gather(*(add_bucket(i) for i in range(64)))

    assert len(limiter._buckets) == 8
    assert admitted == 8
    assert rejected == 56
    assert limiter._saturation_rejections == 56


@pytest.mark.asyncio
async def test_saturation_does_not_evict_active_exhausted_bucket() -> None:
    limiter = RateLimiterMiddleware(
        _App(), per_minute=1, burst=1, max_buckets=2, bucket_ttl=300
    )

    async with limiter._get_state_lock():
        tracked, _ = limiter._bucket_for("203.0.113.10")
        second, _ = limiter._bucket_for("203.0.113.11")
        assert tracked is not None and second is not None
        ok, _ = tracked.take()
        assert ok
        tracked_identity = id(tracked)

    for i in range(100):
        async with limiter._get_state_lock():
            newcomer, retry = limiter._bucket_for(f"198.18.0.{i}")
            assert newcomer is None
            assert retry > 0

    async with limiter._get_state_lock():
        tracked_again, _ = limiter._bucket_for("203.0.113.10")
        assert tracked_again is not None
        assert id(tracked_again) == tracked_identity
        ok, retry = tracked_again.take()

    assert not ok
    assert retry > 0
    assert len(limiter._buckets) == 2


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"per_minute": 0}, "per_minute must be finite and positive"),
        ({"per_minute": float("nan")}, "per_minute must be finite and positive"),
        ({"per_minute": float("inf")}, "per_minute must be finite and positive"),
        ({"burst": 0}, "burst must be finite and positive"),
        ({"burst": float("nan")}, "burst must be finite and positive"),
        ({"max_buckets": 0}, "max_buckets must be finite and positive"),
        ({"max_buckets": float("inf")}, "max_buckets must be finite and positive"),
        ({"max_buckets": 1.5}, "max_buckets must be an integer"),
        ({"bucket_ttl": 0}, "bucket_ttl must be finite and positive"),
        ({"bucket_ttl": float("nan")}, "bucket_ttl must be finite and positive"),
        ({"bucket_ttl": float("inf")}, "bucket_ttl must be finite and positive"),
    ],
)
def test_rate_limiter_rejects_hostile_configuration(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        RateLimiterMiddleware(_App(), **kwargs)


@pytest.mark.parametrize(
    ("retry", "expected"),
    [
        (0.0, 1),
        (0.1, 1),
        (1.2, 2),
        (86_399.1, 86_400),
        (90_000.0, 86_400),
        (float("inf"), 86_400),
        (float("nan"), 86_400),
    ],
)
def test_retry_after_is_finite_and_bounded(retry, expected) -> None:
    assert api_middleware._bounded_retry_after(retry) == expected
