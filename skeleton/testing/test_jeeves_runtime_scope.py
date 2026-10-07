from __future__ import annotations

from skeleton.jeeves.agent.frontier_runtime import ScopedGeneralizingRuntimeEpistemicGuard
from skeleton.jeeves.agent.policy import PolicyDecision
from skeleton.jeeves.agent.tools import (
    ArgumentRule,
    ToolExecutionContext,
    ToolExecutor,
    ToolGrant,
    ToolRegistry,
    ToolSpec,
)
from skeleton.jeeves.agent.types import (
    Budget,
    Decision,
    RiskTier,
    ToolCall,
    Usage,
    stable_fingerprint,
)
from skeleton.jeeves.agent.runtime_guard import RuntimeGuardRequest, RuntimeGuardSignals


def _guard_and_spec():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="read_record",
        description="Read a scoped record.",
        risk=RiskTier.READ_ONLY,
        arguments=(ArgumentRule("record_id", "string"),),
    )
    registry.register(spec, lambda arguments, context: {"ok": True})
    executor = ToolExecutor(registry)
    return ScopedGeneralizingRuntimeEpistemicGuard(executor), spec


def _request(
    spec: ToolSpec,
    *,
    run_id: str,
    tenant_id: str | None,
    workspace_id: str | None,
) -> RuntimeGuardRequest:
    call = ToolCall(
        call_id=f"call-{run_id}",
        name=spec.name,
        arguments={"record_id": "customer_alpha"},
    )
    context = ToolExecutionContext(
        run_id=run_id,
        user_id="user-scope",
        trace_id=f"trace-{run_id}",
    )
    grant = ToolGrant(
        tool_name=spec.name,
        allowed_risks=(RiskTier.READ_ONLY,),
        max_calls=5,
        argument_fingerprint=stable_fingerprint(call.arguments),
    )
    metadata = {}
    if tenant_id is not None:
        metadata["tenant_id"] = tenant_id
    if workspace_id is not None:
        metadata["workspace_id"] = workspace_id
    return RuntimeGuardRequest(
        run_id=run_id,
        goal_id="goal-scope",
        step_id="step-scope",
        attempt=1,
        plan_version=1,
        call=call,
        execution_context=context,
        tool_spec=spec,
        grants=(grant,),
        host_policy_decision=PolicyDecision(
            Decision.ALLOW,
            "host allowed",
            "scope-policy",
            risk=RiskTier.READ_ONLY,
        ),
        confirmed_actions=(),
        usage=Usage(),
        budget=Budget(),
        signals=RuntimeGuardSignals(
            progress=0.2,
            uncertainty=0.5,
            budget_pressure=0.1,
            failure_pressure=0.0,
        ),
        metadata=metadata,
    )


def test_runs_in_same_tenant_workspace_share_learning_state() -> None:
    guard, spec = _guard_and_spec()
    first = _request(
        spec,
        run_id="run-scope-a",
        tenant_id="tenant-alpha",
        workspace_id="workspace-one",
    )
    second = _request(
        spec,
        run_id="run-scope-b",
        tenant_id="tenant-alpha",
        workspace_id="workspace-one",
    )

    first_identity = guard.learning_identity(first)
    second_identity = guard.learning_identity(second)

    assert first_identity["state_id"] == second_identity["state_id"]
    assert first_identity["action_id"] == second_identity["action_id"]


def test_different_tenant_does_not_share_learning_state() -> None:
    guard, spec = _guard_and_spec()
    first = _request(
        spec,
        run_id="run-scope-a",
        tenant_id="tenant-alpha",
        workspace_id="workspace-one",
    )
    second = _request(
        spec,
        run_id="run-scope-b",
        tenant_id="tenant-bravo",
        workspace_id="workspace-one",
    )

    first_identity = guard.learning_identity(first)
    second_identity = guard.learning_identity(second)

    assert first_identity["state_id"] != second_identity["state_id"]
    assert first_identity["action_id"] == second_identity["action_id"]


def test_different_workspace_does_not_share_learning_state() -> None:
    guard, spec = _guard_and_spec()
    first = _request(
        spec,
        run_id="run-scope-a",
        tenant_id="tenant-alpha",
        workspace_id="workspace-one",
    )
    second = _request(
        spec,
        run_id="run-scope-b",
        tenant_id="tenant-alpha",
        workspace_id="workspace-two",
    )

    first_identity = guard.learning_identity(first)
    second_identity = guard.learning_identity(second)

    assert first_identity["state_id"] != second_identity["state_id"]


def test_learning_scope_feature_does_not_contain_raw_scope_identifiers() -> None:
    guard, spec = _guard_and_spec()
    request = _request(
        spec,
        run_id="run-scope-a",
        tenant_id="tenant-super-secret",
        workspace_id="workspace-private-name",
    )

    state = guard._compact_state(request, phase="pre")
    rendered_features = repr(state.features)

    assert "tenant-super-secret" not in rendered_features
    assert "workspace-private-name" not in rendered_features
    assert len(state.features["learning_scope"]) == 16


def test_unscoped_requests_share_only_the_unscoped_partition() -> None:
    guard, spec = _guard_and_spec()
    first = _request(
        spec,
        run_id="run-scope-a",
        tenant_id=None,
        workspace_id=None,
    )
    second = _request(
        spec,
        run_id="run-scope-b",
        tenant_id=None,
        workspace_id=None,
    )
    scoped = _request(
        spec,
        run_id="run-scope-c",
        tenant_id="tenant-alpha",
        workspace_id=None,
    )

    first_state = guard.learning_identity(first)["state_id"]
    second_state = guard.learning_identity(second)["state_id"]
    scoped_state = guard.learning_identity(scoped)["state_id"]

    assert first_state == second_state
    assert scoped_state != first_state