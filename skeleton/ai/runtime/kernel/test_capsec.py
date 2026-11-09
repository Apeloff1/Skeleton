"""Contract tests for the B031 capsec gate (deny-by-default + audit).

Relative imports on purpose: the exact mirror under ``skeleton/ai/runtime``
then exercises its own copy of ``capsec``.
"""

from __future__ import annotations

import time

import pytest

from .capabilities import Capability, CapabilityError, TokenIssuer
from .capsec import (
    CAPSEC_INTERFACE_VERSION,
    Action,
    AuditRecord,
    CapabilityGate,
    Decision,
    DenyAllGate,
    InMemoryAuditSink,
    KernelCapabilityGate,
    ReasonCode,
    token_expires_at,
)

TOOL = Action("tool.grep", "invoke", resource="grep")


def _gate():
    issuer = TokenIssuer(secret=b"k" * 32)
    sink = InMemoryAuditSink()
    return issuer, sink, KernelCapabilityGate(issuer, sink)


def test_interface_version_and_protocol_conformance():
    _, _, gate = _gate()
    assert CAPSEC_INTERFACE_VERSION == 1
    assert isinstance(gate, CapabilityGate)
    assert isinstance(DenyAllGate(), CapabilityGate)


def test_allows_covered_action_and_audits_it():
    issuer, sink, gate = _gate()
    tok = issuer.mint("klint", [Capability("tool.grep", "invoke")])
    decision = gate.check(tok, TOOL)
    assert isinstance(decision, Decision) and decision.allowed and bool(decision)
    assert decision.reason == ReasonCode.ALLOWED
    assert decision.subject == "klint"
    (record,) = sink.records
    assert isinstance(record, AuditRecord)
    assert record.allowed and record.matched_scope == "tool.grep"
    assert tok not in repr(record.to_dict())  # bearer token never audited


@pytest.mark.parametrize("cap", [None, "", b"bytes", 42])
def test_unsigned_inputs_are_denied(cap):
    _, sink, gate = _gate()
    decision = gate.check(cap, TOOL)
    assert not decision and decision.reason == ReasonCode.UNSIGNED_TOKEN
    assert len(sink.records) == 1 and not sink.records[0].allowed


def test_forged_and_tampered_tokens_are_denied():
    issuer, _, gate = _gate()
    other = TokenIssuer(secret=b"x" * 32)
    forged = other.mint("klint", [Capability("tool.grep", "invoke")])
    assert gate.check(forged, TOOL).reason == ReasonCode.FORGED
    assert gate.check("not-a-token", TOOL).reason == ReasonCode.FORGED


def test_uncovered_scope_is_denied():
    issuer, _, gate = _gate()
    tok = issuer.mint("klint", [Capability("tool.grep", "invoke")])
    assert gate.check(tok, Action("tool.rm", "invoke")).reason == ReasonCode.NOT_COVERED
    assert gate.check(tok, Action("tool.grep", "write")).reason == ReasonCode.NOT_COVERED


def test_expiring_capability_allows_until_expiry_then_denies():
    issuer = TokenIssuer(secret=b"k" * 32)
    now = [1_000.0]
    gate = KernelCapabilityGate(issuer, clock=lambda: now[0])
    tok = issuer.mint("bork", [Capability("provider.openai", "call", expires_at=1_010.0)])
    action = Action("provider.openai", "call")
    decision = gate.check(tok, action)
    assert decision.allowed and decision.expires_at == 1_010.0
    now[0] = 1_010.0
    assert gate.check(tok, action).reason == ReasonCode.EXPIRED


def test_revoked_token_is_denied():
    issuer, _, gate = _gate()
    tok = issuer.mint("klint", [Capability("tool.grep", "invoke")])
    issuer.revoke(issuer.verify(tok).token_id)
    assert gate.check(tok, TOOL).reason == ReasonCode.REVOKED


def test_wildcards_only_widen_on_the_grant_side():
    issuer, _, gate = _gate()
    tok = issuer.mint("klint", [Capability("tool.grep", "invoke")])
    assert gate.check(tok, Action("*", "invoke")).reason == ReasonCode.MALFORMED_ACTION
    assert gate.check(tok, Action("tool.grep", "*")).reason == ReasonCode.MALFORMED_ACTION
    broad = issuer.mint("root", [Capability("*", "*")])
    assert gate.check(broad, TOOL).allowed


def test_attenuated_token_carries_parent_into_audit():
    issuer, sink, gate = _gate()
    parent = issuer.mint("bork", [Capability("integration.github", "*")])
    child = issuer.attenuate(parent, [Capability("integration.github", "read")])
    assert gate.check(child, Action("integration.github", "read")).allowed
    assert sink.records[-1].parent_id == issuer.verify(parent).token_id
    assert not gate.check(child, Action("integration.github", "write")).allowed


def test_audit_failure_forces_deny():
    class Broken:
        def record(self, entry):
            raise OSError("disk full")

    issuer = TokenIssuer(secret=b"k" * 32)
    gate = KernelCapabilityGate(issuer, Broken())
    tok = issuer.mint("klint", [Capability("tool.grep", "invoke")])
    decision = gate.check(tok, TOOL)
    assert not decision.allowed and decision.reason == ReasonCode.AUDIT_UNAVAILABLE
    with pytest.raises(CapabilityError):
        decision.require()


def test_deny_all_gate_denies_and_audits():
    sink = InMemoryAuditSink()
    decision = DenyAllGate(sink).check("anything", TOOL)
    assert not decision and decision.reason == ReasonCode.GATE_DISABLED
    assert len(sink.records) == 1


def test_token_expires_at_is_earliest_capability_expiry():
    issuer = TokenIssuer(secret=b"k" * 32)
    later = time.time() + 100
    tok = issuer.mint("s", [Capability("a", "b", expires_at=later),
                            Capability("c", "d", expires_at=later - 50),
                            Capability("e", "f")])
    assert token_expires_at(issuer.verify(tok)) == later - 50
