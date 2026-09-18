from __future__ import annotations

import pytest

from skeleton.jeeves.agent.execution_audit import AuditEventKind
from skeleton.jeeves.agent.model_based_control import TransitionOutcome
from skeleton.jeeves.agent.policy import PolicyDecision
from skeleton.jeeves.agent.runtime_guard import (
    GuardAdmissionMode,
    RuntimeEpistemicGuard,
    RuntimeGuardDenied,
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


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


def _fixture(risk: RiskTier = RiskTier.REVERSIBLE):
    clock = FakeClock()
    calls: list[tuple[int, str]] = []
    registry = ToolRegistry()
    spec = ToolSpec(
        name="write_value",
        description="Write a bounded value for runtime guard tests.",
        risk=risk,
        arguments=(
            ArgumentRule("value", "integer", minimum=0, maximum=100),
        ),
        produces_evidence=True,
    )
    registry.register(
        spec,
        lambda arguments, context: calls.append(
            (arguments["value"], context.run_id)
        )
        or {"value": arguments["value"], "status": "ok"},
    )
    executor = ToolExecutor(registry, clock=clock, monotonic=clock)
    guard = RuntimeEpistemicGuard(executor, wall_clock=clock)
    return clock, calls, registry, spec, executor, guard


def _request(
    spec: ToolSpec,
    *,
    call_id: str = "call-guard-1",
    run_id: str = "run-guard-1",
    step_id: str = "step-guard-1",
    attempt: int = 1,
    confirmed_actions: tuple[str, ...] = (),
    value: int = 7,
) -> RuntimeGuardRequest:
    call = ToolCall(
        call_id=call_id,
        name=spec.name,
        arguments={"value": value},
        reason="guard test",
    )
    context = ToolExecutionContext(
        run_id=run_id,
        user_id="user-guard",
        trace_id="trace-guard",
    )
    grant = ToolGrant(
        tool_name=spec.name,
        allowed_risks=(spec.risk,),
        max_calls=20,
        argument_fingerprint=stable_fingerprint(call.arguments),
    )
    host = PolicyDecision(
        Decision.ALLOW,
        "host policy allowed guarded test call",
        "test-policy",
        risk=spec.risk,
    )
    return RuntimeGuardRequest(
        run_id=run_id,
        goal_id="goal-guard",
        step_id=step_id,
        attempt=attempt,
        plan_version=1,
        call=call,
        execution_context=context,
        tool_spec=spec,
        grants=(grant,),
        host_policy_decision=host,
        confirmed_actions=confirmed_actions,
        usage=Usage(),
        budget=Budget(),
        signals=RuntimeGuardSignals(
            progress=0.2,
            uncertainty=0.5,
            budget_pressure=0.1,
            failure_pressure=0.0,
        ),
    )


def _finalize(guard: RuntimeEpistemicGuard, execution, *, passed: bool = True):
    observation = execution.observation
    evidence_ids = tuple(ref.evidence_id for ref in observation.evidence)
    evidence_fingerprint = stable_fingerprint(
        [(ref.evidence_id, ref.fingerprint) for ref in observation.evidence]
    )
    return guard.finalize(
        execution,
        verification_score=0.95 if passed else 0.10,
        outcome=TransitionOutcome.SUCCESS if passed else TransitionOutcome.FAILURE,
        evidence_ids=evidence_ids,
        evidence_fingerprint=evidence_fingerprint,
        signals=RuntimeGuardSignals(
            progress=0.5 if passed else 0.2,
            uncertainty=0.2,
            budget_pressure=0.2,
            failure_pressure=0.0 if passed else 0.5,
            terminal=False,
        ),
    )


def test_reversible_first_call_uses_explicit_cold_start_then_learns() -> None:
    _, calls, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    request = _request(spec)

    execution = guard.execute(request)

    assert execution.admission_mode is GuardAdmissionMode.COLD_START_HOST_TRUST
    assert execution.prediction.observations == 0
    assert execution.observation.ok is True
    assert calls == [(7, "run-guard-1")]

    finalization = _finalize(guard, execution)
    assert finalization.outcome is TransitionOutcome.SUCCESS
    assert finalization.verification_score == 0.95
    assert finalization.experience.evidence_ids
    assert guard.transition_model.predict(
        execution.pre_state.state_id,
        execution.action.action_id,
    ).observations == 1

    report = guard.verify_audit(
        "run-guard-1",
        require_finalized_operations=True,
    )
    assert report.valid is True
    assert report.operations[0].finalized is True


def test_second_same_state_action_is_model_gated_not_cold_start() -> None:
    _, calls, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    first = guard.execute(_request(spec, call_id="call-first"))
    _finalize(guard, first)

    second = guard.execute(_request(spec, call_id="call-second", step_id="step-guard-1"))

    assert second.prediction.observations == 1
    assert second.admission_mode is GuardAdmissionMode.MODEL_GATED
    assert second.decision.selected_action is not None
    assert calls == [(7, "run-guard-1"), (7, "run-guard-1")]
    _finalize(guard, second)


def test_mutating_cold_start_requires_exact_runtime_confirmation() -> None:
    _, calls, _, spec, _, guard = _fixture(RiskTier.MUTATING)
    unconfirmed = _request(spec)

    with pytest.raises(RuntimeGuardDenied):
        guard.execute(unconfirmed)

    assert calls == []

    confirmation = (f"confirm:{spec.name}:run-guard-1",)
    confirmed = _request(
        spec,
        call_id="call-confirmed",
        confirmed_actions=confirmation,
    )
    execution = guard.execute(confirmed)

    assert execution.admission_mode is GuardAdmissionMode.COLD_START_HOST_TRUST
    assert "exact_runtime_confirmation_present" in execution.decision.reasons
    assert calls == [(7, "run-guard-1")]
    _finalize(guard, execution)


def test_high_impact_cold_start_fails_closed_even_if_host_says_allow() -> None:
    _, calls, _, spec, _, guard = _fixture(RiskTier.HIGH_IMPACT)
    request = _request(
        spec,
        confirmed_actions=(f"confirm:{spec.name}:run-guard-1",),
    )

    with pytest.raises(RuntimeGuardDenied) as exc_info:
        guard.execute(request)

    assert calls == []
    assert exc_info.value.disposition is not None
    ledger = guard.audit_store.get("run-guard-1")
    assert ledger is not None
    assert ledger.entries()[-1].kind is AuditEventKind.EXECUTION_DENIED


def test_duplicate_operation_is_rejected_before_second_tool_execution() -> None:
    _, calls, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    request = _request(spec)
    first = guard.execute(request)
    assert calls == [(7, "run-guard-1")]

    with pytest.raises(RuntimeGuardDenied, match="duplicate or replayed"):
        guard.execute(request)

    assert calls == [(7, "run-guard-1")]
    _finalize(guard, first)


def test_finalization_cannot_be_replayed() -> None:
    _, _, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    execution = guard.execute(_request(spec))
    first = _finalize(guard, execution)

    with pytest.raises(Exception, match="already finalized"):
        _finalize(guard, execution)

    assert guard.finalizations("run-guard-1") == (first,)


def test_failed_verification_trains_failure_not_success() -> None:
    _, _, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    execution = guard.execute(_request(spec))
    finalization = _finalize(guard, execution, passed=False)

    assert finalization.outcome is TransitionOutcome.FAILURE
    prediction = guard.transition_model.predict(
        execution.pre_state.state_id,
        execution.action.action_id,
    )
    assert prediction.outcome_probabilities["failure"] == 1.0
    assert prediction.expected_verification == 0.10
    assert prediction.expected_reward < 0.0


def test_resume_accepts_checkpoint_as_verified_prefix_of_longer_chain() -> None:
    _, _, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    execution = guard.execute(_request(spec))
    prefix = guard.audit_checkpoint("run-guard-1")
    _finalize(guard, execution)
    current = guard.audit_checkpoint("run-guard-1")
    assert current.event_count > prefix.event_count

    resumed = guard.note_resume(
        "run-guard-1",
        checkpoint_sequence=7,
        expected_audit_head=prefix.head_hash,
        expected_audit_events=prefix.event_count,
    )

    assert resumed.event_count == current.event_count + 1
    assert guard.verify_audit("run-guard-1").valid is True


def test_resume_rejects_tampered_checkpoint_prefix_head() -> None:
    _, _, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    execution = guard.execute(_request(spec))
    prefix = guard.audit_checkpoint("run-guard-1")
    _finalize(guard, execution)

    with pytest.raises(Exception, match="prefix head mismatch"):
        guard.note_resume(
            "run-guard-1",
            checkpoint_sequence=7,
            expected_audit_head="9" * 64,
            expected_audit_events=prefix.event_count,
        )


def test_guard_rejects_host_policy_denial_without_touching_tool() -> None:
    _, calls, _, spec, _, guard = _fixture(RiskTier.REVERSIBLE)
    request = _request(spec)
    denied = RuntimeGuardRequest(
        run_id=request.run_id,
        goal_id=request.goal_id,
        step_id=request.step_id,
        attempt=request.attempt,
        plan_version=request.plan_version,
        call=request.call,
        execution_context=request.execution_context,
        tool_spec=request.tool_spec,
        grants=request.grants,
        host_policy_decision=PolicyDecision(
            Decision.DENY,
            "host denied",
            "test-policy",
            risk=spec.risk,
        ),
        confirmed_actions=request.confirmed_actions,
        usage=request.usage,
        budget=request.budget,
        signals=request.signals,
    )

    with pytest.raises(RuntimeGuardDenied, match="not already allowed"):
        guard.execute(denied)

    assert calls == []