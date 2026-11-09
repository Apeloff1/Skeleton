from __future__ import annotations

from skeleton.jeeves.agent.epistemic_authorization import ExecutionPermit
from skeleton.jeeves.agent.epistemic_tool_gate import (
    PermitBoundToolExecutor,
    ToolExecutionIntent,
    bind_intent_metadata,
)
from skeleton.jeeves.agent.model_based_control import AbstractAction
from skeleton.jeeves.agent.tools import ToolExecutionContext
from skeleton.jeeves.agent.types import RiskTier, ToolCall, stable_fingerprint


def _permit(intent: ToolExecutionIntent) -> ExecutionPermit:
    action = AbstractAction(
        action_id=intent.action_id,
        name="bound action",
        capability=intent.tool_name,
        risk=RiskTier.REVERSIBLE,
        metadata=bind_intent_metadata({}, intent),
    )
    return ExecutionPermit(
        permit_id="permit-identity-test",
        token_id="token-identity-test",
        decision_id="decision-identity-test",
        action=action,
        authorized_at=100.0,
        world_fingerprint=stable_fingerprint({"world": 1}),
        model_fingerprint=stable_fingerprint({"model": 1}),
        policy_fingerprint=stable_fingerprint({"policy": 1}),
        permit_fingerprint=stable_fingerprint({"permit": 1}),
    )


def test_tool_intent_fingerprint_binds_call_and_user_identity() -> None:
    call = ToolCall(
        call_id="call-original",
        name="write_value",
        arguments={"value": 7},
    )
    context = ToolExecutionContext(
        run_id="run-original",
        user_id="user-original",
        trace_id="trace-original",
    )
    original = ToolExecutionIntent.bind(
        action_id="action-original",
        call=call,
        context=context,
    )
    changed_call = ToolExecutionIntent.bind(
        action_id="action-original",
        call=ToolCall(
            call_id="call-substituted",
            name="write_value",
            arguments={"value": 7},
        ),
        context=context,
    )
    changed_user = ToolExecutionIntent.bind(
        action_id="action-original",
        call=call,
        context=ToolExecutionContext(
            run_id="run-original",
            user_id="user-substituted",
            trace_id="trace-original",
        ),
    )

    assert original.fingerprint != changed_call.fingerprint
    assert original.fingerprint != changed_user.fingerprint
    assert original.call_id == "call-original"
    assert original.user_id == "user-original"


def test_binding_rejects_call_id_substitution_even_with_same_arguments() -> None:
    original_call = ToolCall(
        call_id="call-original",
        name="write_value",
        arguments={"value": 7},
    )
    context = ToolExecutionContext(
        run_id="run-original",
        user_id="user-original",
        trace_id="trace-original",
    )
    intent = ToolExecutionIntent.bind(
        action_id="action-original",
        call=original_call,
        context=context,
    )
    permit = _permit(intent)
    substituted_call = ToolCall(
        call_id="call-substituted",
        name="write_value",
        arguments={"value": 7},
    )

    mismatches = PermitBoundToolExecutor.binding_mismatches(
        permit=permit,
        intent=intent,
        call=substituted_call,
        context=context,
    )

    assert mismatches == ("call_id",)


def test_binding_rejects_user_substitution_even_with_same_run_and_trace() -> None:
    call = ToolCall(
        call_id="call-original",
        name="write_value",
        arguments={"value": 7},
    )
    context = ToolExecutionContext(
        run_id="run-original",
        user_id="user-original",
        trace_id="trace-original",
    )
    intent = ToolExecutionIntent.bind(
        action_id="action-original",
        call=call,
        context=context,
    )
    permit = _permit(intent)
    substituted_context = ToolExecutionContext(
        run_id="run-original",
        user_id="user-substituted",
        trace_id="trace-original",
    )

    mismatches = PermitBoundToolExecutor.binding_mismatches(
        permit=permit,
        intent=intent,
        call=call,
        context=substituted_context,
    )

    assert mismatches == ("user_id",)
