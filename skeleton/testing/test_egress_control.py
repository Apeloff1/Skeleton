from __future__ import annotations

import socket

import pytest

from skeleton.ai.runtime.security.egress_control import (
    EgressControlError,
    EgressPolicy,
    EgressRequest,
    evaluate_egress,
)


def resolver_for(*addresses: str):
    def resolve(host,port,*args):
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET,
             socket.SOCK_STREAM,
             socket.IPPROTO_TCP,
             "",
             (address,port,0,0) if ":" in address else (address,port))
            for address in addresses
        ]
    return resolve


def policy() -> EgressPolicy:
    return EgressPolicy(
        policy_id="EGRESS.V1",
        allowed_hosts=("example.com",),
        allowed_purposes=("provider-api",),
    )


def request(**changes: object) -> EgressRequest:
    values=dict(
        request_id="req-1",
        url="https://example.com/v1",
        purpose="provider-api",
        subject_id="worker-a",
    )
    values.update(changes)
    return EgressRequest(**values)


def test_public_allowlisted_destination_is_authorized() -> None:
    decision=evaluate_egress(
        policy(),
        request(),
        resolver=resolver_for("93.184.216.34"),
    )
    assert decision.allowed is True
    assert decision.reason_code=="authorized"
    assert decision.destination is not None
    assert decision.destination.host=="example.com"


def test_unapproved_purpose_fails_before_resolution() -> None:
    called=False
    def resolver(*args):
        nonlocal called
        called=True
        raise AssertionError("resolver should not run")
    decision=evaluate_egress(
        policy(),
        request(purpose="telemetry"),
        resolver=resolver,
    )
    assert decision.allowed is False
    assert decision.reason_code=="purpose_denied"
    assert called is False


def test_mixed_public_private_dns_fails_closed() -> None:
    decision=evaluate_egress(
        policy(),
        request(),
        resolver=resolver_for("93.184.216.34","127.0.0.1"),
    )
    assert decision.allowed is False
    assert decision.reason_code=="destination_invalid"
    assert decision.destination is None


def test_public_but_unapproved_host_is_denied() -> None:
    decision=evaluate_egress(
        policy(),
        request(url="https://example.org/v1"),
        resolver=resolver_for("93.184.216.34"),
    )
    assert decision.allowed is False
    assert decision.reason_code=="host_denied"


def test_allow_by_default_egress_policy_is_forbidden() -> None:
    with pytest.raises(EgressControlError,match="default action"):
        EgressPolicy(
            "bad",
            ("example.com",),
            ("provider-api",),
            default_action="allow",
        )


def test_unapproved_host_is_rejected_without_any_dns_lookup() -> None:
    queries = []

    def resolver(host, port, *args):
        queries.append((host, port))
        raise AssertionError("disallowed host must never be resolved")

    decision = evaluate_egress(
        policy(), request(url="https://untrusted.example.org/crawl"), resolver=resolver
    )
    assert decision.allowed is False
    assert decision.reason_code == "host_denied"
    assert decision.destination is None
    assert queries == []


def test_invalid_internal_url_is_rejected_without_dns_lookup() -> None:
    def resolver(*args):
        raise AssertionError("internal hosts must never be resolved")

    decision = evaluate_egress(
        policy(), request(url="https://metadata.google.internal/latest"), resolver=resolver
    )
    assert decision.allowed is False
    assert decision.reason_code == "destination_invalid"
    assert decision.destination is None


def test_allowed_host_still_requires_verified_public_resolution() -> None:
    seen = []

    def resolver(host, port, *args):
        seen.append((host, port))
        return resolver_for("127.0.0.1")(host, port, *args)

    decision = evaluate_egress(policy(), request(), resolver=resolver)
    assert seen == [("example.com", 443)]
    assert decision.allowed is False
    assert decision.reason_code == "destination_invalid"
    assert decision.destination is None
