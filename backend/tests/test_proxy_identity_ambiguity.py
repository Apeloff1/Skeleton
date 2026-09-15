"""Regression coverage for ambiguous proxy and request identity headers."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

import api_middleware


def _request(client_host: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": headers,
            "client": (client_host, 43210),
            "server": ("testserver", 80),
        }
    )


def test_quoted_xff_token_fails_closed_to_direct_peer(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    request = _request(
        "10.0.0.5",
        [(b"x-forwarded-for", b'"198.51.100.24", 10.0.0.7')],
    )

    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_duplicate_request_id_field_lines_are_replaced() -> None:
    request = _request(
        "198.51.100.24",
        [
            (b"x-request-id", b"trace-a"),
            (b"x-request-id", b"trace-b"),
        ],
    )

    request_id = api_middleware._request_id(request)
    assert request_id not in {"trace-a", "trace-b"}
    assert len(request_id) == 32
