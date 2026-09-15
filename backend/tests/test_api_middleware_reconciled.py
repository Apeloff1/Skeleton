"""Adversarial regressions for the reconciled API trust boundary."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from api_middleware import RateLimiterMiddleware, RequestIdMiddleware


def _request(
    *,
    path: str = "/api/test",
    client_host: str = "192.0.2.10",
    xff: str | None = None,
    request_ids: str | list[str] | None = None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("latin-1")))
    if request_ids is not None:
        values = [request_ids] if isinstance(request_ids, str) else request_ids
        headers.extend((b"x-request-id", value.encode("latin-1")) for value in values)
    if extra_headers:
        headers.extend(extra_headers)
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers,
            "client": (client_host, 43210),
            "server": ("testserver", 80),
        }
    )


def _trust(monkeypatch, *cidrs: str) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        tuple(ipaddress.ip_network(value) for value in cidrs),
    )


def test_untrusted_peer_cannot_spoof_forwarded_identity(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request(client_host="198.51.100.24", xff="203.0.113.99")
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_trusted_proxy_chain_resolves_nearest_untrusted_hop(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "203.0.113.0/24")
    request = _request(
        client_host="10.0.0.5",
        xff="198.51.100.24, 203.0.113.7",
    )
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_malformed_duplicate_and_all_trusted_xff_fail_closed(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "203.0.113.0/24")
    malformed = _request(client_host="10.0.0.5", xff="198.51.100.24, nope")
    duplicate = _request(
        client_host="10.0.0.5",
        extra_headers=[
            (b"x-forwarded-for", b"198.51.100.24"),
            (b"x-forwarded-for", b"203.0.113.7"),
        ],
    )
    all_trusted = _request(client_host="10.0.0.5", xff="203.0.113.7")
    assert api_middleware._client_ip(malformed) == "10.0.0.5"
    assert api_middleware._client_ip(duplicate) == "10.0.0.5"
    assert api_middleware._client_ip(all_trusted) == "10.0.0.5"


def test_malformed_proxy_allowlist_disables_forwarded_trust() -> None:
    assert api_middleware._parse_trusted_proxy_networks(
        "10.0.0.0/8, definitely-not-a-cidr"
    ) == ()


def test_request_id_rejects_ambiguous_unsafe_and_oversized_values() -> None:
    accepted = _request(request_ids="trace_2026-09-15:abc")
    duplicate = _request(request_ids=["same", "same"])
    unsafe = _request(request_ids="bad id")
    oversized = _request(request_ids="a" * 129)
    assert api_middleware._request_id(accepted) == "trace_2026-09-15:abc"
    for request in (duplicate, unsafe, oversized):
        generated = api_middleware._request_id(request)
        assert len(generated) == 32
        int(generated, 16)


def test_request_id_middleware_uses_one_value_everywhere() -> None:
    request = _request(request_ids="trace-safe:1")

    async def handler(inner: Request) -> Response:
        response = Response(status_code=200)
        response.headers["X-Test-Request-Id"] = inner.state.request_id
        return response

    response = asyncio.run(RequestIdMiddleware(object()).dispatch(request, handler))
    assert request.state.request_id == "trace-safe:1"
    assert response.headers["x-request-id"] == "trace-safe:1"
    assert response.headers["x-test-request-id"] == "trace-safe:1"


def test_api_route_matching_is_segment_aware() -> None:
    assert api_middleware._is_api_path("/api")
    assert api_middleware._is_api_path("/api/health")
    assert not api_middleware._is_api_path("/apiary")
    assert not api_middleware._is_api_path("/api-v2")


def test_rate_limiter_prunes_only_expired_state() -> None:
    limiter = RateLimiterMiddleware(object(), per_minute=60, burst=1, max_buckets=3, bucket_ttl=300)
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        bucket, retry = limiter._bucket_for(ip)
        assert bucket is not None and retry == 0.0
    limiter._buckets["10.0.0.1"].last -= 301
    bucket, retry = limiter._bucket_for("10.0.0.4")
    assert bucket is not None and retry == 0.0
    assert set(limiter._buckets) == {"10.0.0.2", "10.0.0.3", "10.0.0.4"}
    assert limiter._expired_pruned == 1


def test_rate_limiter_saturation_preserves_active_state() -> None:
    limiter = RateLimiterMiddleware(object(), per_minute=1, burst=1, max_buckets=2, bucket_ttl=300)
    tracked, _ = limiter._bucket_for("203.0.113.10")
    other, _ = limiter._bucket_for("203.0.113.11")
    assert tracked is not None and other is not None
    consumed, _ = tracked.take()
    assert consumed
    tracked_identity = id(tracked)
    for i in range(32):
        newcomer, retry = limiter._bucket_for(f"198.18.0.{i}")
        assert newcomer is None and retry > 0
    tracked_again, _ = limiter._bucket_for("203.0.113.10")
    assert tracked_again is not None and id(tracked_again) == tracked_identity
    consumed, retry = tracked_again.take()
    assert not consumed and retry > 0


def test_rate_limiter_serializes_concurrent_cardinality_admission() -> None:
    limiter = RateLimiterMiddleware(object(), per_minute=600, burst=1, max_buckets=8, bucket_ttl=300)

    async def add(i: int) -> bool:
        async with limiter._get_state_lock():
            bucket, _ = limiter._bucket_for(f"192.0.2.{i}")
            return bucket is not None

    admitted = asyncio.run(asyncio.gather(*(add(i) for i in range(64)))) if False else None
    # asyncio.gather needs a running loop; keep the test independent of pytest-asyncio.
    async def exercise() -> list[bool]:
        return await asyncio.gather(*(add(i) for i in range(64)))

    results = asyncio.run(exercise())
    assert sum(results) == 8
    assert len(limiter._buckets) == 8
    assert limiter._saturation_rejections == 56


@pytest.mark.parametrize(
    "kwargs",
    [
        {"per_minute": 0},
        {"per_minute": -1},
        {"per_minute": math.inf},
        {"per_minute": math.nan},
        {"burst": 0},
        {"burst": -1},
        {"bucket_ttl": 0},
        {"bucket_ttl": math.inf},
        {"max_buckets": 0},
    ],
)
def test_rate_limiter_rejects_invalid_configuration(kwargs) -> None:
    with pytest.raises(ValueError):
        RateLimiterMiddleware(object(), **kwargs)


def test_retry_after_is_always_finite_and_bounded() -> None:
    assert api_middleware._bounded_retry_after(float("inf")) == 86_400
    assert api_middleware._bounded_retry_after(0.0001) == 1
    assert api_middleware._bounded_retry_after(999_999_999) == 86_400


def test_outer_rate_limit_short_circuit_propagates_canonical_request_id() -> None:
    request = _request(request_ids=["first", "second"])
    limiter = RateLimiterMiddleware(object(), per_minute=1, burst=1)
    bucket, _ = limiter._bucket_for("192.0.2.10")
    assert bucket is not None
    consumed, _ = bucket.take()
    assert consumed

    async def should_not_run(_request: Request) -> Response:
        raise AssertionError("rate-limited request reached downstream")

    response = asyncio.run(limiter.dispatch(request, should_not_run))
    payload = json.loads(response.body)
    assert response.status_code == 429
    assert len(request.state.request_id) == 32
    assert response.headers["x-request-id"] == request.state.request_id
    assert payload["request_id"] == request.state.request_id


def test_non_api_lookalike_bypasses_rate_limiter() -> None:
    request = _request(path="/apiary", client_host="198.51.100.2")
    limiter = RateLimiterMiddleware(object(), per_minute=1, burst=1)

    async def handler(_request: Request) -> Response:
        return Response(status_code=204)

    response = asyncio.run(limiter.dispatch(request, handler))
    assert response.status_code == 204
    assert limiter._buckets == {}
