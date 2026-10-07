from __future__ import annotations

import socket

import pytest

from gameforge.rooms import room_api_gateway as gateway


_PUBLIC = [
    (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        ("93.184.216.34", 443),
    )
]


def _enable_host(monkeypatch: pytest.MonkeyPatch, host: str = "api.example.com") -> None:
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({host}))
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *args, **kwargs: list(_PUBLIC))


def test_prepare_external_request_separates_authority_from_path_and_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_host(monkeypatch)

    origin, target = gateway._prepare_external_request(
        "https://api.example.com//evil.example/v1?q=https://internal.example/"
    )

    assert origin == "https://api.example.com"
    assert target == "/evil.example/v1?q=https://internal.example/"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://user:pass@api.example.com/v1",
        "https://api.example.com:444/v1",
        "https://api.example.com/v1#fragment",
        "https://api.example.com\\@evil.example/v1",
        "https://evil.example/v1",
    ],
)
def test_prepare_external_request_rejects_authority_confusion(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    _enable_host(monkeypatch)

    with pytest.raises(ValueError):
        gateway._prepare_external_request(url)


def test_prepare_external_request_rejects_private_dns_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({"api.example.com"}))
    monkeypatch.setattr(
        gateway.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            )
        ],
    )

    with pytest.raises(ValueError, match="non-public"):
        gateway._prepare_external_request("https://api.example.com/v1")


def test_request_method_and_timeout_are_bounded() -> None:
    assert gateway._safe_method("get") == "GET"
    assert gateway._safe_timeout("8") == 8.0

    with pytest.raises(ValueError):
        gateway._safe_method("CONNECT")
    with pytest.raises(ValueError):
        gateway._safe_timeout("inf")
    with pytest.raises(ValueError):
        gateway._safe_timeout("31")


def test_forwarded_host_and_header_injection_are_rejected() -> None:
    with pytest.raises(ValueError):
        gateway._safe_headers({"Host": "internal.example"})
    with pytest.raises(ValueError):
        gateway._safe_headers({"X-Test": "ok\r\nHost: internal.example"})
