"""AI approval, planning budget, tool guard, exchange, and session tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.approval import AIApprovalError, AIApprovalRegistry
from skeleton.shells.ai.budget import AIBudget, AIBudgetExceeded, AIBudgetLimit
from skeleton.shells.ai.observation import AIObservation
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.tool_exchange import AIToolCall, AIToolResult
from skeleton.shells.ai.tool_guard import (
    AIToolGuardRegistry,
    ToolGuardDecision,
    ToolGuardTripwire,
)
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal


def fp(char):
    return char * 64


def test_ai_approval_exact_binding():
    registry = AIApprovalRegistry()
    approval = registry.approve(
        principal="p",
        intent_fingerprint=fp("a"),
        proposal_fingerprint=fp("b"),
        approved_by="operator",
    )
    assert registry.require(
        approval,
        principal="p",
        intent_fingerprint=fp("a"),
        proposal_fingerprint=fp("b"),
    ) == approval


@pytest.mark.parametrize(
    "changes",
    [
        {"principal": "q"},
        {"intent_fingerprint": lambda: fp("c")},
        {"proposal_fingerprint": lambda: fp("d")},
    ],
)
def test_ai_approval_mismatch_fails(changes):
    registry = AIApprovalRegistry()
    approval = registry.approve(
        principal="p",
        intent_fingerprint=fp("a"),
        proposal_fingerprint=fp("b"),
        approved_by="operator",
    )
    args = {
        "principal": "p",
        "intent_fingerprint": fp("a"),
        "proposal_fingerprint": fp("b"),
    }
    for key, value in changes.items():
        args[key] = value() if callable(value) else value
    with pytest.raises(AIApprovalError):
        registry.require(approval, **args)


def test_ai_approval_consume_invalidates():
    registry = AIApprovalRegistry()
    approval = registry.approve(
        principal="p",
        intent_fingerprint=fp("a"),
        proposal_fingerprint=fp("b"),
        approved_by="operator",
    )
    registry.consume(
        approval,
        principal="p",
        intent_fingerprint=fp("a"),
        proposal_fingerprint=fp("b"),
    )
    with pytest.raises(AIApprovalError):
        registry.require(
            approval,
            principal="p",
            intent_fingerprint=fp("a"),
            proposal_fingerprint=fp("b"),
        )


def test_ai_approval_expiry():
    now = [0.0]
    registry = AIApprovalRegistry(clock=lambda: now[0])
    approval = registry.approve(
        principal="p",
        intent_fingerprint=fp("a"),
        proposal_fingerprint=fp("b"),
        approved_by="operator",
        ttl_seconds=1,
    )
    now[0] = 1
    with pytest.raises(AIApprovalError):
        registry.require(
            approval,
            principal="p",
            intent_fingerprint=fp("a"),
            proposal_fingerprint=fp("b"),
        )


def test_ai_budget_tracks_model_actions():
    budget = AIBudget()
    usage = budget.model_call(actions=3)
    assert usage.model_calls == 1
    assert usage.candidates == 1
    assert usage.actions_proposed == 3


def test_ai_budget_model_limit():
    budget = AIBudget(AIBudgetLimit(max_model_calls=1))
    budget.model_call()
    with pytest.raises(AIBudgetExceeded):
        budget.model_call()


def test_ai_budget_action_limit():
    budget = AIBudget(AIBudgetLimit(max_actions_proposed=2))
    with pytest.raises(AIBudgetExceeded):
        budget.model_call(actions=3)


def test_ai_budget_critique_and_verification():
    budget = AIBudget()
    budget.critique_call()
    budget.verification_round()
    snapshot = budget.snapshot()
    assert snapshot.critique_calls == 1
    assert snapshot.verification_rounds == 1


def observation(ok=True):
    return AIObservation(
        observation_id="o",
        correlation_id="c",
        command="python",
        ok=ok,
        returncode=0 if ok else 1,
        timed_out=False,
        output_limited=False,
        duration_ms=1,
        stdout_bytes=0,
        stderr_bytes=0,
        stdout_digest=fp("a"),
        stderr_digest=fp("b"),
    )


def test_tool_guard_input_allow():
    guards = AIToolGuardRegistry()
    guards.register_input("python", lambda action: ToolGuardDecision(True))
    assert guards.check_input(AIAction("a", "python"))[0].allowed


def test_tool_guard_input_tripwire():
    guards = AIToolGuardRegistry()
    guards.register_input(
        "python",
        lambda action: ToolGuardDecision(False, "blocked", "not allowed"),
    )
    with pytest.raises(ToolGuardTripwire):
        guards.check_input(AIAction("a", "python"))


def test_tool_guard_output_tripwire():
    guards = AIToolGuardRegistry()
    guards.register_output(
        "python",
        lambda action, result: ToolGuardDecision(False, "bad_output", "blocked"),
    )
    with pytest.raises(ToolGuardTripwire):
        guards.check_output(AIAction("a", "python"), observation())


def test_tool_guard_wrong_return_type():
    guards = AIToolGuardRegistry()
    guards.register_input("python", lambda action: True)
    with pytest.raises(TypeError):
        guards.check_input(AIAction("a", "python"))


def test_tool_call_fingerprint_stable():
    call = AIToolCall("c", "s", "p", AIAction("a", "python"), 0)
    assert len(call.fingerprint) == 64
    assert call.fingerprint == call.fingerprint


def test_tool_result_metadata_copied():
    metadata = {"x": "1"}
    result = AIToolResult("c", observation(), "completed", metadata=metadata)
    metadata["x"] = "2"
    assert result.metadata["x"] == "1"


def test_ai_session_happy_state_path():
    item = AIIntent("i", "Do work")
    session = AIShellSession("s", item)
    session.transition(AISessionPhase.PLANNING)
    plan = AIPlanProposal(
        "p",
        "i",
        (AIAction("a", "python"),),
        confidence=0.9,
        uncertainty=0.1,
    )
    session.set_proposal(plan)
    session.transition(AISessionPhase.REVIEW)
    session.transition(AISessionPhase.APPROVED)
    session.transition(AISessionPhase.EXECUTING)
    session.transition(AISessionPhase.VERIFYING)
    session.transition(AISessionPhase.COMPLETE)
    assert session.phase is AISessionPhase.COMPLETE


def test_ai_session_rejects_invalid_jump():
    session = AIShellSession("s", AIIntent("i", "Do work"))
    with pytest.raises(RuntimeError):
        session.transition(AISessionPhase.EXECUTING)


def test_ai_session_proposal_must_match_intent():
    session = AIShellSession("s", AIIntent("i", "Do work"))
    session.transition(AISessionPhase.PLANNING)
    plan = AIPlanProposal(
        "p",
        "other",
        (AIAction("a", "python"),),
        confidence=0.9,
        uncertainty=0.1,
    )
    with pytest.raises(ValueError):
        session.set_proposal(plan)
