"""B031 phase 2 tests: capabilities wiring, scoped/expiring tokens, audit records."""

from __future__ import annotations

import json

import pytest

from skeleton.kernel.capabilities import (
    AttenuationError,
    Capability,
    CapabilityError,
    TokenIssuer,
)
from skeleton.kernel.capsec import (
    Action,
    AuditRecord,
    CapabilityGate,
    CompositeAuditSink,
    InMemoryAuditSink,
    KernelCapabilityGate,
    ReasonCode,
    capability_for,
    mint_scoped,
)

SECRET = b"s" * 32
TOOL = Action("tool.search", "invoke", resource="search")
PROVIDER = Action("provider.openai", "call", resource="openai")


class Clock:
    def __init__(self, t: float = 1_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _setup(clock: Clock | None = None):
    issuer = TokenIssuer(secret=SECRET)
    sink = InMemoryAuditSink()
    return issuer, sink, issuer.gate(sink, clock=clock)


# --- capabilities.py wiring (extend-only) ---------------------------------

def test_issuer_gate_returns_kernel_gate_over_same_issuer():
    issuer, sink, gate = _setup()
    assert isinstance(gate, KernelCapabilityGate)
    assert isinstance(gate, CapabilityGate)
    assert gate.audit_sink is sink
    token = issuer.mint("klint", [Capability("tool.search", "invoke")])
    assert gate.check(token, TOOL).allowed
    issuer.revoke(issuer.verify(token).token_id)
    assert gate.check(token, TOOL).reason == ReasonCode.REVOKED


def test_issuer_gate_defaults_to_in_memory_sink():
    gate = TokenIssuer(secret=SECRET).gate()
    assert isinstance(gate.audit_sink, InMemoryAuditSink)
    assert not gate.check(None, TOOL)
    assert len(gate.audit_sink.records) == 1


def test_gate_from_other_issuer_rejects_token_as_forged():
    issuer, _, _ = _setup()
    token = issuer.mint("klint", [Capability("tool.search", "invoke")])
    other = TokenIssuer(secret=b"x" * 32).gate()
    assert other.check(token, TOOL).reason == ReasonCode.FORGED


def test_legacy_issuer_check_is_unchanged():
    issuer, _, _ = _setup()
    token = issuer.mint("klint", [Capability("tool.search", "invoke")])
    assert issuer.check(token, "tool.search", "invoke") is True
    assert issuer.check(token, "tool.other", "invoke") is False


# --- scoped tokens --------------------------------------------------------

def test_capability_for_is_exact_and_rejects_bad_input():
    cap = capability_for(TOOL)
    assert (cap.scope, cap.action, cap.expires_at) == ("tool.search", "invoke", None)
    assert capability_for(TOOL, ttl_seconds=30, now=100.0).expires_at == 130.0
    with pytest.raises(ValueError):
        capability_for(Action("*", "invoke"))
    with pytest.raises(ValueError):
        capability_for(TOOL, ttl_seconds=0)
    with pytest.raises(ValueError):
        capability_for(TOOL, ttl_seconds=True)


def test_mint_scoped_token_only_covers_listed_actions():
    clock = Clock()
    issuer, sink, gate = _setup(clock)
    token = mint_scoped(issuer, "bork", [TOOL, PROVIDER])
    assert gate.check(token, TOOL).allowed
    assert gate.check(token, PROVIDER).allowed
    denied = gate.check(token, Action("provider.anthropic", "call"))
    assert denied.reason == ReasonCode.NOT_COVERED and denied.subject == "bork"
    assert gate.check(token, Action("tool.search", "delete")).reason == ReasonCode.NOT_COVERED


def test_constrained_scope_must_match_exactly():
    issuer, _, gate = _setup()
    constraint = frozenset({("tenant", "t1")})
    token = mint_scoped(issuer, "bork", [Action("integration.slack", "post", constraints=constraint)])
    assert gate.check(token, Action("integration.slack", "post", constraints=constraint)).allowed
    assert not gate.check(token, Action("integration.slack", "post"))
    assert not gate.check(token, Action("integration.slack", "post",
                                        constraints=frozenset({("tenant", "t2")})))


def test_resource_label_never_widens_authority():
    issuer, _, gate = _setup()
    token = mint_scoped(issuer, "klint", [TOOL])
    other = Action("tool.shell", "invoke", resource="search")
    assert gate.check(token, other).reason == ReasonCode.NOT_COVERED


def test_attenuated_token_is_narrower_and_cannot_escalate():
    issuer, sink, gate = _setup()
    parent = issuer.mint("bork", [Capability("*", "call")])
    child = issuer.attenuate(parent, [capability_for(PROVIDER)])
    assert gate.check(child, PROVIDER).allowed
    assert gate.check(child, Action("provider.other", "call")).reason == ReasonCode.NOT_COVERED
    with pytest.raises(AttenuationError):
        issuer.attenuate(child, [Capability("tool.search", "invoke")])


# --- expiring tokens ------------------------------------------------------

def test_scoped_token_expires_after_ttl():
    clock = Clock(1_000.0)
    issuer, _, gate = _setup(clock)
    token = mint_scoped(issuer, "klint", [TOOL], ttl_seconds=60, now=clock.t)
    allowed = gate.check(token, TOOL)
    assert allowed.allowed and allowed.expires_at == 1_060.0
    clock.t = 1_059.999
    assert gate.check(token, TOOL).allowed
    clock.t = 1_060.0
    assert gate.check(token, TOOL).reason == ReasonCode.EXPIRED


def test_any_lapsed_capability_expires_whole_token():
    clock = Clock(0.0)
    issuer, _, gate = _setup(clock)
    token = issuer.mint("bork", [
        Capability("tool.search", "invoke"),
        Capability("provider.openai", "call", expires_at=10.0),
    ])
    assert gate.check(token, TOOL).allowed
    clock.t = 11.0
    assert gate.check(token, TOOL).reason == ReasonCode.EXPIRED


def test_denied_decision_require_raises_with_record_id():
    issuer, sink, gate = _setup()
    decision = gate.check(None, TOOL)
    with pytest.raises(CapabilityError) as exc:
        decision.require()
    assert decision.audit.record_id in str(exc.value.context)


# --- audit records --------------------------------------------------------

def test_every_decision_is_audited_with_unique_ids_and_no_token():
    clock = Clock(5.0)
    issuer, sink, gate = _setup(clock)
    token = mint_scoped(issuer, "klint", [TOOL])
    decisions = [
        gate.check(token, TOOL),
        gate.check(token, PROVIDER),
        gate.check("garbage", TOOL),
        gate.check(None, TOOL),
        gate.check(token, Action("", "invoke")),
    ]
    records = sink.records
    assert len(records) == len(decisions)
    assert [r.record_id for r in records] == [d.audit.record_id for d in decisions]
    assert len({r.record_id for r in records}) == len(records)
    assert [r.reason for r in records] == [
        ReasonCode.ALLOWED, ReasonCode.NOT_COVERED, ReasonCode.FORGED,
        ReasonCode.UNSIGNED_TOKEN, ReasonCode.MALFORMED_ACTION,
    ]
    assert all(r.decided_at == 5.0 for r in records)
    serialised = json.dumps([r.to_dict() for r in records])
    assert token not in serialised


def test_allowed_record_carries_identity_and_match():
    issuer, sink, gate = _setup()
    token = mint_scoped(issuer, "klint", [TOOL])
    record = gate.check(token, TOOL).audit
    tid = issuer.verify(token).token_id
    assert isinstance(record, AuditRecord)
    assert (record.subject, record.token_id, record.parent_id) == ("klint", tid, None)
    assert (record.matched_scope, record.matched_action) == ("tool.search", "invoke")
    assert record.gate == "capsec.kernel"
    assert record.to_dict()["action"] == TOOL.to_dict()


def test_in_memory_sink_query_filters():
    issuer, sink, gate = _setup()
    a = mint_scoped(issuer, "klint", [TOOL])
    b = mint_scoped(issuer, "bork", [PROVIDER])
    gate.check(a, TOOL)
    gate.check(a, PROVIDER)
    gate.check(b, PROVIDER)
    assert len(sink.denied()) == 1
    assert len(sink.query(subject="bork")) == 1
    assert len(sink.query(scope="provider.openai")) == 2
    assert len(sink.query(allowed=True, scope="provider.openai")) == 1
    assert len(sink.query(reason=ReasonCode.NOT_COVERED)) == 1
    tid = issuer.verify(a).token_id
    assert len(sink.query(token_id=tid)) == 2


def test_in_memory_sink_is_bounded():
    sink = InMemoryAuditSink(max_records=3)
    gate = TokenIssuer(secret=SECRET).gate(sink)
    ids = [gate.check(None, TOOL).audit.record_id for _ in range(5)]
    assert [r.record_id for r in sink.records] == ids[-3:]


def test_composite_sink_fans_out_and_fails_closed():
    issuer = TokenIssuer(secret=SECRET)
    a, b = InMemoryAuditSink(), InMemoryAuditSink()
    gate = issuer.gate(CompositeAuditSink(a, b))
    token = mint_scoped(issuer, "klint", [TOOL])
    assert gate.check(token, TOOL).allowed
    assert len(a.records) == len(b.records) == 1

    class Broken:
        def record(self, entry):
            raise OSError("disk full")

    strict = issuer.gate(CompositeAuditSink(a, Broken()))
    decision = strict.check(token, TOOL)
    assert not decision.allowed and decision.reason == ReasonCode.AUDIT_UNAVAILABLE
    assert decision.audit.detail["original_reason"] == ReasonCode.ALLOWED
    with pytest.raises(ValueError):
        CompositeAuditSink()
    with pytest.raises(TypeError):
        CompositeAuditSink(object())
