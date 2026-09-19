from __future__ import annotations

import socket

import pytest

from skeleton.security.outbound_url import (
    ResolvedDestination,
    resolve_public_https_url,
    validate_connected_peer,
    validate_public_https_redirect,
    validate_public_https_url,
    validate_resolution_set,
)


def answer(address: str, port: int = 443):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (
        (address, port, 0, 0)
        if family == socket.AF_INET6
        else (address, port)
    )
    return (
        family,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        sockaddr,
    )


def resolver_for(*addresses: str):
    def resolve(
        host: str,
        port: int,
        family: int,
        socktype: int,
        proto: int,
    ):
        assert host
        assert port > 0
        assert family == socket.AF_UNSPEC
        assert socktype == socket.SOCK_STREAM
        assert proto == socket.IPPROTO_TCP
        return [answer(item, port) for item in addresses]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        " http://example.com/",
        "https://example.com/ ",
        "https://example.com/\n",
        "https://example.com/\x00",
    ],
)
def test_url_input_must_be_canonical_not_trimmed(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_https_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/",
        "https://service.local/",
        "https://service.localdomain/",
        "https://service.internal/",
        "https://metadata.google.internal/",
        "https://127.0.0.1/",
        "https://10.0.0.1/",
        "https://169.254.169.254/",
        "https://[::1]/",
        "https://[fe80::1]/",
        "https://224.0.0.1/",
        "https://0.0.0.0/",
        "https://internal/",
    ],
)
def test_syntax_policy_rejects_local_or_non_public_targets(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_https_url(url)


def test_public_literal_ip_skips_dns_but_still_builds_snapshot() -> None:
    called = False

    def resolver(*_args):
        nonlocal called
        called = True
        raise AssertionError("literal IP should not require DNS")

    destination = resolve_public_https_url(
        "https://8.8.8.8/resource",
        resolver=resolver,
    )

    assert called is False
    assert destination.addresses == ("8.8.8.8",)
    assert destination.host == "8.8.8.8"
    assert destination.port == 443


def test_public_dns_answers_are_canonicalized_and_deduplicated() -> None:
    destination = resolve_public_https_url(
        "https://api.example.com/resource",
        resolver=resolver_for(
            "8.8.8.8",
            "1.1.1.1",
            "8.8.8.8",
        ),
    )

    assert destination.addresses == ("1.1.1.1", "8.8.8.8")


@pytest.mark.parametrize(
    "private_address",
    [
        "127.0.0.1",
        "10.0.0.10",
        "172.16.1.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_mixed_dns_answer_with_any_private_address_fails_closed(
    private_address: str,
) -> None:
    with pytest.raises(ValueError, match="non-public"):
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=resolver_for("8.8.8.8", private_address),
        )


def test_empty_dns_answer_fails_closed() -> None:
    with pytest.raises(ValueError, match="no addresses"):
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=lambda *_args: [],
        )


def test_dns_failure_is_redacted_to_generic_error() -> None:
    secret = "signed-url-secret-value"

    def explode(*_args):
        raise OSError(secret)

    with pytest.raises(ValueError, match="DNS resolution failed") as caught:
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=explode,
        )

    assert secret not in str(caught.value)


def test_dns_answer_count_is_bounded() -> None:
    addresses = [
        f"8.8.8.{index}"
        for index in range(1, 18)
    ]
    with pytest.raises(ValueError, match="address bound"):
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=resolver_for(*addresses),
        )


def test_custom_lower_address_bound_is_enforced() -> None:
    with pytest.raises(ValueError, match="address bound"):
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=resolver_for("8.8.8.8", "1.1.1.1"),
            max_addresses=1,
        )


@pytest.mark.parametrize("bound", [0, -1, 17, True, 1.5])
def test_invalid_resolution_bounds_are_rejected(bound: object) -> None:
    with pytest.raises(ValueError):
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=resolver_for("8.8.8.8"),
            max_addresses=bound,  # type: ignore[arg-type]
        )


def test_malformed_dns_evidence_fails_closed() -> None:
    with pytest.raises(ValueError, match="malformed"):
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=lambda *_args: [("bad",)],
        )


def test_non_text_dns_address_fails_closed() -> None:
    malformed = (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        (12345, 443),
    )
    with pytest.raises(ValueError, match="non-text"):
        resolve_public_https_url(
            "https://api.example.com/",
            resolver=lambda *_args: [malformed],
        )


def test_connect_time_peer_must_match_approved_resolution_snapshot() -> None:
    destination = ResolvedDestination(
        url="https://api.example.com/",
        host="api.example.com",
        port=443,
        addresses=("8.8.8.8", "1.1.1.1"),
    )

    assert validate_connected_peer(destination, "8.8.8.8") == "8.8.8.8"

    with pytest.raises(ValueError, match="does not match"):
        validate_connected_peer(destination, "9.9.9.9")


@pytest.mark.parametrize(
    "peer",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
    ],
)
def test_connect_time_peer_can_never_be_private(peer: str) -> None:
    destination = ResolvedDestination(
        url="https://api.example.com/",
        host="api.example.com",
        port=443,
        addresses=("8.8.8.8",),
    )

    with pytest.raises(ValueError, match="not public"):
        validate_connected_peer(destination, peer)


def test_same_origin_https_redirect_is_allowed() -> None:
    target, host = validate_public_https_redirect(
        "https://api.example.com/start",
        "https://api.example.com/next?cursor=1",
    )

    assert target == "https://api.example.com/next?cursor=1"
    assert host == "api.example.com"


def test_explicit_default_port_is_same_origin() -> None:
    target, host = validate_public_https_redirect(
        "https://api.example.com/start",
        "https://api.example.com:443/next",
    )

    assert target.endswith(":443/next")
    assert host == "api.example.com"


@pytest.mark.parametrize(
    "target",
    [
        "https://other.example.com/next",
        "https://api.example.com:444/next",
        "https://127.0.0.1/next",
        "http://api.example.com/next",
        "https://user:pass@api.example.com/next",
    ],
)
def test_redirect_revalidates_and_rejects_origin_or_security_change(
    target: str,
) -> None:
    with pytest.raises(ValueError):
        validate_public_https_redirect(
            "https://api.example.com/start",
            target,
        )


def test_cross_origin_redirect_requires_explicit_opt_in() -> None:
    target, host = validate_public_https_redirect(
        "https://api.example.com/start",
        "https://cdn.example.net/next",
        allow_cross_origin=True,
    )

    assert target == "https://cdn.example.net/next"
    assert host == "cdn.example.net"


def test_cross_origin_opt_in_still_rejects_private_destination() -> None:
    with pytest.raises(ValueError):
        validate_public_https_redirect(
            "https://api.example.com/start",
            "https://10.0.0.1/private",
            allow_cross_origin=True,
        )


def test_validate_resolution_set_rejects_mixed_private_values() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_resolution_set(("8.8.8.8", "127.0.0.1"))


def test_validate_resolution_set_is_canonical_and_deduplicated() -> None:
    assert validate_resolution_set(
        ("8.8.8.8", "1.1.1.1", "8.8.8.8")
    ) == ("1.1.1.1", "8.8.8.8")


def test_resolved_destination_constructor_rejects_private_evidence() -> None:
    with pytest.raises(ValueError, match="non-public"):
        ResolvedDestination(
            url="https://api.example.com/",
            host="api.example.com",
            port=443,
            addresses=("127.0.0.1",),
        )


def test_resolved_destination_constructor_rejects_duplicate_evidence() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        ResolvedDestination(
            url="https://api.example.com/",
            host="api.example.com",
            port=443,
            addresses=("8.8.8.8", "8.8.8.8"),
        )
