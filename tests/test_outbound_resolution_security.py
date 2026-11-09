from __future__ import annotations

import socket

import pytest

from skeleton.security.outbound_url import (
    resolve_public_https_url,
    validate_connected_peer,
    validate_public_https_redirect,
    validate_resolution_set,
)


def answer(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def test_public_dns_snapshot_is_returned() -> None:
    destination = resolve_public_https_url(
        "https://example.com/hook",
        resolver=lambda *_args: [answer("93.184.216.34")],
    )
    assert destination.host == "example.com"
    assert destination.addresses == ("93.184.216.34",)
    assert validate_connected_peer(destination, "93.184.216.34") == "93.184.216.34"


def test_mixed_public_private_dns_answers_fail_closed() -> None:
    with pytest.raises(ValueError, match="non-public"):
        resolve_public_https_url(
            "https://example.com/hook",
            resolver=lambda *_args: [
                answer("93.184.216.34"),
                answer("127.0.0.1"),
            ],
        )


def test_dns_rebinding_peer_mismatch_is_rejected() -> None:
    destination = resolve_public_https_url(
        "https://example.com/hook",
        resolver=lambda *_args: [answer("93.184.216.34")],
    )
    with pytest.raises(ValueError, match="does not match"):
        validate_connected_peer(destination, "93.184.216.35")
    with pytest.raises(ValueError, match="not public"):
        validate_connected_peer(destination, "10.0.0.2")


def test_resolution_answer_count_is_bounded() -> None:
    answers = [answer(f"8.8.8.{index}") for index in range(1, 18)]
    with pytest.raises(ValueError, match="address bound"):
        resolve_public_https_url(
            "https://example.com/hook",
            resolver=lambda *_args: answers,
        )


def test_redirect_revalidation_rejects_cross_origin_by_default() -> None:
    with pytest.raises(ValueError, match="changes origin"):
        validate_public_https_redirect(
            "https://example.com/start",
            "https://other.example.com/next",
        )

    assert validate_public_https_redirect(
        "https://example.com/start",
        "https://example.com/next",
    ) == ("https://example.com/next", "example.com")


def test_pre_resolved_set_rejects_private_or_empty() -> None:
    with pytest.raises(ValueError):
        validate_resolution_set([])
    with pytest.raises(ValueError):
        validate_resolution_set(["169.254.169.254"])
    assert validate_resolution_set(["1.1.1.1", "8.8.8.8"]) == ("1.1.1.1", "8.8.8.8")
