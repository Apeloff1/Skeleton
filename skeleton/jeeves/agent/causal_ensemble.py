"""Bayesian causal-model ensemble and robust epistemic control for Jeeves.

A single structural causal model can be internally coherent and still be wrong.
This module therefore treats *causal structure and mechanism choice themselves*
as uncertain.  It maintains a posterior over competing SCM hypotheses, updates
that posterior from verified observations, decomposes predictive uncertainty,
and chooses actions under both epistemic and downside risk.

The layer provides:

* Bayesian model averaging over competing causal structures/mechanisms;
* posterior updating from observational or interventional likelihoods;
* Bayesian surprise and effective model count diagnostics;
* epistemic/aleatoric uncertainty decomposition via model disagreement;
* robust action ranking by mean value, lower-confidence bound, minimax or CVaR;
* information-directed action scoring that trades regret against information;
* intervention design that targets disagreement between causal hypotheses;
* posterior collapse/drift alarms and immutable posterior snapshots.

Like the rest of Jeeves' evidence architecture, model predictions are planning
artifacts.  They never become factual evidence merely because the ensemble
agrees with itself.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .causal_epistemics import (
    ActionEvaluation,
    ActiveInferencePlanner,
    CategoricalDistribution,
    CausalEpistemicError,
    EpistemicAction,
    Preference,
    StructuralCausalModel,
    entropy_bits,
    js_divergence_bits,
    kl_divergence_bits,
)
from .types import (
    AgentContractError,
    RiskTier,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class CausalEnsembleError(RuntimeError):
    pass


class RobustObjective(str, Enum):
    MEAN = "mean"
    LOWER_CONFIDENCE = "lower_confidence"
    MINIMAX = "minimax"
    CVAR = "cvar"
    INFORMATION_DIRECTED = "information_directed"


@dataclass(frozen=True, slots=True)
class CausalModelHypothesis:
    hypothesis_id: str
    model: StructuralCausalModel
    log_prior_weight: float = 0.0
    reliability: float = 1.0
    provenance: tuple[str, ...] = ()
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_id", require_id("hypothesis_id", self.hypothesis_id))
        if not isinstance(self.model, StructuralCausalModel):
            raise AgentContractError("model must be StructuralCausalModel")
        log_weight = finite_number("log_prior_weight", self.log_prior_weight)
        object.__setattr__(self, "log_prior_weight", log_weight)
        object.__setattr__(self, "reliability", probability("reliability", self.reliability))
        object.__setattr__(self, "provenance", tuple(require_id("provenance", item) for item in self.provenance))
        object.__setattr__(self, "description", bounded_text("description", self.description, maximum=8192, allow_empty=True))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "hypothesis_id": self.hypothesis_id,
            "model": self.model.fingerprint,
            "log_prior_weight": self.log_prior_weight,
            "reliability": self.reliability,
            "provenance": self.provenance,
        })


@dataclass(frozen=True, slots=True)
class ModelPosterior:
    weights: Mapping[str, float]
    log_weights: Mapping[str, float]
    sequence: int
    updated_at: float
    evidence_count: int
    fingerprint: str

    def __post_init__(self) -> None:
        weights = {require_id("hypothesis_id", key): probability(f"weight[{key}]", value) for key, value in dict(self.weights).items()}
        if weights and abs(sum(weights.values()) - 1.0) > 1e-8:
            raise AgentContractError("posterior weights must sum to one")
        log_weights = {require_id("hypothesis_id", key): finite_number(f"log_weight[{key}]", value) for key, value in dict(self.log_weights).items()}
        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "log_weights", log_weights)
        object.__setattr__(self, "sequence", positive_int("sequence", self.sequence, maximum=1_000_000_000))
        updated = finite_number("updated_at", self.updated_at)
        if updated < 0:
            raise AgentContractError("updated_at must be non-negative")
        object.__setattr__(self, "updated_at", updated)
        if isinstance(self.evidence_count, bool) or not isinstance(self.evidence_count, int) or self.evidence_count < 0:
            raise AgentContractError("evidence_count must be non-negative integer")

    @property
    def entropy_bits(self) -> float:
        return entropy_bits(self.weights) if self.weights else 0.0

    @property
    def effective_model_count(self) -> float:
        return 2.0 ** self.entropy_bits if self.weights else 0.0

    @property
    def maximum_weight(self) -> float:
        return max(self.weights.values(), default=0.0)


@dataclass(frozen=True, slots=True)
class PosteriorUpdate:
    update_id: str
    prior_fingerprint: str
    posterior_fingerprint: str
    observation: Mapping[str, str]
    conditioning_evidence: Mapping[str, str]
    interventions: Mapping[str, str]
    likelihoods: Mapping[str, float]
    surprise_bits: float
    sequence: int
    at: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ModelPrediction:
    hypothesis_id: str
    posterior_weight: float
    distribution: CategoricalDistribution
    model_fingerprint: str


@dataclass(frozen=True, slots=True)
class EnsemblePrediction:
    variable_id: str
    mixture: CategoricalDistribution
    per_model: tuple[ModelPrediction, ...]
    total_entropy_bits: float
    expected_aleatoric_entropy_bits: float
    epistemic_information_bits: float
    maximum_pairwise_js_bits: float
    posterior_fingerprint: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ModelUtility:
    hypothesis_id: str
    weight: float
    expected_utility: float
    expected_free_energy: float
    information_gain_bits: float
    safety_penalty: float
    action_fingerprint: str


@dataclass(frozen=True, slots=True)
class RobustActionEvaluation:
    action_id: str
    objective: RobustObjective
    mean_utility: float
    standard_deviation: float
    minimum_utility: float
    cvar_utility: float
    lower_confidence_utility: float
    model_information_gain_bits: float
    information_ratio: float
    posterior_disagreement: float
    robust_score: float
    per_model: tuple[ModelUtility, ...]
    support_mass: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class EnsembleExperiment:
    experiment_id: str
    action: EpistemicAction
    observation_target: str
    expected_model_information_gain_bits: float
    expected_outcome_entropy_bits: float
    cost: float
    safety_penalty: float
    score: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PosteriorHealth:
    hypothesis_count: int
    posterior_entropy_bits: float
    effective_model_count: float
    maximum_weight: float
    collapsed: bool
    diffuse: bool
    stale: bool
    update_count: int
    reasons: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class EnsemblePolicy:
    likelihood_floor: float = 1e-8
    posterior_floor: float = 1e-8
    reliability_exponent: float = 1.0
    forgetting_rate: float = 0.0
    posterior_temperature: float = 1.0
    lower_confidence_k: float = 1.0
    cvar_alpha: float = 0.25
    model_information_weight: float = 0.30
    action_information_weight: float = 0.15
    cost_weight: float = 0.10
    safety_weight: float = 0.40
    collapse_threshold: float = 0.995
    diffuse_effective_fraction: float = 0.75
    stale_seconds: float = 3600.0

    def __post_init__(self) -> None:
        for name in ("likelihood_floor", "posterior_floor"):
            value = finite_number(name, getattr(self, name))
            if not 0 < value < 1:
                raise AgentContractError(f"{name} must be in (0, 1)")
            object.__setattr__(self, name, value)
        for name in ("reliability_exponent", "posterior_temperature", "lower_confidence_k", "model_information_weight", "action_information_weight", "cost_weight", "safety_weight", "stale_seconds"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        if self.posterior_temperature <= 0 or self.stale_seconds <= 0:
            raise AgentContractError("posterior_temperature and stale_seconds must be positive")
        for name in ("forgetting_rate", "cvar_alpha", "collapse_threshold", "diffuse_effective_fraction"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if self.cvar_alpha <= 0:
            raise AgentContractError("cvar_alpha must be > 0")


class BayesianCausalEnsemble:
    """Posterior over competing finite categorical structural causal models."""

    _RISK_PENALTY = {
        RiskTier.READ_ONLY: 0.00,
        RiskTier.REVERSIBLE: 0.04,
        RiskTier.MUTATING: 0.18,
        RiskTier.EXTERNAL: 0.35,
        RiskTier.HIGH_IMPACT: 0.80,
    }

    def __init__(
        self,
        hypotheses: Sequence[CausalModelHypothesis] = (),
        *,
        preferences: Sequence[Preference] = (),
        policy: EnsemblePolicy | None = None,
        clock: Callable[[], float] = time.time,
        history_limit: int = 4096,
    ) -> None:
        self.policy = policy or EnsemblePolicy()
        self.preferences = tuple(preferences)
        if any(not isinstance(item, Preference) for item in self.preferences):
            raise TypeError("preferences must contain Preference")
        self._clock = clock
        self._history_limit = positive_int("history_limit", history_limit, maximum=1_000_000)
        self._hypotheses: dict[str, CausalModelHypothesis] = {}
        self._log_weights: dict[str, float] = {}
        self._sequence = 0
        self._evidence_count = 0
        self._updates: list[PosteriorUpdate] = []
        self._snapshots: list[ModelPosterior] = []
        self._lock = threading.RLock()
        for hypothesis in hypotheses:
            self.add_hypothesis(hypothesis)

    def add_hypothesis(self, hypothesis: CausalModelHypothesis) -> None:
        if not isinstance(hypothesis, CausalModelHypothesis):
            raise TypeError("hypothesis must be CausalModelHypothesis")
        with self._lock:
            prior = self._hypotheses.get(hypothesis.hypothesis_id)
            if prior is not None and prior.fingerprint != hypothesis.fingerprint:
                raise CausalEnsembleError(f"hypothesis id collision: {hypothesis.hypothesis_id}")
            self._hypotheses[hypothesis.hypothesis_id] = hypothesis
            self._log_weights[hypothesis.hypothesis_id] = hypothesis.log_prior_weight
            self._assert_compatible_domains()
            self._sequence += 1
            self._snapshot_locked()

    def remove_hypothesis(self, hypothesis_id: str) -> bool:
        hypothesis_id = require_id("hypothesis_id", hypothesis_id)
        with self._lock:
            existed = self._hypotheses.pop(hypothesis_id, None) is not None
            self._log_weights.pop(hypothesis_id, None)
            if existed and self._hypotheses:
                self._sequence += 1
                self._snapshot_locked()
            return existed

    def hypotheses(self) -> tuple[CausalModelHypothesis, ...]:
        with self._lock:
            return tuple(self._hypotheses[key] for key in sorted(self._hypotheses))

    def _assert_compatible_domains(self) -> None:
        hypotheses = list(self._hypotheses.values())
        if len(hypotheses) < 2:
            return
        baseline = {variable.variable_id: variable.domain for variable in hypotheses[0].model.variables()}
        for hypothesis in hypotheses[1:]:
            candidate = {variable.variable_id: variable.domain for variable in hypothesis.model.variables()}
            shared = set(baseline) & set(candidate)
            mismatched = [key for key in shared if baseline[key] != candidate[key]]
            if mismatched:
                raise CausalEnsembleError(f"hypotheses disagree on variable domains: {mismatched}")

    def posterior(self) -> ModelPosterior:
        with self._lock:
            return self._posterior_locked()

    def _posterior_locked(self) -> ModelPosterior:
        if not self._hypotheses:
            raise CausalEnsembleError("ensemble has no hypotheses")
        log_weights = dict(self._log_weights)
        maximum = max(log_weights.values())
        temperature = self.policy.posterior_temperature
        raw = {
            key: math.exp((value - maximum) / temperature)
            for key, value in log_weights.items()
        }
        floor = self.policy.posterior_floor
        raw = {key: max(floor, value) for key, value in raw.items()}
        total = sum(raw.values())
        weights = {key: value / total for key, value in raw.items()}
        at = self._clock()
        fp = stable_fingerprint({
            "sequence": self._sequence,
            "weights": weights,
            "evidence_count": self._evidence_count,
        })
        return ModelPosterior(weights, log_weights, max(1, self._sequence), at, self._evidence_count, fp)

    def _snapshot_locked(self) -> ModelPosterior:
        posterior = self._posterior_locked()
        self._snapshots.append(posterior)
        if len(self._snapshots) > self._history_limit:
            del self._snapshots[: len(self._snapshots) - self._history_limit]
        return posterior

    def snapshots(self) -> tuple[ModelPosterior, ...]:
        with self._lock:
            return tuple(self._snapshots)

    def update(
        self,
        observation: Mapping[str, str],
        *,
        conditioning_evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
    ) -> PosteriorUpdate:
        observation = {require_id("observation variable", key): str(value) for key, value in dict(observation).items()}
        if not observation:
            raise CausalEnsembleError("posterior update requires an observation")
        conditioning = {require_id("conditioning variable", key): str(value) for key, value in dict(conditioning_evidence or {}).items()}
        interventions = {require_id("intervention variable", key): str(value) for key, value in dict(interventions or {}).items()}
        with self._lock:
            prior = self._posterior_locked()
            likelihoods: dict[str, float] = {}
            new_logs: dict[str, float] = {}
            forgetting = self.policy.forgetting_rate
            uniform_log = -math.log(max(1, len(self._hypotheses)))
            for hypothesis_id, hypothesis in self._hypotheses.items():
                likelihood = self._observation_likelihood(
                    hypothesis.model,
                    observation,
                    conditioning=conditioning,
                    interventions=interventions,
                )
                likelihood = max(self.policy.likelihood_floor, likelihood)
                likelihoods[hypothesis_id] = likelihood
                old = self._log_weights[hypothesis_id]
                retained = (1.0 - forgetting) * old + forgetting * uniform_log
                reliability = max(self.policy.likelihood_floor, hypothesis.reliability) ** self.policy.reliability_exponent
                new_logs[hypothesis_id] = retained + math.log(likelihood * reliability)
            self._log_weights = new_logs
            self._evidence_count += 1
            self._sequence += 1
            posterior = self._snapshot_locked()
            surprise = kl_divergence_bits(posterior.weights, prior.weights)
            update_id = stable_id("ensemble-update", {
                "sequence": self._sequence,
                "prior": prior.fingerprint,
                "posterior": posterior.fingerprint,
                "observation": observation,
                "conditioning": conditioning,
                "interventions": interventions,
            })
            update = PosteriorUpdate(
                update_id=update_id,
                prior_fingerprint=prior.fingerprint,
                posterior_fingerprint=posterior.fingerprint,
                observation=observation,
                conditioning_evidence=conditioning,
                interventions=interventions,
                likelihoods=likelihoods,
                surprise_bits=surprise,
                sequence=self._sequence,
                at=self._clock(),
                fingerprint=stable_fingerprint({
                    "update": update_id,
                    "likelihoods": likelihoods,
                    "surprise": surprise,
                }),
            )
            self._updates.append(update)
            if len(self._updates) > self._history_limit:
                del self._updates[: len(self._updates) - self._history_limit]
            return update

    @staticmethod
    def _observation_likelihood(
        model: StructuralCausalModel,
        observation: Mapping[str, str],
        *,
        conditioning: Mapping[str, str],
        interventions: Mapping[str, str],
    ) -> float:
        evidence = dict(conditioning)
        probability_mass = 1.0
        for variable_id, observed_value in sorted(observation.items()):
            distribution = model.marginal(
                variable_id,
                evidence=evidence,
                interventions=interventions,
            )
            p = distribution.probability_of(observed_value)
            probability_mass *= p
            evidence[variable_id] = observed_value
        return probability_mass

    def predict(
        self,
        variable_id: str,
        *,
        evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
    ) -> EnsemblePrediction:
        variable_id = require_id("variable_id", variable_id)
        posterior = self.posterior()
        per_model: list[ModelPrediction] = []
        support: tuple[str, ...] | None = None
        mixture_values: dict[str, float] = {}
        expected_entropy = 0.0
        for hypothesis in self.hypotheses():
            weight = posterior.weights[hypothesis.hypothesis_id]
            distribution = hypothesis.model.marginal(variable_id, evidence=evidence, interventions=interventions)
            if support is None:
                support = distribution.support
                mixture_values = {value: 0.0 for value in support}
            elif support != distribution.support:
                raise CausalEnsembleError("model prediction supports differ")
            for value in support:
                mixture_values[value] += weight * distribution.values[value]
            expected_entropy += weight * distribution.entropy_bits
            per_model.append(ModelPrediction(hypothesis.hypothesis_id, weight, distribution, hypothesis.model.fingerprint))
        if support is None:
            raise CausalEnsembleError("ensemble has no hypotheses")
        mixture = CategoricalDistribution(mixture_values, support)
        epistemic = max(0.0, mixture.entropy_bits - expected_entropy)
        maximum_js = 0.0
        for index, left in enumerate(per_model):
            for right in per_model[index + 1 :]:
                maximum_js = max(maximum_js, js_divergence_bits(left.distribution.values, right.distribution.values))
        fp = stable_fingerprint({
            "variable": variable_id,
            "posterior": posterior.fingerprint,
            "mixture": mixture.as_json(),
            "models": [(item.hypothesis_id, item.distribution.as_json()) for item in per_model],
        })
        return EnsemblePrediction(
            variable_id=variable_id,
            mixture=mixture,
            per_model=tuple(per_model),
            total_entropy_bits=mixture.entropy_bits,
            expected_aleatoric_entropy_bits=expected_entropy,
            epistemic_information_bits=epistemic,
            maximum_pairwise_js_bits=maximum_js,
            posterior_fingerprint=posterior.fingerprint,
            fingerprint=fp,
        )

    def evaluate_action(
        self,
        action: EpistemicAction,
        *,
        evidence: Mapping[str, str] | None = None,
        objective: RobustObjective = RobustObjective.LOWER_CONFIDENCE,
    ) -> RobustActionEvaluation:
        if not isinstance(action, EpistemicAction):
            raise TypeError("action must be EpistemicAction")
        if not isinstance(objective, RobustObjective):
            objective = RobustObjective(str(objective))
        posterior = self.posterior()
        values: list[ModelUtility] = []
        for hypothesis in self.hypotheses():
            planner = ActiveInferencePlanner(hypothesis.model, self.preferences)
            evaluation = planner.evaluate(action, current_evidence=evidence)
            values.append(ModelUtility(
                hypothesis_id=hypothesis.hypothesis_id,
                weight=posterior.weights[hypothesis.hypothesis_id],
                expected_utility=evaluation.expected_utility,
                expected_free_energy=evaluation.expected_free_energy,
                information_gain_bits=evaluation.information_gain_bits,
                safety_penalty=evaluation.safety_penalty,
                action_fingerprint=evaluation.fingerprint,
            ))
        mean = sum(item.weight * item.expected_utility for item in values)
        variance = sum(item.weight * (item.expected_utility - mean) ** 2 for item in values)
        std = math.sqrt(max(0.0, variance))
        minimum = min((item.expected_utility for item in values), default=mean)
        cvar = self._weighted_cvar(values, alpha=self.policy.cvar_alpha)
        lower = mean - self.policy.lower_confidence_k * std
        model_info = self._action_model_information_gain(action, evidence=evidence)
        disagreement = std + model_info
        maximum = max((item.expected_utility for item in values), default=mean)
        regret = max(0.0, maximum - mean)
        ratio = (regret * regret) / max(1e-9, model_info)
        if objective is RobustObjective.MEAN:
            robust = mean
        elif objective is RobustObjective.LOWER_CONFIDENCE:
            robust = lower
        elif objective is RobustObjective.MINIMAX:
            robust = minimum
        elif objective is RobustObjective.CVAR:
            robust = cvar
        else:
            robust = mean + self.policy.model_information_weight * model_info - ratio * 0.05
        robust -= self.policy.cost_weight * action.base_cost
        robust -= self.policy.safety_weight * self._RISK_PENALTY[action.risk]
        fp = stable_fingerprint({
            "action": action.action_id,
            "objective": objective.value,
            "posterior": posterior.fingerprint,
            "mean": mean,
            "std": std,
            "minimum": minimum,
            "cvar": cvar,
            "lower": lower,
            "model_info": model_info,
            "ratio": ratio,
            "robust": robust,
        })
        return RobustActionEvaluation(
            action_id=action.action_id,
            objective=objective,
            mean_utility=mean,
            standard_deviation=std,
            minimum_utility=minimum,
            cvar_utility=cvar,
            lower_confidence_utility=lower,
            model_information_gain_bits=model_info,
            information_ratio=ratio,
            posterior_disagreement=disagreement,
            robust_score=robust,
            per_model=tuple(values),
            support_mass=sum(item.weight for item in values),
            fingerprint=fp,
        )

    @staticmethod
    def _weighted_cvar(values: Sequence[ModelUtility], *, alpha: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values, key=lambda item: (item.expected_utility, item.hypothesis_id))
        target = max(1e-9, alpha)
        remaining = target
        total = 0.0
        used = 0.0
        for item in ordered:
            take = min(remaining, item.weight)
            if take <= 0:
                continue
            total += take * item.expected_utility
            used += take
            remaining -= take
            if remaining <= 1e-12:
                break
        return total / used if used > 0 else ordered[0].expected_utility

    def _action_model_information_gain(
        self,
        action: EpistemicAction,
        *,
        evidence: Mapping[str, str] | None,
    ) -> float:
        if not action.observation_targets:
            return 0.0
        posterior = self.posterior()
        total = 0.0
        for target in action.observation_targets:
            predictions = []
            mixture_values: dict[str, float] = {}
            support: tuple[str, ...] | None = None
            for hypothesis in self.hypotheses():
                distribution = hypothesis.model.marginal(target, evidence=evidence, interventions=action.interventions)
                weight = posterior.weights[hypothesis.hypothesis_id]
                predictions.append((weight, distribution))
                support = support or distribution.support
                for value in distribution.support:
                    mixture_values[value] = mixture_values.get(value, 0.0) + weight * distribution.values[value]
            if support is None:
                continue
            mixture = CategoricalDistribution(mixture_values, support)
            expected_entropy = sum(weight * distribution.entropy_bits for weight, distribution in predictions)
            total += max(0.0, mixture.entropy_bits - expected_entropy)
        return total

    def rank_actions(
        self,
        actions: Sequence[EpistemicAction],
        *,
        evidence: Mapping[str, str] | None = None,
        objective: RobustObjective = RobustObjective.LOWER_CONFIDENCE,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
    ) -> tuple[RobustActionEvaluation, ...]:
        risk_order = {
            RiskTier.READ_ONLY: 0,
            RiskTier.REVERSIBLE: 1,
            RiskTier.MUTATING: 2,
            RiskTier.EXTERNAL: 3,
            RiskTier.HIGH_IMPACT: 4,
        }
        values = [
            self.evaluate_action(action, evidence=evidence, objective=objective)
            for action in actions
            if risk_order[action.risk] <= risk_order[maximum_risk]
        ]
        values.sort(key=lambda item: (item.robust_score, item.mean_utility, item.action_id), reverse=True)
        return tuple(values)

    def design_experiments(
        self,
        actions: Sequence[EpistemicAction],
        *,
        evidence: Mapping[str, str] | None = None,
        maximum_risk: RiskTier = RiskTier.REVERSIBLE,
        limit: int = 8,
    ) -> tuple[EnsembleExperiment, ...]:
        limit = positive_int("limit", limit, maximum=1000)
        risk_order = {
            RiskTier.READ_ONLY: 0,
            RiskTier.REVERSIBLE: 1,
            RiskTier.MUTATING: 2,
            RiskTier.EXTERNAL: 3,
            RiskTier.HIGH_IMPACT: 4,
        }
        experiments: list[EnsembleExperiment] = []
        for action in actions:
            if risk_order[action.risk] > risk_order[maximum_risk]:
                continue
            for target in action.observation_targets:
                posterior = self.posterior()
                per_model: list[tuple[float, CategoricalDistribution]] = []
                mixture_values: dict[str, float] = {}
                support: tuple[str, ...] | None = None
                for hypothesis in self.hypotheses():
                    weight = posterior.weights[hypothesis.hypothesis_id]
                    distribution = hypothesis.model.marginal(target, evidence=evidence, interventions=action.interventions)
                    per_model.append((weight, distribution))
                    support = support or distribution.support
                    for value in distribution.support:
                        mixture_values[value] = mixture_values.get(value, 0.0) + weight * distribution.values[value]
                if support is None:
                    continue
                mixture = CategoricalDistribution(mixture_values, support)
                expected_entropy = sum(weight * distribution.entropy_bits for weight, distribution in per_model)
                model_information = max(0.0, mixture.entropy_bits - expected_entropy)
                cost = action.base_cost
                safety = self._RISK_PENALTY[action.risk] + (0.0 if action.reversible else 0.25)
                score = model_information - self.policy.cost_weight * cost - self.policy.safety_weight * safety
                experiment_id = stable_id("ensemble-experiment", {
                    "action": action.action_id,
                    "target": target,
                    "posterior": posterior.fingerprint,
                })
                experiments.append(EnsembleExperiment(
                    experiment_id=experiment_id,
                    action=action,
                    observation_target=target,
                    expected_model_information_gain_bits=model_information,
                    expected_outcome_entropy_bits=mixture.entropy_bits,
                    cost=cost,
                    safety_penalty=safety,
                    score=score,
                    fingerprint=stable_fingerprint({
                        "experiment": experiment_id,
                        "model_info": model_information,
                        "outcome_entropy": mixture.entropy_bits,
                        "score": score,
                    }),
                ))
        experiments.sort(key=lambda item: (item.score, item.expected_model_information_gain_bits, item.experiment_id), reverse=True)
        return tuple(experiments[:limit])

    def health(self) -> PosteriorHealth:
        posterior = self.posterior()
        count = len(posterior.weights)
        effective_fraction = posterior.effective_model_count / max(1, count)
        collapsed = count > 1 and posterior.maximum_weight >= self.policy.collapse_threshold
        diffuse = count > 1 and effective_fraction >= self.policy.diffuse_effective_fraction
        stale = self._clock() - posterior.updated_at >= self.policy.stale_seconds
        reasons: list[str] = []
        if collapsed:
            reasons.append("posterior collapsed onto one causal hypothesis")
        if diffuse:
            reasons.append("posterior remains structurally diffuse")
        if stale:
            reasons.append("posterior has not been updated recently")
        if not reasons:
            reasons.append("posterior health within configured bounds")
        fp = stable_fingerprint({
            "posterior": posterior.fingerprint,
            "collapsed": collapsed,
            "diffuse": diffuse,
            "stale": stale,
            "updates": len(self._updates),
        })
        return PosteriorHealth(
            hypothesis_count=count,
            posterior_entropy_bits=posterior.entropy_bits,
            effective_model_count=posterior.effective_model_count,
            maximum_weight=posterior.maximum_weight,
            collapsed=collapsed,
            diffuse=diffuse,
            stale=stale,
            update_count=len(self._updates),
            reasons=tuple(reasons),
            fingerprint=fp,
        )

    def updates(self) -> tuple[PosteriorUpdate, ...]:
        with self._lock:
            return tuple(self._updates)

    @property
    def fingerprint(self) -> str:
        posterior = self.posterior()
        return stable_fingerprint({
            "hypotheses": [(item.hypothesis_id, item.fingerprint) for item in self.hypotheses()],
            "posterior": posterior.fingerprint,
            "updates": [item.fingerprint for item in self.updates()],
        })

    def summary(self) -> dict[str, Any]:
        posterior = self.posterior()
        health = self.health()
        return {
            "hypotheses": len(self._hypotheses),
            "weights": dict(sorted(posterior.weights.items())),
            "posterior_entropy_bits": posterior.entropy_bits,
            "effective_model_count": posterior.effective_model_count,
            "maximum_weight": posterior.maximum_weight,
            "updates": len(self._updates),
            "collapsed": health.collapsed,
            "diffuse": health.diffuse,
            "stale": health.stale,
            "fingerprint": self.fingerprint,
        }
