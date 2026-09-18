from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.durable_runtime import (
    DurableFrontierJeevesAgentRuntime,
    DurableRuntimeError,
    _CheckpointCodec,
)
from skeleton.jeeves.agent.model_based_control import TransitionOutcome
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
    ToolCall,
    Usage,
    stable_fingerprint,
)
from skeleton.jeeves.agent.world_model import Proposition
from skeleton.state.run_store import StateConflict


def _router() -> ProviderRouter:
    return ProviderRouter([DeterministicProvider([])])


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_durable_record",
            description="Read one durable fixture record.",
            risk=RiskTier.READ_ONLY,
            arguments=(ArgumentRule("record_id", "string"),),
        ),
        lambda arguments, context: {
            "ok": True,
            "record_id": arguments["record_id"],
            "run_id": context.run_id,
        },
    )
    return registry


def _inputs(run_id: str) -> RunInputs:
    return RunInputs(
        goal=Goal(
            goal_id="goal-durable-runtime",
            objective="Exercise restart-safe Jeeves state.",
        ),
        tenant_id="tenant-durable",
        user_id="user-durable",
        workspace_id="workspace-durable",
        run_id=run_id,
    )


def _runtime(path, worker_id: str) -> DurableFrontierJeevesAgentRuntime:
    return DurableFrontierJeevesAgentRuntime(
        provider_router=_router(),
        state_path=path,
        worker_id=worker_id,
        tool_registry=_registry(),
    )


def _claim_for_private_checkpoint(runtime, inputs: RunInputs) -> None:
    runtime.run_store.create_run(
        inputs.run_id,
        input={"goal_id": inputs.goal.goal_id, "test": True},
    )
    runtime.run_store.claim_run(
        inputs.run_id,
        runtime.worker_id,
        lease_seconds=runtime.lease_seconds,
    )


def _guard_request(runtime, run_id: str) -> RuntimeGuardRequest:
    registered = runtime.tools.get("read_durable_record")
    assert registered is not None
    call = ToolCall(
        call_id=f"call-{run_id}",
        name="read_durable_record",
        arguments={"record_id": "fixture"},
    )
    grant = ToolGrant(
        tool_name=call.name,
        allowed_risks=(RiskTier.READ_ONLY,),
        max_calls=4,
        argument_fingerprint=stable_fingerprint(call.arguments),
    )
    return RuntimeGuardRequest(
        run_id=run_id,
        goal_id="goal-durable-runtime",
        step_id="step-durable",
        attempt=1,
        plan_version=1,
        call=call,
        execution_context=ToolExecutionContext(
            run_id=run_id,
            user_id="user-durable",
            trace_id=f"trace-{run_id}",
        ),
        tool_spec=registered.spec,
        grants=(grant,),
        host_policy_decision=PolicyDecision(
            Decision.ALLOW,
            "host allowed",
            "durable-test-policy",
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
        metadata={
            "tenant_id": "tenant-durable",
            "workspace_id": "workspace-durable",
        },
    )


def test_checkpoint_codec_roundtrips_frontier_checkpoint_fingerprint(tmp_path) -> None:
    runtime = _runtime(tmp_path / "state.sqlite3", "worker-a")
    inputs = _inputs("run-checkpoint-codec")
    _claim_for_private_checkpoint(runtime, inputs)
    state = runtime._new_state(inputs.run_id, inputs)
    checkpoint = runtime.checkpointer.latest(inputs.run_id)
    assert checkpoint is not None

    restored = _CheckpointCodec.decode(_CheckpointCodec.encode(checkpoint))

    assert restored == checkpoint
    assert restored.fingerprint == checkpoint.fingerprint
    assert state.run_id == restored.run_id


def test_world_and_checkpoint_reconstruct_in_fresh_runtime(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    first = _runtime(path, "worker-a")
    inputs = _inputs("run-world-restart")
    _claim_for_private_checkpoint(first, inputs)
    state = first._new_state(inputs.run_id, inputs)
    proposition = Proposition.create(
        "service",
        "healthy",
        True,
        scope="workspace-durable",
    )
    first.runtime_guard.world.upsert_proposition(proposition, prior=0.77)
    checkpoint = first._checkpoint(state)
    expected_world = first.runtime_guard.world.snapshot(persist=False).fingerprint

    durable_record = first.run_store.resume_state(inputs.run_id).checkpoint
    assert durable_record is not None

    second = _runtime(path, "worker-a")
    restored_checkpoint = second._restore_envelope(durable_record.state)

    assert restored_checkpoint.fingerprint == checkpoint.fingerprint
    assert second.runtime_guard.world.snapshot(persist=False).fingerprint == expected_world
    belief = second.runtime_guard.world.require_belief(proposition.proposition_id)
    assert belief.probability == pytest.approx(0.77)


def test_transition_model_and_lineage_reconstruct_from_wal(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    first = _runtime(path, "worker-a")
    request = _guard_request(first, "run-model-restart")

    execution = first.runtime_guard.execute(request)
    refs = execution.observation.evidence
    finalization = first.runtime_guard.finalize(
        execution,
        verification_score=0.96,
        outcome=TransitionOutcome.SUCCESS,
        evidence_ids=tuple(ref.evidence_id for ref in refs),
        evidence_fingerprint=stable_fingerprint(
            [(ref.evidence_id, ref.fingerprint) for ref in refs]
        ),
        signals=RuntimeGuardSignals(
            progress=0.8,
            uncertainty=0.2,
            budget_pressure=0.2,
            failure_pressure=0.0,
        ),
    )
    first_model = first.runtime_guard.transition_model.fingerprint
    first_lineage = first.runtime_guard.model_lineage_checkpoint()

    second = _runtime(path, "worker-b")

    assert second.runtime_guard.transition_model.fingerprint == first_model
    second_lineage = second.runtime_guard.model_lineage_checkpoint()
    assert second_lineage == first_lineage
    prediction = second.runtime_guard.transition_model.predict(
        execution.pre_state.state_id,
        execution.action.action_id,
    )
    assert prediction.observations == 1
    assert finalization.model_fingerprint == first_model


def test_audit_can_be_ahead_of_runtime_checkpoint_after_observation(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    first = _runtime(path, "worker-a")
    inputs = _inputs("run-audit-ahead")
    _claim_for_private_checkpoint(first, inputs)
    state = first._new_state(inputs.run_id, inputs)
    durable_before = first.run_store.resume_state(inputs.run_id).checkpoint
    assert durable_before is not None

    request = _guard_request(first, inputs.run_id)
    execution = first.runtime_guard.execute(request)
    assert execution.observation.ok
    # Simulate death here: no runtime checkpoint and no verifier finalization.

    second = _runtime(path, "worker-b")
    restored = second._restore_envelope(durable_before.state)
    assert restored.run_id == inputs.run_id
    ambiguous = second._ambiguous_side_effects(inputs.run_id)
    # READ_ONLY is intentionally recoverable without side-effect quarantine.
    assert ambiguous == ()
    audit = second.runtime_guard.verify_audit(
        inputs.run_id,
        require_finalized_operations=False,
    )
    assert audit.operations[0].observation_fingerprint == execution.observation_fingerprint
    assert audit.operations[0].finalized is False


def test_durable_envelope_tamper_is_rejected(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    runtime = _runtime(path, "worker-a")
    inputs = _inputs("run-envelope-tamper")
    _claim_for_private_checkpoint(runtime, inputs)
    runtime._new_state(inputs.run_id, inputs)
    record = runtime.run_store.resume_state(inputs.run_id).checkpoint
    assert record is not None

    forged = dict(record.state)
    forged_checkpoint = dict(forged["checkpoint"])
    forged_checkpoint["last_error"] = "forged"
    forged["checkpoint"] = forged_checkpoint

    with pytest.raises(DurableRuntimeError, match="envelope fingerprint mismatch"):
        runtime._restore_envelope(forged)


def test_second_worker_cannot_steal_live_durable_run_lease(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    first = _runtime(path, "worker-a")
    inputs = _inputs("run-lease-fence")
    _claim_for_private_checkpoint(first, inputs)
    first._new_state(inputs.run_id, inputs)

    second = _runtime(path, "worker-b")
    with pytest.raises(StateConflict, match="leased by another worker"):
        second.run_store.claim_run(
            inputs.run_id,
            second.worker_id,
            lease_seconds=second.lease_seconds,
        )


def test_durable_run_requires_explicit_run_id(tmp_path) -> None:
    runtime = _runtime(tmp_path / "state.sqlite3", "worker-a")
    inputs = replace(_inputs("run-explicit"), run_id=None)

    with pytest.raises(DurableRuntimeError, match="explicit run_id"):
        runtime.run(inputs)