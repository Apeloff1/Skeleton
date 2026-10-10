from __future__ import annotations

import sqlite3

import pytest

from skeleton.automation.agents.agent_runtime import (
    AgentDescriptor,
    AgentLifecycleState,
    AgentResourceUsage,
    AgentRuntimeConflict,
    AgentRuntimeDenied,
    AgentRuntimeError,
    DurableAgentSupervisor,
    SQLiteAgentRuntimeStore,
)
from skeleton.automation.agents.delegation_qualification import (
    AgentDelegationAuthority,
    DelegationBudget,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _budget(
    *,
    parallel: int = 2,
    steps: int = 10,
    tokens: int = 1_000,
    cost: float = 10.0,
    wall: float = 100.0,
) -> DelegationBudget:
    return DelegationBudget(
        max_parallel_tasks=parallel,
        max_steps=steps,
        max_tokens=tokens,
        max_cost_units=cost,
        max_wall_time_s=wall,
    )


def _descriptor(
    *,
    agent_id: str = "agent-a",
    budget: DelegationBudget | None = None,
) -> AgentDescriptor:
    return AgentDescriptor(
        agent_id=agent_id,
        role="builder",
        objective_scopes=("repo", "tests"),
        capabilities=("read", "write"),
        memory_policy="bounded",
        budget=budget or _budget(),
    )


def _authority(
    *,
    agent_id: str = "agent-a",
    budget: DelegationBudget | None = None,
    expires_at: float = 1_000.0,
    capabilities: tuple[str, ...] = ("read", "write"),
    scopes: tuple[str, ...] = ("repo", "tests"),
) -> AgentDelegationAuthority:
    return AgentDelegationAuthority(
        agent_id=agent_id,
        parent_agent_id="supervisor",
        generation=2,
        capabilities=capabilities,
        scopes=scopes,
        budget=budget or _budget(),
        expires_at=expires_at,
        delegation_id="delegation-a",
    )


def test_durable_agent_lifecycle_and_resource_accounting(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    clock = Clock()
    supervisor = DurableAgentSupervisor(store, clock=clock)

    registered = supervisor.register(
        "tenant-a",
        _descriptor(),
        _authority(),
    )
    assert registered.state is AgentLifecycleState.REGISTERED
    assert registered.sequence == 1
    assert registered.active_task_ids == ()
    assert registered.usage == AgentResourceUsage()

    running = supervisor.start("tenant-a", "agent-a")
    assert running.state is AgentLifecycleState.RUNNING

    acquired = supervisor.acquire_task("tenant-a", "agent-a", "task-1")
    assert acquired.active_task_ids == ("task-1",)

    metered = supervisor.record_usage(
        "tenant-a",
        "agent-a",
        steps=2,
        tokens=120,
        cost_units=0.5,
        wall_time_s=3.0,
    )
    assert metered.usage == AgentResourceUsage(
        steps=2,
        tokens=120,
        cost_units=0.5,
        wall_time_s=3.0,
    )

    released = supervisor.release_task(
        "tenant-a",
        "agent-a",
        "task-1",
    )
    assert released.active_task_ids == ()

    completed = supervisor.complete("tenant-a", "agent-a")
    assert completed.state is AgentLifecycleState.COMPLETED
    assert completed.usage == metered.usage

    history = supervisor.history("tenant-a", "agent-a")
    assert [item.sequence for item in history] == list(
        range(1, len(history) + 1)
    )
    assert history[0].previous_digest == "0" * 64
    for previous, current in zip(history, history[1:]):
        assert current.previous_digest == previous.checkpoint_digest


def test_restart_restores_exact_checkpoint_and_usage(tmp_path) -> None:
    path = tmp_path / "agent.sqlite3"
    clock = Clock()

    first_store = SQLiteAgentRuntimeStore(path)
    first = DurableAgentSupervisor(first_store, clock=clock)
    first.register("tenant-a", _descriptor(), _authority())
    first.start("tenant-a", "agent-a")
    first.acquire_task("tenant-a", "agent-a", "task-1")
    expected = first.record_usage(
        "tenant-a",
        "agent-a",
        steps=1,
        tokens=50,
        cost_units=0.25,
        wall_time_s=1.5,
    )
    first_store.close()

    reopened = SQLiteAgentRuntimeStore(path)
    second = DurableAgentSupervisor(reopened, clock=clock)

    restored = second.checkpoint("tenant-a", "agent-a")

    assert restored == expected
    assert restored.state is AgentLifecycleState.RUNNING
    assert restored.active_task_ids == ("task-1",)
    assert restored.usage.tokens == 50


def test_registration_rejects_authority_capability_widening(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())

    descriptor = AgentDescriptor(
        agent_id="agent-a",
        role="builder",
        objective_scopes=("repo",),
        capabilities=("read",),
        memory_policy="bounded",
        budget=_budget(),
    )
    authority = _authority(
        capabilities=("read", "write"),
        scopes=("repo",),
    )

    with pytest.raises(
        AgentRuntimeDenied,
        match="exceeds descriptor capabilities",
    ):
        supervisor.register("tenant-a", descriptor, authority)


def test_registration_rejects_authority_scope_widening(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())

    with pytest.raises(
        AgentRuntimeDenied,
        match="exceeds descriptor objective scopes",
    ):
        supervisor.register(
            "tenant-a",
            _descriptor(),
            _authority(scopes=("repo", "tests", "prod")),
        )


def test_registration_rejects_authority_budget_widening(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())

    with pytest.raises(
        AgentRuntimeDenied,
        match="exceeds descriptor resource budget",
    ):
        supervisor.register(
            "tenant-a",
            _descriptor(budget=_budget(parallel=1)),
            _authority(budget=_budget(parallel=2)),
        )


def test_parallel_task_limit_is_enforced_without_state_drift(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())
    budget = _budget(parallel=1)
    supervisor.register(
        "tenant-a",
        _descriptor(budget=budget),
        _authority(budget=budget),
    )
    supervisor.start("tenant-a", "agent-a")
    first = supervisor.acquire_task("tenant-a", "agent-a", "task-1")

    with pytest.raises(
        AgentRuntimeDenied,
        match="parallel-task budget exhausted",
    ):
        supervisor.acquire_task("tenant-a", "agent-a", "task-2")

    assert supervisor.checkpoint("tenant-a", "agent-a") == first


def test_cumulative_resource_budget_is_fail_closed(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())
    budget = _budget(tokens=100)
    supervisor.register(
        "tenant-a",
        _descriptor(budget=budget),
        _authority(budget=budget),
    )
    supervisor.start("tenant-a", "agent-a")
    accepted = supervisor.record_usage(
        "tenant-a",
        "agent-a",
        tokens=90,
    )

    with pytest.raises(
        AgentRuntimeDenied,
        match="resource budget exhausted",
    ):
        supervisor.record_usage(
            "tenant-a",
            "agent-a",
            tokens=11,
        )

    assert supervisor.checkpoint("tenant-a", "agent-a") == accepted


def test_authority_expiry_blocks_new_work_but_not_accounting_cleanup(
    tmp_path,
) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    clock = Clock(100.0)
    supervisor = DurableAgentSupervisor(store, clock=clock)
    supervisor.register(
        "tenant-a",
        _descriptor(),
        _authority(expires_at=110.0),
    )
    supervisor.start("tenant-a", "agent-a")
    supervisor.acquire_task("tenant-a", "agent-a", "task-1")

    clock.value = 110.0

    with pytest.raises(
        AgentRuntimeDenied,
        match="delegation authority is expired",
    ):
        supervisor.acquire_task("tenant-a", "agent-a", "task-2")

    accounted = supervisor.record_usage(
        "tenant-a",
        "agent-a",
        steps=1,
        tokens=25,
        cost_units=0.1,
        wall_time_s=0.5,
    )
    assert accounted.usage.tokens == 25

    released = supervisor.release_task(
        "tenant-a",
        "agent-a",
        "task-1",
    )
    assert released.active_task_ids == ()

    completed = supervisor.complete("tenant-a", "agent-a")
    assert completed.state is AgentLifecycleState.COMPLETED


def test_expired_authority_cannot_start_suspended_agent(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    clock = Clock(100.0)
    supervisor = DurableAgentSupervisor(store, clock=clock)
    supervisor.register(
        "tenant-a",
        _descriptor(),
        _authority(expires_at=105.0),
    )
    supervisor.start("tenant-a", "agent-a")
    supervisor.suspend("tenant-a", "agent-a")
    clock.value = 105.0

    with pytest.raises(
        AgentRuntimeDenied,
        match="delegation authority is expired",
    ):
        supervisor.start("tenant-a", "agent-a")


def test_suspend_and_complete_require_no_active_tasks(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())
    supervisor.register("tenant-a", _descriptor(), _authority())
    supervisor.start("tenant-a", "agent-a")
    supervisor.acquire_task("tenant-a", "agent-a", "task-1")

    with pytest.raises(
        AgentRuntimeDenied,
        match="cannot suspend while tasks are active",
    ):
        supervisor.suspend("tenant-a", "agent-a")
    with pytest.raises(
        AgentRuntimeDenied,
        match="cannot complete while tasks are active",
    ):
        supervisor.complete("tenant-a", "agent-a")


def test_cancel_terminalizes_and_clears_active_tasks(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())
    supervisor.register("tenant-a", _descriptor(), _authority())
    supervisor.start("tenant-a", "agent-a")
    supervisor.acquire_task("tenant-a", "agent-a", "task-1")

    cancelled = supervisor.cancel(
        "tenant-a",
        "agent-a",
        reason="operator-cancelled",
    )

    assert cancelled.state is AgentLifecycleState.CANCELLED
    assert cancelled.active_task_ids == ()
    assert supervisor.cancel("tenant-a", "agent-a") == cancelled


def test_duplicate_registration_must_be_identical(tmp_path) -> None:
    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    supervisor = DurableAgentSupervisor(store, clock=Clock())
    original = supervisor.register(
        "tenant-a",
        _descriptor(),
        _authority(),
    )
    replay = supervisor.register(
        "tenant-a",
        _descriptor(),
        _authority(),
    )
    assert replay == original

    with pytest.raises(
        AgentRuntimeConflict,
        match="different contract",
    ):
        supervisor.register(
            "tenant-a",
            AgentDescriptor(
                agent_id="agent-a",
                role="reviewer",
                objective_scopes=("repo", "tests"),
                capabilities=("read", "write"),
                memory_policy="bounded",
                budget=_budget(),
            ),
            _authority(),
        )


def test_tampered_checkpoint_is_rejected_on_restore(tmp_path) -> None:
    path = tmp_path / "agent.sqlite3"
    store = SQLiteAgentRuntimeStore(path)
    supervisor = DurableAgentSupervisor(store, clock=Clock())
    supervisor.register("tenant-a", _descriptor(), _authority())
    supervisor.start("tenant-a", "agent-a")
    store.close()

    connection = sqlite3.connect(path)
    row = connection.execute(
        """
        SELECT sequence, checkpoint_json
        FROM agent_runtime_checkpoint
        ORDER BY sequence DESC LIMIT 1
        """
    ).fetchone()
    assert row is not None
    payload = str(row[1]).replace(
        '"state":"running"',
        '"state":"completed"',
    )
    connection.execute(
        """
        UPDATE agent_runtime_checkpoint
        SET checkpoint_json = ?
        WHERE sequence = ?
        """,
        (payload, row[0]),
    )
    connection.commit()
    connection.close()

    reopened = SQLiteAgentRuntimeStore(path)
    restored = DurableAgentSupervisor(reopened, clock=Clock())

    with pytest.raises(
        AgentRuntimeError,
        match="checkpoint digest mismatch",
    ):
        restored.checkpoint("tenant-a", "agent-a")


def test_store_rejects_stale_checkpoint_append(tmp_path) -> None:
    from skeleton.automation.agents import agent_runtime as runtime_module

    store = SQLiteAgentRuntimeStore(tmp_path / "agent.sqlite3")
    clock = Clock()
    supervisor = DurableAgentSupervisor(store, clock=clock)
    first = supervisor.register(
        "tenant-a",
        _descriptor(),
        _authority(),
    )

    descriptor, authority = store.registration(
        "tenant-a",
        "agent-a",
    ) or (None, None)
    assert descriptor is not None
    assert authority is not None

    stale = runtime_module._checkpoint(
        tenant_id="tenant-a",
        agent_id="agent-a",
        sequence=first.sequence + 1,
        state=AgentLifecycleState.RUNNING,
        descriptor_digest=descriptor.digest,
        authority_digest=authority.digest,
        usage=first.usage,
        active_task_ids=(),
        reason="started",
        created_at=clock(),
        previous_digest=first.checkpoint_digest,
    )

    supervisor.start("tenant-a", "agent-a")

    with pytest.raises(
        AgentRuntimeConflict,
        match="sequence changed before append",
    ):
        store.append(stale)
