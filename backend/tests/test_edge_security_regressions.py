from __future__ import annotations

import asyncio
import ipaddress
import math
import sys
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import Response

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from middleware import security  # noqa: E402
from middleware.security import AuditMiddleware, RateLimitMiddleware  # noqa: E402


class _App:
    pass


def _request(
    peer: str | None,
    *,
    path: str = "/api/run",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers or [],
        "client": (peer, 12345) if peer is not None else None,
        "server": ("testserver", 80),
    }
    return Request(scope)


def _networks(*cidrs: str):
    return tuple(ipaddress.ip_network(value) for value in cidrs)


def _reset_rate_state() -> None:
    RateLimitMiddleware._buckets.clear()
    RateLimitMiddleware._lock = None
    RateLimitMiddleware._saturation_rejections = 0
    RateLimitMiddleware._expired_pruned = 0


def test_untrusted_peer_cannot_spoof_xff() -> None:
    request = _request(
        "198.51.100.10",
        headers=[(b"x-forwarded-for", b"203.0.113.99")],
    )
    assert security._client_ip(request, _networks("10.0.0.0/8")) == "198.51.100.10"


def test_trusted_proxy_chain_uses_nearest_untrusted_hop() -> None:
    request = _request(
        "10.0.0.5",
        headers=[(b"x-forwarded-for", b"192.0.2.250, 198.51.100.24")],
    )
    assert security._client_ip(request, _networks("10.0.0.0/8")) == "198.51.100.24"


def test_duplicate_xff_fails_closed_to_direct_peer() -> None:
    request = _request(
        "10.0.0.5",
        headers=[
            (b"x-forwarded-for", b"198.51.100.1"),
            (b"x-forwarded-for", b"198.51.100.2"),
        ],
    )
    assert security._client_ip(request, _networks("10.0.0.0/8")) == "10.0.0.5"


def test_empty_or_malformed_forwarded_hops_fail_closed() -> None:
    networks = _networks("10.0.0.0/8")
    empty = _request(
        "10.0.0.5",
        headers=[(b"x-forwarded-for", b"198.51.100.1, , 203.0.113.2")],
    )
    malformed = _request(
        "10.0.0.5",
        headers=[(b"x-forwarded-for", b"198.51.100.1, not-an-ip")],
    )
    assert security._client_ip(empty, networks) == "10.0.0.5"
    assert security._client_ip(malformed, networks) == "10.0.0.5"


def test_request_id_rejects_controls_duplicates_and_oversize() -> None:
    valid = _request(
        "198.51.100.1", headers=[(b"x-request-id", b"trace-01.prod:abc_123")]
    )
    newline = _request(
        "198.51.100.1", headers=[(b"x-request-id", b"trace\r\ninjected")]
    )
    duplicate = _request(
        "198.51.100.1",
        headers=[(b"x-request-id", b"one"), (b"x-request-id", b"two")],
    )
    oversized = _request(
        "198.51.100.1", headers=[(b"x-request-id", b"a" * 129)]
    )

    assert security._safe_request_id(valid) == "trace-01.prod:abc_123"
    for request in (newline, duplicate, oversized):
        value = security._safe_request_id(request)
        assert len(value) == 16
        assert value.isalnum()


def test_route_matching_is_segment_aware() -> None:
    assert security._matches_route_boundary("/api", "/api")
    assert security._matches_route_boundary("/api/jobs", "/api")
    assert security._matches_route_boundary("/api/security/audit", "/api/security")
    assert not security._matches_route_boundary("/apiary", "/api")
    assert not security._matches_route_boundary("/api/health-check", "/api/health")
    assert not security._matches_route_boundary(
        "/api/telemetry/eventual", "/api/telemetry/event"
    )


@pytest.mark.parametrize("rps", [0.0, -1.0, math.inf, -math.inf, math.nan])
def test_rate_limiter_rejects_invalid_rps(rps: float) -> None:
    _reset_rate_state()
    with pytest.raises(ValueError):
        RateLimitMiddleware(_App(), rps=rps)


def test_rate_limiter_rejects_invalid_capacity_configuration() -> None:
    _reset_rate_state()
    with pytest.raises(ValueError):
        RateLimitMiddleware(_App(), burst=0)
    with pytest.raises(ValueError):
        RateLimitMiddleware(_App(), max_buckets=0)
    with pytest.raises(ValueError):
        RateLimitMiddleware(_App(), bucket_ttl=0)


def test_rate_limiter_prunes_idle_state_and_stays_bounded(monkeypatch) -> None:
    _reset_rate_state()
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "")
    limiter = RateLimitMiddleware(
        _App(), rps=1, burst=1, max_buckets=2, bucket_ttl=30
    )
    now = 1000.0
    RateLimitMiddleware._buckets[("198.51.100.1", "/api/run")] = security._Bucket(0, now - 31)
    RateLimitMiddleware._buckets[("198.51.100.2", "/api/run")] = security._Bucket(0, now)

    pruned = limiter._prune_expired(now)
    assert pruned == 1
    assert len(RateLimitMiddleware._buckets) == 1
    assert ("198.51.100.1", "/api/run") not in RateLimitMiddleware._buckets


def test_rate_limiter_saturation_preserves_active_state(monkeypatch) -> None:
    _reset_rate_state()
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "")
    limiter = RateLimitMiddleware(
        _App(), rps=1, burst=1, max_buckets=2, bucket_ttl=300
    )
    now = 1000.0
    first = security._Bucket(0, now)
    second = security._Bucket(0, now)
    RateLimitMiddleware._buckets[("198.51.100.1", "/api/run")] = first
    RateLimitMiddleware._buckets[("198.51.100.2", "/api/run")] = second

    assert limiter._prune_expired(now) == 0
    assert limiter._retry_until_capacity(now) > 0
    assert RateLimitMiddleware._buckets[("198.51.100.1", "/api/run")] is first
    assert RateLimitMiddleware._buckets[("198.51.100.2", "/api/run")] is second


def test_audit_content_length_parsing_never_raises() -> None:
    good = _request("198.51.100.1", headers=[(b"content-length", b"123")])
    malformed = _request("198.51.100.1", headers=[(b"content-length", b"-1")])
    duplicate = _request(
        "198.51.100.1",
        headers=[(b"content-length", b"1"), (b"content-length", b"1")],
    )
    absurd = _request(
        "198.51.100.1", headers=[(b"content-length", b"9" * 65)]
    )

    assert AuditMiddleware._declared_size(good) == 123
    assert AuditMiddleware._declared_size(malformed) is None
    assert AuditMiddleware._declared_size(duplicate) is None
    assert AuditMiddleware._declared_size(absurd) is None


def test_audit_sanitizes_request_id_and_control_text(monkeypatch) -> None:
    AuditMiddleware._buf.clear()
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "")
    middleware = AuditMiddleware(_App())
    request = _request(
        "198.51.100.1",
        headers=[
            (b"x-request-id", b"evil\r\nline"),
            (b"user-agent", b"agent\r\nspoof"),
        ],
    )

    async def call_next(_: Request) -> Response:
        return Response(status_code=204)

    response = asyncio.run(middleware.dispatch(request, call_next))
    assert response.status_code == 204
    row = AuditMiddleware._buf[-1]
    assert len(row["rid"]) == 16
    assert "\n" not in row["rid"] and "\r" not in row["rid"]
    assert "\n" not in row["ua"] and "\r" not in row["ua"]
    assert "\\r\\n" in row["ua"]
