from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.agents.delegation_qualification import (
    AgentDelegationAuthority,
    AgentDelegationError,
    DelegationBudget,
    qualify_agent_delegation,
)
from skeleton.agents.swarm_fencing import LeaseFence
from skeleton.agents.swarm_runtime import (
    SwarmTask,
    TaskState as RuntimeTaskState,
)
from skeleton.swarm.handoff import TaskEnvelope, TaskState


NOW = 1_800_000_000.0


def _budget(
    *,
    max_parallel_tasks: int = 4,
    max_steps: int = 16,
    max_tokens: int = 20_000,
    max_cost_units: float = 20.0,
    max_wall_time_s: float = 600.0,
) -> DelegationBudget:
    return DelegationBudget(
        max_parallel_tasks=max_parallel_tasks,
        max_steps=max_steps,
        max_tokens=max_tokens,
        max_cost_units=max_cost_units,
        max_wall_time_s=max_wall_time_s,
    )


def _parent(**overrides: object) -> AgentDelegationAuthority:
    values: dict[str, object] = {
        "agent_id": "supervisor-1",
        "parent_agent_id": None,
        "generation": 1,
        "capabilities": ("repo.read", "repo.write", "tests.run"),
        "scopes": ("repo:Apeloff1/Skeleton", "branch:p1"),
        "budget": _budget(),
        "expires_at": NOW + 3600.0,
        "delegation_id": "delegation-root-1",
    }
    values.update(overrides)
    return AgentDelegationAuthority(**values)


def _child(**overrides: object) -> AgentDelegationAuthority:
    values: dict[str, object] = {
        "agent_id": "worker-1",
        "parent_agent_id": "supervisor-1",
        "generation": 2,
        "capabilities": ("repo.read", "tests.run"),
        "scopes": ("repo:Apeloff1/Skeleton",),
        "budget": _budget(
            max_parallel_tasks=2,
            max_steps=8,
            max_tokens=10_000,
            max_cost_units=8.0,
            max_wall_time_s=300.0,
        ),
        "expires_at": NOW + 1800.0,
        "delegation_id": "delegation-child-1",
    }
    values.update(overrides)
    return AgentDelegationAuthority(**values)


def _envelope(**overrides: object) -> TaskEnvelope:
    values: dict[str, object] = {
        "task_id": "task-1",
        "capability": "tests.run",
        "input": {"suite": "unit", "shard": 1},
        "requester": "supervisor-1",
        "state": TaskState.WORKING,
        "assignee": "worker-1",
        "artefacts": [],
        "error": None,
        "created_at": NOW - 30.0,
        "updated_at": NOW - 10.0,
    }
    values.update(overrides)
    return TaskEnvelope(**values)


def _fence(**overrides: object) -> LeaseFence:
    values: dict[str, object] = {
        "task_id": "task-1",
        "worker_id": "worker-1",
        "attempt": 1,
        "deadline": NOW + 60.0,
    }
    values.update(overrides)
    return LeaseFence(**values)



def _live_task(**overrides: object) -> SwarmTask:
    values: dict[str, object] = {
        "id": "task-1",
        "payload": {"suite": "unit", "shard": 1},
        "required_capabilities": frozenset({"tests.run"}),
        "state": RuntimeTaskState.LEASED,
        "attempts": 1,
        "leased_to": "worker-1",
        "lease_deadline": NOW + 60.0,
    }
    values.update(overrides)
    return SwarmTask(**values)


def _qualify(**overrides):
    values = {
        "parent": _parent(),
        "child": _child(),
        "envelope": _envelope(),
        "fence": _fence(),
        "live_task": _live_task(),
        "observed_at": NOW,
    }
    values.update(overrides)
    return qualify_agent_delegation(**values)


def test_accepts_exact_bounded_handoff_and_lease() -> None:
    decision = _qualify()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.decision_digest) == 64

    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "agent_delegation_qualification"
    assert evidence.digest == decision.decision_digest


@pytest.mark.parametrize(
    ("child", "reason"),
    (
        (
            _child(capabilities=("repo.read", "tests.run", "secrets.read")),
            "child-capability-authority-widened",
        ),
        (
            _child(scopes=("repo:Apeloff1/Skeleton", "tenant:other")),
            "child-scope-authority-widened",
        ),
        (
            _child(
                budget=_budget(
                    max_parallel_tasks=8,
                    max_steps=8,
                    max_tokens=10_000,
                    max_cost_units=8.0,
                    max_wall_time_s=300.0,
                )
            ),
            "child-budget-authority-widened",
        ),
        (
            _child(expires_at=NOW + 7200.0),
            "child-expiry-exceeds-parent",
        ),
        (
            _child(parent_agent_id="other-parent"),
            "parent-identity-mismatch",
        ),
        (
            _child(generation=3),
            "delegation-generation-mismatch",
        ),
        (
            _child(delegation_id="delegation-root-1"),
            "delegation-id-reused",
        ),
    ),
)
def test_child_authority_cannot_widen_or_break_lineage(
    child: AgentDelegationAuthority,
    reason: str,
) -> None:
    decision = _qualify(child=child)

    assert decision.accepted is False
    assert reason in decision.reasons


@pytest.mark.parametrize(
    ("envelope", "reason"),
    (
        (
            _envelope(requester="other-parent"),
            "handoff-requester-mismatch",
        ),
        (
            _envelope(assignee="other-worker"),
            "handoff-assignee-mismatch",
        ),
        (
            _envelope(capability="repo.write"),
            "handoff-capability-not-delegated",
        ),
        (
            _envelope(state=TaskState.SUBMITTED),
            "handoff-not-working",
        ),
        (
            _envelope(updated_at=NOW + 1.0),
            "handoff-future-dated",
        ),
        (
            _envelope(created_at=NOW, updated_at=NOW - 1.0),
            "handoff-time-order-invalid",
        ),
    ),
)
def test_handoff_identity_and_state_fail_closed(
    envelope: TaskEnvelope,
    reason: str,
) -> None:
    decision = _qualify(envelope=envelope)

    assert decision.accepted is False
    assert reason in decision.reasons


@pytest.mark.parametrize(
    ("fence", "reason"),
    (
        (
            _fence(task_id="other-task"),
            "lease-task-mismatch",
        ),
        (
            _fence(worker_id="other-worker"),
            "lease-worker-mismatch",
        ),
        (
            _fence(deadline=NOW),
            "lease-expired",
        ),
        (
            _fence(deadline=None),
            "lease-deadline-missing",
        ),
    ),
)
def test_lease_fence_must_match_exact_live_handoff(
    fence: LeaseFence,
    reason: str,
) -> None:
    decision = _qualify(fence=fence)

    assert decision.accepted is False
    assert reason in decision.reasons


def test_expired_parent_or_child_authority_rejects() -> None:
    parent = _parent(expires_at=NOW - 1.0)
    child = _child(expires_at=NOW - 2.0)

    decision = _qualify(parent=parent, child=child)

    assert decision.accepted is False
    assert "parent-authority-expired" in decision.reasons
    assert "child-authority-expired" in decision.reasons


def test_rejected_decision_cannot_become_promotion_evidence() -> None:
    decision = _qualify(
        child=_child(capabilities=("repo.read", "tests.run", "secrets.read"))
    )

    assert decision.accepted is False
    with pytest.raises(AgentDelegationError, match="cannot become"):
        decision.accepted_evidence_ref()


def test_authority_tokens_are_sorted_deduplicated_and_digest_stable() -> None:
    left = _child(
        capabilities=("tests.run", "repo.read", "tests.run"),
        scopes=("repo:Apeloff1/Skeleton", "repo:Apeloff1/Skeleton"),
    )
    right = _child(
        capabilities=("repo.read", "tests.run"),
        scopes=("repo:Apeloff1/Skeleton",),
    )

    assert left.capabilities == right.capabilities
    assert left.scopes == right.scopes
    assert left.digest == right.digest


def test_handoff_json_key_order_does_not_change_decision_identity() -> None:
    left = _qualify(
        envelope=_envelope(input={"suite": "unit", "shard": 1}),
    )
    right = _qualify(
        envelope=_envelope(input={"shard": 1, "suite": "unit"}),
    )

    assert left.accepted is True
    assert right.accepted is True
    assert left.handoff_digest == right.handoff_digest
    assert left.decision_digest == right.decision_digest


def test_non_json_handoff_payload_fails_closed() -> None:
    envelope = _envelope(input={"bad": object()})

    with pytest.raises(
        AgentDelegationError,
        match="handoff payload must be canonical JSON",
    ):
        _qualify(envelope=envelope)


def test_observation_time_is_not_part_of_stable_decision_identity() -> None:
    first = _qualify(observed_at=NOW)
    second = _qualify(observed_at=NOW + 10.0)

    assert first.accepted is True
    assert second.accepted is True
    assert first.observed_at != second.observed_at
    assert first.decision_digest == second.decision_digest


def test_budget_requires_positive_finite_values() -> None:
    with pytest.raises(AgentDelegationError, match="max_parallel_tasks"):
        _budget(max_parallel_tasks=0)
    with pytest.raises(AgentDelegationError, match="max_cost_units"):
        _budget(max_cost_units=float("nan"))
    with pytest.raises(AgentDelegationError, match="max_wall_time_s"):
        _budget(max_wall_time_s=0.0)


def test_authority_rejects_self_parenting() -> None:
    with pytest.raises(AgentDelegationError, match="delegate authority to itself"):
        _child(agent_id="worker-1", parent_agent_id="worker-1")


def test_parent_and_child_digests_bind_budget_and_authority() -> None:
    baseline = _qualify()
    tighter = _qualify(
        child=_child(
            budget=_budget(
                max_parallel_tasks=1,
                max_steps=6,
                max_tokens=8_000,
                max_cost_units=6.0,
                max_wall_time_s=240.0,
            )
        )
    )

    assert baseline.accepted is True
    assert tighter.accepted is True
    assert baseline.child_authority_digest != tighter.child_authority_digest
    assert baseline.decision_digest != tighter.decision_digest

@pytest.mark.parametrize(
    ("live_task", "reason"),
    (
        (
            _live_task(id="other-task"),
            "live-lease-task-mismatch",
        ),
        (
            _live_task(state=RuntimeTaskState.QUEUED),
            "live-lease-not-leased",
        ),
        (
            _live_task(leased_to="other-worker"),
            "live-lease-worker-mismatch",
        ),
        (
            _live_task(attempts=2),
            "live-lease-attempt-mismatch",
        ),
        (
            _live_task(lease_deadline=NOW + 120.0),
            "live-lease-deadline-mismatch",
        ),
        (
            _live_task(required_capabilities=frozenset({"repo.read"})),
            "live-task-capability-mismatch",
        ),
    ),
)
def test_live_lease_snapshot_prevents_stale_fence_reuse(
    live_task: SwarmTask,
    reason: str,
) -> None:
    decision = _qualify(live_task=live_task)

    assert decision.accepted is False
    assert reason in decision.reasons


def test_live_lease_identity_is_digest_bound() -> None:
    baseline = _qualify()
    changed = _qualify(
        live_task=_live_task(
            required_capabilities=frozenset({"tests.run", "repo.read"})
        )
    )

    assert baseline.accepted is True
    assert changed.accepted is True
    assert baseline.live_lease_digest != changed.live_lease_digest
    assert baseline.decision_digest != changed.decision_digest

def test_rejects_authority_exactly_at_expiry_boundary() -> None:
    parent = _parent(expires_at=NOW)
    decision = _qualify(parent=parent)
    assert decision.accepted is False
    assert "parent-authority-expired" in decision.reasons

    child = _child(expires_at=NOW)
    decision = _qualify(child=child)
    assert decision.accepted is False
    assert "child-authority-expired" in decision.reasons
