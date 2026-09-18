"""Falsification tournaments for Jeeves epistemic research.

A language model can generate plausible explanations cheaply; the hard system
problem is deciding which explanation deserves belief and which observation is
most useful next.  This module keeps that decision in deterministic host code.

Hypotheses must expose explicit predictive distributions for named probes.
Jeeves then chooses observations by expected information gain, penalizes cost
and risk, and updates posterior weights only after an outcome is observed.
Unsupported narrative quality has no direct authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

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


_EPS = 1e-12
_RISK_PENALTY = {
    RiskTier.READ_ONLY: 0.0,
    RiskTier.REVERSIBLE: 0.08,
    RiskTier.MUTATING: 0.30,
    RiskTier.EXTERNAL: 0.55,
    RiskTier.HIGH_IMPACT: 1.0,
}


def _normalize(values: Mapping[str, float], *, name: str) -> dict[str, float]:
    if not values:
        raise AgentContractError(f"{name} cannot be empty")
    cleaned: dict[str, float] = {}
    for key, value in values.items():
        key = require_id(f"{name}_key", key)
        cleaned[key] = probability(f"{name}[{key}]", value)
    total = sum(cleaned.values())
    if total <= 0:
        raise AgentContractError(f"{name} must contain positive probability mass")
    return {key: value / total for key, value in sorted(cleaned.items())}


def _entropy_bits(values: Mapping[str, float]) -> float:
    return -sum(p * math.log2(p) for p in values.values() if p > 0)


@dataclass(frozen=True, slots=True)
class HypothesisPrediction:
    probe_id: str
    distribution: Mapping[str, float]
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_id", require_id("probe_id", self.probe_id))
        object.__setattr__(
            self,
            "distribution",
            _normalize(self.distribution, name="prediction"),
        )
        object.__setattr__(
            self,
            "rationale",
            bounded_text("rationale", self.rationale, maximum=4096, allow_empty=True),
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "probe_id": self.probe_id,
                "distribution": self.distribution,
                "rationale": self.rationale,
            }
        )


@dataclass(frozen=True, slots=True)
class CompetingHypothesis:
    hypothesis_id: str
    statement: str
    prior_weight: float
    predictions: tuple[HypothesisPrediction, ...]
    assumptions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hypothesis_id",
            require_id("hypothesis_id", self.hypothesis_id),
        )
        object.__setattr__(
            self,
            "statement",
            bounded_text("statement", self.statement, maximum=8192),
        )
        object.__setattr__(self, "prior_weight", probability("prior_weight", self.prior_weight))
        predictions = tuple(self.predictions)
        if not predictions:
            raise AgentContractError("hypothesis requires at least one prediction")
        if any(not isinstance(item, HypothesisPrediction) for item in predictions):
            raise AgentContractError("predictions must contain HypothesisPrediction")
        ids = [item.probe_id for item in predictions]
        if len(ids) != len(set(ids)):
            raise AgentContractError("hypothesis has duplicate predictions for a probe")
        object.__setattr__(
            self,
            "predictions",
            tuple(sorted(predictions, key=lambda item: item.probe_id)),
        )
        object.__setattr__(
            self,
            "assumptions",
            tuple(
                bounded_text("assumption", item, maximum=2048)
                for item in self.assumptions
            ),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            tuple(sorted(set(require_id("evidence_ref", item) for item in self.evidence_refs))),
        )
        object.__setattr__(
            self,
            "provenance",
            tuple(sorted(set(require_id("provenance", item) for item in self.provenance))),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    def prediction(self, probe_id: str) -> HypothesisPrediction | None:
        probe_id = require_id("probe_id", probe_id)
        for item in self.predictions:
            if item.probe_id == probe_id:
                return item
        return None

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "hypothesis_id": self.hypothesis_id,
                "statement": self.statement,
                "prior_weight": self.prior_weight,
                "predictions": [item.fingerprint for item in self.predictions],
                "assumptions": self.assumptions,
                "evidence_refs": self.evidence_refs,
                "provenance": self.provenance,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class DiscriminatingProbe:
    probe_id: str
    question: str
    outcome_support: tuple[str, ...]
    expected_cost: float = 0.1
    risk: RiskTier = RiskTier.READ_ONLY
    reversible: bool = True
    evidence_only: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_id", require_id("probe_id", self.probe_id))
        object.__setattr__(
            self,
            "question",
            bounded_text("question", self.question, maximum=8192),
        )
        support = tuple(require_id("outcome", item) for item in self.outcome_support)
        if len(support) < 2 or len(support) != len(set(support)):
            raise AgentContractError("probe outcome support must contain at least two unique outcomes")
        object.__setattr__(self, "outcome_support", support)
        cost = finite_number("expected_cost", self.expected_cost)
        if cost < 0:
            raise AgentContractError("expected_cost must be non-negative")
        object.__setattr__(self, "expected_cost", cost)
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "probe_id": self.probe_id,
                "question": self.question,
                "outcome_support": self.outcome_support,
                "expected_cost": self.expected_cost,
                "risk": self.risk.value,
                "reversible": self.reversible,
                "evidence_only": self.evidence_only,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class TournamentPolicy:
    information_gain_weight: float = 1.0
    pairwise_separation_weight: float = 0.35
    decision_value_weight: float = 0.75
    cost_weight: float = 0.20
    risk_weight: float = 0.70
    missing_prediction_penalty: float = 0.40
    likelihood_floor: float = 1e-6
    maximum_probes: int = 32

    def __post_init__(self) -> None:
        for name in (
            "information_gain_weight",
            "pairwise_separation_weight",
            "decision_value_weight",
            "cost_weight",
            "risk_weight",
            "missing_prediction_penalty",
        ):
            value = finite_number(name, getattr(self, name))
            if value < 0 or value > 100:
                raise AgentContractError(f"{name} must be in [0, 100]")
            object.__setattr__(self, name, value)
        floor = finite_number("likelihood_floor", self.likelihood_floor)
        if not 0 < floor <= 0.1:
            raise AgentContractError("likelihood_floor must be in (0, 0.1]")
        object.__setattr__(self, "likelihood_floor", floor)
        object.__setattr__(
            self,
            "maximum_probes",
            positive_int("maximum_probes", self.maximum_probes, maximum=10000),
        )


@dataclass(frozen=True, slots=True)
class ProbeEvaluation:
    probe_id: str
    expected_information_gain_bits: float
    expected_posterior_entropy_bits: float
    pairwise_separation: float
    prediction_coverage: float
    expected_decision_value: float
    expected_cost: float
    risk_penalty: float
    score: float
    outcome_mixture: Mapping[str, float]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class TournamentRound:
    tournament_id: str
    posterior: Mapping[str, float]
    evaluations: tuple[ProbeEvaluation, ...]
    selected_probe_id: str | None
    posterior_entropy_bits: float
    effective_hypotheses: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class TournamentUpdate:
    tournament_id: str
    probe_id: str
    observed_outcome: str
    prior: Mapping[str, float]
    posterior: Mapping[str, float]
    likelihoods: Mapping[str, float]
    predictive_probability: float
    surprise_bits: float
    information_gain_bits: float
    winner_id: str
    winner_probability: float
    falsified_ids: tuple[str, ...]
    falsification_threshold: float
    fingerprint: str


class HypothesisTournament:
    """Host-side Bayesian tournament over explicit predictive hypotheses."""

    def __init__(
        self,
        hypotheses: Sequence[CompetingHypothesis],
        probes: Sequence[DiscriminatingProbe],
        *,
        policy: TournamentPolicy | None = None,
        decision_impact: float = 1.0,
    ) -> None:
        self.policy = policy or TournamentPolicy()
        self.decision_impact = probability("decision_impact", decision_impact)
        self._hypotheses = tuple(sorted(hypotheses, key=lambda item: item.hypothesis_id))
        self._probes = tuple(sorted(probes, key=lambda item: item.probe_id))
        if len(self._hypotheses) < 2:
            raise AgentContractError("tournament requires at least two hypotheses")
        if len({item.hypothesis_id for item in self._hypotheses}) != len(self._hypotheses):
            raise AgentContractError("duplicate hypothesis_id")
        if not self._probes:
            raise AgentContractError("tournament requires at least one probe")
        if len({item.probe_id for item in self._probes}) != len(self._probes):
            raise AgentContractError("duplicate probe_id")
        priors = {item.hypothesis_id: item.prior_weight for item in self._hypotheses}
        self._posterior = _normalize(priors, name="hypothesis_prior")
        self.tournament_id = stable_id(
            "hypothesis-tournament",
            {
                "hypotheses": [item.fingerprint for item in self._hypotheses],
                "probes": [item.fingerprint for item in self._probes],
                "decision_impact": self.decision_impact,
            },
            length=30,
        )
        self._history: list[TournamentUpdate] = []

    @property
    def posterior(self) -> Mapping[str, float]:
        return dict(self._posterior)

    @property
    def posterior_entropy_bits(self) -> float:
        return _entropy_bits(self._posterior)

    @property
    def effective_hypotheses(self) -> float:
        return 2.0 ** self.posterior_entropy_bits

    def round(self) -> TournamentRound:
        evaluations = [self.evaluate_probe(probe) for probe in self._probes]
        evaluations.sort(
            key=lambda item: (
                item.score,
                item.expected_information_gain_bits,
                item.pairwise_separation,
                item.probe_id,
            ),
            reverse=True,
        )
        evaluations = evaluations[: self.policy.maximum_probes]
        selected = evaluations[0].probe_id if evaluations else None
        payload = {
            "tournament": self.tournament_id,
            "posterior": self._posterior,
            "evaluations": [item.fingerprint for item in evaluations],
            "selected": selected,
        }
        return TournamentRound(
            tournament_id=self.tournament_id,
            posterior=dict(self._posterior),
            evaluations=tuple(evaluations),
            selected_probe_id=selected,
            posterior_entropy_bits=self.posterior_entropy_bits,
            effective_hypotheses=self.effective_hypotheses,
            fingerprint=stable_fingerprint(payload),
        )

    def evaluate_probe(self, probe: DiscriminatingProbe) -> ProbeEvaluation:
        if not isinstance(probe, DiscriminatingProbe):
            raise TypeError("probe must be DiscriminatingProbe")
        support = probe.outcome_support
        predicted: dict[str, dict[str, float]] = {}
        covered_weight = 0.0
        mixture = {outcome: 0.0 for outcome in support}
        for hypothesis in self._hypotheses:
            weight = self._posterior[hypothesis.hypothesis_id]
            prediction = hypothesis.prediction(probe.probe_id)
            if prediction is None:
                continue
            if set(prediction.distribution) != set(support):
                raise AgentContractError(
                    f"prediction support mismatch for {hypothesis.hypothesis_id}/{probe.probe_id}"
                )
            dist = dict(prediction.distribution)
            predicted[hypothesis.hypothesis_id] = dist
            covered_weight += weight
            for outcome in support:
                mixture[outcome] += weight * dist[outcome]
        if covered_weight <= 0:
            mixture = {outcome: 1.0 / len(support) for outcome in support}
        else:
            mixture = _normalize(mixture, name="outcome_mixture")

        current_entropy = self.posterior_entropy_bits
        expected_entropy = 0.0
        for outcome in support:
            outcome_probability = mixture[outcome]
            if outcome_probability <= 0:
                continue
            posterior_for_outcome: dict[str, float] = {}
            for hypothesis in self._hypotheses:
                hid = hypothesis.hypothesis_id
                dist = predicted.get(hid)
                likelihood = (
                    dist[outcome]
                    if dist is not None
                    else self.policy.likelihood_floor
                )
                posterior_for_outcome[hid] = self._posterior[hid] * max(
                    self.policy.likelihood_floor,
                    likelihood,
                )
            posterior_for_outcome = _normalize(
                posterior_for_outcome,
                name="posterior_for_outcome",
            )
            expected_entropy += outcome_probability * _entropy_bits(posterior_for_outcome)
        information_gain = max(0.0, current_entropy - expected_entropy)

        pairwise = 0.0
        pair_weight = 0.0
        for left_index, left in enumerate(self._hypotheses):
            left_dist = predicted.get(left.hypothesis_id)
            if left_dist is None:
                continue
            for right in self._hypotheses[left_index + 1 :]:
                right_dist = predicted.get(right.hypothesis_id)
                if right_dist is None:
                    continue
                weight = self._posterior[left.hypothesis_id] * self._posterior[right.hypothesis_id]
                separation = 0.5 * sum(
                    abs(left_dist[outcome] - right_dist[outcome])
                    for outcome in support
                )
                pairwise += weight * separation
                pair_weight += weight
        pairwise_separation = pairwise / pair_weight if pair_weight > 0 else 0.0
        coverage = min(1.0, covered_weight)
        expected_value = self.decision_impact * information_gain * coverage
        risk_penalty = _RISK_PENALTY[probe.risk]
        missing_penalty = self.policy.missing_prediction_penalty * (1.0 - coverage)
        score = (
            self.policy.information_gain_weight * information_gain
            + self.policy.pairwise_separation_weight * pairwise_separation
            + self.policy.decision_value_weight * expected_value
            - self.policy.cost_weight * probe.expected_cost
            - self.policy.risk_weight * risk_penalty
            - missing_penalty
        )
        payload = {
            "tournament": self.tournament_id,
            "probe": probe.fingerprint,
            "posterior": self._posterior,
            "information_gain": information_gain,
            "expected_entropy": expected_entropy,
            "pairwise": pairwise_separation,
            "coverage": coverage,
            "value": expected_value,
            "score": score,
            "mixture": mixture,
        }
        return ProbeEvaluation(
            probe_id=probe.probe_id,
            expected_information_gain_bits=information_gain,
            expected_posterior_entropy_bits=expected_entropy,
            pairwise_separation=pairwise_separation,
            prediction_coverage=coverage,
            expected_decision_value=expected_value,
            expected_cost=probe.expected_cost,
            risk_penalty=risk_penalty,
            score=score,
            outcome_mixture=mixture,
            fingerprint=stable_fingerprint(payload),
        )

    def observe(
        self,
        probe_id: str,
        observed_outcome: str,
        *,
        falsification_threshold: float = 0.02,
    ) -> TournamentUpdate:
        probe_id = require_id("probe_id", probe_id)
        observed_outcome = require_id("observed_outcome", observed_outcome)
        threshold = probability("falsification_threshold", falsification_threshold)
        probe = self._probe(probe_id)
        if observed_outcome not in probe.outcome_support:
            raise AgentContractError("observed outcome is outside probe support")

        prior = dict(self._posterior)
        prior_entropy = _entropy_bits(prior)
        likelihoods: dict[str, float] = {}
        weighted: dict[str, float] = {}
        for hypothesis in self._hypotheses:
            hid = hypothesis.hypothesis_id
            prediction = hypothesis.prediction(probe_id)
            likelihood = (
                prediction.distribution[observed_outcome]
                if prediction is not None
                else self.policy.likelihood_floor
            )
            likelihood = max(self.policy.likelihood_floor, likelihood)
            likelihoods[hid] = likelihood
            weighted[hid] = prior[hid] * likelihood
        predictive_probability = sum(weighted.values())
        surprise_bits = -math.log2(max(_EPS, predictive_probability))
        posterior = _normalize(weighted, name="posterior")
        self._posterior = posterior
        posterior_entropy = _entropy_bits(posterior)
        information_gain = max(0.0, prior_entropy - posterior_entropy)
        winner_id = max(posterior, key=lambda key: (posterior[key], key))
        falsified = tuple(
            sorted(
                hid
                for hid, likelihood in likelihoods.items()
                if likelihood <= threshold
            )
        )
        payload = {
            "tournament": self.tournament_id,
            "probe_id": probe_id,
            "observed": observed_outcome,
            "prior": prior,
            "posterior": posterior,
            "likelihoods": likelihoods,
            "predictive_probability": predictive_probability,
            "surprise_bits": surprise_bits,
            "information_gain": information_gain,
            "falsified": falsified,
        }
        update = TournamentUpdate(
            tournament_id=self.tournament_id,
            probe_id=probe_id,
            observed_outcome=observed_outcome,
            prior=prior,
            posterior=posterior,
            likelihoods=likelihoods,
            predictive_probability=predictive_probability,
            surprise_bits=surprise_bits,
            information_gain_bits=information_gain,
            winner_id=winner_id,
            winner_probability=posterior[winner_id],
            falsified_ids=falsified,
            falsification_threshold=threshold,
            fingerprint=stable_fingerprint(payload),
        )
        self._history.append(update)
        return update

    def history(self) -> tuple[TournamentUpdate, ...]:
        return tuple(self._history)

    def dump_state(self) -> dict[str, Any]:
        """Serialize initial contracts plus observations for deterministic replay."""

        return {
            "version": 1,
            "decision_impact": self.decision_impact,
            "policy": {
                name: getattr(self.policy, name)
                for name in self.policy.__dataclass_fields__
            },
            "hypotheses": [
                {
                    "hypothesis_id": item.hypothesis_id,
                    "statement": item.statement,
                    "prior_weight": item.prior_weight,
                    "predictions": [
                        {
                            "probe_id": prediction.probe_id,
                            "distribution": dict(prediction.distribution),
                            "rationale": prediction.rationale,
                        }
                        for prediction in item.predictions
                    ],
                    "assumptions": list(item.assumptions),
                    "evidence_refs": list(item.evidence_refs),
                    "provenance": list(item.provenance),
                    "metadata": dict(item.metadata),
                }
                for item in self._hypotheses
            ],
            "probes": [
                {
                    "probe_id": item.probe_id,
                    "question": item.question,
                    "outcome_support": list(item.outcome_support),
                    "expected_cost": item.expected_cost,
                    "risk": item.risk.value,
                    "reversible": item.reversible,
                    "evidence_only": item.evidence_only,
                    "metadata": dict(item.metadata),
                }
                for item in self._probes
            ],
            "observations": [
                {
                    "probe_id": item.probe_id,
                    "observed_outcome": item.observed_outcome,
                    "falsification_threshold": item.falsification_threshold,
                    "expected_update_fingerprint": item.fingerprint,
                }
                for item in self._history
            ],
            "posterior": dict(self._posterior),
            "tournament_id": self.tournament_id,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "HypothesisTournament":
        """Rebuild a tournament by replaying observations and verify fingerprints."""

        payload = json_safe(dict(state))
        if payload.get("version") != 1:
            raise AgentContractError("unsupported tournament state version")
        hypotheses = tuple(
            CompetingHypothesis(
                hypothesis_id=value["hypothesis_id"],
                statement=value["statement"],
                prior_weight=value["prior_weight"],
                predictions=tuple(
                    HypothesisPrediction(
                        probe_id=prediction["probe_id"],
                        distribution=dict(prediction["distribution"]),
                        rationale=prediction.get("rationale", ""),
                    )
                    for prediction in value["predictions"]
                ),
                assumptions=tuple(value.get("assumptions", ())),
                evidence_refs=tuple(value.get("evidence_refs", ())),
                provenance=tuple(value.get("provenance", ())),
                metadata=dict(value.get("metadata", {})),
            )
            for value in payload.get("hypotheses", ())
        )
        probes = tuple(
            DiscriminatingProbe(
                probe_id=value["probe_id"],
                question=value["question"],
                outcome_support=tuple(value["outcome_support"]),
                expected_cost=value.get("expected_cost", 0.1),
                risk=RiskTier(value.get("risk", RiskTier.READ_ONLY.value)),
                reversible=bool(value.get("reversible", True)),
                evidence_only=bool(value.get("evidence_only", True)),
                metadata=dict(value.get("metadata", {})),
            )
            for value in payload.get("probes", ())
        )
        tournament = cls(
            hypotheses,
            probes,
            policy=TournamentPolicy(**dict(payload.get("policy", {}))),
            decision_impact=payload.get("decision_impact", 1.0),
        )
        expected_id = payload.get("tournament_id")
        if expected_id is not None and tournament.tournament_id != expected_id:
            raise AgentContractError("tournament identity mismatch during replay")
        for observation in payload.get("observations", ()):
            update = tournament.observe(
                observation["probe_id"],
                observation["observed_outcome"],
                falsification_threshold=observation.get(
                    "falsification_threshold",
                    0.02,
                ),
            )
            expected = observation.get("expected_update_fingerprint")
            if expected is not None and update.fingerprint != expected:
                raise AgentContractError(
                    "tournament update fingerprint mismatch during replay"
                )
        expected_posterior = payload.get("posterior")
        if expected_posterior is not None:
            normalized = _normalize(
                dict(expected_posterior),
                name="stored_posterior",
            )
            if stable_fingerprint(normalized) != stable_fingerprint(tournament.posterior):
                raise AgentContractError(
                    "tournament posterior mismatch after deterministic replay"
                )
        return tournament

    def _probe(self, probe_id: str) -> DiscriminatingProbe:
        for probe in self._probes:
            if probe.probe_id == probe_id:
                return probe
        raise AgentContractError(f"unknown probe {probe_id}")
