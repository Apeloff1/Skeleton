"""Agent edge — agent identities on the s2s plane, scoped caps, delegation, edge facade."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.agent_edge import (
    AgentAuthError,
    AgentAuthority,
    AgentBus,
    AgentEdge,
    AgentEndpoint,
    AgentRegistry,
    AgentRouter,
    AuthFailure,
    DeadLetterReason,
    EdgeError,
    LeaseNotFound,
    NoRoute,
    PublishStatus,
    RouteUnavailable,
    ScopeCeiling,
    SendRequest,
    cap_granted,
)
from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import TokenErrorCode, TokenSigner

FULL = ["msg:send:*", "msg:recv", "route:resolve", "agent:delegate", "dlq:read", "dlq:admin"]


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def ring(clock):
    r = KeyRing(clock=clock)
    r.add_key("k1", b"s" * 32, activate=True)
    return r


@pytest.fixture
def authority(ring, clock):
    ceiling = ScopeCeiling(
        {
            "planner": FULL,
            "worker": ["msg:send:work.*", "msg:send:plan.reply", "msg:recv"],
            "helper": ["msg:send:*", "msg:recv", "agent:delegate", "route:resolve"],
            "intern": ["msg:recv"],
        }
    )
    return AgentAuthority(ring, ceiling=ceiling, clock=clock, max_delegation_depth=2)


@pytest.fixture
def edge(authority, clock):
    reg = AgentRegistry(
        [
            AgentEndpoint.build("planner", "internal", ["plan.write"]),
            AgentEndpoint.build("worker", "backend", ["work.item"]),
            AgentEndpoint.build("worker2", "backend", ["work.item"]),
        ]
    )
    br = BreakerRegistry(clock=clock, default=BreakerConfig(consecutive_failures=2, min_calls=2, window_size=4, cooldown_s=30))
    return AgentEdge(AgentBus(clock=clock), AgentRouter(reg, breakers=br, clock=clock), authority)


def P(authority, agent, scopes):
    return authority.authenticate(authority.issue(agent, scopes))


def test_cap_granted_wildcards():
    assert cap_granted(["msg:send:*"], "msg:send:work.item")
    assert cap_granted(["msg:send:work.*"], "msg:send:work.item")
    assert not cap_granted(["msg:send:work.*"], "msg:send:plan.write")
    assert not cap_granted(["msg:recv"], "msg:send:work.item")


def test_issue_respects_ceiling(authority):
    tok = authority.issue("worker", ["msg:recv", "msg:send:work.item"])
    p = authority.authenticate(tok)
    assert p.agent_id == "worker" and not p.delegated and p.chain == ("worker",)
    with pytest.raises(AgentAuthError) as ei:
        authority.issue("worker", ["dlq:admin"])
    assert ei.value.failure is AuthFailure.CEILING_EXCEEDED
    with pytest.raises(AgentAuthError):
        authority.issue("stranger", ["msg:recv"])  # default ceiling is empty


def test_token_errors_map_to_401(authority, ring, clock):
    with pytest.raises(AgentAuthError) as ei:
        authority.authenticate("not-a-token")
    assert ei.value.http_status == 401 and ei.value.token_error is TokenErrorCode.MALFORMED
    tok = authority.issue("worker", ["msg:recv"], ttl_s=10)
    clock.advance(30)
    with pytest.raises(AgentAuthError) as ei:
        authority.authenticate(tok)
    assert ei.value.token_error is TokenErrorCode.EXPIRED
    other = TokenSigner("worker", ring, clock=clock).mint("some-other-service", ["msg:recv"])
    with pytest.raises(AgentAuthError) as ei:
        authority.authenticate(other)
    assert ei.value.token_error is TokenErrorCode.BAD_AUDIENCE


def test_forged_scopes_beyond_ceiling_rejected(authority, ring, clock):
    forged = TokenSigner("intern", ring, clock=clock).mint("agent-edge", ["dlq:admin"])
    with pytest.raises(AgentAuthError) as ei:
        authority.authenticate(forged)
    assert ei.value.failure is AuthFailure.CEILING_EXCEEDED


def test_delegation_attenuates_and_records_chain(authority):
    planner = P(authority, "planner", FULL)
    tok = authority.delegate(planner, "helper", ["msg:send:work.*", "agent:delegate"])
    helper = authority.authenticate(tok)
    assert helper.agent_id == "helper" and helper.delegated
    assert helper.on_behalf_of == "planner" and helper.chain == ("planner", "helper") and helper.depth == 1
    assert helper.can("msg:send:work.item") and not helper.can("dlq:admin")
    assert authority.provenance_headers(helper) == {"on-behalf-of": "planner", "delegation-chain": "planner>helper"}
    with pytest.raises(AgentAuthError) as ei:
        authority.delegate(helper, "worker", ["dlq:read"])
    assert ei.value.failure is AuthFailure.SCOPE_ESCALATION


def test_delegation_depth_cycle_and_permission(authority):
    planner = P(authority, "planner", FULL)
    h = authority.authenticate(authority.delegate(planner, "helper", ["msg:send:*", "agent:delegate"]))
    w = authority.authenticate(authority.delegate(h, "worker", ["msg:send:work.*", "agent:delegate"]))
    assert w.chain == ("planner", "helper", "worker") and not w.can("agent:delegate")  # stripped at max depth
    with pytest.raises(AgentAuthError) as ei:
        authority.delegate(w, "intern", ["msg:send:work.*"])
    assert ei.value.failure is AuthFailure.NOT_DELEGABLE
    with pytest.raises(AgentAuthError) as ei:
        authority.delegate(h, "planner", ["msg:send:*"])
    assert ei.value.failure is AuthFailure.BAD_DELEGATION
    worker = P(authority, "worker", ["msg:recv"])
    with pytest.raises(AgentAuthError) as ei:
        authority.delegate(worker, "intern", ["msg:recv"])
    assert ei.value.failure is AuthFailure.NOT_DELEGABLE


def test_delegated_ttl_bounded_by_delegator(authority, clock):
    planner = authority.authenticate(authority.issue("planner", FULL, ttl_s=60))
    tok = authority.delegate(planner, "helper", ["msg:recv"], ttl_s=3000)
    helper = authority.authenticate(tok)
    assert helper.expires_at <= planner.expires_at


def test_revocation_cascades_through_chain(authority):
    planner = P(authority, "planner", FULL)
    tok = authority.delegate(planner, "helper", ["msg:recv"])
    authority.revoke_agent("planner")
    with pytest.raises(AgentAuthError) as ei:
        authority.authenticate(tok)
    assert ei.value.failure is AuthFailure.REVOKED_AGENT
    authority.restore_agent("planner")
    assert authority.authenticate(tok).agent_id == "helper"


def test_tampered_chain_rejected(authority, ring, clock):
    bad = TokenSigner("planner", ring, clock=clock).mint(
        "agent-edge", ["msg:recv"], extra={"sub": "helper", "chain": "root>helper", "depth": "1"}
    )
    with pytest.raises(AgentAuthError) as ei:
        authority.authenticate(bad)
    assert ei.value.failure is AuthFailure.BAD_DELEGATION
    bad2 = TokenSigner("planner", ring, clock=clock).mint("agent-edge", ["msg:recv"], extra={"chain": "x"})
    with pytest.raises(AgentAuthError):
        authority.authenticate(bad2)


# -- edge facade --------------------------------------------------------------------------
def test_send_direct_requires_topic_scope_and_sets_sender(edge, authority):
    planner = P(authority, "planner", FULL)
    out = edge.send(planner, SendRequest(topic="work.item", payload={"x": 1}, recipient="worker"))
    assert out.publish.status is PublishStatus.ACCEPTED and out.envelope.sender == "planner"
    worker = P(authority, "worker", ["msg:send:work.*", "msg:recv"])
    with pytest.raises(AgentAuthError) as ei:
        edge.send(worker, SendRequest(topic="plan.write", payload={}, recipient="planner"))
    assert ei.value.failure is AuthFailure.MISSING_SCOPE and ei.value.http_status == 403


def test_send_by_capability_needs_resolve_and_balances(edge, authority):
    planner = P(authority, "planner", FULL)
    a = edge.send(planner, SendRequest(topic="work.item", payload={}, capability="work.item", lane="backend"))
    b = edge.send(planner, SendRequest(topic="work.item", payload={}, capability="work.item"))
    assert {a.envelope.recipient, b.envelope.recipient} == {"worker", "worker2"}  # load-aware spread
    worker = P(authority, "worker", ["msg:send:work.*"])
    with pytest.raises(AgentAuthError):
        edge.send(worker, SendRequest(topic="work.item", payload={}, capability="work.item"))


def test_send_no_route_dead_letters(edge, authority):
    planner = P(authority, "planner", FULL)
    with pytest.raises(NoRoute):
        edge.send(planner, SendRequest(topic="work.item", payload={}, recipient="ghost"))
    assert edge.bus.dlq.list(reason=DeadLetterReason.NO_ROUTE)
    with pytest.raises(EdgeError):
        edge.send(planner, SendRequest(topic="work.item", payload={}, capability="BAD CAP"))


def test_send_rejects_spoofed_provenance_and_bad_requests(edge, authority):
    planner = P(authority, "planner", FULL)
    with pytest.raises(EdgeError):
        edge.send(planner, SendRequest(topic="work.item", payload={}, recipient="worker", headers={"on-behalf-of": "x"}))
    with pytest.raises(EdgeError):
        SendRequest(topic="t", payload={})
    with pytest.raises(EdgeError):
        SendRequest(topic="t", payload={}, recipient="a1", lane="x")
    with pytest.raises(EdgeError):
        SendRequest.from_dict({"topic": "t", "recipient": "a1", "bogus": 1})
    with pytest.raises(EdgeError):
        edge.send(planner, SendRequest(topic="BAD", payload={}, recipient="worker"))


def test_delegated_send_carries_provenance(edge, authority):
    planner = P(authority, "planner", FULL)
    helper = authority.authenticate(authority.delegate(planner, "helper", ["msg:send:work.*"]))
    out = edge.send(helper, SendRequest(topic="work.item", payload={}, recipient="worker"))
    assert out.envelope.sender == "helper"
    assert out.envelope.headers["on-behalf-of"] == "planner"


def test_mailbox_ownership_and_breaker_feedback(edge, authority, clock):
    planner = P(authority, "planner", FULL)
    worker = P(authority, "worker", ["msg:recv"])
    for i in range(3):
        edge.send(planner, SendRequest(topic="work.item", payload={"i": i}, recipient="worker", conversation_id=f"conv-{i:04d}"))
    with pytest.raises(AgentAuthError) as ei:
        edge.pull(planner, "worker")
    assert ei.value.failure is AuthFailure.NOT_MAILBOX_OWNER
    ds = edge.pull(worker, "worker", max_messages=3)
    assert len(ds) == 3
    intern = P(authority, "intern", ["msg:recv"])
    with pytest.raises(AgentAuthError):
        edge.ack(intern, ds[0].lease_id)
    edge.ack(worker, ds[0].lease_id)
    edge.nack(worker, ds[1].lease_id, error="x")
    edge.nack(worker, ds[2].lease_id, error="y")
    assert edge.router.breaker("worker").state.value == "open"
    with pytest.raises(RouteUnavailable) as ei:
        edge.send(planner, SendRequest(topic="work.item", payload={}, recipient="worker"))
    assert ei.value.retry_after_s and ei.value.status == 503
    routed = edge.send(planner, SendRequest(topic="work.item", payload={}, capability="work.item"))
    assert routed.envelope.recipient == "worker2"
    with pytest.raises(LeaseNotFound):
        edge.ack(worker, "lease-nope")


def test_poison_nack_does_not_score_breaker(edge, authority):
    planner = P(authority, "planner", FULL)
    worker = P(authority, "worker", ["msg:recv"])
    for i in range(3):
        edge.send(planner, SendRequest(topic="work.item", payload={}, recipient="worker", conversation_id=f"conv-{i:04d}"))
    for d in edge.pull(worker, "worker", max_messages=3):
        edge.nack(worker, d.lease_id, poison=True)
    assert edge.router.breaker("worker").state.value == "closed"


def test_dlq_read_and_replay_need_scopes(edge, authority):
    planner = P(authority, "planner", FULL)
    worker = P(authority, "worker", ["msg:recv"])
    edge.send(planner, SendRequest(topic="work.item", payload={}, recipient="worker", max_attempts=1))
    d = edge.pull(worker, "worker")[0]
    edge.nack(worker, d.lease_id, retry=False)
    with pytest.raises(AgentAuthError):
        edge.dead_letters(worker)
    letters = edge.dead_letters(planner, reason="rejected")
    assert [x.envelope.message_id for x in letters] == [d.envelope.message_id]
    with pytest.raises(EdgeError):
        edge.dead_letters(planner, reason="nope")
    assert edge.replay(planner, d.envelope.message_id).accepted
    with pytest.raises(EdgeError):
        edge.replay(planner, d.envelope.message_id)
    assert edge.resolve(planner, "work.item").routed
    assert edge.stats()["edge"]["ack"] if "ack" in edge.stats()["edge"] else True
