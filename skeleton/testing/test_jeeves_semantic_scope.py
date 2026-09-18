from __future__ import annotations

import pytest

from skeleton.jeeves.agent.execution_audit import AuditEventKind
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime
from skeleton.jeeves.agent.provider import (
    DeterministicProvider,
    ProviderRouter,
)
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.semantic_frontier import LensInteractionKind
from skeleton.jeeves.agent.semantic_plane import SemanticLensPlane
from skeleton.jeeves.agent.semantic_scope import ScopedSemanticPlanePool
from skeleton.jeeves.agent.types import AgentContractError, Goal


class TickClock:
    def __init__(self) -> None:
        self.value = 5_000.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


def _inputs(
    run_id: str,
    *,
    tenant: str = "tenant-scope",
    user: str = "user-a",
    workspace: str = "workspace-a",
    session: str = "session-a",
) -> RunInputs:
    return RunInputs(
        goal=Goal(
            "goal-semantic-scope",
            "Keep mutable semantic learning inside its data scope.",
            success_criteria=(
                "Do not leak learned semantic state across scopes.",
            ),
        ),
        tenant_id=tenant,
        user_id=user,
        workspace_id=workspace,
        session_id=session,
        run_id=run_id,
    )


def _runtime(clock: TickClock) -> FrontierJeevesAgentRuntime:
    provider = DeterministicProvider(("unused",))
    return FrontierJeevesAgentRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )


def _declare_one(plane: SemanticLensPlane, run: str):
    candidate = plane.topology.bridge_candidates(
        limit=1,
        minimum_score=0.0,
    )[0]
    prediction = plane.declare_topology_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run=run,
        predicted_at=10.0,
    )
    return candidate, prediction


def test_scope_pool_shares_contract_but_isolates_mutable_semantic_state() -> None:
    template = SemanticLensPlane()
    pool = ScopedSemanticPlanePool(template, maximum_scopes=8)

    left = pool.get("tenant", "user-a", "workspace")
    same = pool.get("tenant", "user-a", "workspace")
    right = pool.get("tenant", "user-b", "workspace")

    assert same is left
    assert right is not left
    assert left is not template
    assert left.registry is right.registry is template.registry
    assert left.topology is right.topology is template.topology
    assert left.fingerprint == right.fingerprint == template.fingerprint

    assert left.topology_learning is not right.topology_learning
    assert left.prediction_ledger is not right.prediction_ledger
    assert left.governance is not right.governance
    assert left.governance.registry.lab is not right.governance.registry.lab
    assert left.tangent_graph is not right.tangent_graph

    _declare_one(left, "left-run")

    assert left.topology_learning.snapshot().prediction_count == 1
    assert right.topology_learning.snapshot().prediction_count == 0
    assert template.topology_learning.snapshot().prediction_count == 0


def test_runtime_semantic_scope_persists_across_sessions_but_not_workspaces() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    first = _inputs(
        "run-scope-session-a",
        session="session-a",
    )
    later_session = _inputs(
        "run-scope-session-b",
        session="session-b",
    )
    other_workspace = _inputs(
        "run-scope-workspace-b",
        workspace="workspace-b",
        session="session-c",
    )

    first_plane = runtime.semantic_plane_for(first)
    later_plane = runtime.semantic_plane_for(later_session)
    other_plane = runtime.semantic_plane_for(other_workspace)

    assert later_plane is first_plane
    assert other_plane is not first_plane

    _declare_one(first_plane, "cross-session-run")

    assert later_plane.topology_learning.snapshot().prediction_count == 1
    assert other_plane.topology_learning.snapshot().prediction_count == 0


def test_scope_pool_lru_eviction_only_resets_evicted_scope() -> None:
    template = SemanticLensPlane()
    pool = ScopedSemanticPlanePool(template, maximum_scopes=2)

    first = pool.get("tenant", "user-a", "workspace")
    second = pool.get("tenant", "user-b", "workspace")
    _declare_one(second, "second-run")

    # Touch first so second is the least-recently-used scope.
    assert pool.get("tenant", "user-a", "workspace") is first
    third = pool.get("tenant", "user-c", "workspace")

    assert third is not first
    assert pool.contains("tenant", "user-a", "workspace") is True
    assert pool.contains("tenant", "user-b", "workspace") is False
    assert pool.contains("tenant", "user-c", "workspace") is True

    second_fresh = pool.get("tenant", "user-b", "workspace")
    assert second_fresh is not second
    assert second_fresh.topology_learning.snapshot().prediction_count == 0


def test_scope_bound_topology_state_round_trips_only_into_same_scope() -> None:
    template = SemanticLensPlane()
    pool = ScopedSemanticPlanePool(template, maximum_scopes=4)

    left = pool.get("tenant", "user-a", "workspace")
    _declare_one(left, "durable-left")
    state = pool.export_topology_state(
        "tenant",
        "user-a",
        "workspace",
    )

    with pytest.raises(
        AgentContractError,
        match="another learning scope",
    ):
        pool.restore_topology_state(
            "tenant",
            "user-b",
            "workspace",
            state,
        )

    assert pool.drop("tenant", "user-a", "workspace") is True
    restored = pool.restore_topology_state(
        "tenant",
        "user-a",
        "workspace",
        state.as_json(),
    )

    assert restored.prediction_count == 1
    same_scope = pool.get("tenant", "user-a", "workspace")
    assert same_scope.topology_learning.snapshot().prediction_count == 1


def test_runtime_checkpoint_binds_semantic_scope_and_scoped_learning_root() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-scope-checkpoint")
    state = runtime._new_state(inputs.run_id, inputs)
    checkpoint = runtime.checkpointer.latest(state.run_id)
    assert checkpoint is not None

    scope = runtime.semantic_learning_scope(inputs)
    plane = runtime.semantic_plane_for(inputs)

    assert (
        checkpoint.metadata["semantic_learning_scope_fingerprint"]
        == scope.fingerprint
    )
    assert checkpoint.metadata["semantic_scoping_enabled"] is True
    assert (
        checkpoint.metadata["semantic_topology_learning_fingerprint"]
        == plane.topology_learning.fingerprint
    )

    ledger = runtime.runtime_guard.audit_store.get(state.run_id)
    assert ledger is not None
    binding = next(
        item
        for item in reversed(ledger.entries())
        if item.kind is AuditEventKind.CHECKPOINT_BOUND
        and item.payload.get("checkpoint_sequence") == checkpoint.sequence
    )
    assert (
        binding.payload["semantic_learning_scope_fingerprint"]
        == scope.fingerprint
    )
    assert (
        binding.payload["semantic_topology_learning_fingerprint"]
        == plane.topology_learning.fingerprint
    )


def test_other_scope_learning_does_not_invalidate_checkpoint_resume() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    left_inputs = _inputs("run-scope-resume-left")
    state = runtime._new_state(left_inputs.run_id, left_inputs)
    checkpoint = runtime.checkpointer.latest(state.run_id)
    assert checkpoint is not None

    other_inputs = _inputs(
        "run-scope-resume-right",
        user="user-b",
        workspace="workspace-b",
        session="session-b",
    )
    other_plane = runtime.semantic_plane_for(other_inputs)
    _declare_one(other_plane, "other-scope-run")

    restored = runtime._state_from_checkpoint(
        left_inputs,
        checkpoint,
    )

    assert restored.run_id == state.run_id
    left_plane = runtime.semantic_plane_for(left_inputs)
    assert left_plane.topology_learning.snapshot().prediction_count == 0
    assert other_plane.topology_learning.snapshot().prediction_count == 1
