from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.agents.delegation import (
    AgentIdentity,
    DelegationBudget,
    DelegationContractError,
    DelegationGrant,
    DelegationUsage,
    HandoffPacket,
    authorize_child_commit,
    authorize_swarm_child_commit,
    derive_child_grant,
)
from skeleton.agents.swarm_exact_lease import lease_exact
from skeleton.agents.swarm_fencing import fence_for
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask


NOW = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)
OBJ = "1" * 64
CTX = "2" * 64
CHECKPOINT = "3" * 64


def _parent() -> AgentIdentity:
    return AgentIdentity(
        agent_id="agent-parent",
        principal_id="principal-root",
        tenant_id="tenant-a",
        capabilities=("tool.execute", "read", "write", "delegate"),
    )


def _child(
    *,
    agent_id: str = "agent-child",
    tenant_id: str = "tenant-a",
    capabilities: tuple[str, ...] = ("tool.execute", "read"),
) -> AgentIdentity:
    return AgentIdentity(
        agent_id=agent_id,
        principal_id="principal-child",
        tenant_id=tenant_id,
        capabilities=capabilities,
    )


def _parent_budget() -> DelegationBudget:
    return DelegationBudget(
        max_steps=100,
        max_tokens=100_000,
        max_cost_micros=5_000_000,
        max_wall_seconds=600,
        max_tool_calls=50,
        max_delegation_depth=3,
    )


def _child_budget(
    *,
    max_steps: int = 20,
    max_tokens: int = 10_000,
    max_cost_micros: int = 500_000,
    max_wall_seconds: float = 120,
    max_tool_calls: int = 10,
    max_delegation_depth: int = 2,
) -> DelegationBudget:
    return DelegationBudget(
        max_steps=max_steps,
        max_tokens=max_tokens,
        max_cost_micros=max_cost_micros,
        max_wall_seconds=max_wall_seconds,
        max_tool_calls=max_tool_calls,
        max_delegation_depth=max_delegation_depth,
    )


def _handoff(*, state_refs: tuple[str, ...] = ("artifact:1", "memory:2")) -> HandoffPacket:
    return HandoffPacket(
        operation_id="operation-1",
        objective_digest=OBJ,
        context_digest=CTX,
        state_refs=state_refs,
        checkpoint_digest=CHECKPOINT,
    )


def _grant(
    *,
    child: AgentIdentity | None = None,
    parent_budget: DelegationBudget | None = None,
    budget: DelegationBudget | None = None,
    lease_task_id: str = "swarm-task-1",
    lease_epoch: int = 1,
    delegation_depth: int = 1,
    issued_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(seconds=60),
) -> DelegationGrant:
    return DelegationGrant(
        delegation_id="delegation-1",
        lease_task_id=lease_task_id,
        parent_authority_digest="4" * 64,
        parent=_parent(),
        child=child or _child(),
        parent_budget=parent_budget or _parent_budget(),
        budget=budget or _child_budget(),
        handoff=_handoff(),
        issued_at=issued_at,
        expires_at=expires_at,
        lease_epoch=lease_epoch,
        delegation_depth=delegation_depth,
    )


def _usage(**overrides: int | float) -> DelegationUsage:
    values: dict[str, int | float] = {
        "steps": 5,
        "tokens": 2_000,
        "cost_micros": 100_000,
        "wall_seconds": 10.0,
        "tool_calls": 2,
    }
    values.update(overrides)
    return DelegationUsage(**values)


def test_identity_and_handoff_are_canonical() -> None:
    left = _child(capabilities=("read", "tool.execute", "read"))
    right = _child(capabilities=("tool.execute", "read"))
    handoff_left = _handoff(state_refs=("memory:2", "artifact:1", "memory:2"))
    handoff_right = _handoff(state_refs=("artifact:1", "memory:2"))

    assert left.capabilities == ("read", "tool.execute")
    assert left.digest == right.digest
    assert handoff_left.state_refs == ("artifact:1", "memory:2")
    assert handoff_left.digest == handoff_right.digest


def test_grant_binds_subset_authority_budget_handoff_and_fence() -> None:
    grant = _grant()

    payload = grant.authority_payload()

    assert set(payload["child"]["capabilities"]) < set(payload["parent"]["capabilities"])
    assert grant.budget.is_subset_of(grant.parent_budget)
    assert payload["handoff_digest"] == grant.handoff.digest
    assert payload["lease_task_id"] == "swarm-task-1"
    assert payload["parent_authority_digest"] == "4" * 64
    assert len(grant.digest) == 64
    assert len(grant.fencing_token) == 64


def test_child_capability_widening_fails_closed() -> None:
    with pytest.raises(DelegationContractError, match="exceed parent authority"):
        _grant(child=_child(capabilities=("tool.execute", "admin.root")))


def test_cross_tenant_delegation_fails_closed() -> None:
    with pytest.raises(DelegationContractError, match="cross tenant"):
        _grant(child=_child(tenant_id="tenant-b"))


def test_same_agent_cannot_delegate_to_itself() -> None:
    parent = _parent()
    child = AgentIdentity(
        agent_id=parent.agent_id,
        principal_id="principal-child",
        tenant_id=parent.tenant_id,
        capabilities=("read",),
    )
    with pytest.raises(DelegationContractError, match="must differ"):
        _grant(child=child)


@pytest.mark.parametrize(
    "budget",
    (
        _child_budget(max_steps=101),
        _child_budget(max_tokens=100_001),
        _child_budget(max_cost_micros=5_000_001),
        _child_budget(max_wall_seconds=601),
        _child_budget(max_tool_calls=51),
        _child_budget(max_delegation_depth=4),
    ),
)
def test_budget_widening_fails_closed(budget: DelegationBudget) -> None:
    with pytest.raises(DelegationContractError, match="exceeds parent budget"):
        _grant(budget=budget)


def test_lease_cannot_outlive_delegated_wall_budget() -> None:
    with pytest.raises(DelegationContractError, match="lease duration exceeds"):
        _grant(
            budget=_child_budget(max_wall_seconds=30),
            expires_at=NOW + timedelta(seconds=31),
        )


def test_delegation_depth_must_be_positive_and_within_budget() -> None:
    with pytest.raises(DelegationContractError, match="delegation_depth"):
        _grant(delegation_depth=0)

    with pytest.raises(DelegationContractError, match="depth exceeds"):
        _grant(
            budget=_child_budget(max_delegation_depth=1),
            delegation_depth=2,
        )


def test_descendant_grant_advances_depth_and_cannot_outlive_parent() -> None:
    parent_grant = _grant(
        budget=_child_budget(max_delegation_depth=2),
        expires_at=NOW + timedelta(seconds=90),
    )
    grandchild = AgentIdentity(
        agent_id="agent-grandchild",
        principal_id="principal-grandchild",
        tenant_id="tenant-a",
        capabilities=("read",),
    )

    child_grant = derive_child_grant(
        parent_grant,
        delegation_id="delegation-2",
        lease_task_id="swarm-task-2",
        child=grandchild,
        budget=DelegationBudget(
            max_steps=5,
            max_tokens=1_000,
            max_cost_micros=50_000,
            max_wall_seconds=30,
            max_tool_calls=2,
            max_delegation_depth=2,
        ),
        handoff=_handoff(state_refs=("artifact:child",)),
        issued_at=NOW + timedelta(seconds=5),
        expires_at=NOW + timedelta(seconds=35),
        lease_epoch=1,
    )

    assert child_grant.parent == parent_grant.child
    assert child_grant.parent_authority_digest == parent_grant.digest
    assert child_grant.delegation_depth == 2

    with pytest.raises(DelegationContractError, match="cannot outlive parent"):
        derive_child_grant(
            parent_grant,
            delegation_id="delegation-3",
            lease_task_id="swarm-task-3",
            child=grandchild,
            budget=child_grant.budget,
            handoff=_handoff(state_refs=("artifact:late",)),
            issued_at=NOW + timedelta(seconds=10),
            expires_at=NOW + timedelta(seconds=91),
            lease_epoch=1,
        )

    with pytest.raises(DelegationContractError, match="depth exhausted"):
        derive_child_grant(
            child_grant,
            delegation_id="delegation-4",
            lease_task_id="swarm-task-4",
            child=AgentIdentity(
                agent_id="agent-great-grandchild",
                principal_id="principal-great-grandchild",
                tenant_id="tenant-a",
                capabilities=("read",),
            ),
            budget=child_grant.budget,
            handoff=_handoff(state_refs=("artifact:deep",)),
            issued_at=NOW + timedelta(seconds=10),
            expires_at=NOW + timedelta(seconds=20),
            lease_epoch=1,
        )


def test_generic_commit_authorization_accepts_exact_grant() -> None:
    grant = _grant()

    decision = authorize_child_commit(
        grant,
        child_agent_id=grant.child.agent_id,
        presented_task_id=grant.lease_task_id,
        presented_epoch=grant.lease_epoch,
        presented_fencing_token=grant.fencing_token,
        handoff_digest=grant.handoff.digest,
        usage=_usage(),
        required_capability="tool.execute",
        now=NOW + timedelta(seconds=1),
    )

    assert decision.accepted is True
    assert decision.reason == "authorized"
    assert decision.accepted_evidence_ref().digest == decision.digest


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("child_agent_id", "agent-other", "child identity mismatch"),
        ("presented_task_id", "task-other", "lease task mismatch"),
        ("presented_epoch", 2, "stale lease epoch"),
        ("presented_fencing_token", "f" * 64, "fencing token mismatch"),
        ("handoff_digest", "e" * 64, "handoff digest mismatch"),
        ("required_capability", "write", "required capability not delegated"),
    ),
)
def test_generic_commit_authorization_rejects_identity_drift(
    field: str,
    value: object,
    reason: str,
) -> None:
    grant = _grant()
    kwargs: dict[str, object] = {
        "child_agent_id": grant.child.agent_id,
        "presented_task_id": grant.lease_task_id,
        "presented_epoch": grant.lease_epoch,
        "presented_fencing_token": grant.fencing_token,
        "handoff_digest": grant.handoff.digest,
        "usage": _usage(),
        "required_capability": "tool.execute",
        "now": NOW + timedelta(seconds=1),
    }
    kwargs[field] = value

    decision = authorize_child_commit(grant, **kwargs)

    assert decision.accepted is False
    assert decision.reason == reason
    with pytest.raises(DelegationContractError, match="cannot become promotion evidence"):
        decision.accepted_evidence_ref()


def test_generic_commit_rejects_time_and_budget_drift() -> None:
    grant = _grant()

    before = authorize_child_commit(
        grant,
        child_agent_id=grant.child.agent_id,
        presented_task_id=grant.lease_task_id,
        presented_epoch=grant.lease_epoch,
        presented_fencing_token=grant.fencing_token,
        handoff_digest=grant.handoff.digest,
        usage=_usage(),
        required_capability="tool.execute",
        now=NOW - timedelta(seconds=1),
    )
    expired = authorize_child_commit(
        grant,
        child_agent_id=grant.child.agent_id,
        presented_task_id=grant.lease_task_id,
        presented_epoch=grant.lease_epoch,
        presented_fencing_token=grant.fencing_token,
        handoff_digest=grant.handoff.digest,
        usage=_usage(),
        required_capability="tool.execute",
        now=grant.expires_at,
    )
    over_budget = authorize_child_commit(
        grant,
        child_agent_id=grant.child.agent_id,
        presented_task_id=grant.lease_task_id,
        presented_epoch=grant.lease_epoch,
        presented_fencing_token=grant.fencing_token,
        handoff_digest=grant.handoff.digest,
        usage=_usage(tokens=grant.budget.max_tokens + 1),
        required_capability="tool.execute",
        now=NOW + timedelta(seconds=1),
    )

    assert before.reason == "lease not yet valid"
    assert expired.reason == "lease expired"
    assert over_budget.reason == "delegation budget exceeded"


def _leased_runtime(
    *,
    worker_capabilities: frozenset[str] = frozenset({"tool.execute", "read"}),
) -> tuple[SwarmRuntime, list[float], object]:
    clock = [100.0]
    runtime = SwarmRuntime(default_lease_seconds=30.0, clock=lambda: clock[0])
    runtime.register_worker(
        "agent-child",
        capabilities=worker_capabilities,
        capacity=1,
    )
    runtime.submit(
        SwarmTask(
            id="swarm-task-1",
            payload={"kind": "delegated"},
            required_capabilities=frozenset({"tool.execute"}),
        )
    )
    leased = lease_exact(runtime, "agent-child", "swarm-task-1")
    return runtime, clock, fence_for(leased)


def test_live_swarm_fence_authorizes_current_child_only() -> None:
    runtime, _clock, fence = _leased_runtime()
    grant = _grant(
        child=_child(agent_id="agent-child"),
        lease_task_id="swarm-task-1",
        lease_epoch=fence.attempt,
    )

    decision = authorize_swarm_child_commit(
        runtime,
        fence,
        grant,
        usage=_usage(),
        required_capability="tool.execute",
        now=NOW + timedelta(seconds=1),
    )

    assert decision.accepted is True


def test_live_worker_capabilities_must_cover_delegated_authority() -> None:
    runtime, _clock, fence = _leased_runtime(
        worker_capabilities=frozenset({"tool.execute"})
    )
    grant = _grant(
        child=_child(agent_id="agent-child"),
        lease_task_id="swarm-task-1",
        lease_epoch=fence.attempt,
    )

    decision = authorize_swarm_child_commit(
        runtime,
        fence,
        grant,
        usage=_usage(),
        required_capability="tool.execute",
        now=NOW + timedelta(seconds=1),
    )

    assert decision.accepted is False
    assert decision.reason == "runtime worker capability mismatch"


def test_runtime_deadline_rejects_even_before_reaper_runs() -> None:
    runtime, clock, fence = _leased_runtime()
    grant = _grant(
        child=_child(agent_id="agent-child"),
        lease_task_id="swarm-task-1",
        lease_epoch=fence.attempt,
    )
    clock[0] = 130.0

    decision = authorize_swarm_child_commit(
        runtime,
        fence,
        grant,
        usage=_usage(),
        required_capability="tool.execute",
        now=NOW + timedelta(seconds=10),
    )

    assert decision.accepted is False
    assert decision.reason == "runtime lease expired"


def test_reissued_lease_fences_out_prior_attempt() -> None:
    runtime, clock, old_fence = _leased_runtime()
    old_grant = _grant(
        child=_child(agent_id="agent-child"),
        lease_task_id="swarm-task-1",
        lease_epoch=old_fence.attempt,
    )
    clock[0] = 131.0
    assert runtime.reap_expired() == 1
    new_lease = lease_exact(runtime, "agent-child", "swarm-task-1")
    new_fence = fence_for(new_lease)

    stale_runtime = authorize_swarm_child_commit(
        runtime,
        old_fence,
        old_grant,
        usage=_usage(),
        required_capability="tool.execute",
        now=NOW + timedelta(seconds=15),
    )
    stale_epoch = authorize_swarm_child_commit(
        runtime,
        new_fence,
        old_grant,
        usage=_usage(),
        required_capability="tool.execute",
        now=NOW + timedelta(seconds=15),
    )

    assert new_fence.attempt == old_fence.attempt + 1
    assert stale_runtime.reason == "runtime lease fence rejected"
    assert stale_epoch.reason == "stale lease epoch"
