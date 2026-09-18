from __future__ import annotations

import pytest

from skeleton.jeeves.agent.rational_metareasoning import (
    ComputationAction,
    ComputationOutcome,
    DecisionAlternative,
    MetaActionKind,
    MetaBudget,
    MetaState,
    MetareasoningPolicy,
    RationalMetareasoner,
    SelectionReason,
)


def _state(**overrides: object) -> MetaState:
    values = {
        "decisions": (
            DecisionAlternative("a", 10.0, 0.2),
            DecisionAlternative("b", 9.0, 0.1),
        ),
        "belief_entropy": 1.0,
        "current_risk": 0.2,
        "budget": MetaBudget(remaining_compute=100.0, remaining_tokens=10000, remaining_money=10.0, remaining_seconds=60.0),
        "delay_cost_per_second": 0.1,
        "compute_utility_rate": 1.0,
        "money_utility_rate": 1.0,
        "token_utility_rate": 0.0,
        "information_utility_rate": 0.0,
        "risk_reduction_utility_rate": 0.0,
    }
    values.update(overrides)
    return MetaState(**values)  # type: ignore[arg-type]


def _action(
    identifier: str,
    *,
    kind: MetaActionKind = MetaActionKind.THINK,
    utility_if_first: float = 10.0,
    utility_if_second: float = 9.0,
    cost: float = 0.0,
    delay: float = 0.0,
    entropy: float = 0.5,
    risk: float = 0.2,
    mandatory: bool = False,
) -> ComputationAction:
    return ComputationAction(
        action_id=identifier,
        kind=kind,
        outcomes=(
            ComputationOutcome(
                probability=1.0,
                posterior_utilities={"a": utility_if_first, "b": utility_if_second},
                posterior_entropy=entropy,
                posterior_risk=risk,
            ),
        ),
        compute_cost=cost,
        delay_seconds=delay,
        mandatory=mandatory,
    )


def test_positive_decision_value_can_justify_computation() -> None:
    action = _action("search", utility_if_first=10.0, utility_if_second=13.0, cost=1.0)
    assessment = RationalMetareasoner().assess(_state(), action)
    assert assessment.expected_decision_improvement == pytest.approx(3.0)
    assert assessment.value_of_computation == pytest.approx(2.0)
    decision = RationalMetareasoner().choose(_state(), (action,))
    assert decision.selected_action_id == "search"
    assert decision.reason == SelectionReason.POSITIVE_VALUE_OF_COMPUTATION


def test_negative_value_stops_instead_of_reasoning_forever() -> None:
    action = _action("think", cost=2.0, delay=1.0)
    decision = RationalMetareasoner().choose(_state(), (action,))
    assert decision.selected_kind == MetaActionKind.STOP
    assert decision.reason == SelectionReason.NO_POSITIVE_COMPUTATION


def test_information_gain_is_not_utility_by_default() -> None:
    action = _action("info", entropy=0.0, cost=0.1)
    assessment = RationalMetareasoner().assess(_state(), action)
    assert assessment.expected_information_gain == pytest.approx(1.0)
    assert assessment.expected_decision_improvement == pytest.approx(0.0)
    assert assessment.value_of_computation == pytest.approx(-0.1)


def test_information_gain_can_be_given_explicit_task_value() -> None:
    action = _action("info", entropy=0.0, cost=0.1)
    state = _state(information_utility_rate=0.5)
    assessment = RationalMetareasoner().assess(state, action)
    assert assessment.value_of_computation == pytest.approx(0.4)


def test_mandatory_safety_action_can_override_myopic_negative_voc() -> None:
    mandatory = _action("verify", kind=MetaActionKind.VERIFY, cost=20.0, mandatory=True)
    decision = RationalMetareasoner().choose(_state(), (mandatory,))
    assert decision.selected_action_id == "verify"
    assert decision.reason == SelectionReason.MANDATORY_SAFETY


def test_mandatory_action_still_cannot_violate_hard_budget() -> None:
    mandatory = _action("verify", kind=MetaActionKind.VERIFY, cost=101.0, mandatory=True)
    decision = RationalMetareasoner().choose(_state(), (mandatory,))
    assert decision.selected_kind == MetaActionKind.STOP
    assert decision.reason == SelectionReason.BUDGET_EXHAUSTED


def test_zero_time_budget_stops() -> None:
    state = _state(budget=MetaBudget(100.0, 10000, 10.0, 0.0))
    decision = RationalMetareasoner().choose(state, (_action("think"),))
    assert decision.selected_kind == MetaActionKind.STOP
    assert decision.reason == SelectionReason.DEADLINE


def test_simulation_cannot_be_promoted_to_external_evidence() -> None:
    outcome = ComputationOutcome(1.0, {"a": 10.0, "b": 9.0}, 0.5, 0.2)
    with pytest.raises(ValueError, match="simulation"):
        ComputationAction(
            action_id="sim",
            kind=MetaActionKind.SIMULATE,
            outcomes=(outcome,),
            evidence_producing=True,
        )


def test_outcome_distribution_must_be_normalized() -> None:
    with pytest.raises(ValueError, match="sum to one"):
        ComputationAction(
            action_id="bad",
            kind=MetaActionKind.THINK,
            outcomes=(
                ComputationOutcome(0.4, {"a": 10.0, "b": 9.0}, 0.5, 0.2),
                ComputationOutcome(0.4, {"a": 10.0, "b": 9.0}, 0.5, 0.2),
            ),
        )


def test_missing_posterior_decision_utility_fails_closed() -> None:
    action = ComputationAction(
        action_id="bad",
        kind=MetaActionKind.THINK,
        outcomes=(ComputationOutcome(1.0, {"a": 10.0}, 0.5, 0.2),),
    )
    with pytest.raises(ValueError, match="missing posterior utilities"):
        RationalMetareasoner().assess(_state(), action)


def test_information_directed_tie_breaking_is_deterministic() -> None:
    state = _state(information_utility_rate=1.0)
    # Equal VOC, but action x removes more entropy and therefore yields a lower
    # information ratio under the same posterior regret.
    x = _action("x", utility_if_first=10.0, utility_if_second=11.0, entropy=0.0)
    y = _action("y", utility_if_first=10.0, utility_if_second=11.0, entropy=0.5)
    reasoner = RationalMetareasoner(
        MetareasoningPolicy(prefer_information_directed_within=1.0)
    )
    first = reasoner.choose(state, (x, y))
    second = reasoner.choose(state, (x, y))
    assert first.fingerprint == second.fingerprint
    assert first.selected_action_id in {"x", "y"}
