"""Adversarial regression coverage for the integrated API middleware boundary."""

from __future__ import annotations

import asyncio
import ipaddress
import json

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from api_middleware import RateLimiterMiddleware, RequestIdMiddleware


def _request(
    *,
    path: str = "/api/test",
    client_host: str | None = "192.0.2.10",
    request_ids: str | list[str] | None = None,
    xff: str | list[str] | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if request_ids is not None:
        values = [request_ids] if isinstance(request_ids, str) else request_ids
        headers.extend((b"x-request-id", value.encode("latin-1")) for value in values)
    if xff is not None:
        values = [xff] if isinstance(xff, str) else xff
        headers.extend((b"x-forwarded-for", value.encode("latin-1")) for value in values)
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": (client_host, 12345) if client_host is not None else None,
            "server": ("test", 80),
            "scheme": "http",
        }
    )


async def _handler(request: Request) -> Response:
    response = Response(status_code=204)
    response.headers["X-Test-Request-Id"] = getattr(request.state, "request_id", "-")
    return response


def _run_request_id(request_ids: str | list[str] | None) -> tuple[str, str, str]:
    request = _request(request_ids=request_ids)

    async def exercise() -> tuple[str, str, str]:
        response = await RequestIdMiddleware(object()).dispatch(request, _handler)
        return (
            request.state.request_id,
            response.headers["x-request-id"],
            response.headers["x-test-request-id"],
        )

    return asyncio.run(exercise())


def _assert_generated(values: tuple[str, str, str]) -> str:
    state_id, response_id, downstream_id = values
    assert state_id == response_id == downstream_id
    assert len(state_id) == 32
    assert state_id.isascii()
    int(state_id, 16)
    return state_id


def test_safe_request_id_round_trips_unchanged() -> None:
    state_id, response_id, downstream_id = _run_request_id("trace_2026-09-15:abc")
    assert state_id == "trace_2026-09-15:abc"
    assert state_id == response_id == downstream_id


def test_request_id_boundary_replaces_ambiguous_or_unsafe_values() -> None:
    cases: list[str | list[str] | None] = [
        None,
        "bad id",
        "bad\nvalue",
        "caf\xe9",
        "a" * 129,
        ["one", "two"],
        ["same", "same"],
    ]
    generated = {_assert_generated(_run_request_id(value)) for value in cases}
    assert len(generated) == len(cases)


def test_request_id_accepts_bounded_ascii_edge() -> None:
    value = "a" * 128
    state_id, response_id, downstream_id = _run_request_id(value)
    assert state_id == response_id == downstream_id == value


def test_request_id_generation_has_no_small_sample_collisions() -> None:
    generated = {_assert_generated(_run_request_id(None)) for _ in range(128)}
    assert len(generated) == 128


def test_trusted_proxy_parser_fails_closed_on_any_bad_entry() -> None:
    assert api_middleware._parse_trusted_proxy_networks("10.0.0.0/8,not-a-cidr") == ()


def test_untrusted_peer_cannot_spoof_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    request = _request(client_host="198.51.100.20", xff="203.0.113.99")
    assert api_middleware._client_ip(request) == "198.51.100.20"


def test_trusted_proxy_chain_walks_right_to_left(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    request = _request(
        client_host="10.0.0.10",
        xff="203.0.113.7, 10.0.0.8, 10.0.0.9",
    )
    assert api_middleware._client_ip(request) == "203.0.113.7"


def test_ambiguous_or_malformed_xff_falls_back_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    duplicate = _request(
        client_host="10.0.0.10",
        xff=["203.0.113.1", "203.0.113.2"],
    )
    malformed = _request(client_host="10.0.0.10", xff="203.0.113.1, ,10.0.0.9")
    invalid = _request(client_host="10.0.0.10", xff="not-an-ip")
    assert api_middleware._client_ip(duplicate) == "10.0.0.10"
    assert api_middleware._client_ip(malformed) == "10.0.0.10"
    assert api_middleware._client_ip(invalid) == "10.0.0.10"


def test_all_trusted_forwarded_hops_fall_back_to_direct_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    request = _request(client_host="10.0.0.10", xff="10.0.0.7,10.0.0.8")
    assert api_middleware._client_ip(request) == "10.0.0.10"


def test_route_prefix_matching_rejects_lookalikes() -> None:
    assert api_middleware._matches_path_prefix("/api")
    assert api_middleware._matches_path_prefix("/api/health")
    assert not api_middleware._matches_path_prefix("/apix")
    assert not api_middleware._matches_path_prefix("/api-v2")
    assert not api_middleware._matches_path_prefix("/API/test")


def _admit(limiter: RateLimiterMiddleware, ip: str):
    async def exercise():
        async with limiter._get_state_lock():
            return limiter._bucket_for(ip)

    return asyncio.run(exercise())


def test_rate_limiter_prunes_expired_state_and_stays_bounded() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=60, burst=1, max_buckets=3, bucket_ttl=300
    )
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        bucket, retry = _admit(limiter, ip)
        assert bucket is not None
        assert retry == 0.0

    limiter._buckets["10.0.0.1"].last -= 301
    bucket, retry = _admit(limiter, "10.0.0.4")
    assert bucket is not None
    assert retry == 0.0
    assert len(limiter._buckets) == 3
    assert "10.0.0.1" not in limiter._buckets
    assert limiter._expired_pruned == 1


def test_rate_limiter_saturation_preserves_active_bucket_state() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=1, burst=1, max_buckets=2, bucket_ttl=300
    )
    tracked, _ = _admit(limiter, "203.0.113.10")
    second, _ = _admit(limiter, "203.0.113.11")
    assert tracked is not None and second is not None
    consumed, _ = tracked.take()
    assert consumed
    tracked_identity = id(tracked)

    for index in range(100):
        newcomer, retry = _admit(limiter, f"198.18.0.{index}")
        assert newcomer is None
        assert retry > 0

    tracked_again, _ = _admit(limiter, "203.0.113.10")
    assert tracked_again is not None
    assert id(tracked_again) == tracked_identity
    consumed, retry = tracked_again.take()
    assert not consumed
    assert retry > 0
    assert len(limiter._buckets) == 2
    assert limiter._saturation_rejections == 100


def test_rate_limiter_serializes_concurrent_high_cardinality_admission() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=600, burst=1, max_buckets=8, bucket_ttl=300
    )

    async def exercise() -> tuple[int, int]:
        async def add(index: int) -> bool:
            async with limiter._get_state_lock():
                bucket, retry = limiter._bucket_for(f"192.0.2.{index}")
                if bucket is None:
                    assert retry > 0
                    return False
                assert retry == 0.0
                return True

        results = await asyncio.gather(*(add(index) for index in range(64)))
        return sum(results), len(results) - sum(results)

    admitted, rejected = asyncio.run(exercise())
    assert admitted == 8
    assert rejected == 56
    assert len(limiter._buckets) == 8
    assert limiter._saturation_rejections == 56


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"per_minute": 0}, "per_minute must be positive"),
        ({"burst": 0}, "burst must be positive"),
        ({"max_buckets": 0}, "max_buckets must be positive"),
        ({"bucket_ttl": 0}, "bucket_ttl must be a positive finite number"),
        ({"bucket_ttl": float("inf")}, "bucket_ttl must be a positive finite number"),
    ],
)
def test_rate_limiter_rejects_nonpositive_or_nonfinite_configuration(
    kwargs: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        RateLimiterMiddleware(object(), **kwargs)


def test_rate_limit_short_circuit_uses_one_canonical_request_id() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=1, burst=1, max_buckets=4, bucket_ttl=300
    )
    bucket, _ = _admit(limiter, "192.0.2.10")
    assert bucket is not None
    consumed, _ = bucket.take()
    assert consumed

    request = _request(request_ids=["first", "second"])
    response = asyncio.run(limiter.dispatch(request, _handler))
    payload = json.loads(response.body)
    assert response.status_code == 429
    assert len(request.state.request_id) == 32
    int(request.state.request_id, 16)
    assert response.headers["x-request-id"] == request.state.request_id
    assert payload["request_id"] == request.state.request_id


def test_rate_limiter_does_not_capture_api_prefix_lookalikes() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=1, burst=1, max_buckets=1, bucket_ttl=300
    )
    bucket, _ = _admit(limiter, "192.0.2.10")
    assert bucket is not None
    consumed, _ = bucket.take()
    assert consumed

    request = _request(path="/apix")
    response = asyncio.run(limiter.dispatch(request, _handler))
    assert response.status_code == 204


def test_missing_peer_identity_is_not_exempt_from_rate_limiting() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=1, burst=1, max_buckets=2, bucket_ttl=300
    )
    request_one = _request(client_host=None)
    request_two = _request(client_host=None)

    first = asyncio.run(limiter.dispatch(request_one, _handler))
    second = asyncio.run(limiter.dispatch(request_two, _handler))
    assert first.status_code == 204
    assert second.status_code == 429
