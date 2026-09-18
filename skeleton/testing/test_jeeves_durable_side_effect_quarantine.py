from __future__ import annotations

from skeleton.jeeves.agent.durable_runtime import DurableFrontierJeevesAgentRuntime
from skeleton.jeeves.agent.execution_audit import AuditEventKind
from skeleton.jeeves.agent.policy import PolicyDecision
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.runtime_guard import RuntimeGuardRequest, RuntimeGuardSignals
from skeleton.jeeves.agent.tools import (
    ArgumentRule,
    ToolExecutionContext,
    ToolGrant,
    ToolRegistry,
    ToolSpec,
)
from skeleton.jeeves.agent.types import (
    Budget,
    Decision,
    Goal,
    RiskTier,
    TerminationReason,
    ToolCall,
    Usage,
    stable_fingerprint,
)


def _runtime(path, worker_id: str, calls: list[str]) -> DurableFrontierJeevesAgentRuntime:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="mutate_durable_record",
            description="Perform one durable mutation fixture.",
            risk=RiskTier.MUTATING,
            arguments=(ArgumentRule("record_id", "string"),),
        ),
        lambda arguments, context: calls.append(arguments["record_id"])
        or {"ok": True, "record_id": arguments["record_id"], "changed": True},
    )
    return DurableFrontierJeevesAgentRuntime(
        provider_router=ProviderRouter([DeterministicProvider([])]),
        state_path=path,
        worker_id=worker_id,
        tool_registry=registry,
    )


def _inputs(run_id: str) -> RunInputs:
    return RunInputs(
        goal=Goal(
            goal_id="goal-durable-mutation",
            objective="Prove crash recovery never repeats an ambiguous mutation.",
        ),
        tenant_id="tenant-durable",
        user_id="user-durable",
        workspace_id="workspace-durable",
        run_id=run_id,
    )


def test_observed_mutation_after_older_checkpoint_forces_reconciliation_on_restart(
    tmp_path,
) -> None:
    path = tmp_path / "jeeves.sqlite3"
    run_id = "run-mutation-crash"
    first_calls: list[str] = []
    first = _runtime(path, "worker-stable", first_calls)
    inputs = _inputs(run_id)

    # Establish a durable runtime checkpoint before the external mutation.
    first.run_store.create_run(run_id, input={"goal_id": inputs.goal.goal_id})
    first.run_store.claim_run(
        run_id,
        first.worker_id,
        lease_seconds=first.lease_seconds,
    )
    first._new_state(run_id, inputs)
    durable_checkpoint = first.run_store.resume_state(run_id).checkpoint
    assert durable_checkpoint is not None

    registered = first.tools.get("mutate_durable_record")
    assert registered is not None
    call = ToolCall(
        call_id="call-mutation-crash",
        name=registered.spec.name,
        arguments={"record_id": "record-a"},
    )
    confirmation_id = f"confirm:{registered.spec.name}:{run_id}"
    request = RuntimeGuardRequest(
        run_id=run_id,
        goal_id=inputs.goal.goal_id,
        step_id="step-mutation-crash",
        attempt=1,
        plan_version=1,
        call=call,
        execution_context=ToolExecutionContext(
            run_id=run_id,
            user_id=inputs.user_id,
            trace_id="trace-mutation-crash",
        ),
        tool_spec=registered.spec,
        grants=(
            ToolGrant(
                tool_name=registered.spec.name,
                allowed_risks=(RiskTier.MUTATING,),
                max_calls=1,
                argument_fingerprint=stable_fingerprint(call.arguments),
            ),
        ),
        host_policy_decision=PolicyDecision(
            Decision.ALLOW,
            "explicitly confirmed mutation",
            "durable-mutation-policy",
            risk=RiskTier.MUTATING,
        ),
        confirmed_actions=(confirmation_id,),
        usage=Usage(),
        budget=Budget(),
        signals=RuntimeGuardSignals(
            progress=0.2,
            uncertainty=0.5,
            budget_pressure=0.1,
            failure_pressure=0.0,
        ),
        metadata={
            "tenant_id": inputs.tenant_id,
            "workspace_id": inputs.workspace_id,
        },
    )

    execution = first.runtime_guard.execute(request)
    assert execution.observation.ok
    assert first_calls == ["record-a"]
    # Simulated hard death: do NOT verifier-finalize and do NOT write another
    # runtime checkpoint. SQLite audit already contains TOOL_OBSERVED.

    second_calls: list[str] = []
    second = _runtime(path, "worker-stable", second_calls)
    result = second.resume(inputs, run_id)

    assert result.success is False
    assert result.reason is TerminationReason.CONFIRMATION_REQUIRED
    assert result.metadata["required_action"] == "reconcile_external_state_before_new_execution"
    quarantine = result.metadata["recovery_quarantine"]
    assert execution.operation_id in quarantine["operations"]
    assert second_calls == []

    # Recovery closes the orphaned audit operation as failed/reconciliation
    # required, but it never fabricates a verifier result or transition-learning
    # event for the ambiguous mutation.
    report = second.runtime_guard.verify_audit(
        run_id,
        require_finalized_operations=False,
    )
    operation = next(
        item for item in report.operations if item.operation_id == execution.operation_id
    )
    assert operation.observation_fingerprint == execution.observation_fingerprint
    assert operation.finalized is False
    assert operation.terminal_kind is AuditEventKind.EXECUTION_FAILED
    assert second.runtime_guard.transition_model.predict(
        execution.pre_state.state_id,
        execution.action.action_id,
    ).observations == 0