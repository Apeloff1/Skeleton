from __future__ import annotations

import pytest

from skeleton.jeeves.agent.epistemic_authorization import DecisionAuthorizer
from skeleton.jeeves.agent.epistemic_planning import (
    ActionCandidate,
    BeliefRequirement,
    DecisionDisposition,
    DecisionPolicy,
    EpistemicDecisionBridge,
)
from skeleton.jeeves.agent.epistemic_tool_gate import (
    AuthorizedToolDenied,
    PermitBoundToolExecutor,
    ToolExecutionIntent,
    bind_intent_metadata,
)
from skeleton.jeeves.agent.model_based_control import (
    AbstractAction,
    CompactState,
    LearnedTransitionModel,
    TransitionOutcome,
    transition_experience,
)
from skeleton.jeeves.agent.tools import (
    ArgumentRule,
    ToolDenied,
    ToolExecutionContext,
    ToolExecutor,
    ToolGrant,
    ToolRegistry,
    ToolSpec,
)
from skeleton.jeeves.agent.types import RiskTier, ToolCall, stable_fingerprint
from skeleton.jeeves.agent.world_model import BeliefGraph, Proposition


def _state(name: str, *, terminal: bool = False) -> CompactState:
    return CompactState.from_signals(
        features={"phase": name},
        progress=1.0 if terminal else 0.5,
        uncertainty=0.1,
        budget_pressure=0.1,
        failure_pressure=0.0,
        risk=RiskTier.READ_ONLY,
        terminal=terminal,
    )


def _authorized_fixture():
    world = BeliefGraph(clock=lambda: 50.0)
    proposition = Proposition.create(
        "tool-execution",
        "precondition",
        "satisfied",
        scope="test",
    )
    world.upsert_proposition(proposition, prior=0.96)

    context = ToolExecutionContext(
        run_id="run-bound-tool",
        user_id="user-test",
        trace_id="trace-bound-tool",
    )
    call = ToolCall(
        call_id="call-bound-tool",
        name="mutate_value",
        arguments={"value": 7},
        reason="test exact binding",
    )
    intent = ToolExecutionIntent.bind(
        action_id="action-bound-tool",
        call=call,
        context=context,
    )
    action = AbstractAction(
        action_id=intent.action_id,
        name="mutate bound value",
        capability="mutate_value",
        risk=RiskTier.REVERSIBLE,
        reversible=True,
        metadata=bind_intent_metadata({}, intent),
    )

    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    for index in range(24):
        model.observe(
            transition_experience(
                run_id=f"training-{index}",
                state=start,
                action=action,
                next_state=done,
                outcome=TransitionOutcome.SUCCESS,
                reward=0.85,
                verification_score=0.98,
                cost=0.01,
                latency_ms=3.0,
                observed_at=float(index + 1),
            )
        )

    bridge = EpistemicDecisionBridge(
        world,
        model,
        policy=DecisionPolicy(
            minimum_lower_utility=-1.0,
            maximum_regret=1.0,
            require_stress_survival=False,
        ),
    )
    decision = bridge.decide(
        start.state_id,
        [
            ActionCandidate(
                action=action,
                requirements=(
                    BeliefRequirement(
                        proposition.proposition_id,
                        observation_cost=0.5,
                    ),
                ),
            )
        ],
    )
    assert decision.disposition is DecisionDisposition.ACT

    authorizer = DecisionAuthorizer(world, model, clock=lambda: 100.0)
    issued = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert issued.allowed is True
    assert issued.token is not None

    calls: list[tuple[int, str]] = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="mutate_value",
            description="Mutate a bounded test value.",
            risk=RiskTier.REVERSIBLE,
            arguments=(ArgumentRule("value", "integer", minimum=0, maximum=100),),
        ),
        lambda arguments, execution_context: calls.append(
            (arguments["value"], execution_context.run_id)
        )
        or {"value": arguments["value"], "changed": True},
    )
    executor = ToolExecutor(registry, clock=lambda: 100.0)
    gate = PermitBoundToolExecutor(authorizer, executor)
    grant = ToolGrant(
        tool_name="mutate_value",
        allowed_risks=(RiskTier.REVERSIBLE,),
        max_calls=1,
        argument_fingerprint=stable_fingerprint(call.arguments),
    )
    return (
        decision,
        authorizer,
        gate,
        issued.token,
        intent,
        call,
        context,
        grant,
        calls,
    )


def test_exact_intent_requires_both_epistemic_permit_and_host_grant() -> None:
    decision, _, gate, token, intent, call, context, grant, calls = _authorized_fixture()

    result = gate.execute(
        token,
        intent,
        call,
        context,
        grants=(grant,),
        expected_policy_fingerprint=decision.policy_fingerprint,
    )

    assert result.authorization.allowed is True
    assert result.permit.action.action_id == intent.action_id
    assert result.observation.ok is True
    assert result.observation.payload == {"value": 7, "changed": True}
    assert len(result.observation.evidence) == 1
    assert calls == [(7, context.run_id)]


def test_argument_substitution_is_rejected_after_token_is_burned() -> None:
    decision, authorizer, gate, token, intent, _, context, grant, calls = _authorized_fixture()
    substituted = ToolCall(
        call_id="call-substituted-arguments",
        name="mutate_value",
        arguments={"value": 8},
    )

    with pytest.raises(AuthorizedToolDenied, match="arguments"):
        gate.execute(
            token,
            intent,
            substituted,
            context,
            grants=(grant,),
            expected_policy_fingerprint=decision.policy_fingerprint,
        )

    assert calls == []
    state = authorizer.token_state(token.token_id)
    assert state is not None and state["consumed"] is True

    with pytest.raises(AuthorizedToolDenied, match="token_already_consumed"):
        gate.execute(
            token,
            intent,
            substituted,
            context,
            grants=(grant,),
            expected_policy_fingerprint=decision.policy_fingerprint,
        )


def test_run_or_trace_substitution_is_rejected() -> None:
    decision, _, gate, token, intent, call, _, grant, calls = _authorized_fixture()
    wrong_context = ToolExecutionContext(
        run_id="run-other",
        user_id="user-test",
        trace_id="trace-other",
    )

    with pytest.raises(AuthorizedToolDenied) as exc_info:
        gate.execute(
            token,
            intent,
            call,
            wrong_context,
            grants=(grant,),
            expected_policy_fingerprint=decision.policy_fingerprint,
        )

    assert "run_id" in str(exc_info.value)
    assert "trace_id" in str(exc_info.value)
    assert calls == []


def test_missing_host_grant_still_denies_after_epistemic_authorization() -> None:
    decision, authorizer, gate, token, intent, call, context, _, calls = _authorized_fixture()

    with pytest.raises(ToolDenied, match="no active grant"):
        gate.execute(
            token,
            intent,
            call,
            context,
            grants=(),
            expected_policy_fingerprint=decision.policy_fingerprint,
        )

    assert calls == []
    state = authorizer.token_state(token.token_id)
    assert state is not None and state["consumed"] is True


def test_action_without_prebound_intent_cannot_execute() -> None:
    decision, _, gate, token, intent, call, context, grant, calls = _authorized_fixture()
    permit_action = decision.selected_action
    assert permit_action is not None

    # The real fixture is bound.  A distinct intent cannot be retrofitted after
    # the decision because its fingerprint will not match action metadata.
    different_intent = ToolExecutionIntent.bind(
        action_id=intent.action_id,
        call=ToolCall(
            call_id="call-different-intent",
            name="mutate_value",
            arguments={"value": 9},
        ),
        context=context,
    )

    with pytest.raises(AuthorizedToolDenied, match="action_intent_fingerprint"):
        gate.execute(
            token,
            different_intent,
            call,
            context,
            grants=(grant,),
            expected_policy_fingerprint=decision.policy_fingerprint,
        )

    assert calls == []


def test_binding_helper_rejects_rebinding_existing_metadata() -> None:
    _, _, _, _, intent, _, context, _, _ = _authorized_fixture()
    other_call = ToolCall(
        call_id="call-other-binding",
        name="mutate_value",
        arguments={"value": 10},
    )
    other = ToolExecutionIntent.bind(
        action_id=intent.action_id,
        call=other_call,
        context=context,
    )

    metadata = bind_intent_metadata({}, intent)
    with pytest.raises(ValueError, match="different tool intent"):
        bind_intent_metadata(metadata, other)
