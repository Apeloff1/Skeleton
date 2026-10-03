from __future__ import annotations

import pytest

from skeleton.kernel.capabilities import TokenIssuer
from skeleton.kernel.capsec import Action, InMemoryAuditSink, mint_scoped

from .capsec import KernelToolAuthorizer, declared_capability_action, tool_actions
from .errors import CapabilityDeniedError


def _issuer_gate():
    issuer = TokenIssuer(secret=b"k" * 32)
    audit = InMemoryAuditSink()
    return issuer, issuer.gate(audit), audit


def test_declared_capability_maps_scope_verb_and_resource_constraint() -> None:
    action = declared_capability_action("fs.read", resource="file:/tmp/a")
    assert action.scope == "fs"
    assert action.verb == "read"
    assert action.resource == "file:/tmp/a"
    assert action.constraints == frozenset({("resource", "file:/tmp/a")})


def test_tool_actions_always_require_explicit_tool_invoke() -> None:
    actions = tool_actions("reader", ("fs.read",), ("file:/b", "file:/a"))
    assert actions[0] == Action(scope="tool.reader", verb="invoke", resource="reader")
    assert [(a.scope, a.verb, a.resource) for a in actions[1:]] == [
        ("fs", "read", "file:/a"),
        ("fs", "read", "file:/b"),
    ]


def test_default_authorizer_fails_closed_without_kernel_gate() -> None:
    with pytest.raises(CapabilityDeniedError) as info:
        KernelToolAuthorizer().authorize(None, tool_name="clock")
    assert info.value.reason == "gate_disabled"


def test_kernel_authorizer_uses_signed_token_subject_and_audits_every_action() -> None:
    issuer, gate, audit = _issuer_gate()
    actions = tool_actions("reader", ("fs.read",), ("file:/tmp/a",))
    cap = mint_scoped(issuer, "agent:reader", actions, ttl_seconds=60)

    auth = KernelToolAuthorizer(gate).authorize(
        cap,
        tool_name="reader",
        capabilities=("fs.read",),
        resources=("file:/tmp/a",),
    )

    assert auth.subject == "agent:reader"
    assert auth.actions == actions
    assert len(auth.audit_record_ids) == len(actions)
    assert len(audit.records) == len(actions)
    assert all(record.allowed for record in audit.records)


def test_missing_declared_capability_fails_before_execution() -> None:
    issuer, gate, audit = _issuer_gate()
    cap = mint_scoped(
        issuer,
        "agent:reader",
        (Action(scope="tool.reader", verb="invoke", resource="reader"),),
        ttl_seconds=60,
    )

    with pytest.raises(CapabilityDeniedError) as info:
        KernelToolAuthorizer(gate).authorize(
            cap,
            tool_name="reader",
            capabilities=("fs.read",),
        )

    assert info.value.reason == "not_covered"
    assert len(audit.records) == 2
    assert audit.records[0].allowed is True
    assert audit.records[1].allowed is False


def test_resource_constrained_capability_cannot_cross_resource_boundary() -> None:
    issuer, gate, _audit = _issuer_gate()
    allowed_actions = tool_actions("reader", ("fs.read",), ("file:/tmp/a",))
    cap = mint_scoped(issuer, "agent:reader", allowed_actions, ttl_seconds=60)

    with pytest.raises(CapabilityDeniedError) as info:
        KernelToolAuthorizer(gate).authorize(
            cap,
            tool_name="reader",
            capabilities=("fs.read",),
            resources=("file:/tmp/b",),
        )
    assert info.value.reason == "not_covered"


def test_forged_token_is_denied() -> None:
    issuer, gate, _audit = _issuer_gate()
    cap = mint_scoped(
        issuer,
        "agent:reader",
        (Action(scope="tool.reader", verb="invoke", resource="reader"),),
        ttl_seconds=60,
    )
    forged = cap[:-1] + ("A" if cap[-1] != "A" else "B")

    with pytest.raises(CapabilityDeniedError) as info:
        KernelToolAuthorizer(gate).authorize(forged, tool_name="reader")
    assert info.value.reason in {"forged", "invalid_token"}
