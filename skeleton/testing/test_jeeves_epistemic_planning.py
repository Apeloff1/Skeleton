from __future__ import annotations

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
from skeleton.jeeves.agent.types import RiskTier
from skeleton.jeeves.agent.world_model import BeliefGraph, Proposition


def _state(name: str, *, terminal: bool = False) -> CompactState:
    return CompactState.from_signals(
        features={"phase": name},
        progress=0.5 if not terminal else 1.0,
        uncertainty=0.2,
        budget_pressure=0.1,
        failure_pressure=0.0,
        risk=RiskTier.READ_ONLY,
        terminal=terminal,
    )


def _action(
    name: str,
    *,
    risk: RiskTier = RiskTier.REVERSIBLE,
    cost: float = 0.0,
) -> AbstractAction:
    return AbstractAction(
        action_id=f"action-{name}",
        name=name,
        capability=f"capability-{name}",
        risk=risk,
        estimated_external_cost=cost,
        reversible=risk in {RiskTier.READ_ONLY, RiskTier.REVERSIBLE},
    )


def _train(
    model: LearnedTransitionModel,
    *,
    state: CompactState,
    action: AbstractAction,
    next_state: CompactState,
    count: int,
    reward: float,
    verification: float,
    cost: float = 0.0,
    outcome: TransitionOutcome = TransitionOutcome.SUCCESS,
) -> None:
    for index in range(count):
        model.observe(
            transition_experience(
                run_id=f"run-{action.action_id}-{index}",
                state=state,
                action=action,
                next_state=next_state,
                outcome=outcome,
                reward=reward,
                verification_score=verification,
                cost=cost,
                latency_ms=10.0,
                observed_at=float(index + 1),
            )
        )


def _world_with_probability(probability: float) -> tuple[BeliefGraph, Proposition]:
    world = BeliefGraph(clock=lambda: 100.0)
    proposition = Proposition.create(
        "deployment",
        "precondition",
        "satisfied",
        scope="test",
    )
    world.upsert_proposition(proposition, prior=probability)
    return world, proposition


def test_supported_low_uncertainty_candidate_is_actionable() -> None:
    world, proposition = _world_with_probability(0.90)
    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    action = _action("safe")
    _train(
        model,
        state=start,
        action=action,
        next_state=done,
        count=16,
        reward=0.80,
        verification=0.95,
        cost=0.05,
    )

    bridge = EpistemicDecisionBridge(world, model)
    candidate = ActionCandidate(
        action=action,
        requirements=(
            BeliefRequirement(
                proposition.proposition_id,
                desired_probability=1.0,
                importance=1.0,
                observation_cost=0.05,
                hypothetical_reliability=0.8,
            ),
        ),
    )

    assessment = bridge.assess(start.state_id, candidate)
    decision = bridge.decide(start.state_id, [candidate])

    assert assessment.eligible is True
    assert assessment.prediction.observations == 16
    assert assessment.utility.lower > 0.0
    assert decision.disposition is DecisionDisposition.ACT
    assert decision.selected_action == action
    assert decision.selected_observation is None


def test_unknown_transition_prefers_information_when_probe_value_is_positive() -> None:
    world, proposition = _world_with_probability(0.50)
    model = LearnedTransitionModel()
    start = _state("start")
    action = _action("unknown")

    policy = DecisionPolicy(
        maximum_model_uncertainty=1.0,
        minimum_belief_satisfaction=0.0,
        minimum_verification=0.0,
        minimum_lower_utility=-1.0,
        observation_margin=0.01,
        require_stress_survival=False,
    )
    bridge = EpistemicDecisionBridge(world, model, policy=policy)
    candidate = ActionCandidate(
        action=action,
        requirements=(
            BeliefRequirement(
                proposition.proposition_id,
                observation_cost=0.01,
                hypothetical_reliability=0.95,
            ),
        ),
        minimum_observations=1,
    )

    assessment = bridge.assess(start.state_id, candidate)
    decision = bridge.decide(start.state_id, [candidate])

    assert assessment.eligible is False
    assert "insufficient_transition_observations" in assessment.veto_reasons
    assert decision.disposition is DecisionDisposition.OBSERVE
    assert decision.selected_action is None
    assert decision.selected_observation is not None
    assert decision.selected_observation.proposition_id == proposition.proposition_id
    assert decision.selected_observation.information_gain_bits > 0.0
    assert decision.selected_observation.net_value > 0.0


def test_risk_ceiling_fails_closed_without_information_escape_hatch() -> None:
    world = BeliefGraph(clock=lambda: 100.0)
    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    action = _action("dangerous", risk=RiskTier.HIGH_IMPACT)
    _train(
        model,
        state=start,
        action=action,
        next_state=done,
        count=25,
        reward=1.0,
        verification=1.0,
    )

    bridge = EpistemicDecisionBridge(
        world,
        model,
        policy=DecisionPolicy(
            maximum_risk=RiskTier.REVERSIBLE,
            minimum_lower_utility=-2.0,
            maximum_regret=1.0,
            require_stress_survival=False,
        ),
    )
    candidate = ActionCandidate(action=action)
    assessment = bridge.assess(start.state_id, candidate)
    decision = bridge.decide(start.state_id, [candidate])

    assert assessment.eligible is False
    assert "risk_above_policy" in assessment.veto_reasons
    assert decision.disposition is DecisionDisposition.ABSTAIN
    assert decision.selected_action is None
    assert decision.selected_observation is None


def test_belief_veto_is_distinct_from_average_satisfaction() -> None:
    world, proposition = _world_with_probability(0.60)
    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    action = _action("requires-strong-belief")
    _train(
        model,
        state=start,
        action=action,
        next_state=done,
        count=20,
        reward=0.9,
        verification=0.95,
    )

    bridge = EpistemicDecisionBridge(
        world,
        model,
        policy=DecisionPolicy(
            minimum_belief_satisfaction=0.0,
            minimum_lower_utility=-2.0,
            require_stress_survival=False,
        ),
    )
    candidate = ActionCandidate(
        action=action,
        requirements=(
            BeliefRequirement(
                proposition.proposition_id,
                desired_probability=1.0,
                veto_below=0.80,
            ),
        ),
    )
    assessment = bridge.assess(start.state_id, candidate)

    assert assessment.evidence_satisfaction == 0.60
    assert "belief_veto:" + proposition.proposition_id in assessment.veto_reasons
    assert assessment.eligible is False


def test_decision_fingerprint_binds_world_and_model_state() -> None:
    world, proposition = _world_with_probability(0.85)
    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    action = _action("bind-state")
    _train(
        model,
        state=start,
        action=action,
        next_state=done,
        count=12,
        reward=0.7,
        verification=0.9,
    )
    policy = DecisionPolicy(
        minimum_lower_utility=-2.0,
        require_stress_survival=False,
    )
    bridge = EpistemicDecisionBridge(world, model, policy=policy)
    candidate = ActionCandidate(
        action=action,
        requirements=(BeliefRequirement(proposition.proposition_id),),
    )

    first = bridge.decide(start.state_id, [candidate])
    repeated = bridge.decide(start.state_id, [candidate])
    assert first.fingerprint == repeated.fingerprint
    assert first.world_fingerprint == repeated.world_fingerprint
    assert first.model_fingerprint == repeated.model_fingerprint

    world.set_prior(proposition.proposition_id, 0.65, reason="test mutation")
    changed_world = bridge.decide(start.state_id, [candidate])
    assert changed_world.world_fingerprint != first.world_fingerprint
    assert changed_world.fingerprint != first.fingerprint

    _train(
        model,
        state=start,
        action=action,
        next_state=done,
        count=1,
        reward=-0.5,
        verification=0.2,
        outcome=TransitionOutcome.FAILURE,
    )
    changed_model = bridge.decide(start.state_id, [candidate])
    assert changed_model.model_fingerprint != changed_world.model_fingerprint
    assert changed_model.fingerprint != changed_world.fingerprint


def test_regret_table_compares_candidates_on_common_stress_scenarios() -> None:
    world, proposition = _world_with_probability(0.90)
    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    stable = _action("stable")
    brittle = _action("brittle")

    _train(
        model,
        state=start,
        action=stable,
        next_state=done,
        count=36,
        reward=0.62,
        verification=0.92,
        cost=0.02,
    )
    _train(
        model,
        state=start,
        action=brittle,
        next_state=done,
        count=2,
        reward=0.75,
        verification=0.92,
        cost=0.02,
    )

    bridge = EpistemicDecisionBridge(
        world,
        model,
        policy=DecisionPolicy(
            maximum_model_uncertainty=1.0,
            minimum_lower_utility=-2.0,
            maximum_regret=1.0,
            require_stress_survival=False,
        ),
    )
    requirement = BeliefRequirement(proposition.proposition_id)
    decision = bridge.decide(
        start.state_id,
        [
            ActionCandidate(action=stable, requirements=(requirement,)),
            ActionCandidate(action=brittle, requirements=(requirement,)),
        ],
    )

    assert {row.action_id for row in decision.regret} == {
        stable.action_id,
        brittle.action_id,
    }
    for row in decision.regret:
        assert row.worst_case_regret >= row.nominal_regret >= 0.0
        assert "joint_adverse" in row.scenario_regrets
        assert "interval_lower" in row.scenario_regrets


def test_assessment_fingerprint_changes_when_candidate_contract_changes() -> None:
    world, proposition = _world_with_probability(0.90)
    model = LearnedTransitionModel()
    start = _state("start")
    done = _state("done", terminal=True)
    action = _action("contract")
    _train(
        model,
        state=start,
        action=action,
        next_state=done,
        count=10,
        reward=0.5,
        verification=0.9,
    )
    bridge = EpistemicDecisionBridge(
        world,
        model,
        policy=DecisionPolicy(
            minimum_lower_utility=-2.0,
            require_stress_survival=False,
        ),
    )

    loose = ActionCandidate(
        action=action,
        requirements=(
            BeliefRequirement(proposition.proposition_id, importance=1.0),
        ),
    )
    strict = ActionCandidate(
        action=action,
        requirements=(
            BeliefRequirement(
                proposition.proposition_id,
                importance=2.0,
                veto_below=0.95,
            ),
        ),
    )

    loose_assessment = bridge.assess(start.state_id, loose)
    strict_assessment = bridge.assess(start.state_id, strict)

    assert loose_assessment.candidate_fingerprint != strict_assessment.candidate_fingerprint
    assert loose_assessment.fingerprint != strict_assessment.fingerprint
    assert strict_assessment.eligible is False
