"""Decision-theoretic control of Jeeves' own computation.

Reasoning is not free.  This module treats THINK/SEARCH/SIMULATE/VERIFY/
EXPERIMENT/TOOL as metalevel actions whose value is derived from how they may
change the external decision, minus resource and delay costs.  The core follows
rational metareasoning/value-of-computation ideas while adding explicit entropy,
risk, budget, and information-directed diagnostics.

Important boundaries:
* information gain is not utility by itself;
* simulations never become external evidence here;
* safety-mandated verification can be required even when its myopic VOC is
  negative;
* outcome distributions must be supplied by a calibrated model or empirical
  estimator -- this module does not invent them;
* the default selector is myopic and bounded.  It is therefore an auditable
  approximation, not a claim of Bayes-optimal metareasoning.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Mapping, Optional, Sequence, Tuple


class MetaActionKind(str, Enum):
    THINK = "think"
    SEARCH = "search"
    SIMULATE = "simulate"
    VERIFY = "verify"
    EXPERIMENT = "experiment"
    TOOL = "tool"
    ACT = "act"
    STOP = "stop"


class SelectionReason(str, Enum):
    MANDATORY_SAFETY = "mandatory_safety"
    POSITIVE_VALUE_OF_COMPUTATION = "positive_value_of_computation"
    INFORMATION_DIRECTED = "information_directed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE = "deadline"
    NO_POSITIVE_COMPUTATION = "no_positive_computation"
    NO_FEASIBLE_COMPUTATION = "no_feasible_computation"


@dataclass(frozen=True)
class DecisionAlternative:
    decision_id: str
    expected_utility: float
    downside_risk: float = 0.0

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError("decision_id is required")
        _finite(self.expected_utility, "expected_utility")
        _probability(self.downside_risk, "downside_risk")


@dataclass(frozen=True)
class ComputationOutcome:
    probability: float
    posterior_utilities: Mapping[str, float]
    posterior_entropy: float
    posterior_risk: float
    observation_label: str = ""

    def __post_init__(self) -> None:
        _probability(self.probability, "outcome probability")
        _finite(self.posterior_entropy, "posterior_entropy")
        if self.posterior_entropy < 0.0:
            raise ValueError("posterior_entropy cannot be negative")
        _probability(self.posterior_risk, "posterior_risk")
        if not self.posterior_utilities:
            raise ValueError("posterior_utilities cannot be empty")
        for value in self.posterior_utilities.values():
            _finite(value, "posterior utility")


@dataclass(frozen=True)
class ComputationAction:
    action_id: str
    kind: MetaActionKind
    outcomes: Tuple[ComputationOutcome, ...]
    monetary_cost: float = 0.0
    compute_cost: float = 0.0
    delay_seconds: float = 0.0
    token_cost: int = 0
    mandatory: bool = False
    safety_relevant: bool = False
    evidence_producing: bool = False
    evidence_class: str = ""
    provenance_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("action_id is required")
        if self.kind in {MetaActionKind.ACT, MetaActionKind.STOP}:
            raise ValueError("ComputationAction must be a computational metalevel action")
        for name, value in (
            ("monetary_cost", self.monetary_cost),
            ("compute_cost", self.compute_cost),
            ("delay_seconds", self.delay_seconds),
        ):
            _finite(value, name)
            if value < 0.0:
                raise ValueError(name + " cannot be negative")
        if self.token_cost < 0:
            raise ValueError("token_cost cannot be negative")
        if not self.outcomes:
            raise ValueError("computation must have at least one modeled outcome")
        probability = sum(item.probability for item in self.outcomes)
        if abs(probability - 1.0) > 1e-9:
            raise ValueError("computation outcome probabilities must sum to one")
        if self.kind == MetaActionKind.SIMULATE and self.evidence_producing:
            raise ValueError("simulation cannot be marked as external evidence")


@dataclass(frozen=True)
class MetaBudget:
    remaining_compute: float
    remaining_tokens: int
    remaining_money: float
    remaining_seconds: float

    def __post_init__(self) -> None:
        for name, value in (
            ("remaining_compute", self.remaining_compute),
            ("remaining_money", self.remaining_money),
            ("remaining_seconds", self.remaining_seconds),
        ):
            _finite(value, name)
            if value < 0.0:
                raise ValueError(name + " cannot be negative")
        if self.remaining_tokens < 0:
            raise ValueError("remaining_tokens cannot be negative")

    def can_afford(self, action: ComputationAction) -> bool:
        return (
            action.compute_cost <= self.remaining_compute
            and action.token_cost <= self.remaining_tokens
            and action.monetary_cost <= self.remaining_money
            and action.delay_seconds <= self.remaining_seconds
        )


@dataclass(frozen=True)
class MetaState:
    decisions: Tuple[DecisionAlternative, ...]
    belief_entropy: float
    current_risk: float
    budget: MetaBudget
    delay_cost_per_second: float = 0.0
    compute_utility_rate: float = 1.0
    money_utility_rate: float = 1.0
    token_utility_rate: float = 0.0
    information_utility_rate: float = 0.0
    risk_reduction_utility_rate: float = 0.0

    def __post_init__(self) -> None:
        if not self.decisions:
            raise ValueError("at least one external decision is required")
        if len({item.decision_id for item in self.decisions}) != len(self.decisions):
            raise ValueError("decision ids must be unique")
        _finite(self.belief_entropy, "belief_entropy")
        if self.belief_entropy < 0.0:
            raise ValueError("belief_entropy cannot be negative")
        _probability(self.current_risk, "current_risk")
        for name, value in (
            ("delay_cost_per_second", self.delay_cost_per_second),
            ("compute_utility_rate", self.compute_utility_rate),
            ("money_utility_rate", self.money_utility_rate),
            ("token_utility_rate", self.token_utility_rate),
            ("information_utility_rate", self.information_utility_rate),
            ("risk_reduction_utility_rate", self.risk_reduction_utility_rate),
        ):
            _finite(value, name)
            if value < 0.0:
                raise ValueError(name + " cannot be negative")

    @property
    def default_decision(self) -> DecisionAlternative:
        return max(self.decisions, key=lambda item: (item.expected_utility, item.decision_id))

    @property
    def default_utility(self) -> float:
        return self.default_decision.expected_utility


@dataclass(frozen=True)
class ComputationAssessment:
    action_id: str
    kind: MetaActionKind
    feasible: bool
    mandatory: bool
    expected_post_computation_utility: float
    expected_decision_improvement: float
    expected_information_gain: float
    expected_risk_reduction: float
    resource_cost: float
    delay_cost: float
    value_of_computation: float
    expected_regret_after: float
    information_ratio: float
    evidence_producing: bool
    fingerprint: str


@dataclass(frozen=True)
class MetaDecision:
    selected_action_id: Optional[str]
    selected_kind: MetaActionKind
    reason: SelectionReason
    assessment: Optional[ComputationAssessment]
    default_external_decision_id: str
    default_external_utility: float
    considered: Tuple[ComputationAssessment, ...]
    fingerprint: str


@dataclass(frozen=True)
class MetareasoningPolicy:
    minimum_value_of_computation: float = 0.0
    prefer_information_directed_within: float = 1e-9
    maximum_information_ratio: float = float("inf")
    force_mandatory_actions: bool = True
    stop_at_zero_time: bool = True

    def __post_init__(self) -> None:
        _finite(self.minimum_value_of_computation, "minimum_value_of_computation")
        if self.prefer_information_directed_within < 0.0:
            raise ValueError("prefer_information_directed_within cannot be negative")
        if self.maximum_information_ratio < 0.0:
            raise ValueError("maximum_information_ratio cannot be negative")


class RationalMetareasoner:
    """Auditable myopic value-of-computation controller."""

    def __init__(self, policy: Optional[MetareasoningPolicy] = None) -> None:
        self.policy = policy or MetareasoningPolicy()

    def assess(self, state: MetaState, action: ComputationAction) -> ComputationAssessment:
        feasible = state.budget.can_afford(action)
        expected_post = 0.0
        expected_entropy = 0.0
        expected_risk = 0.0
        expected_regret = 0.0
        current_ids = {item.decision_id for item in state.decisions}
        current_best = state.default_utility

        for outcome in action.outcomes:
            missing = current_ids - set(outcome.posterior_utilities)
            if missing:
                raise ValueError(
                    "computation outcome is missing posterior utilities for: "
                    + ",".join(sorted(missing))
                )
            best = max(outcome.posterior_utilities[item] for item in current_ids)
            expected_post += outcome.probability * best
            expected_entropy += outcome.probability * outcome.posterior_entropy
            expected_risk += outcome.probability * outcome.posterior_risk
            # Opportunity loss if the best posterior decision differs from the
            # currently preferred external action.
            default_after = outcome.posterior_utilities[state.default_decision.decision_id]
            expected_regret += outcome.probability * max(0.0, best - default_after)

        improvement = expected_post - current_best
        information_gain = max(0.0, state.belief_entropy - expected_entropy)
        risk_reduction = max(0.0, state.current_risk - expected_risk)
        resource_cost = (
            action.compute_cost * state.compute_utility_rate
            + action.monetary_cost * state.money_utility_rate
            + action.token_cost * state.token_utility_rate
        )
        delay_cost = action.delay_seconds * state.delay_cost_per_second
        value = (
            improvement
            + information_gain * state.information_utility_rate
            + risk_reduction * state.risk_reduction_utility_rate
            - resource_cost
            - delay_cost
        )
        if information_gain > 0.0:
            information_ratio = (expected_regret * expected_regret) / information_gain
        elif expected_regret == 0.0:
            information_ratio = 0.0
        else:
            information_ratio = float("inf")
        payload = {
            "action": action.action_id,
            "kind": action.kind.value,
            "feasible": feasible,
            "mandatory": action.mandatory,
            "post": _canonical_float(expected_post),
            "improvement": _canonical_float(improvement),
            "information_gain": _canonical_float(information_gain),
            "risk_reduction": _canonical_float(risk_reduction),
            "resource_cost": _canonical_float(resource_cost),
            "delay_cost": _canonical_float(delay_cost),
            "voc": _canonical_float(value),
            "regret": _canonical_float(expected_regret),
            "information_ratio": _canonical_float(information_ratio),
            "provenance": list(action.provenance_ids),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ComputationAssessment(
            action_id=action.action_id,
            kind=action.kind,
            feasible=feasible,
            mandatory=action.mandatory,
            expected_post_computation_utility=expected_post,
            expected_decision_improvement=improvement,
            expected_information_gain=information_gain,
            expected_risk_reduction=risk_reduction,
            resource_cost=resource_cost,
            delay_cost=delay_cost,
            value_of_computation=value,
            expected_regret_after=expected_regret,
            information_ratio=information_ratio,
            evidence_producing=action.evidence_producing,
            fingerprint=fingerprint,
        )

    def choose(
        self,
        state: MetaState,
        actions: Sequence[ComputationAction],
    ) -> MetaDecision:
        assessments = tuple(self.assess(state, action) for action in actions)
        by_id = {item.action_id: item for item in assessments}
        feasible_actions = [action for action in actions if by_id[action.action_id].feasible]

        if self.policy.force_mandatory_actions:
            mandatory = [action for action in feasible_actions if action.mandatory]
            if mandatory:
                chosen = max(
                    mandatory,
                    key=lambda action: (
                        by_id[action.action_id].value_of_computation,
                        -by_id[action.action_id].information_ratio,
                        action.action_id,
                    ),
                )
                return self._decision(
                    state,
                    by_id[chosen.action_id],
                    SelectionReason.MANDATORY_SAFETY,
                    assessments,
                )

        if self.policy.stop_at_zero_time and state.budget.remaining_seconds <= 0.0:
            return self._stop(state, assessments, SelectionReason.DEADLINE)
        if not feasible_actions:
            exhausted = any(
                (
                    action.compute_cost > state.budget.remaining_compute
                    or action.token_cost > state.budget.remaining_tokens
                    or action.monetary_cost > state.budget.remaining_money
                    or action.delay_seconds > state.budget.remaining_seconds
                )
                for action in actions
            )
            reason = SelectionReason.BUDGET_EXHAUSTED if exhausted else SelectionReason.NO_FEASIBLE_COMPUTATION
            return self._stop(state, assessments, reason)

        feasible = [by_id[action.action_id] for action in feasible_actions]
        best_value = max(item.value_of_computation for item in feasible)
        if best_value <= self.policy.minimum_value_of_computation:
            return self._stop(state, assessments, SelectionReason.NO_POSITIVE_COMPUTATION)

        near_best = [
            item
            for item in feasible
            if best_value - item.value_of_computation <= self.policy.prefer_information_directed_within
        ]
        information_candidates = [
            item
            for item in near_best
            if item.information_ratio <= self.policy.maximum_information_ratio
        ]
        if information_candidates:
            chosen = min(
                information_candidates,
                key=lambda item: (item.information_ratio, -item.value_of_computation, item.action_id),
            )
            reason = (
                SelectionReason.INFORMATION_DIRECTED
                if len(near_best) > 1
                else SelectionReason.POSITIVE_VALUE_OF_COMPUTATION
            )
        else:
            chosen = max(feasible, key=lambda item: (item.value_of_computation, item.action_id))
            reason = SelectionReason.POSITIVE_VALUE_OF_COMPUTATION
        return self._decision(state, chosen, reason, assessments)

    @staticmethod
    def _decision(
        state: MetaState,
        selected: ComputationAssessment,
        reason: SelectionReason,
        considered: Tuple[ComputationAssessment, ...],
    ) -> MetaDecision:
        payload = {
            "selected": selected.action_id,
            "kind": selected.kind.value,
            "reason": reason.value,
            "default": state.default_decision.decision_id,
            "considered": [item.fingerprint for item in considered],
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return MetaDecision(
            selected_action_id=selected.action_id,
            selected_kind=selected.kind,
            reason=reason,
            assessment=selected,
            default_external_decision_id=state.default_decision.decision_id,
            default_external_utility=state.default_utility,
            considered=considered,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _stop(
        state: MetaState,
        considered: Tuple[ComputationAssessment, ...],
        reason: SelectionReason,
    ) -> MetaDecision:
        payload = {
            "selected": None,
            "kind": MetaActionKind.STOP.value,
            "reason": reason.value,
            "default": state.default_decision.decision_id,
            "considered": [item.fingerprint for item in considered],
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return MetaDecision(
            selected_action_id=None,
            selected_kind=MetaActionKind.STOP,
            reason=reason,
            assessment=None,
            default_external_decision_id=state.default_decision.decision_id,
            default_external_utility=state.default_utility,
            considered=considered,
            fingerprint=fingerprint,
        )


def _finite(value: float, name: str) -> None:
    numeric = float(value)
    if math.isnan(numeric) or math.isinf(numeric):
        raise ValueError(name + " must be finite")


def _probability(value: float, name: str) -> None:
    _finite(value, name)
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(name + " must be in [0, 1]")


def _canonical_float(value: float) -> object:
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if math.isnan(value):
        raise ValueError("NaN cannot be fingerprinted")
    return round(float(value), 12)
