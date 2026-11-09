"""Epistemic decision bridge for Jeeves.

This module couples two already distinct Jeeves surfaces without collapsing their
semantics:

* :mod:`world_model` represents factual/epistemic uncertainty over propositions.
* :mod:`model_based_control` represents empirical uncertainty over action effects.

The bridge is intentionally advisory.  It never executes tools, never writes
beliefs, never promotes imagined transitions into evidence, and never grants an
action permission.  Its job is narrower: decide whether the current evidence
supports acting, gathering information, or abstaining, while preserving enough
structure for audit and replay.

The implementation uses interval-valued utility, minimax regret, deterministic
stress scenarios, and an explicit value-of-information comparison.  This keeps
the control question inspectable even when point estimates look attractive.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .model_based_control import AbstractAction, LearnedTransitionModel, PredictedTransition
from .types import (
    AgentContractError,
    RiskTier,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)
from .world_model import BeliefGraph, CounterfactualProbe


class EpistemicDecisionError(RuntimeError):
    """Raised when an epistemic decision contract cannot be evaluated safely."""


class DecisionDisposition(str, Enum):
    ACT = "act"
    OBSERVE = "observe"
    ABSTAIN = "abstain"


class StressKind(str, Enum):
    NOMINAL = "nominal"
    EPISTEMIC_PESSIMISM = "epistemic_pessimism"
    MODEL_PESSIMISM = "model_pessimism"
    VERIFICATION_DROP = "verification_drop"
    COST_INFLATION = "cost_inflation"
    JOINT_ADVERSE = "joint_adverse"


_RISK_ORDER = {
    RiskTier.READ_ONLY: 0,
    RiskTier.REVERSIBLE: 1,
    RiskTier.MUTATING: 2,
    RiskTier.EXTERNAL: 3,
    RiskTier.HIGH_IMPACT: 4,
}

_RISK_PENALTY = {
    RiskTier.READ_ONLY: 0.0,
    RiskTier.REVERSIBLE: 0.08,
    RiskTier.MUTATING: 0.22,
    RiskTier.EXTERNAL: 0.42,
    RiskTier.HIGH_IMPACT: 0.70,
}


@dataclass(frozen=True, slots=True)
class BeliefRequirement:
    """A proposition whose truth or falsity changes an action's desirability."""

    proposition_id: str
    desired_probability: float = 1.0
    importance: float = 1.0
    veto_below: float | None = None
    observation_cost: float = 0.1
    hypothetical_reliability: float = 0.8

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposition_id",
            require_id("proposition_id", self.proposition_id),
        )
        object.__setattr__(
            self,
            "desired_probability",
            probability("desired_probability", self.desired_probability),
        )
        importance = finite_number("importance", self.importance)
        if not 0.0 <= importance <= 10.0:
            raise AgentContractError("importance must be in [0, 10]")
        object.__setattr__(self, "importance", importance)
        if self.veto_below is not None:
            object.__setattr__(
                self,
                "veto_below",
                probability("veto_below", self.veto_below),
            )
        object.__setattr__(
            self,
            "observation_cost",
            probability("observation_cost", self.observation_cost),
        )
        object.__setattr__(
            self,
            "hypothetical_reliability",
            probability("hypothetical_reliability", self.hypothetical_reliability),
        )

    def satisfaction(self, current_probability: float) -> float:
        """Return [0, 1] agreement with the desired truth probability."""

        p = probability("current_probability", current_probability)
        return max(0.0, 1.0 - abs(p - self.desired_probability))


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    action: AbstractAction
    requirements: tuple[BeliefRequirement, ...] = ()
    intrinsic_value: float = 0.0
    downside_weight: float = 1.0
    evidence_weight: float = 1.0
    model_weight: float = 1.0
    verification_weight: float = 0.35
    cost_weight: float = 0.15
    risk_weight: float = 0.25
    minimum_observations: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.action, AbstractAction):
            raise AgentContractError("action must be AbstractAction")
        requirements = tuple(self.requirements)
        if any(not isinstance(item, BeliefRequirement) for item in requirements):
            raise AgentContractError("requirements must contain BeliefRequirement")
        if len({item.proposition_id for item in requirements}) != len(requirements):
            raise AgentContractError("duplicate belief requirement")
        object.__setattr__(self, "requirements", requirements)

        intrinsic = finite_number("intrinsic_value", self.intrinsic_value)
        if not -1.0 <= intrinsic <= 1.0:
            raise AgentContractError("intrinsic_value must be in [-1, 1]")
        object.__setattr__(self, "intrinsic_value", intrinsic)

        for name in (
            "downside_weight",
            "evidence_weight",
            "model_weight",
            "verification_weight",
            "cost_weight",
            "risk_weight",
        ):
            value = finite_number(name, getattr(self, name))
            if not 0.0 <= value <= 10.0:
                raise AgentContractError(f"{name} must be in [0, 10]")
            object.__setattr__(self, name, value)

        object.__setattr__(
            self,
            "minimum_observations",
            positive_int("minimum_observations", self.minimum_observations, maximum=10_000_000),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def action_id(self) -> str:
        return self.action.action_id


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    maximum_risk: RiskTier = RiskTier.REVERSIBLE
    minimum_lower_utility: float = 0.0
    maximum_regret: float = 0.30
    maximum_model_uncertainty: float = 0.65
    minimum_belief_satisfaction: float = 0.55
    minimum_verification: float = 0.45
    observation_margin: float = 0.04
    abstain_margin: float = 0.0
    model_uncertainty_width: float = 0.45
    epistemic_uncertainty_width: float = 0.40
    verification_uncertainty_width: float = 0.20
    cost_uncertainty_width: float = 0.15
    require_stress_survival: bool = True
    require_nonnegative_joint_adverse: bool = False
    maximum_candidates: int = 128
    maximum_requirements_per_candidate: int = 64

    def __post_init__(self) -> None:
        if not isinstance(self.maximum_risk, RiskTier):
            object.__setattr__(self, "maximum_risk", RiskTier(str(self.maximum_risk)))

        for name in (
            "maximum_regret",
            "maximum_model_uncertainty",
            "minimum_belief_satisfaction",
            "minimum_verification",
            "observation_margin",
            "model_uncertainty_width",
            "epistemic_uncertainty_width",
            "verification_uncertainty_width",
            "cost_uncertainty_width",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))

        lower = finite_number("minimum_lower_utility", self.minimum_lower_utility)
        abstain = finite_number("abstain_margin", self.abstain_margin)
        if not -2.0 <= lower <= 2.0:
            raise AgentContractError("minimum_lower_utility must be in [-2, 2]")
        if not -2.0 <= abstain <= 2.0:
            raise AgentContractError("abstain_margin must be in [-2, 2]")
        object.__setattr__(self, "minimum_lower_utility", lower)
        object.__setattr__(self, "abstain_margin", abstain)
        object.__setattr__(
            self,
            "maximum_candidates",
            positive_int("maximum_candidates", self.maximum_candidates, maximum=4096),
        )
        object.__setattr__(
            self,
            "maximum_requirements_per_candidate",
            positive_int(
                "maximum_requirements_per_candidate",
                self.maximum_requirements_per_candidate,
                maximum=4096,
            ),
        )


@dataclass(frozen=True, slots=True)
class BeliefContribution:
    proposition_id: str
    probability: float
    desired_probability: float
    satisfaction: float
    entropy_bits: float
    contradiction_pressure: float
    importance: float
    vetoed: bool
    probe: CounterfactualProbe


@dataclass(frozen=True, slots=True)
class UtilityInterval:
    lower: float
    point: float
    upper: float

    def __post_init__(self) -> None:
        lower = finite_number("lower", self.lower)
        point = finite_number("point", self.point)
        upper = finite_number("upper", self.upper)
        if lower > point + 1e-12 or point > upper + 1e-12:
            raise AgentContractError("utility interval must satisfy lower <= point <= upper")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "point", point)
        object.__setattr__(self, "upper", upper)

    @property
    def width(self) -> float:
        return self.upper - self.lower


@dataclass(frozen=True, slots=True)
class StressResult:
    kind: StressKind
    utility: float
    passed: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    action_id: str
    candidate_fingerprint: str
    prediction: PredictedTransition
    beliefs: tuple[BeliefContribution, ...]
    evidence_satisfaction: float
    epistemic_uncertainty: float
    contradiction_pressure: float
    utility: UtilityInterval
    stress: tuple[StressResult, ...]
    veto_reasons: tuple[str, ...]
    eligible: bool
    robust_floor: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ObservationOpportunity:
    action_id: str
    proposition_id: str
    current_action_utility: float
    expected_post_observation_utility: float
    information_gain_bits: float
    observation_cost: float
    net_value: float
    probe_priority: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RegretRow:
    action_id: str
    worst_case_regret: float
    nominal_regret: float
    scenario_regrets: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class EpistemicDecision:
    decision_id: str
    disposition: DecisionDisposition
    selected_action: AbstractAction | None
    selected_observation: ObservationOpportunity | None
    assessments: tuple[CandidateAssessment, ...]
    regret: tuple[RegretRow, ...]
    reasons: tuple[str, ...]
    world_fingerprint: str
    model_fingerprint: str
    policy_fingerprint: str
    fingerprint: str


class EpistemicDecisionBridge:
    """Join belief uncertainty and transition uncertainty without mutating either."""

    def __init__(
        self,
        world: BeliefGraph,
        model: LearnedTransitionModel,
        *,
        policy: DecisionPolicy | None = None,
    ) -> None:
        if not isinstance(world, BeliefGraph):
            raise TypeError("world must be BeliefGraph")
        if not isinstance(model, LearnedTransitionModel):
            raise TypeError("model must be LearnedTransitionModel")
        self.world = world
        self.model = model
        self.policy = policy or DecisionPolicy()

    def assess(self, state_id: str, candidate: ActionCandidate) -> CandidateAssessment:
        if not isinstance(candidate, ActionCandidate):
            raise TypeError("candidate must be ActionCandidate")
        state_id = require_id("state_id", state_id)
        prediction = self.model.predict(state_id, candidate.action_id)

        beliefs: list[BeliefContribution] = []
        vetoes: list[str] = []
        weighted_satisfaction = 0.0
        total_importance = 0.0
        weighted_entropy = 0.0
        weighted_contradiction = 0.0

        if len(candidate.requirements) > self.policy.maximum_requirements_per_candidate:
            vetoes.append("requirement_budget_exceeded")

        for requirement in candidate.requirements[: self.policy.maximum_requirements_per_candidate]:
            state = self.world.require_belief(requirement.proposition_id)
            satisfaction = requirement.satisfaction(state.probability)
            contradiction = self.world.contradiction_pressure(requirement.proposition_id)
            probe = self.world.counterfactual_probe(
                requirement.proposition_id,
                hypothetical_reliability=requirement.hypothetical_reliability,
                observation_cost=requirement.observation_cost,
            )
            vetoed = (
                requirement.veto_below is not None
                and satisfaction + 1e-12 < requirement.veto_below
            )
            if vetoed:
                vetoes.append(f"belief_veto:{requirement.proposition_id}")
            importance = requirement.importance
            total_importance += importance
            weighted_satisfaction += importance * satisfaction
            weighted_entropy += importance * state.entropy_bits
            weighted_contradiction += importance * contradiction
            beliefs.append(
                BeliefContribution(
                    proposition_id=requirement.proposition_id,
                    probability=state.probability,
                    desired_probability=requirement.desired_probability,
                    satisfaction=satisfaction,
                    entropy_bits=state.entropy_bits,
                    contradiction_pressure=contradiction,
                    importance=importance,
                    vetoed=vetoed,
                    probe=probe,
                )
            )

        evidence_satisfaction = (
            weighted_satisfaction / total_importance if total_importance else 1.0
        )
        epistemic_uncertainty = (
            min(1.0, weighted_entropy / total_importance) if total_importance else 0.0
        )
        contradiction_pressure = (
            min(1.0, weighted_contradiction / total_importance)
            if total_importance
            else 0.0
        )

        if _RISK_ORDER[candidate.action.risk] > _RISK_ORDER[self.policy.maximum_risk]:
            vetoes.append("risk_above_policy")
        if prediction.observations < candidate.minimum_observations:
            vetoes.append("insufficient_transition_observations")
        if prediction.uncertainty > self.policy.maximum_model_uncertainty:
            vetoes.append("model_uncertainty_above_policy")
        if evidence_satisfaction < self.policy.minimum_belief_satisfaction:
            vetoes.append("belief_satisfaction_below_policy")
        if prediction.expected_verification < self.policy.minimum_verification:
            vetoes.append("verification_below_policy")

        point = self._point_utility(candidate, prediction, evidence_satisfaction)
        width = self._utility_width(
            candidate,
            prediction,
            epistemic_uncertainty=epistemic_uncertainty,
            contradiction_pressure=contradiction_pressure,
        )
        interval = UtilityInterval(
            lower=point - width,
            point=point,
            upper=point + width,
        )
        stress = self._stress(
            candidate,
            prediction,
            evidence_satisfaction=evidence_satisfaction,
            epistemic_uncertainty=epistemic_uncertainty,
            contradiction_pressure=contradiction_pressure,
        )
        robust_floor = min((item.utility for item in stress), default=interval.lower)
        if interval.lower < self.policy.minimum_lower_utility:
            vetoes.append("lower_utility_below_policy")
        if self.policy.require_stress_survival and any(not item.passed for item in stress):
            vetoes.append("stress_survival_failed")
        if (
            self.policy.require_nonnegative_joint_adverse
            and next(
                (
                    item.utility
                    for item in stress
                    if item.kind is StressKind.JOINT_ADVERSE
                ),
                0.0,
            )
            < 0.0
        ):
            vetoes.append("joint_adverse_negative")

        candidate_fingerprint = stable_fingerprint(
            {
                "action": candidate.action_id,
                "requirements": [
                    (
                        item.proposition_id,
                        item.desired_probability,
                        item.importance,
                        item.veto_below,
                    )
                    for item in candidate.requirements
                ],
                "intrinsic": candidate.intrinsic_value,
                "weights": (
                    candidate.downside_weight,
                    candidate.evidence_weight,
                    candidate.model_weight,
                    candidate.verification_weight,
                    candidate.cost_weight,
                    candidate.risk_weight,
                ),
                "minimum_observations": candidate.minimum_observations,
                "metadata": candidate.metadata,
            }
        )
        fingerprint = stable_fingerprint(
            {
                "candidate": candidate_fingerprint,
                "prediction": self._prediction_fingerprint(prediction),
                "beliefs": [
                    (
                        item.proposition_id,
                        item.probability,
                        item.satisfaction,
                        item.entropy_bits,
                        item.contradiction_pressure,
                        item.vetoed,
                    )
                    for item in beliefs
                ],
                "interval": (interval.lower, interval.point, interval.upper),
                "stress": [(item.kind.value, item.utility, item.passed) for item in stress],
                "vetoes": tuple(sorted(set(vetoes))),
            }
        )
        return CandidateAssessment(
            action_id=candidate.action_id,
            candidate_fingerprint=candidate_fingerprint,
            prediction=prediction,
            beliefs=tuple(beliefs),
            evidence_satisfaction=evidence_satisfaction,
            epistemic_uncertainty=epistemic_uncertainty,
            contradiction_pressure=contradiction_pressure,
            utility=interval,
            stress=stress,
            veto_reasons=tuple(sorted(set(vetoes))),
            eligible=not vetoes,
            robust_floor=robust_floor,
            fingerprint=fingerprint,
        )

    def decide(
        self,
        state_id: str,
        candidates: Sequence[ActionCandidate],
    ) -> EpistemicDecision:
        state_id = require_id("state_id", state_id)
        candidate_tuple = tuple(candidates)
        if not candidate_tuple:
            raise EpistemicDecisionError("at least one candidate is required")
        if len(candidate_tuple) > self.policy.maximum_candidates:
            raise EpistemicDecisionError("candidate budget exceeded")
        if any(not isinstance(item, ActionCandidate) for item in candidate_tuple):
            raise TypeError("candidates must contain ActionCandidate")
        if len({item.action_id for item in candidate_tuple}) != len(candidate_tuple):
            raise EpistemicDecisionError("duplicate candidate action_id")

        assessments = tuple(self.assess(state_id, item) for item in candidate_tuple)
        regret = self._regret_table(assessments)
        regret_by_id = {item.action_id: item for item in regret}
        candidate_by_id = {item.action_id: item for item in candidate_tuple}

        viable = [
            item
            for item in assessments
            if item.eligible
            and regret_by_id[item.action_id].worst_case_regret <= self.policy.maximum_regret
        ]
        viable.sort(
            key=lambda item: (
                item.robust_floor,
                item.utility.lower,
                -regret_by_id[item.action_id].worst_case_regret,
                item.utility.point,
                item.action_id,
            ),
            reverse=True,
        )
        selected_assessment = viable[0] if viable else None

        observation = self._best_observation(
            assessments=assessments,
            candidate_by_id=candidate_by_id,
        )

        reasons: list[str] = []
        disposition: DecisionDisposition
        selected_action: AbstractAction | None = None
        selected_observation: ObservationOpportunity | None = None

        if selected_assessment is None:
            if observation is not None and observation.net_value > self.policy.observation_margin:
                disposition = DecisionDisposition.OBSERVE
                selected_observation = observation
                reasons.append("no_action_cleared_all_gates; positive_information_value")
            else:
                disposition = DecisionDisposition.ABSTAIN
                reasons.append("no_action_cleared_all_gates")
                if observation is None:
                    reasons.append("no_material_information_opportunity")
                else:
                    reasons.append("information_value_below_margin")
        else:
            selected_regret = regret_by_id[selected_assessment.action_id]
            act_floor = selected_assessment.robust_floor
            observe_value = observation.net_value if observation is not None else -math.inf
            if (
                observation is not None
                and observe_value > act_floor + self.policy.observation_margin
            ):
                disposition = DecisionDisposition.OBSERVE
                selected_observation = observation
                reasons.append("information_value_exceeds_robust_action_floor")
            elif act_floor >= self.policy.abstain_margin:
                disposition = DecisionDisposition.ACT
                selected_action = candidate_by_id[selected_assessment.action_id].action
                reasons.append("robust_action_cleared_policy")
                reasons.append(
                    f"worst_case_regret={selected_regret.worst_case_regret:.6f}"
                )
            else:
                disposition = DecisionDisposition.ABSTAIN
                reasons.append("robust_floor_below_abstain_margin")

        world_fingerprint = self.world.snapshot(persist=False).fingerprint
        model_fingerprint = self.model.fingerprint
        policy_fingerprint = stable_fingerprint(
            {
                "maximum_risk": self.policy.maximum_risk.value,
                "minimum_lower_utility": self.policy.minimum_lower_utility,
                "maximum_regret": self.policy.maximum_regret,
                "maximum_model_uncertainty": self.policy.maximum_model_uncertainty,
                "minimum_belief_satisfaction": self.policy.minimum_belief_satisfaction,
                "minimum_verification": self.policy.minimum_verification,
                "observation_margin": self.policy.observation_margin,
                "abstain_margin": self.policy.abstain_margin,
                "widths": (
                    self.policy.model_uncertainty_width,
                    self.policy.epistemic_uncertainty_width,
                    self.policy.verification_uncertainty_width,
                    self.policy.cost_uncertainty_width,
                ),
                "stress": (
                    self.policy.require_stress_survival,
                    self.policy.require_nonnegative_joint_adverse,
                ),
            }
        )
        fingerprint = stable_fingerprint(
            {
                "state": state_id,
                "disposition": disposition.value,
                "action": selected_action.action_id if selected_action else None,
                "observation": (
                    (
                        selected_observation.action_id,
                        selected_observation.proposition_id,
                        selected_observation.fingerprint,
                    )
                    if selected_observation
                    else None
                ),
                "assessments": [item.fingerprint for item in assessments],
                "regret": [
                    (
                        item.action_id,
                        item.worst_case_regret,
                        item.nominal_regret,
                        tuple(sorted(item.scenario_regrets.items())),
                    )
                    for item in regret
                ],
                "world": world_fingerprint,
                "model": model_fingerprint,
                "policy": policy_fingerprint,
            }
        )
        return EpistemicDecision(
            decision_id=stable_id("epistemic_decision", {"fingerprint": fingerprint}),
            disposition=disposition,
            selected_action=selected_action,
            selected_observation=selected_observation,
            assessments=assessments,
            regret=regret,
            reasons=tuple(reasons),
            world_fingerprint=world_fingerprint,
            model_fingerprint=model_fingerprint,
            policy_fingerprint=policy_fingerprint,
            fingerprint=fingerprint,
        )

    def _point_utility(
        self,
        candidate: ActionCandidate,
        prediction: PredictedTransition,
        evidence_satisfaction: float,
    ) -> float:
        model_term = prediction.expected_reward
        verification_term = prediction.expected_verification - 0.5
        cost_term = min(1.0, prediction.expected_cost)
        risk_term = _RISK_PENALTY[candidate.action.risk]
        evidence_term = evidence_satisfaction - 0.5
        downside = (
            prediction.outcome_probabilities.get("failure", 0.0)
            + prediction.outcome_probabilities.get("blocked", 0.0)
        )
        return (
            candidate.intrinsic_value
            + candidate.model_weight * model_term
            + candidate.evidence_weight * evidence_term
            + candidate.verification_weight * verification_term
            - candidate.cost_weight * cost_term
            - candidate.risk_weight * risk_term
            - candidate.downside_weight * downside
        )

    def _utility_width(
        self,
        candidate: ActionCandidate,
        prediction: PredictedTransition,
        *,
        epistemic_uncertainty: float,
        contradiction_pressure: float,
    ) -> float:
        model = (
            candidate.model_weight
            * self.policy.model_uncertainty_width
            * prediction.uncertainty
        )
        epistemic = (
            candidate.evidence_weight
            * self.policy.epistemic_uncertainty_width
            * min(1.0, epistemic_uncertainty + contradiction_pressure * 0.5)
        )
        verification = (
            candidate.verification_weight
            * self.policy.verification_uncertainty_width
            * (1.0 - prediction.expected_verification)
        )
        cost = (
            candidate.cost_weight
            * self.policy.cost_uncertainty_width
            * min(1.0, prediction.expected_cost)
        )
        return max(0.0, model + epistemic + verification + cost)

    def _stress(
        self,
        candidate: ActionCandidate,
        prediction: PredictedTransition,
        *,
        evidence_satisfaction: float,
        epistemic_uncertainty: float,
        contradiction_pressure: float,
    ) -> tuple[StressResult, ...]:
        point = self._point_utility(candidate, prediction, evidence_satisfaction)

        epistemic_drop = candidate.evidence_weight * min(
            1.0,
            epistemic_uncertainty * 0.5 + contradiction_pressure * 0.5,
        )
        model_drop = candidate.model_weight * prediction.uncertainty * 0.5
        verification_drop = candidate.verification_weight * min(
            0.5,
            (1.0 - prediction.expected_verification) + 0.15,
        )
        cost_drop = candidate.cost_weight * min(
            1.0,
            prediction.expected_cost * 0.5 + 0.15,
        )
        joint = epistemic_drop + model_drop + verification_drop + cost_drop

        values = (
            (StressKind.NOMINAL, point, ("nominal point utility",)),
            (
                StressKind.EPISTEMIC_PESSIMISM,
                point - epistemic_drop,
                ("belief entropy and contradiction pressure stressed",),
            ),
            (
                StressKind.MODEL_PESSIMISM,
                point - model_drop,
                ("transition-model uncertainty stressed",),
            ),
            (
                StressKind.VERIFICATION_DROP,
                point - verification_drop,
                ("verification expectation degraded",),
            ),
            (
                StressKind.COST_INFLATION,
                point - cost_drop,
                ("bounded cost inflation applied",),
            ),
            (
                StressKind.JOINT_ADVERSE,
                point - joint,
                ("epistemic, model, verification, and cost stresses combined",),
            ),
        )
        floor = self.policy.minimum_lower_utility
        return tuple(
            StressResult(kind, utility, utility + 1e-12 >= floor, notes)
            for kind, utility, notes in values
        )

    def _best_observation(
        self,
        *,
        assessments: Sequence[CandidateAssessment],
        candidate_by_id: Mapping[str, ActionCandidate],
    ) -> ObservationOpportunity | None:
        opportunities: list[ObservationOpportunity] = []
        for assessment in assessments:
            candidate = candidate_by_id[assessment.action_id]
            if not assessment.beliefs:
                continue
            requirement_by_id = {
                item.proposition_id: item for item in candidate.requirements
            }
            for belief in assessment.beliefs:
                requirement = requirement_by_id[belief.proposition_id]
                post_support_satisfaction = requirement.satisfaction(
                    belief.probe.if_supported_probability
                )
                post_refute_satisfaction = requirement.satisfaction(
                    belief.probe.if_refuted_probability
                )
                support_utility = self._point_utility(
                    candidate,
                    assessment.prediction,
                    self._replace_weighted_satisfaction(
                        assessment,
                        proposition_id=belief.proposition_id,
                        replacement=post_support_satisfaction,
                    ),
                )
                refute_utility = self._point_utility(
                    candidate,
                    assessment.prediction,
                    self._replace_weighted_satisfaction(
                        assessment,
                        proposition_id=belief.proposition_id,
                        replacement=post_refute_satisfaction,
                    ),
                )
                p = belief.probability
                expected = p * support_utility + (1.0 - p) * refute_utility
                raw_gain = max(0.0, expected - assessment.utility.point)
                information_bonus = min(
                    0.25,
                    belief.probe.expected_information_gain_bits * 0.20,
                )
                net = (
                    raw_gain
                    + information_bonus
                    + belief.probe.priority * 0.05
                    - requirement.observation_cost
                )
                fingerprint = stable_fingerprint(
                    {
                        "action": assessment.action_id,
                        "proposition": belief.proposition_id,
                        "current": assessment.utility.point,
                        "expected": expected,
                        "information_gain": belief.probe.expected_information_gain_bits,
                        "cost": requirement.observation_cost,
                        "net": net,
                        "assessment": assessment.fingerprint,
                    }
                )
                opportunities.append(
                    ObservationOpportunity(
                        action_id=assessment.action_id,
                        proposition_id=belief.proposition_id,
                        current_action_utility=assessment.utility.point,
                        expected_post_observation_utility=expected,
                        information_gain_bits=belief.probe.expected_information_gain_bits,
                        observation_cost=requirement.observation_cost,
                        net_value=net,
                        probe_priority=belief.probe.priority,
                        fingerprint=fingerprint,
                    )
                )
        if not opportunities:
            return None
        opportunities.sort(
            key=lambda item: (
                item.net_value,
                item.information_gain_bits,
                item.probe_priority,
                item.action_id,
                item.proposition_id,
            ),
            reverse=True,
        )
        return opportunities[0]

    @staticmethod
    def _replace_weighted_satisfaction(
        assessment: CandidateAssessment,
        *,
        proposition_id: str,
        replacement: float,
    ) -> float:
        replacement = probability("replacement", replacement)
        total = sum(item.importance for item in assessment.beliefs)
        if total <= 0:
            return assessment.evidence_satisfaction
        value = 0.0
        for item in assessment.beliefs:
            satisfaction = (
                replacement if item.proposition_id == proposition_id else item.satisfaction
            )
            value += item.importance * satisfaction
        return value / total

    def _regret_table(
        self,
        assessments: Sequence[CandidateAssessment],
    ) -> tuple[RegretRow, ...]:
        if not assessments:
            return ()

        scenario_values: dict[str, dict[str, float]] = {}
        for assessment in assessments:
            scenario_values[assessment.action_id] = {
                StressKind.NOMINAL.value: assessment.utility.point,
                **{item.kind.value: item.utility for item in assessment.stress},
                "interval_lower": assessment.utility.lower,
            }

        scenario_names = sorted(
            {name for values in scenario_values.values() for name in values}
        )
        best_by_scenario = {
            name: max(values.get(name, -math.inf) for values in scenario_values.values())
            for name in scenario_names
        }

        rows: list[RegretRow] = []
        for assessment in assessments:
            values = scenario_values[assessment.action_id]
            regrets = {
                name: max(0.0, best_by_scenario[name] - values.get(name, -math.inf))
                for name in scenario_names
            }
            rows.append(
                RegretRow(
                    action_id=assessment.action_id,
                    worst_case_regret=max(regrets.values(), default=0.0),
                    nominal_regret=regrets.get(StressKind.NOMINAL.value, 0.0),
                    scenario_regrets=dict(sorted(regrets.items())),
                )
            )
        rows.sort(
            key=lambda item: (
                item.worst_case_regret,
                item.nominal_regret,
                item.action_id,
            )
        )
        return tuple(rows)

    @staticmethod
    def _prediction_fingerprint(prediction: PredictedTransition) -> str:
        return stable_fingerprint(
            {
                "state": prediction.state_id,
                "action": prediction.action_id,
                "next": sorted(prediction.next_state_probabilities.items()),
                "outcomes": sorted(prediction.outcome_probabilities.items()),
                "reward": prediction.expected_reward,
                "verification": prediction.expected_verification,
                "cost": prediction.expected_cost,
                "latency": prediction.expected_latency_ms,
                "uncertainty": prediction.uncertainty,
                "observations": prediction.observations,
            }
        )
