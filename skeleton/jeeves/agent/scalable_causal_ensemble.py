"""Factorized Bayesian causal ensemble for high-dimensional Jeeves control.

This module preserves the posterior/model-averaging contract from
``causal_ensemble`` but routes likelihoods and action predictions through sparse
variable elimination.  It is the production path for supervisor/control-plane
models where exact full-joint enumeration is intentionally infeasible.

Model uncertainty and within-model stochasticity remain separate:

* variable elimination computes exact marginals inside each causal hypothesis;
* Bayesian weights represent uncertainty *between* hypotheses;
* model-information gain measures how informative an action's observations are
  about which causal hypothesis is correct;
* robust objectives consume the resulting distribution of model utilities.
"""

from __future__ import annotations

import math
import threading
from typing import Any, Mapping, Sequence

from .causal_ensemble import (
    BayesianCausalEnsemble,
    EnsembleExperiment,
    EnsemblePrediction,
    ModelPrediction,
    ModelUtility,
    RobustActionEvaluation,
    RobustObjective,
)
from .causal_epistemics import (
    CategoricalDistribution,
    EpistemicAction,
    kl_divergence_bits,
    js_divergence_bits,
)
from .causal_inference import InferencePolicy, VariableEliminationEngine
from .types import RiskTier, require_id, stable_fingerprint, stable_id


class ScalableEnsembleError(RuntimeError):
    pass


class FactorizedBayesianCausalEnsemble(BayesianCausalEnsemble):
    """Bayesian causal ensemble backed by sparse exact variable elimination."""

    def __init__(
        self,
        *args: Any,
        inference_policy: InferencePolicy | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.inference_policy = inference_policy or InferencePolicy(
            maximum_sparse_entries=300_000,
            maximum_dense_capacity=8_000_000,
            ancestor_pruning=True,
        )
        self._engine_cache: dict[str, VariableEliminationEngine] = {}
        self._engine_lock = threading.RLock()

    def _engine(self, hypothesis_id: str) -> VariableEliminationEngine:
        hypothesis_id = require_id("hypothesis_id", hypothesis_id)
        hypothesis = next(
            (item for item in self.hypotheses() if item.hypothesis_id == hypothesis_id),
            None,
        )
        if hypothesis is None:
            raise ScalableEnsembleError(f"unknown hypothesis: {hypothesis_id}")
        cache_key = f"{hypothesis_id}:{hypothesis.model.fingerprint}"
        with self._engine_lock:
            engine = self._engine_cache.get(cache_key)
            if engine is None:
                engine = VariableEliminationEngine(
                    hypothesis.model,
                    policy=self.inference_policy,
                )
                # Drop stale revisions of the same hypothesis id.
                prefix = f"{hypothesis_id}:"
                self._engine_cache = {
                    key: value
                    for key, value in self._engine_cache.items()
                    if not key.startswith(prefix)
                }
                self._engine_cache[cache_key] = engine
            return engine

    def add_hypothesis(self, hypothesis: Any) -> None:
        super().add_hypothesis(hypothesis)
        if hasattr(self, "_engine_lock"):
            with self._engine_lock:
                self._engine_cache = {
                    key: value
                    for key, value in self._engine_cache.items()
                    if not key.startswith(f"{hypothesis.hypothesis_id}:")
                }

    def remove_hypothesis(self, hypothesis_id: str) -> bool:
        removed = super().remove_hypothesis(hypothesis_id)
        if removed:
            with self._engine_lock:
                self._engine_cache = {
                    key: value
                    for key, value in self._engine_cache.items()
                    if not key.startswith(f"{hypothesis_id}:")
                }
        return removed

    def _observation_likelihood(
        self,
        model: Any,
        observation: Mapping[str, str],
        *,
        conditioning: Mapping[str, str],
        interventions: Mapping[str, str],
    ) -> float:
        hypothesis = next(
            (item for item in self.hypotheses() if item.model is model),
            None,
        )
        if hypothesis is None:
            # Fingerprint fallback supports cloned/deserialized model identity.
            hypothesis = next(
                (
                    item
                    for item in self.hypotheses()
                    if item.model.fingerprint == model.fingerprint
                ),
                None,
            )
        if hypothesis is None:
            raise ScalableEnsembleError("likelihood model is not an ensemble hypothesis")
        engine = self._engine(hypothesis.hypothesis_id)
        combined = dict(conditioning)
        combined.update(observation)
        joint = engine.evidence_likelihood(combined, interventions=interventions)
        if not conditioning:
            return joint
        denominator = engine.evidence_likelihood(conditioning, interventions=interventions)
        if denominator <= 0:
            return 0.0
        return max(0.0, min(1.0, joint / denominator))

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
            distribution = self._engine(hypothesis.hypothesis_id).marginal(
                variable_id,
                evidence=evidence,
                interventions=interventions,
            )
            weight = posterior.weights[hypothesis.hypothesis_id]
            if support is None:
                support = distribution.support
                mixture_values = {value: 0.0 for value in support}
            elif support != distribution.support:
                raise ScalableEnsembleError("hypotheses disagree on prediction support")
            for value in support:
                mixture_values[value] += weight * distribution.values[value]
            expected_entropy += weight * distribution.entropy_bits
            per_model.append(
                ModelPrediction(
                    hypothesis.hypothesis_id,
                    weight,
                    distribution,
                    hypothesis.model.fingerprint,
                )
            )
        if support is None:
            raise ScalableEnsembleError("ensemble contains no hypotheses")
        mixture = CategoricalDistribution(mixture_values, support)
        epistemic = max(0.0, mixture.entropy_bits - expected_entropy)
        maximum_js = 0.0
        for index, left in enumerate(per_model):
            for right in per_model[index + 1 :]:
                maximum_js = max(
                    maximum_js,
                    js_divergence_bits(
                        left.distribution.values,
                        right.distribution.values,
                    ),
                )
        fp = stable_fingerprint(
            {
                "variable": variable_id,
                "posterior": posterior.fingerprint,
                "mixture": mixture.as_json(),
                "models": [
                    (item.hypothesis_id, item.distribution.as_json())
                    for item in per_model
                ],
                "backend": "variable-elimination",
            }
        )
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
        model_info = self._action_model_information_gain(action, evidence=evidence)
        values: list[ModelUtility] = []
        for hypothesis in self.hypotheses():
            engine = self._engine(hypothesis.hypothesis_id)
            pragmatic = 0.0
            for preference in self.preferences:
                distribution = engine.marginal(
                    preference.variable_id,
                    evidence=evidence,
                    interventions=action.interventions,
                )
                pragmatic += preference.weight * kl_divergence_bits(
                    distribution.values,
                    preference.desired.values,
                )
            ambiguity = 0.0
            for target in action.observation_targets:
                ambiguity += engine.marginal(
                    target,
                    evidence=evidence,
                    interventions=action.interventions,
                ).entropy_bits
            intervention_cost = action.base_cost
            for variable_id in action.interventions:
                intervention_cost += hypothesis.model.variable(variable_id).intervention_cost
            safety = (
                self._RISK_PENALTY[action.risk]
                + action.blast_radius * 0.5
                + (0.0 if action.reversible else 0.35)
            )
            # Known-model epistemic value is deliberately zero here.  Structural
            # uncertainty is accounted for once, at ensemble level, by model_info.
            efe = (
                pragmatic
                + 0.25 * ambiguity
                + self.policy.cost_weight * intervention_cost
                + self.policy.safety_weight * safety
            )
            utility = -efe
            values.append(
                ModelUtility(
                    hypothesis_id=hypothesis.hypothesis_id,
                    weight=posterior.weights[hypothesis.hypothesis_id],
                    expected_utility=utility,
                    expected_free_energy=efe,
                    information_gain_bits=0.0,
                    safety_penalty=safety,
                    action_fingerprint=stable_fingerprint(
                        {
                            "hypothesis": hypothesis.hypothesis_id,
                            "action": action.action_id,
                            "pragmatic": pragmatic,
                            "ambiguity": ambiguity,
                            "cost": intervention_cost,
                            "safety": safety,
                        }
                    ),
                )
            )
        mean = sum(item.weight * item.expected_utility for item in values)
        variance = sum(
            item.weight * (item.expected_utility - mean) ** 2 for item in values
        )
        std = math.sqrt(max(0.0, variance))
        minimum = min((item.expected_utility for item in values), default=mean)
        cvar = self._weighted_cvar(values, alpha=self.policy.cvar_alpha)
        lower = mean - self.policy.lower_confidence_k * std
        maximum = max((item.expected_utility for item in values), default=mean)
        regret = max(0.0, maximum - mean)
        information_ratio = (regret * regret) / max(1e-9, model_info)
        if objective is RobustObjective.MEAN:
            score = mean
        elif objective is RobustObjective.LOWER_CONFIDENCE:
            score = lower
        elif objective is RobustObjective.MINIMAX:
            score = minimum
        elif objective is RobustObjective.CVAR:
            score = cvar
        else:
            score = (
                mean
                + self.policy.model_information_weight * model_info
                - 0.05 * information_ratio
            )
        score -= self.policy.cost_weight * action.base_cost
        score -= self.policy.safety_weight * self._RISK_PENALTY[action.risk]
        fp = stable_fingerprint(
            {
                "action": action.action_id,
                "objective": objective.value,
                "posterior": posterior.fingerprint,
                "mean": mean,
                "std": std,
                "minimum": minimum,
                "cvar": cvar,
                "lower": lower,
                "model_info": model_info,
                "information_ratio": information_ratio,
                "score": score,
                "backend": "variable-elimination",
            }
        )
        return RobustActionEvaluation(
            action_id=action.action_id,
            objective=objective,
            mean_utility=mean,
            standard_deviation=std,
            minimum_utility=minimum,
            cvar_utility=cvar,
            lower_confidence_utility=lower,
            model_information_gain_bits=model_info,
            information_ratio=information_ratio,
            posterior_disagreement=std + model_info,
            robust_score=score,
            per_model=tuple(values),
            support_mass=sum(item.weight for item in values),
            fingerprint=fp,
        )

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
            predictions: list[tuple[float, CategoricalDistribution]] = []
            mixture_values: dict[str, float] = {}
            support: tuple[str, ...] | None = None
            for hypothesis in self.hypotheses():
                distribution = self._engine(hypothesis.hypothesis_id).marginal(
                    target,
                    evidence=evidence,
                    interventions=action.interventions,
                )
                weight = posterior.weights[hypothesis.hypothesis_id]
                predictions.append((weight, distribution))
                support = support or distribution.support
                for value in distribution.support:
                    mixture_values[value] = (
                        mixture_values.get(value, 0.0)
                        + weight * distribution.values[value]
                    )
            if support is None:
                continue
            mixture = CategoricalDistribution(mixture_values, support)
            expected_entropy = sum(
                weight * distribution.entropy_bits
                for weight, distribution in predictions
            )
            total += max(0.0, mixture.entropy_bits - expected_entropy)
        return total

    def design_experiments(
        self,
        actions: Sequence[EpistemicAction],
        *,
        evidence: Mapping[str, str] | None = None,
        maximum_risk: RiskTier = RiskTier.REVERSIBLE,
        limit: int = 8,
    ) -> tuple[EnsembleExperiment, ...]:
        risk_order = {
            RiskTier.READ_ONLY: 0,
            RiskTier.REVERSIBLE: 1,
            RiskTier.MUTATING: 2,
            RiskTier.EXTERNAL: 3,
            RiskTier.HIGH_IMPACT: 4,
        }
        candidates: list[EnsembleExperiment] = []
        for action in actions:
            if risk_order[action.risk] > risk_order[maximum_risk]:
                continue
            for target in action.observation_targets:
                info = self._target_model_information_gain(
                    action,
                    target,
                    evidence=evidence,
                )
                prediction = self._predict_under_action(
                    target,
                    action,
                    evidence=evidence,
                )
                safety = self._RISK_PENALTY[action.risk] + (
                    0.0 if action.reversible else 0.25
                )
                score = (
                    info
                    - self.policy.cost_weight * action.base_cost
                    - self.policy.safety_weight * safety
                )
                experiment_id = stable_id(
                    "factor-ensemble-experiment",
                    {
                        "action": action.action_id,
                        "target": target,
                        "posterior": self.posterior().fingerprint,
                    },
                )
                candidates.append(
                    EnsembleExperiment(
                        experiment_id=experiment_id,
                        action=action,
                        observation_target=target,
                        expected_model_information_gain_bits=info,
                        expected_outcome_entropy_bits=prediction.total_entropy_bits,
                        cost=action.base_cost,
                        safety_penalty=safety,
                        score=score,
                        fingerprint=stable_fingerprint(
                            {
                                "experiment": experiment_id,
                                "info": info,
                                "entropy": prediction.total_entropy_bits,
                                "score": score,
                            }
                        ),
                    )
                )
        candidates.sort(
            key=lambda item: (
                item.score,
                item.expected_model_information_gain_bits,
                item.experiment_id,
            ),
            reverse=True,
        )
        return tuple(candidates[:limit])

    def _target_model_information_gain(
        self,
        action: EpistemicAction,
        target: str,
        *,
        evidence: Mapping[str, str] | None,
    ) -> float:
        posterior = self.posterior()
        mixture_values: dict[str, float] = {}
        support: tuple[str, ...] | None = None
        expected_entropy = 0.0
        for hypothesis in self.hypotheses():
            distribution = self._engine(hypothesis.hypothesis_id).marginal(
                target,
                evidence=evidence,
                interventions=action.interventions,
            )
            weight = posterior.weights[hypothesis.hypothesis_id]
            support = support or distribution.support
            for value in distribution.support:
                mixture_values[value] = (
                    mixture_values.get(value, 0.0)
                    + weight * distribution.values[value]
                )
            expected_entropy += weight * distribution.entropy_bits
        if support is None:
            return 0.0
        mixture = CategoricalDistribution(mixture_values, support)
        return max(0.0, mixture.entropy_bits - expected_entropy)

    def _predict_under_action(
        self,
        target: str,
        action: EpistemicAction,
        *,
        evidence: Mapping[str, str] | None,
    ) -> EnsemblePrediction:
        return self.predict(
            target,
            evidence=evidence,
            interventions=action.interventions,
        )


class ScalableCausalEnsembleFactory:
    """Small factory used by control planes to ensure one inference policy."""

    def __init__(self, inference_policy: InferencePolicy | None = None) -> None:
        self.inference_policy = inference_policy or InferencePolicy()

    def create(self, *args: Any, **kwargs: Any) -> FactorizedBayesianCausalEnsemble:
        return FactorizedBayesianCausalEnsemble(
            *args,
            inference_policy=self.inference_policy,
            **kwargs,
        )
