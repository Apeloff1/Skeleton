from __future__ import annotations

from dataclasses import replace

from skeleton.jeeves.agent.epistemic_authorization import (
    AuthorizationFailure,
    AuthorizationPolicy,
    DecisionAuthorizer,
)
from skeleton.jeeves.agent.epistemic_planning import (
    ActionCandidate,
    BeliefRequirement,
    DecisionDisposition,
    DecisionPolicy,
    EpistemicDecisionBridge,
)
from skeleton.jeeves.agent.model_based_control import (
    AbstractAction,
    CompactState,
    LearnedTransitionModel,
    TransitionOutcome,
    transition_experience,
)
from skeleton.jeeves.agent.types import RiskTier, stable_fingerprint
from skeleton.jeeves.agent.world_model import BeliefGraph, Proposition


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


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


def _trained_fixture() -> tuple[
    BeliefGraph,
    Proposition,
    LearnedTransitionModel,
    CompactState,
    CompactState,
    AbstractAction,
]:
    world = BeliefGraph(clock=lambda: 50.0)
    proposition = Proposition.create(
        "authorization",
        "precondition",
        "satisfied",
        scope="test",
    )
    world.upsert_proposition(proposition, prior=0.95)

    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    action = AbstractAction(
        action_id="action-authorized",
        name="authorized action",
        capability="authorization-test",
        risk=RiskTier.REVERSIBLE,
        reversible=True,
    )
    for index in range(25):
        model.observe(
            transition_experience(
                run_id=f"auth-run-{index}",
                state=start,
                action=action,
                next_state=done,
                outcome=TransitionOutcome.SUCCESS,
                reward=0.8,
                verification_score=0.98,
                cost=0.01,
                latency_ms=5.0,
                observed_at=float(index + 1),
            )
        )
    return world, proposition, model, start, done, action


def _act_decision(
    world: BeliefGraph,
    proposition: Proposition,
    model: LearnedTransitionModel,
    start: CompactState,
    action: AbstractAction,
):
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
    return decision


def test_valid_decision_requires_separate_issue_and_consume() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    clock = FakeClock()
    authorizer = DecisionAuthorizer(world, model, clock=clock)

    issued = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert issued.allowed is True
    assert issued.token is not None
    assert issued.permit is None
    assert authorizer.live_token_count == 1

    consumed = authorizer.consume(
        issued.token,
        action_id=action.action_id,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert consumed.allowed is True
    assert consumed.permit is not None
    assert consumed.permit.action == action
    assert consumed.permit.token_id == issued.token.token_id
    assert authorizer.live_token_count == 0


def test_replay_of_consumed_token_is_rejected() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    authorizer = DecisionAuthorizer(world, model, clock=FakeClock())
    issued = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert issued.token is not None

    first = authorizer.consume(
        issued.token,
        action_id=action.action_id,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    second = authorizer.consume(
        issued.token,
        action_id=action.action_id,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )

    assert first.allowed is True
    assert second.allowed is False
    assert AuthorizationFailure.TOKEN_ALREADY_CONSUMED in second.failures


def test_world_change_between_decision_and_issue_fails_closed() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    world.set_prior(proposition.proposition_id, 0.70, reason="new evidence")

    authorizer = DecisionAuthorizer(world, model, clock=FakeClock())
    result = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )

    assert result.allowed is False
    assert AuthorizationFailure.WORLD_STATE_CHANGED in result.failures
    assert result.token is None


def test_model_change_between_issue_and_consume_invalidates_token() -> None:
    world, proposition, model, start, done, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    authorizer = DecisionAuthorizer(world, model, clock=FakeClock())
    issued = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert issued.allowed is True
    assert issued.token is not None

    model.observe(
        transition_experience(
            run_id="late-model-change",
            state=start,
            action=action,
            next_state=done,
            outcome=TransitionOutcome.FAILURE,
            reward=-1.0,
            verification_score=0.0,
            observed_at=999.0,
        )
    )
    consumed = authorizer.consume(
        issued.token,
        action_id=action.action_id,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )

    assert consumed.allowed is False
    assert AuthorizationFailure.MODEL_STATE_CHANGED in consumed.failures


def test_expired_token_is_rejected() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    clock = FakeClock()
    authorizer = DecisionAuthorizer(
        world,
        model,
        policy=AuthorizationPolicy(token_ttl_seconds=2.0),
        clock=clock,
    )
    issued = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert issued.token is not None

    clock.advance(2.01)
    consumed = authorizer.consume(
        issued.token,
        action_id=action.action_id,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )

    assert consumed.allowed is False
    assert AuthorizationFailure.TOKEN_EXPIRED in consumed.failures


def test_action_substitution_is_rejected() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    authorizer = DecisionAuthorizer(world, model, clock=FakeClock())
    issued = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert issued.token is not None

    result = authorizer.consume(
        issued.token,
        action_id="action-substituted",
        expected_policy_fingerprint=decision.policy_fingerprint,
    )

    assert result.allowed is False
    assert AuthorizationFailure.ACTION_MISMATCH in result.failures


def test_policy_binding_is_required_and_exact() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    authorizer = DecisionAuthorizer(world, model, clock=FakeClock())

    missing = authorizer.issue(decision)
    wrong = authorizer.issue(
        decision,
        expected_policy_fingerprint=stable_fingerprint({"other": "policy"}),
    )

    assert missing.allowed is False
    assert AuthorizationFailure.POLICY_CHANGED in missing.failures
    assert wrong.allowed is False
    assert AuthorizationFailure.POLICY_CHANGED in wrong.failures


def test_revocation_prevents_consumption_and_is_audited() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    decision = _act_decision(world, proposition, model, start, action)
    authorizer = DecisionAuthorizer(world, model, clock=FakeClock())
    issued = authorizer.issue(
        decision,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )
    assert issued.token is not None

    assert authorizer.revoke(issued.token.token_id, reason="operator cancelled") is True
    result = authorizer.consume(
        issued.token,
        action_id=action.action_id,
        expected_policy_fingerprint=decision.policy_fingerprint,
    )

    assert result.allowed is False
    assert AuthorizationFailure.TOKEN_REVOKED in result.failures
    events = authorizer.audit_events(limit=10)
    assert any(event.kind == "revoked" for event in events)
    assert any(event.kind == "consume_rejected" for event in events)


def test_non_act_decision_cannot_be_authorized() -> None:
    world, proposition, model, start, _, action = _trained_fixture()
    act = _act_decision(world, proposition, model, start, action)
    abstain = replace(
        act,
        disposition=DecisionDisposition.ABSTAIN,
        selected_action=None,
        fingerprint=stable_fingerprint(
            {"base": act.fingerprint, "disposition": "abstain"}
        ),
    )
    authorizer = DecisionAuthorizer(world, model, clock=FakeClock())

    result = authorizer.issue(
        abstain,
        expected_policy_fingerprint=abstain.policy_fingerprint,
    )

    assert result.allowed is False
    assert AuthorizationFailure.NOT_ACT_DECISION in result.failures
    assert AuthorizationFailure.MISSING_SELECTED_ACTION in result.failures
