"""Frontier probability lenses for predictive Jeeves reasoning.

The base :mod:`probability_lenses` module deliberately keeps eighteen common
semantics compact and dependency-free.  This module adds a second, orthogonal
layer for modern predictive systems: coverage guarantees, anytime-valid
sequential evidence, tail risk, dependence bounds, reliability, arrival
processes, distribution shift, ensemble decomposition, information-directed
choice, rare-event estimation, competing risks, and partial identification.

These are *lenses*, not interchangeable definitions of probability.  Every
assessment therefore declares what its numeric fields mean and which
assumptions make the estimate valid.  Host code must not average assessments
with incompatible targets or semantics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .probability_lenses import (
    AssessmentShape,
    ProbabilityError,
    binary_entropy,
    log_loss,
)
from .types import finite_number, json_safe, probability, stable_fingerprint

_EPS = 1e-12


class FrontierProbabilityLens(str, Enum):
    CONFORMAL_COVERAGE = "conformal_coverage"
    SEQUENTIAL_E_VALUE = "sequential_e_value"
    ANYTIME_CONFIDENCE = "anytime_confidence"
    EXTREME_TAIL = "extreme_tail"
    DEPENDENCE_BOUNDS = "dependence_bounds"
    RELIABILITY_SYSTEM = "reliability_system"
    POISSON_ARRIVAL = "poisson_arrival"
    COMPETING_RISKS = "competing_risks"
    DISTRIBUTION_SHIFT = "distribution_shift"
    MODEL_MIXTURE = "model_mixture"
    UNCERTAINTY_DECOMPOSITION = "uncertainty_decomposition"
    INFORMATION_DIRECTED = "information_directed"
    DECISION_RISK = "decision_risk"
    RARE_EVENT_IMPORTANCE = "rare_event_importance"
    PARTIAL_IDENTIFICATION = "partial_identification"
    ROBUST_AMBIGUITY_SET = "robust_ambiguity_set"
    PREDICTION_MARKET = "prediction_market"
    RETRIEVAL_COMPETITION = "retrieval_competition"


@dataclass(frozen=True, slots=True)
class FrontierProbabilityAssessment:
    lens: FrontierProbabilityLens
    shape: AssessmentShape
    estimate: float | None = None
    lower: float | None = None
    upper: float | None = None
    confidence: float | None = None
    effective_samples: float | None = None
    target: str = "event_probability"
    assumptions: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.lens, FrontierProbabilityLens):
            object.__setattr__(self, "lens", FrontierProbabilityLens(str(self.lens)))
        if not isinstance(self.shape, AssessmentShape):
            object.__setattr__(self, "shape", AssessmentShape(str(self.shape)))
        if self.estimate is not None:
            object.__setattr__(self, "estimate", probability("estimate", self.estimate))
        if self.lower is not None:
            object.__setattr__(self, "lower", probability("lower", self.lower))
        if self.upper is not None:
            object.__setattr__(self, "upper", probability("upper", self.upper))
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ProbabilityError("frontier lower bound exceeds upper bound")
        if self.estimate is not None and self.lower is not None and self.estimate + _EPS < self.lower:
            raise ProbabilityError("frontier estimate falls below lower bound")
        if self.estimate is not None and self.upper is not None and self.estimate - _EPS > self.upper:
            raise ProbabilityError("frontier estimate exceeds upper bound")
        if self.confidence is not None:
            object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        if self.effective_samples is not None:
            value = finite_number("effective_samples", self.effective_samples)
            if value < 0:
                raise ProbabilityError("effective_samples must be non-negative")
            object.__setattr__(self, "effective_samples", value)
        target = str(self.target).strip()
        if not target:
            raise ProbabilityError("frontier assessment requires a target semantic")
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "assumptions", tuple(str(item).strip() for item in self.assumptions if str(item).strip()))
        object.__setattr__(self, "provenance", tuple(sorted({str(item) for item in self.provenance if str(item)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "lens": self.lens.value,
                "shape": self.shape.value,
                "estimate": self.estimate,
                "lower": self.lower,
                "upper": self.upper,
                "confidence": self.confidence,
                "effective_samples": self.effective_samples,
                "target": self.target,
                "assumptions": self.assumptions,
                "provenance": self.provenance,
                "metadata": dict(self.metadata),
            }
        )


def _non_negative(name: str, value: float) -> float:
    result = finite_number(name, value)
    if result < 0:
        raise ProbabilityError(f"{name} must be non-negative")
    return result


def _positive(name: str, value: float) -> float:
    result = finite_number(name, value)
    if result <= 0:
        raise ProbabilityError(f"{name} must be positive")
    return result


def _weights(items: Sequence[float]) -> tuple[float, ...]:
    if not items:
        raise ProbabilityError("weights cannot be empty")
    values = tuple(_non_negative("weight", item) for item in items)
    total = sum(values)
    if total <= 0:
        raise ProbabilityError("weights sum to zero")
    return tuple(item / total for item in values)


def split_conformal_p_value(
    calibration_nonconformity: Sequence[float],
    candidate_nonconformity: float,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Finite-sample split-conformal rank p-value.

    Exchangeability is an explicit assumption.  The value is not a Bayesian
    posterior probability that the candidate is correct.
    """

    if not calibration_nonconformity:
        raise ProbabilityError("conformal calibration set cannot be empty")
    calibration = tuple(finite_number("nonconformity", value) for value in calibration_nonconformity)
    candidate = finite_number("candidate_nonconformity", candidate_nonconformity)
    ge = sum(value >= candidate for value in calibration)
    p_value = (ge + 1.0) / (len(calibration) + 1.0)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.CONFORMAL_COVERAGE,
        shape=AssessmentShape.EVIDENCE_WEIGHT,
        estimate=p_value,
        effective_samples=float(len(calibration)),
        target="conformal_rank_p_value",
        assumptions=("exchangeable calibration and test examples", "fixed nonconformity rule"),
        provenance=tuple(provenance),
        metadata={"greater_or_equal": ge, "candidate_nonconformity": candidate, "posterior_probability": False},
    )


def conformal_error_bound(alpha: float, *, provenance: Sequence[str] = ()) -> FrontierProbabilityAssessment:
    alpha = probability("alpha", alpha)
    coverage = 1.0 - alpha
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.CONFORMAL_COVERAGE,
        shape=AssessmentShape.POINT,
        estimate=coverage,
        lower=coverage,
        upper=coverage,
        target="nominal_marginal_coverage",
        assumptions=("exchangeability", "valid conformal construction"),
        provenance=tuple(provenance),
        metadata={"alpha": alpha, "conditional_coverage_guaranteed": False},
    )


def sequential_e_value(
    likelihood_ratios: Sequence[float],
    *,
    cap: float = 1e12,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Multiply non-negative test-martingale factors into an e-value.

    The returned estimate is a bounded evidence transform e/(1+e), while the
    raw e-value remains in metadata.  This avoids mislabelling an e-value as a
    posterior probability.
    """

    if not likelihood_ratios:
        raise ProbabilityError("sequential e-value requires factors")
    cap = _positive("cap", cap)
    log_e = 0.0
    for factor in likelihood_ratios:
        value = _non_negative("e-factor", factor)
        if value == 0:
            log_e = float("-inf")
            break
        log_e += math.log(value)
    if log_e == float("-inf"):
        raw = 0.0
    else:
        raw = min(cap, math.exp(min(math.log(cap), log_e)))
    bounded = raw / (1.0 + raw)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.SEQUENTIAL_E_VALUE,
        shape=AssessmentShape.EVIDENCE_WEIGHT,
        estimate=bounded,
        target="anytime_valid_evidence_against_null",
        assumptions=("factors form a valid non-negative test supermartingale under the null",),
        provenance=tuple(provenance),
        metadata={"e_value": raw, "bounded_transform": "e/(1+e)", "posterior_probability": False},
    )


def anytime_hoeffding_interval(
    mean: float,
    samples: int,
    *,
    delta: float = 0.05,
    looks: int = 1,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Conservative bounded-observation confidence sequence approximation.

    A union-bound allocation across ``looks`` keeps the contract explicit.  It
    is intentionally conservative rather than presenting an ordinary fixed-time
    interval as anytime-valid.
    """

    estimate = probability("mean", mean)
    if isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0:
        raise ProbabilityError("samples must be positive integer")
    if isinstance(looks, bool) or not isinstance(looks, int) or looks <= 0:
        raise ProbabilityError("looks must be positive integer")
    delta = probability("delta", delta)
    if delta <= 0:
        raise ProbabilityError("delta must be positive")
    per_look = delta / looks
    radius = math.sqrt(math.log(2.0 / per_look) / (2.0 * samples))
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.ANYTIME_CONFIDENCE,
        shape=AssessmentShape.INTERVAL,
        estimate=estimate,
        lower=max(0.0, estimate - radius),
        upper=min(1.0, estimate + radius),
        confidence=1.0 - delta,
        effective_samples=float(samples),
        target="bounded_mean",
        assumptions=("independent [0,1]-bounded observations", "finite declared look budget"),
        provenance=tuple(provenance),
        metadata={"looks": looks, "per_look_delta": per_look, "method": "Hoeffding_union_bound"},
    )


def generalized_pareto_tail_probability(
    threshold_exceedance_rate: float,
    excess: float,
    *,
    scale: float,
    shape: float,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """GPD peaks-over-threshold tail estimate with supplied fitted parameters."""

    rate = probability("threshold_exceedance_rate", threshold_exceedance_rate)
    x = _non_negative("excess", excess)
    scale = _positive("scale", scale)
    shape = finite_number("shape", shape)
    if abs(shape) < 1e-12:
        conditional_survival = math.exp(-x / scale)
    else:
        base = 1.0 + shape * x / scale
        if base <= 0:
            conditional_survival = 0.0
        else:
            conditional_survival = base ** (-1.0 / shape)
    estimate = max(0.0, min(1.0, rate * conditional_survival))
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.EXTREME_TAIL,
        shape=AssessmentShape.POINT,
        estimate=estimate,
        target="tail_exceedance_probability",
        assumptions=("threshold is sufficiently high", "exceedances are adequately modeled by a GPD"),
        provenance=tuple(provenance),
        metadata={"threshold_exceedance_rate": rate, "excess": x, "scale": scale, "shape": shape},
    )


def frechet_joint_bounds(
    p_a: float,
    p_b: float,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Dependence-agnostic Fréchet-Hoeffding bounds for P(A and B)."""

    a = probability("p_a", p_a)
    b = probability("p_b", p_b)
    lower = max(0.0, a + b - 1.0)
    upper = min(a, b)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.DEPENDENCE_BOUNDS,
        shape=AssessmentShape.INTERVAL,
        lower=lower,
        upper=upper,
        target="joint_probability_A_and_B",
        assumptions=("only marginal probabilities are trusted",),
        provenance=tuple(provenance),
        metadata={"p_a": a, "p_b": b, "independence_not_assumed": True},
    )


def system_reliability(
    component_reliabilities: Sequence[float],
    *,
    topology: str = "series",
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    if not component_reliabilities:
        raise ProbabilityError("reliability system requires components")
    values = tuple(probability("component reliability", item) for item in component_reliabilities)
    topology = str(topology).strip().casefold()
    if topology == "series":
        estimate = math.prod(values)
    elif topology == "parallel":
        estimate = 1.0 - math.prod(1.0 - item for item in values)
    else:
        raise ProbabilityError("topology must be series or parallel")
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.RELIABILITY_SYSTEM,
        shape=AssessmentShape.POINT,
        estimate=estimate,
        target="system_success_probability",
        assumptions=("component failures independent conditional on modeled state",),
        provenance=tuple(provenance),
        metadata={"topology": topology, "components": len(values)},
    )


def poisson_at_least_one(
    rate: float,
    interval: float,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    lam = _non_negative("rate", rate)
    duration = _non_negative("interval", interval)
    estimate = 1.0 - math.exp(-lam * duration)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.POISSON_ARRIVAL,
        shape=AssessmentShape.POINT,
        estimate=estimate,
        target="at_least_one_arrival",
        assumptions=("homogeneous Poisson arrivals", "independent increments"),
        provenance=tuple(provenance),
        metadata={"rate": lam, "interval": duration, "expected_count": lam * duration},
    )


def competing_risk_probability(
    target_hazard: float,
    competing_hazards: Sequence[float],
    interval: float,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    target = _non_negative("target_hazard", target_hazard)
    competitors = tuple(_non_negative("competing_hazard", value) for value in competing_hazards)
    duration = _non_negative("interval", interval)
    total = target + sum(competitors)
    estimate = 0.0 if total <= 0 else (target / total) * (1.0 - math.exp(-total * duration))
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.COMPETING_RISKS,
        shape=AssessmentShape.POINT,
        estimate=estimate,
        target="cumulative_incidence_target_cause",
        assumptions=("constant cause-specific hazards over interval",),
        provenance=tuple(provenance),
        metadata={"target_hazard": target, "competing_hazards": list(competitors), "interval": duration},
    )


def distribution_shift_bound(
    source_probability: float,
    total_variation_distance: float,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Sharp event-probability perturbation bound under known TV distance."""

    source = probability("source_probability", source_probability)
    tv = probability("total_variation_distance", total_variation_distance)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.DISTRIBUTION_SHIFT,
        shape=AssessmentShape.INTERVAL,
        estimate=source,
        lower=max(0.0, source - tv),
        upper=min(1.0, source + tv),
        target="target_domain_event_probability",
        assumptions=("declared total variation bound is valid",),
        provenance=tuple(provenance),
        metadata={"source_probability": source, "tv_distance": tv},
    )


def model_mixture_probability(
    probabilities: Sequence[float],
    weights: Sequence[float] | None = None,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    if not probabilities:
        raise ProbabilityError("model mixture requires probabilities")
    ps = tuple(probability("model probability", item) for item in probabilities)
    ws = _weights(weights if weights is not None else [1.0] * len(ps))
    if len(ws) != len(ps):
        raise ProbabilityError("model mixture weights length mismatch")
    mean = sum(w * p for w, p in zip(ws, ps))
    variance = sum(w * (p - mean) ** 2 for w, p in zip(ws, ps))
    sd = math.sqrt(max(0.0, variance))
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.MODEL_MIXTURE,
        shape=AssessmentShape.POINT,
        estimate=mean,
        lower=max(0.0, mean - 1.96 * sd),
        upper=min(1.0, mean + 1.96 * sd),
        target="posterior_or_ensemble_predictive_probability",
        assumptions=("weights are externally justified", "component forecasts target the same event and horizon"),
        provenance=tuple(provenance),
        metadata={"model_count": len(ps), "between_model_sd": sd, "weights": list(ws)},
    )


def uncertainty_decomposition(
    probabilities: Sequence[float],
    weights: Sequence[float] | None = None,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Bernoulli ensemble total/aleatoric/epistemic variance decomposition."""

    if not probabilities:
        raise ProbabilityError("uncertainty decomposition requires probabilities")
    ps = tuple(probability("model probability", item) for item in probabilities)
    ws = _weights(weights if weights is not None else [1.0] * len(ps))
    if len(ws) != len(ps):
        raise ProbabilityError("uncertainty weights length mismatch")
    mean = sum(w * p for w, p in zip(ws, ps))
    aleatoric = sum(w * p * (1.0 - p) for w, p in zip(ws, ps))
    epistemic = sum(w * (p - mean) ** 2 for w, p in zip(ws, ps))
    total = mean * (1.0 - mean)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.UNCERTAINTY_DECOMPOSITION,
        shape=AssessmentShape.POINT,
        estimate=mean,
        target="ensemble_event_probability",
        assumptions=("Bernoulli target", "component forecasts share target and horizon"),
        provenance=tuple(provenance),
        metadata={
            "total_variance": total,
            "aleatoric_variance": aleatoric,
            "epistemic_variance": epistemic,
            "identity_residual": total - aleatoric - epistemic,
            "predictive_entropy_bits": binary_entropy(mean),
        },
    )


def information_directed_score(
    expected_regret: float,
    expected_information_gain: float,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    regret = _non_negative("expected_regret", expected_regret)
    info = _non_negative("expected_information_gain", expected_information_gain)
    ratio = float("inf") if info <= 0 and regret > 0 else (0.0 if regret <= 0 else regret * regret / max(info, _EPS))
    desirability = 1.0 / (1.0 + ratio) if math.isfinite(ratio) else 0.0
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.INFORMATION_DIRECTED,
        shape=AssessmentShape.EVIDENCE_WEIGHT,
        estimate=desirability,
        target="information_directed_action_desirability",
        assumptions=("regret and information gain are computed on comparable action hypotheses",),
        provenance=tuple(provenance),
        metadata={"expected_regret": regret, "expected_information_gain": info, "information_ratio": "inf" if math.isinf(ratio) else ratio, "event_probability": False},
    )


def cvar_failure_probability(
    losses: Sequence[float],
    *,
    alpha: float = 0.95,
    failure_threshold: float = 0.0,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    if not losses:
        raise ProbabilityError("CVaR assessment requires losses")
    alpha = probability("alpha", alpha)
    if alpha >= 1.0:
        raise ProbabilityError("alpha must be below one")
    values = sorted(finite_number("loss", value) for value in losses)
    start = min(len(values) - 1, max(0, int(math.floor(alpha * len(values)))))
    tail = values[start:]
    cvar = sum(tail) / len(tail)
    failures = sum(value >= failure_threshold for value in values)
    p_failure = failures / len(values)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.DECISION_RISK,
        shape=AssessmentShape.POINT,
        estimate=p_failure,
        effective_samples=float(len(values)),
        target="failure_probability_with_tail_risk",
        assumptions=("loss samples represent the decision-relevant distribution",),
        provenance=tuple(provenance),
        metadata={"alpha": alpha, "cvar": cvar, "failure_threshold": failure_threshold, "tail_count": len(tail)},
    )


def importance_sampling_probability(
    indicators: Sequence[bool | int],
    likelihood_weights: Sequence[float],
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    if not indicators or len(indicators) != len(likelihood_weights):
        raise ProbabilityError("importance sampling requires equal non-empty sequences")
    weights = tuple(_non_negative("likelihood weight", value) for value in likelihood_weights)
    total = sum(weights)
    if total <= 0:
        raise ProbabilityError("importance weights sum to zero")
    ys: list[float] = []
    for value in indicators:
        if value not in {0, 1, False, True}:
            raise ProbabilityError("importance sampling indicators must be binary")
        ys.append(1.0 if bool(value) else 0.0)
    estimate = sum(weight * y for weight, y in zip(weights, ys)) / total
    ess = total * total / max(_EPS, sum(weight * weight for weight in weights))
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.RARE_EVENT_IMPORTANCE,
        shape=AssessmentShape.POINT,
        estimate=estimate,
        effective_samples=ess,
        target="rare_event_probability",
        assumptions=("proposal support covers target event support", "likelihood ratios are correct"),
        provenance=tuple(provenance),
        metadata={"raw_samples": len(ys), "effective_sample_size": ess, "self_normalized": True},
    )


def partial_identification_interval(
    lower: float,
    upper: float,
    *,
    estimand: str,
    assumptions: Sequence[str] = (),
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    lo = probability("lower", lower)
    hi = probability("upper", upper)
    if lo > hi:
        raise ProbabilityError("partial-identification lower exceeds upper")
    estimand = str(estimand).strip()
    if not estimand:
        raise ProbabilityError("estimand is required")
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.PARTIAL_IDENTIFICATION,
        shape=AssessmentShape.INTERVAL,
        lower=lo,
        upper=hi,
        target=estimand,
        assumptions=tuple(assumptions),
        provenance=tuple(provenance),
        metadata={"point_identified": abs(hi - lo) <= _EPS},
    )


def robust_ambiguity_probability(
    candidate_probabilities: Sequence[float],
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    if not candidate_probabilities:
        raise ProbabilityError("ambiguity set cannot be empty")
    values = tuple(probability("candidate probability", value) for value in candidate_probabilities)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.ROBUST_AMBIGUITY_SET,
        shape=AssessmentShape.INTERVAL,
        lower=min(values),
        upper=max(values),
        target="event_probability_over_ambiguity_set",
        assumptions=("candidate set contains the considered plausible models",),
        provenance=tuple(provenance),
        metadata={"model_count": len(values), "midpoint": (min(values) + max(values)) / 2.0},
    )


def log_opinion_pool(
    probabilities: Sequence[float],
    weights: Sequence[float] | None = None,
    *,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Externally weighted log-opinion pool for a common binary target.

    This is intentionally opt-in.  It should only combine calibrated forecasts
    for the exact same proposition and horizon.
    """

    if not probabilities:
        raise ProbabilityError("opinion pool requires probabilities")
    ps = tuple(min(1.0 - _EPS, max(_EPS, probability("forecast", value))) for value in probabilities)
    ws = _weights(weights if weights is not None else [1.0] * len(ps))
    if len(ws) != len(ps):
        raise ProbabilityError("opinion-pool weights length mismatch")
    log_odds = sum(weight * math.log(p / (1.0 - p)) for weight, p in zip(ws, ps))
    estimate = 1.0 / (1.0 + math.exp(-log_odds))
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.PREDICTION_MARKET,
        shape=AssessmentShape.POINT,
        estimate=estimate,
        target="pooled_binary_forecast",
        assumptions=("same proposition", "same forecast horizon", "weights externally justified", "component probabilities calibrated enough for pooling"),
        provenance=tuple(provenance),
        metadata={"weights": list(ws), "pool": "log_opinion"},
    )


def retrieval_competition_probability(
    activations: Sequence[float],
    target_index: int,
    *,
    temperature: float = 1.0,
    provenance: Sequence[str] = (),
) -> FrontierProbabilityAssessment:
    """Softmax competition among simultaneously cued memory candidates."""

    if not activations:
        raise ProbabilityError("retrieval competition requires candidates")
    if isinstance(target_index, bool) or not isinstance(target_index, int) or not 0 <= target_index < len(activations):
        raise ProbabilityError("target_index out of range")
    temperature = _positive("temperature", temperature)
    scaled = [finite_number("activation", value) / temperature for value in activations]
    maximum = max(scaled)
    exp_values = [math.exp(value - maximum) for value in scaled]
    total = sum(exp_values)
    estimate = exp_values[target_index] / total
    entropy = -sum((value / total) * math.log2(value / total) for value in exp_values if value > 0)
    return FrontierProbabilityAssessment(
        lens=FrontierProbabilityLens.RETRIEVAL_COMPETITION,
        shape=AssessmentShape.POINT,
        estimate=estimate,
        target="probability_target_wins_retrieval_competition",
        assumptions=("softmax competition is an adequate retrieval-choice model",),
        provenance=tuple(provenance),
        metadata={"candidate_count": len(activations), "temperature": temperature, "competition_entropy_bits": entropy},
    )


class FrontierProbabilityWorkbench:
    """Registry plus compatibility guard for advanced probability semantics."""

    @staticmethod
    def lenses() -> tuple[FrontierProbabilityLens, ...]:
        return tuple(FrontierProbabilityLens)

    @staticmethod
    def compatible_for_pooling(assessments: Sequence[FrontierProbabilityAssessment]) -> bool:
        if not assessments:
            return False
        targets = {item.target for item in assessments}
        shapes = {item.shape for item in assessments}
        return len(targets) == 1 and shapes == {AssessmentShape.POINT} and all(item.estimate is not None for item in assessments)

    @staticmethod
    def forecast_log_loss(probabilities: Sequence[float], outcomes: Sequence[bool | int]) -> float:
        return log_loss(probabilities, outcomes)

    @staticmethod
    def fingerprint() -> str:
        return stable_fingerprint([lens.value for lens in FrontierProbabilityLens])
