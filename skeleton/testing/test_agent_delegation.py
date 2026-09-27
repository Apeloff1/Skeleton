from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.agents.delegation import (
    AgentDelegationError,
    AgentIdentity,
    DelegationBudget,
    DelegationGrant,
    DelegationUsage,
    HandoffPacket,
    qualify_agent_delegation,
)
from skeleton.agents.swarm_fencing import LeaseFence
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmTask


NOW = 100.0


def _parent() -> AgentIdentity:
    return AgentIdentity(
        agent_id="parent-1",
        tenant_id="tenant-a",
        generation=4,
        authority_scopes=(
            "repo:read",
            "repo:write",
            "tool:execute",
            "artifact:write",
        ),
    )


def _child() -> AgentIdentity:
    return AgentIdentity(
        agent_id="child-1",
        tenant_id="tenant-a",
        generation=2,
        authority_scopes=("repo:read", "repo:write", "tool:execute"),
    )


def _parent_budget() -> DelegationBudget:
    return DelegationBudget(
        max_tool_calls=20,
        max_tokens=20_000,
        max_cost_units=50.0,
        max_wall_time_s=600.0,
        max_payload_bytes=1_000_000,
    )


def _child_budget() -> DelegationBudget:
    return DelegationBudget(
        max_tool_calls=5,
        max_tokens=4_000,
        max_cost_units=10.0,
        max_wall_time_s=120.0,
        max_payload_bytes=100_000,
    )


def _handoff(
    *,
    parent_agent_id: str = "parent-1",
    child_agent_id: str = "child-1",
    task_id: str = "task-1",
    required_scopes: tuple[str, ...] = ("repo:write",),
    created_at: float = NOW,
) -> HandoffPacket:
    return HandoffPacket(
        handoff_id="handoff-1",
        delegation_id="delegation-1",
        task_id=task_id,
        parent_agent_id=parent_agent_id,
        child_agent_id=child_agent_id,
        context_digest="a" * 64,
        payload_digest="b" * 64,
        checkpoint_ref="checkpoint:task-1:v1",
        required_scopes=required_scopes,
        created_at=created_at,
    )


def _grant(
    handoff: HandoffPacket,
    *,
    parent: AgentIdentity | None = None,
    child: AgentIdentity | None = None,
    delegated_scopes: tuple[str, ...] = ("repo:read", "repo:write"),
    parent_budget: DelegationBudget | None = None,
    child_budget: DelegationBudget | None = None,
    issued_at: float = NOW - 1.0,
    expires_at: float = NOW + 100.0,
) -> DelegationGrant:
    return DelegationGrant(
        delegation_id="delegation-1",
        parent=parent or _parent(),
        child=child or _child(),
        delegated_scopes=delegated_scopes,
        parent_remaining_budget=parent_budget or _parent_budget(),
        child_budget=child_budget or _child_budget(),
        handoff_digest=handoff.digest,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def _runtime(*, now: float = NOW) -> tuple[HardenedSwarmRuntime, LeaseFence]:
    clock = [now]
    runtime = HardenedSwarmRuntime(
        default_lease_seconds=30.0,
        clock=lambda: clock[0],
    )
    runtime.register_worker(
        "child-1",
        capabilities=("repo:write", "tool:execute"),
    )
    runtime.submit(
        SwarmTask(
            "task-1",
            {},
            required_capabilities=frozenset({"repo:write"}),
        )
    )
    task = runtime.lease("child-1")[0]
    return runtime, LeaseFence(
        task.id,
        "child-1",
        task.attempts,
        task.lease_deadline,
    )


def _usage(**overrides: object) -> DelegationUsage:
    values: dict[str, object] = {
        "tool_calls": 2,
        "tokens": 1000,
        "cost_units": 2.0,
        "wall_time_s": 10.0,
        "payload_bytes": 1000,
    }
    values.update(overrides)
    return DelegationUsage(**values)


def _decision(**overrides):
    handoff = overrides.pop("handoff", _handoff())
    grant = overrides.pop("grant", _grant(handoff))
    runtime, fence = overrides.pop("runtime_and_fence", _runtime())
    values = {
        "runtime": runtime,
        "grant": grant,
        "handoff": handoff,
        "fence": fence,
        "usage": _usage(),
        "observed_at": NOW + 1.0,
        "checkpoint_persisted": True,
    }
    values.update(overrides)
    return qualify_agent_delegation(**values)


def test_delegation_accepts_exact_bounded_handoff_and_live_fence() -> None:
    decision = _decision()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.decision_digest) == 64
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "agent_delegation"
    assert evidence.digest == decision.decision_digest


def test_delegated_authority_must_be_subset_of_parent_and_child() -> None:
    handoff = _handoff()

    with pytest.raises(AgentDelegationError, match="exceeds parent"):
        _grant(
            handoff,
            delegated_scopes=("admin:root",),
            child=AgentIdentity(
                agent_id="child-1",
                tenant_id="tenant-a",
                generation=2,
                authority_scopes=("admin:root",),
            ),
        )

    with pytest.raises(AgentDelegationError, match="exceeds child"):
        _grant(
            handoff,
            delegated_scopes=("artifact:write",),
        )


def test_delegation_cannot_cross_tenant_boundary() -> None:
    handoff = _handoff()

    with pytest.raises(AgentDelegationError, match="tenant"):
        _grant(
            handoff,
            child=AgentIdentity(
                agent_id="child-1",
                tenant_id="tenant-b",
                generation=2,
                authority_scopes=("repo:read", "repo:write"),
            ),
        )


def test_child_budget_cannot_exceed_parent_remaining_budget() -> None:
    handoff = _handoff()

    with pytest.raises(AgentDelegationError, match="budget exceeds"):
        _grant(
            handoff,
            child_budget=DelegationBudget(
                max_tool_calls=21,
                max_tokens=20_000,
                max_cost_units=50.0,
                max_wall_time_s=600.0,
                max_payload_bytes=1_000_000,
            ),
        )


@pytest.mark.parametrize(
    ("handoff", "reason"),
    (
        (
            _handoff(parent_agent_id="other-parent"),
            "handoff-parent-mismatch",
        ),
        (
            _handoff(child_agent_id="other-child"),
            "handoff-child-mismatch",
        ),
        (
            _handoff(required_scopes=("artifact:write",)),
            "handoff-authority-exceeds-delegation",
        ),
    ),
)
def test_handoff_identity_and_authority_drift_rejects(
    handoff: HandoffPacket,
    reason: str,
) -> None:
    baseline = _handoff()
    grant = _grant(baseline)

    decision = _decision(handoff=handoff, grant=grant)

    assert decision.accepted is False
    assert reason in decision.reasons


def test_handoff_digest_tamper_rejects() -> None:
    baseline = _handoff()
    grant = _grant(baseline)
    tampered = replace(baseline, payload_digest="f" * 64)

    decision = _decision(handoff=tampered, grant=grant)

    assert decision.accepted is False
    assert "handoff-digest-mismatch" in decision.reasons


def test_expired_delegation_and_expired_lease_reject() -> None:
    handoff = _handoff()
    grant = _grant(handoff, expires_at=NOW + 0.5)
    runtime, fence = _runtime()

    decision = _decision(
        handoff=handoff,
        grant=grant,
        runtime_and_fence=(runtime, fence),
        observed_at=NOW + 1.0,
    )

    assert decision.accepted is False
    assert "delegation-expired" in decision.reasons

    lease_decision = _decision(
        runtime_and_fence=(runtime, fence),
        observed_at=(fence.deadline or NOW) + 1.0,
    )
    assert lease_decision.accepted is False
    assert "lease-expired" in lease_decision.reasons


@pytest.mark.parametrize(
    ("usage", "field"),
    (
        (_usage(tool_calls=6), "tool_calls"),
        (_usage(tokens=4001), "tokens"),
        (_usage(cost_units=10.1), "cost"),
        (_usage(wall_time_s=120.1), "wall_time"),
        (_usage(payload_bytes=100_001), "payload"),
    ),
)
def test_every_delegation_budget_dimension_is_bounded(
    usage: DelegationUsage,
    field: str,
) -> None:
    del field
    decision = _decision(usage=usage)

    assert decision.accepted is False
    assert "delegation-budget-exceeded" in decision.reasons


def test_checkpoint_must_be_durably_persisted() -> None:
    decision = _decision(checkpoint_persisted=False)

    assert decision.accepted is False
    assert "handoff-checkpoint-not-persisted" in decision.reasons


def test_wrong_child_lease_rejects() -> None:
    runtime, fence = _runtime()
    wrong = replace(fence, worker_id="other-child")

    decision = _decision(
        runtime_and_fence=(runtime, wrong),
    )

    assert decision.accepted is False
    assert "lease-child-mismatch" in decision.reasons
    assert "lease-fence-stale" in decision.reasons


def test_pre_renewal_fence_becomes_stale_after_deadline_change() -> None:
    runtime, stale = _runtime()
    renewed = runtime.renew("child-1", "task-1", seconds=50.0)

    stale_decision = _decision(
        runtime_and_fence=(runtime, stale),
    )

    assert stale_decision.accepted is False
    assert "lease-fence-stale" in stale_decision.reasons

    current = LeaseFence(
        renewed.id,
        "child-1",
        renewed.attempts,
        renewed.lease_deadline,
    )
    current_decision = _decision(
        runtime_and_fence=(runtime, current),
    )
    assert current_decision.accepted is True


def test_reissued_attempt_invalidates_old_fence() -> None:
    clock = [NOW]
    runtime = HardenedSwarmRuntime(
        default_lease_seconds=1.0,
        clock=lambda: clock[0],
    )
    runtime.register_worker(
        "child-1",
        capabilities=("repo:write", "tool:execute"),
    )
    runtime.submit(
        SwarmTask(
            "task-1",
            {},
            max_attempts=3,
            required_capabilities=frozenset({"repo:write"}),
        )
    )
    first = runtime.lease("child-1")[0]
    stale = LeaseFence(
        first.id,
        "child-1",
        first.attempts,
        first.lease_deadline,
    )
    clock[0] = NOW + 2.0
    runtime.reap_expired()
    second = runtime.lease("child-1")[0]

    decision = _decision(
        runtime_and_fence=(runtime, stale),
        observed_at=NOW + 2.0,
    )
    assert decision.accepted is False
    assert "lease-fence-stale" in decision.reasons

    current = LeaseFence(
        second.id,
        "child-1",
        second.attempts,
        second.lease_deadline,
    )
    current_decision = _decision(
        runtime_and_fence=(runtime, current),
        observed_at=NOW + 2.0,
    )
    assert current_decision.accepted is True


def test_rejected_delegation_cannot_become_promotion_evidence() -> None:
    decision = _decision(checkpoint_persisted=False)

    with pytest.raises(AgentDelegationError, match="cannot become"):
        decision.accepted_evidence_ref()


def test_handoff_scope_and_budget_order_is_canonical() -> None:
    left = _handoff(required_scopes=("repo:write", "repo:read"))
    right = _handoff(required_scopes=("repo:read", "repo:write"))

    assert left.required_scopes == right.required_scopes
    assert left.digest == right.digest

    left_grant = _grant(
        left,
        delegated_scopes=("repo:write", "repo:read"),
    )
    right_grant = _grant(
        right,
        delegated_scopes=("repo:read", "repo:write"),
    )
    assert left_grant.digest == right_grant.digest
