from __future__ import annotations

import pytest

from skeleton.jeeves.agent.audit_assurance import FrontierExecutionReplayVerifier
from skeleton.jeeves.agent.execution_audit import (
    AuditEventKind,
    ExecutionAuditError,
    ExecutionAuditLedger,
    ExecutionReplayVerifier,
    GENESIS_HASH,
    ReplayIssueKind,
)
from skeleton.jeeves.agent.frontier_runtime import (
    FrontierJeevesAgentRuntime,
    ScopedGeneralizingRuntimeEpistemicGuard,
)
from skeleton.jeeves.agent.model_based_control import TransitionOutcome
from skeleton.jeeves.agent.policy import PolicyDecision
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime_guard import (
    RuntimeEpistemicGuard,
    RuntimeGuardRequest,
    RuntimeGuardSignals,
)
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


def _guard_and_request(run_id: str = "run-assurance"):
    registry = ToolRegistry()
    spec = ToolSpec(
        name="read_assurance_record",
        description="Read a deterministic assurance fixture.",
        risk=RiskTier.READ_ONLY,
        arguments=(ArgumentRule("record_id", "string", max_length=64),),
    )
    registry.register(spec, lambda arguments, context: {"ok": True, "value": 7})
    executor = ToolExecutor(registry)
    guard = ScopedGeneralizingRuntimeEpistemicGuard(executor)
    call = ToolCall(
        call_id=f"call-{run_id}",
        name=spec.name,
        arguments={"record_id": "fixture_record"},
    )
    request = RuntimeGuardRequest(
        run_id=run_id,
        goal_id="goal-assurance",
        step_id="step-assurance",
        attempt=1,
        plan_version=1,
        call=call,
        execution_context=ToolExecutionContext(
            run_id=run_id,
            user_id="user-assurance",
            trace_id=f"trace-{run_id}",
        ),
        tool_spec=spec,
        grants=(
            ToolGrant(
                tool_name=spec.name,
                allowed_risks=(RiskTier.READ_ONLY,),
                max_calls=4,
                argument_fingerprint=stable_fingerprint(call.arguments),
            ),
        ),
        host_policy_decision=PolicyDecision(
            Decision.ALLOW,
            "host allowed",
            "assurance-policy",
            risk=RiskTier.READ_ONLY,
        ),
        confirmed_actions=(),
        usage=Usage(),
        budget=Budget(),
        signals=RuntimeGuardSignals(
            progress=0.2,
            uncertainty=0.4,
            budget_pressure=0.1,
            failure_pressure=0.0,
        ),
        metadata={
            "tenant_id": "tenant-assurance",
            "workspace_id": "workspace-assurance",
        },
    )
    return guard, request


def _finalize_kwargs(execution):
    refs = execution.observation.evidence
    return {
        "verification_score": 0.95,
        "outcome": TransitionOutcome.SUCCESS,
        "evidence_ids": tuple(ref.evidence_id for ref in refs),
        "evidence_fingerprint": stable_fingerprint(
            [(ref.evidence_id, ref.fingerprint) for ref in refs]
        ),
        "signals": RuntimeGuardSignals(
            progress=0.8,
            uncertainty=0.2,
            budget_pressure=0.2,
            failure_pressure=0.0,
        ),
    }


def test_frontier_replay_rejects_operation_event_without_operation_id() -> None:
    ledger = ExecutionAuditLedger("run-grammar")
    ledger.append(
        AuditEventKind.TRANSITION_LEARNED,
        {
            "experience_id": "experience-grammar",
            "model_fingerprint": "a" * 64,
        },
    )

    generic = ExecutionReplayVerifier().verify(ledger.entries())
    frontier = FrontierExecutionReplayVerifier().verify(ledger.entries())

    assert generic.valid
    assert not frontier.valid
    assert any(
        issue.kind is ReplayIssueKind.PROTOCOL_ORDER
        and "operation_id" in issue.message
        for issue in frontier.issues
    )


def test_frontier_replay_rejects_incomplete_versioned_checkpoint_roots() -> None:
    ledger = ExecutionAuditLedger("run-binding-grammar")
    ledger.append(
        AuditEventKind.CHECKPOINT_BOUND,
        {
            "frontier_binding_version": 2,
            "checkpoint_sequence": 1,
            "checkpoint_fingerprint": "a" * 64,
            "audit_head_before": GENESIS_HASH,
            "audit_events_before": 0,
            "audit_checkpoint_before": "b" * 64,
            "runtime_guard_policy": "c" * 64,
            "transition_model_fingerprint": "d" * 64,
            # Deliberately omit lineage hash and use an invalid count.
            "transition_model_lineage_count": -1,
            "world_model_fingerprint": "e" * 64,
        },
    )

    report = FrontierExecutionReplayVerifier().verify(ledger.entries())

    assert not report.valid
    messages = " | ".join(issue.message for issue in report.issues)
    assert "transition_model_lineage_hash" in messages
    assert "model-lineage count" in messages


def test_default_frontier_guard_uses_high_assurance_verifier() -> None:
    runtime = FrontierJeevesAgentRuntime(
        provider_router=ProviderRouter([DeterministicProvider([])])
    )
    run_id = "run-frontier-verifier"
    ledger = runtime.runtime_guard.audit_store.get_or_create(run_id)
    ledger.append(
        AuditEventKind.TRANSITION_LEARNED,
        {
            "experience_id": "experience-frontier",
            "model_fingerprint": "f" * 64,
        },
    )

    with pytest.raises(ExecutionAuditError, match="operation_id"):
        runtime.runtime_guard.verify_audit(run_id)


def test_model_lineage_accepts_retained_ancestor_after_legitimate_learning() -> None:
    guard, request = _guard_and_request("run-lineage-legitimate")
    before = guard.model_lineage_checkpoint()

    execution = guard.execute(request)
    guard.finalize(execution, **_finalize_kwargs(execution))
    after = guard.model_lineage_checkpoint()

    assert after["count"] == before["count"] + 1
    assert after["lineage_hash"] != before["lineage_hash"]
    guard.verify_model_lineage_checkpoint(
        count=before["count"],
        lineage_hash=before["lineage_hash"],
    )
    guard.verify_model_lineage_checkpoint(
        count=after["count"],
        lineage_hash=after["lineage_hash"],
    )


def test_out_of_band_model_mutation_breaks_guard_lineage() -> None:
    guard, request = _guard_and_request("run-lineage-bypass")
    before = guard.model_lineage_checkpoint()
    execution = guard.execute(request)

    # Deliberately bypass the subclass override. This models a component that
    # acquired the transition model/guard and mutated learning outside the
    # frontier serialization boundary.
    RuntimeEpistemicGuard.finalize(
        guard,
        execution,
        **_finalize_kwargs(execution),
    )

    with pytest.raises(ExecutionAuditError, match="diverged"):
        guard.model_lineage_checkpoint()
    with pytest.raises(ExecutionAuditError, match="outside guard-owned lineage"):
        guard.verify_model_lineage_checkpoint(
            count=before["count"],
            lineage_hash=before["lineage_hash"],
        )