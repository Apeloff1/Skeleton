"""Typed probability and uncertainty semantics for Jeeves.

The module intentionally does *not* pretend there is one canonical list of
"18 kinds of probability".  Instead it exposes eighteen named lenses that are
useful to the runtime and makes their semantics explicit.  Some lenses produce
ordinary additive point probabilities, while others produce interval-valued or
non-additive support.  Downstream code therefore cannot silently collapse
belief/plausibility, possibility/necessity, likelihood evidence, causal effects,
and calibrated forecasts into one ambiguous confidence scalar.

The implementation is dependency-free and deterministic so it can be used in
replay, evaluation, planning, memory acquisition, and safety-critical gates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .types import AgentContractError, finite_number, json_safe, probability, stable_fingerprint

_EPS = 1e-12


class ProbabilityError(AgentContractError):
    """Raised when an uncertainty assessment violates its semantic contract."""


class ProbabilityLens(str, Enum):
    """Eighteen explicit inference lenses used by Jeeves.

    This is an engineering taxonomy, not a claim that probability theory has a
    universally agreed set of exactly eighteen interpretations.
    """

    CLASSICAL = "classical"
    FREQUENTIST = "frequentist"
    BAYESIAN = "bayesian"
    SUBJECTIVE = "subjective"
    PROPENSITY = "propensity"
    LOGICAL_EVIDENTIAL = "logical_evidential"
    LIKELIHOOD = "likelihood"
    POSTERIOR_PREDICTIVE = "posterior_predictive"
    CAUSAL_INTERVENTIONAL = "causal_interventional"
    COUNTERFACTUAL = "counterfactual"
    TRANSITION = "transition"
    HAZARD_SURVIVAL = "hazard_survival"
    CALIBRATED_FORECAST = "calibrated_forecast"
    IMPRECISE_INTERVAL = "imprecise_interval"
    DEMPSTER_SHAFER = "dempster_shafer"
    POSSIBILITY_NECESSITY = "possibility_necessity"
    GAME_CHANCE = "game_chance"
    MEMORY_RETRIEVAL = "memory_retrieval"
    SURPRISAL = "surprisal"
    HIDDEN_STATE = "hidden_state"
    COPULA_DEPENDENCE = "copula_dependence"
    ROBUST_BAYES = "robust_bayes"
    EXTREME_VALUE = "extreme_value"
    EXCHANGEABILITY = "exchangeability"
    ALEATORIC_EPISTEMIC = "aleatoric_epistemic"
    HIERARCHICAL_BAYES = "hierarchical_bayes"
    CONFORMAL_COVERAGE = "conformal_coverage"
    RISK_SENSITIVE = "risk_sensitive"
    INFORMATION_GAIN = "information_gain"
    ENSEMBLE_MODEL = "ensemble_model"


class AssessmentShape(str, Enum):
    POINT = "point"
    INTERVAL = "interval"
    EVIDENCE_WEIGHT = "evidence_weight"
    NON_ADDITIVE = "non_additive"


@dataclass(frozen=True, slots=True)
class ProbabilityAssessment:
    lens: ProbabilityLens
    shape: AssessmentShape
    estimate: float | None = None
    lower: float | None = None
    upper: float | None = None
    effective_samples: float | None = None
    calibrated: bool = False
    identified: bool = True
    provenance: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.lens, ProbabilityLens):
            object.__setattr__(self, "lens", ProbabilityLens(str(self.lens)))
        if not isinstance(self.shape, AssessmentShape):
            object.__setattr__(self, "shape", AssessmentShape(str(self.shape)))
        if self.estimate is not None:
            object.__setattr__(self, "estimate", probability("estimate", self.estimate))
        if self.lower is not None:
            object.__setattr__(self, "lower", probability("lower", self.lower))
        if self.upper is not None:
            object.__setattr__(self, "upper", probability("upper", self.upper))
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ProbabilityError("lower probability exceeds upper probability")
        if self.estimate is not None and self.lower is not None and self.estimate < self.lower - _EPS:
            raise ProbabilityError("estimate falls below lower bound")
        if self.estimate is not None and self.upper is not None and self.estimate > self.upper + _EPS:
            raise ProbabilityError("estimate exceeds upper bound")
        if self.shape is AssessmentShape.POINT and self.estimate is None:
            raise ProbabilityError("point assessment requires estimate")
        if self.shape in {AssessmentShape.INTERVAL, AssessmentShape.NON_ADDITIVE}:
            if self.lower is None or self.upper is None:
                raise ProbabilityError("interval/non-additive assessment requires lower and upper bounds")
        if self.effective_samples is not None:
            samples = finite_number("effective_samples", self.effective_samples)
            if samples < 0:
                raise ProbabilityError("effective_samples must be non-negative")
            object.__setattr__(self, "effective_samples", samples)
        object.__setattr__(self, "provenance", tuple(sorted({str(item) for item in self.provenance if str(item)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def width(self) -> float:
        if self.lower is None or self.upper is None:
            return 0.0
        return self.upper - self.lower

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.as_json())

    def as_json(self) -> dict[str, Any]:
        return {
            "lens": self.lens.value,
            "shape": self.shape.value,
            "estimate": self.estimate,
            "lower": self.lower,
            "upper": self.upper,
            "effective_samples": self.effective_samples,
            "calibrated": self.calibrated,
            "identified": self.identified,
            "provenance": list(self.provenance),
            "metadata": dict(self.metadata),
        }


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


def _count(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProbabilityError(f"{name} must be a non-negative integer")
    return value


def binary_entropy(p: float) -> float:
    p = probability("p", p)
    if p in {0.0, 1.0}:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def logit(p: float) -> float:
    p = probability("p", p)
    p = min(1.0 - _EPS, max(_EPS, p))
    return math.log(p / (1.0 - p))


def logistic(value: float) -> float:
    x = finite_number("logit", value)
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def wilson_interval(successes: int, trials: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    successes = _count("successes", successes)
    trials = _count("trials", trials)
    if trials <= 0 or successes > trials:
        raise ProbabilityError("Wilson interval requires 0 <= successes <= trials and trials > 0")
    z = _positive("z", z)
    phat = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = (phat + z2 / (2.0 * trials)) / denominator
    half = z * math.sqrt((phat * (1.0 - phat) + z2 / (4.0 * trials)) / trials) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def classical_probability(
    favorable: int,
    total_equiprobable: int,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    favorable = _count("favorable", favorable)
    total = _count("total_equiprobable", total_equiprobable)
    if total <= 0 or favorable > total:
        raise ProbabilityError("classical probability requires 0 <= favorable <= total and total > 0")
    value = favorable / total
    return ProbabilityAssessment(
        ProbabilityLens.CLASSICAL,
        AssessmentShape.POINT,
        estimate=value,
        lower=value,
        upper=value,
        provenance=tuple(provenance),
        metadata={"favorable": favorable, "total_equiprobable": total, "equiprobable_assumption": True},
    )


def frequentist_probability(
    successes: int,
    trials: int,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    successes = _count("successes", successes)
    trials = _count("trials", trials)
    if trials <= 0 or successes > trials:
        raise ProbabilityError("frequentist probability requires 0 <= successes <= trials and trials > 0")
    lower, upper = wilson_interval(successes, trials)
    return ProbabilityAssessment(
        ProbabilityLens.FREQUENTIST,
        AssessmentShape.POINT,
        estimate=successes / trials,
        lower=lower,
        upper=upper,
        effective_samples=float(trials),
        provenance=tuple(provenance),
        metadata={"successes": successes, "trials": trials, "interval": "wilson_95"},
    )


def bayesian_beta_probability(
    successes: float,
    failures: float,
    *,
    alpha_prior: float = 1.0,
    beta_prior: float = 1.0,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    successes = _non_negative("successes", successes)
    failures = _non_negative("failures", failures)
    alpha = _positive("alpha_prior", alpha_prior) + successes
    beta = _positive("beta_prior", beta_prior) + failures
    mean = alpha / (alpha + beta)
    variance = alpha * beta / (((alpha + beta) ** 2) * (alpha + beta + 1.0))
    half = 1.959963984540054 * math.sqrt(max(0.0, variance))
    return ProbabilityAssessment(
        ProbabilityLens.BAYESIAN,
        AssessmentShape.POINT,
        estimate=mean,
        lower=max(0.0, mean - half),
        upper=min(1.0, mean + half),
        effective_samples=successes + failures,
        provenance=tuple(provenance),
        metadata={"alpha": alpha, "beta": beta, "interval": "normal_approx_95"},
    )


def subjective_probability(
    credence: float,
    *,
    elicitation: str = "explicit",
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    value = probability("credence", credence)
    return ProbabilityAssessment(
        ProbabilityLens.SUBJECTIVE,
        AssessmentShape.POINT,
        estimate=value,
        provenance=tuple(provenance),
        metadata={"elicitation": str(elicitation)},
    )


def propensity_probability(
    mechanism_chance: float,
    *,
    mechanism: str,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    value = probability("mechanism_chance", mechanism_chance)
    mechanism = str(mechanism).strip()
    if not mechanism:
        raise ProbabilityError("propensity assessment requires mechanism description")
    return ProbabilityAssessment(
        ProbabilityLens.PROPENSITY,
        AssessmentShape.POINT,
        estimate=value,
        provenance=tuple(provenance),
        metadata={"mechanism": mechanism},
    )


def logical_evidential_probability(
    support_for: float,
    support_against: float,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    positive = _non_negative("support_for", support_for)
    negative = _non_negative("support_against", support_against)
    if positive + negative <= 0:
        raise ProbabilityError("logical/evidential assessment needs non-zero support")
    estimate = positive / (positive + negative)
    return ProbabilityAssessment(
        ProbabilityLens.LOGICAL_EVIDENTIAL,
        AssessmentShape.POINT,
        estimate=estimate,
        provenance=tuple(provenance),
        metadata={"support_for": positive, "support_against": negative, "interpretation": "normalized_evidential_support"},
    )


def likelihood_evidence(
    likelihood_if_true: float,
    likelihood_if_false: float,
    *,
    prior_probability: float | None = None,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    lt = probability("likelihood_if_true", likelihood_if_true)
    lf = probability("likelihood_if_false", likelihood_if_false)
    if lf <= 0:
        if lt <= 0:
            raise ProbabilityError("likelihood ratio undefined when both likelihoods are zero")
        ratio = float("inf")
        evidence_weight = 1.0
    else:
        ratio = lt / lf
        evidence_weight = ratio / (1.0 + ratio)
    metadata: dict[str, Any] = {
        "likelihood_if_true": lt,
        "likelihood_if_false": lf,
        "likelihood_ratio": "inf" if math.isinf(ratio) else ratio,
        "estimate_semantics": "normalized_evidence_weight_not_posterior",
    }
    if prior_probability is not None:
        prior = probability("prior_probability", prior_probability)
        if prior in {0.0, 1.0}:
            posterior = prior
        elif math.isinf(ratio):
            posterior = 1.0
        else:
            posterior_odds = math.exp(logit(prior)) * ratio
            posterior = posterior_odds / (1.0 + posterior_odds)
        metadata["prior_probability"] = prior
        metadata["posterior_probability"] = posterior
    return ProbabilityAssessment(
        ProbabilityLens.LIKELIHOOD,
        AssessmentShape.EVIDENCE_WEIGHT,
        estimate=evidence_weight,
        provenance=tuple(provenance),
        metadata=metadata,
    )


def posterior_predictive_probability(
    posterior_weighted_probabilities: Sequence[tuple[float, float]],
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    if not posterior_weighted_probabilities:
        raise ProbabilityError("posterior predictive assessment requires components")
    weights: list[float] = []
    probabilities: list[float] = []
    for weight, predicted in posterior_weighted_probabilities:
        weights.append(_non_negative("posterior weight", weight))
        probabilities.append(probability("predicted probability", predicted))
    total = sum(weights)
    if total <= 0:
        raise ProbabilityError("posterior predictive weights sum to zero")
    normalized = [weight / total for weight in weights]
    estimate = sum(weight * predicted for weight, predicted in zip(normalized, probabilities))
    variance = sum(weight * (predicted - estimate) ** 2 for weight, predicted in zip(normalized, probabilities))
    spread = math.sqrt(max(0.0, variance))
    return ProbabilityAssessment(
        ProbabilityLens.POSTERIOR_PREDICTIVE,
        AssessmentShape.POINT,
        estimate=estimate,
        lower=max(0.0, estimate - 1.959963984540054 * spread),
        upper=min(1.0, estimate + 1.959963984540054 * spread),
        provenance=tuple(provenance),
        metadata={"components": len(probabilities), "between_model_sd": spread},
    )


def causal_interventional_probability(
    probability_under_do: float,
    *,
    intervention: Mapping[str, Any],
    identified: bool,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    value = probability("probability_under_do", probability_under_do)
    return ProbabilityAssessment(
        ProbabilityLens.CAUSAL_INTERVENTIONAL,
        AssessmentShape.POINT,
        estimate=value,
        identified=bool(identified),
        provenance=tuple(provenance),
        metadata={"intervention": json_safe(dict(intervention)), "operator": "do"},
    )


def counterfactual_probability(
    value: float,
    *,
    factual_world: Mapping[str, Any],
    counterfactual_intervention: Mapping[str, Any],
    identified: bool,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    estimate = probability("counterfactual probability", value)
    return ProbabilityAssessment(
        ProbabilityLens.COUNTERFACTUAL,
        AssessmentShape.POINT,
        estimate=estimate,
        identified=bool(identified),
        provenance=tuple(provenance),
        metadata={
            "factual_world": json_safe(dict(factual_world)),
            "counterfactual_intervention": json_safe(dict(counterfactual_intervention)),
            "warning": None if identified else "estimate_not_individually_identified",
        },
    )


def transition_probability(
    transition_count: float,
    source_total: float,
    *,
    smoothing: float = 0.0,
    outcome_count: int = 1,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    transition_count = _non_negative("transition_count", transition_count)
    source_total = _non_negative("source_total", source_total)
    smoothing = _non_negative("smoothing", smoothing)
    outcome_count = _count("outcome_count", outcome_count)
    if outcome_count <= 0:
        raise ProbabilityError("outcome_count must be positive")
    if transition_count > source_total:
        raise ProbabilityError("transition_count cannot exceed source_total")
    denominator = source_total + smoothing * outcome_count
    if denominator <= 0:
        raise ProbabilityError("transition denominator is zero")
    estimate = (transition_count + smoothing) / denominator
    return ProbabilityAssessment(
        ProbabilityLens.TRANSITION,
        AssessmentShape.POINT,
        estimate=estimate,
        effective_samples=source_total,
        provenance=tuple(provenance),
        metadata={"smoothing": smoothing, "outcome_count": outcome_count},
    )


def hazard_survival_probability(
    hazard_rate: float,
    interval: float,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    hazard = _non_negative("hazard_rate", hazard_rate)
    duration = _non_negative("interval", interval)
    survival = math.exp(-hazard * duration)
    event_probability = 1.0 - survival
    return ProbabilityAssessment(
        ProbabilityLens.HAZARD_SURVIVAL,
        AssessmentShape.POINT,
        estimate=event_probability,
        provenance=tuple(provenance),
        metadata={"hazard_rate": hazard, "interval": duration, "survival_probability": survival, "constant_hazard_assumption": True},
    )


def calibrated_forecast_probability(
    raw_probability: float,
    calibrated_probability: float,
    *,
    calibration_method: str,
    calibration_samples: int,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    raw = probability("raw_probability", raw_probability)
    calibrated = probability("calibrated_probability", calibrated_probability)
    samples = _count("calibration_samples", calibration_samples)
    if samples <= 0:
        raise ProbabilityError("calibrated forecast requires calibration samples")
    return ProbabilityAssessment(
        ProbabilityLens.CALIBRATED_FORECAST,
        AssessmentShape.POINT,
        estimate=calibrated,
        effective_samples=float(samples),
        calibrated=True,
        provenance=tuple(provenance),
        metadata={"raw_probability": raw, "calibration_method": str(calibration_method)},
    )


def imprecise_probability(
    lower: float,
    upper: float,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    return ProbabilityAssessment(
        ProbabilityLens.IMPRECISE_INTERVAL,
        AssessmentShape.INTERVAL,
        lower=lower,
        upper=upper,
        provenance=tuple(provenance),
        metadata={"semantics": "lower_upper_probability_or_credal_envelope"},
    )


def dempster_shafer_support(
    belief: float,
    plausibility: float,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    belief = probability("belief", belief)
    plausibility = probability("plausibility", plausibility)
    if belief > plausibility:
        raise ProbabilityError("Dempster-Shafer belief cannot exceed plausibility")
    return ProbabilityAssessment(
        ProbabilityLens.DEMPSTER_SHAFER,
        AssessmentShape.NON_ADDITIVE,
        lower=belief,
        upper=plausibility,
        provenance=tuple(provenance),
        metadata={"lower_semantics": "belief", "upper_semantics": "plausibility"},
    )


def possibility_necessity_support(
    possibility: float,
    necessity: float,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    possibility = probability("possibility", possibility)
    necessity = probability("necessity", necessity)
    if necessity > possibility:
        raise ProbabilityError("necessity cannot exceed possibility for the same proposition")
    return ProbabilityAssessment(
        ProbabilityLens.POSSIBILITY_NECESSITY,
        AssessmentShape.NON_ADDITIVE,
        lower=necessity,
        upper=possibility,
        provenance=tuple(provenance),
        metadata={"lower_semantics": "necessity", "upper_semantics": "possibility", "additive_probability": False},
    )


def _dice_sum_counts(dice: int, sides: int) -> list[int]:
    dice = _count("dice", dice)
    sides = _count("sides", sides)
    if dice <= 0 or sides <= 1:
        raise ProbabilityError("dice must be positive and sides must exceed one")
    counts = [1]
    for _ in range(dice):
        next_counts = [0] * (len(counts) + sides)
        for current_sum, ways in enumerate(counts):
            for face in range(1, sides + 1):
                next_counts[current_sum + face] += ways
        counts = next_counts
    return counts


def fair_dice_sum_probability(
    dice: int,
    sides: int,
    *,
    minimum_sum: int | None = None,
    maximum_sum: int | None = None,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    counts = _dice_sum_counts(dice, sides)
    low = dice if minimum_sum is None else int(minimum_sum)
    high = dice * sides if maximum_sum is None else int(maximum_sum)
    if low > high:
        raise ProbabilityError("minimum_sum exceeds maximum_sum")
    favorable = sum(ways for total, ways in enumerate(counts) if low <= total <= high)
    all_outcomes = sides ** dice
    value = favorable / all_outcomes
    return ProbabilityAssessment(
        ProbabilityLens.GAME_CHANCE,
        AssessmentShape.POINT,
        estimate=value,
        lower=value,
        upper=value,
        provenance=tuple(provenance),
        metadata={
            "game": "fair_dice_sum",
            "dice": dice,
            "sides": sides,
            "minimum_sum": low,
            "maximum_sum": high,
            "favorable_microstates": favorable,
            "total_microstates": all_outcomes,
            "exact": True,
        },
    )


def empirical_game_probability(
    successes: int,
    trials: int,
    *,
    game: str = "observed_game",
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    base = frequentist_probability(successes, trials, provenance=provenance)
    return ProbabilityAssessment(
        ProbabilityLens.GAME_CHANCE,
        AssessmentShape.POINT,
        estimate=base.estimate,
        lower=base.lower,
        upper=base.upper,
        effective_samples=base.effective_samples,
        provenance=base.provenance,
        metadata={"game": str(game), "exact": False, "estimator": "empirical_frequency", **dict(base.metadata)},
    )


def memory_retrieval_probability(
    activation: float,
    *,
    threshold: float = 0.0,
    noise_scale: float = 1.0,
    storage_strength: float | None = None,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    activation = finite_number("activation", activation)
    threshold = finite_number("threshold", threshold)
    noise = _positive("noise_scale", noise_scale)
    estimate = logistic((activation - threshold) / noise)
    metadata: dict[str, Any] = {
        "activation": activation,
        "threshold": threshold,
        "noise_scale": noise,
        "model": "logistic_retrieval_gate",
    }
    if storage_strength is not None:
        metadata["storage_strength"] = _non_negative("storage_strength", storage_strength)
        metadata["storage_strength_directly_used_for_retrieval"] = False
    return ProbabilityAssessment(
        ProbabilityLens.MEMORY_RETRIEVAL,
        AssessmentShape.POINT,
        estimate=estimate,
        provenance=tuple(provenance),
        metadata=metadata,
    )


def brier_score(probabilities: Sequence[float], outcomes: Sequence[bool | int]) -> float:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ProbabilityError("Brier score requires equal non-empty probability and outcome sequences")
    total = 0.0
    for predicted, outcome in zip(probabilities, outcomes):
        p = probability("forecast probability", predicted)
        if outcome not in {0, 1, False, True}:
            raise ProbabilityError("Brier outcomes must be binary")
        y = 1.0 if bool(outcome) else 0.0
        total += (p - y) ** 2
    return total / len(probabilities)


def log_loss(probabilities: Sequence[float], outcomes: Sequence[bool | int], *, epsilon: float = 1e-12) -> float:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ProbabilityError("log loss requires equal non-empty probability and outcome sequences")
    epsilon = _positive("epsilon", epsilon)
    if epsilon >= 0.5:
        raise ProbabilityError("epsilon must be below 0.5")
    total = 0.0
    for predicted, outcome in zip(probabilities, outcomes):
        p = min(1.0 - epsilon, max(epsilon, probability("forecast probability", predicted)))
        if outcome not in {0, 1, False, True}:
            raise ProbabilityError("log-loss outcomes must be binary")
        y = 1.0 if bool(outcome) else 0.0
        total -= y * math.log(p) + (1.0 - y) * math.log(1.0 - p)
    return total / len(probabilities)


def expected_calibration_error(
    probabilities: Sequence[float],
    outcomes: Sequence[bool | int],
    *,
    bins: int = 10,
) -> float:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ProbabilityError("ECE requires equal non-empty probability and outcome sequences")
    if isinstance(bins, bool) or not isinstance(bins, int) or bins <= 0 or bins > 1000:
        raise ProbabilityError("bins must be an integer in [1, 1000]")
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for predicted, outcome in zip(probabilities, outcomes):
        p = probability("forecast probability", predicted)
        if outcome not in {0, 1, False, True}:
            raise ProbabilityError("ECE outcomes must be binary")
        index = min(bins - 1, int(p * bins))
        buckets[index].append((p, 1.0 if bool(outcome) else 0.0))
    total = len(probabilities)
    error = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        mean_p = sum(item[0] for item in bucket) / len(bucket)
        mean_y = sum(item[1] for item in bucket) / len(bucket)
        error += len(bucket) / total * abs(mean_p - mean_y)
    return error


def hypergeometric_probability(
    population: int,
    success_states: int,
    draws: int,
    successes_drawn: int,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    """Exact probability for uniform sampling without replacement."""
    population = _count("population", population)
    success_states = _count("success_states", success_states)
    draws = _count("draws", draws)
    successes_drawn = _count("successes_drawn", successes_drawn)
    if population <= 0 or success_states > population or draws > population:
        raise ProbabilityError("invalid hypergeometric population/draw counts")
    if successes_drawn > success_states or successes_drawn > draws:
        value = 0.0
    elif draws - successes_drawn > population - success_states:
        value = 0.0
    else:
        value = (
            math.comb(success_states, successes_drawn)
            * math.comb(population - success_states, draws - successes_drawn)
            / math.comb(population, draws)
        )
    return ProbabilityAssessment(
        ProbabilityLens.GAME_CHANCE,
        AssessmentShape.POINT,
        estimate=value,
        lower=value,
        upper=value,
        provenance=tuple(provenance),
        metadata={
            "game": "sampling_without_replacement",
            "population": population,
            "success_states": success_states,
            "draws": draws,
            "successes_drawn": successes_drawn,
            "exact": True,
        },
    )

def memory_pair_next_flip_probability(
    total_pairs: int,
    removed_pairs: int,
    known_singletons: int,
    *,
    targeting_known_singleton: bool = False,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    """Exact chance for the next unknown flip in a pair-matching memory game."""
    total_pairs = _count("total_pairs", total_pairs)
    removed_pairs = _count("removed_pairs", removed_pairs)
    known_singletons = _count("known_singletons", known_singletons)
    if total_pairs <= 0 or removed_pairs > total_pairs:
        raise ProbabilityError("invalid memory-game pair counts")
    remaining_cards = 2 * (total_pairs - removed_pairs)
    if known_singletons > remaining_cards:
        raise ProbabilityError("known_singletons exceeds remaining face-down cards")
    face_down_unknown = remaining_cards - known_singletons
    if face_down_unknown == 0:
        value = 0.0
    elif targeting_known_singleton:
        value = 1.0 / face_down_unknown
    else:
        value = min(1.0, known_singletons / face_down_unknown)
    return ProbabilityAssessment(
        ProbabilityLens.GAME_CHANCE,
        AssessmentShape.POINT,
        estimate=value,
        lower=value,
        upper=value,
        provenance=tuple(provenance),
        metadata={
            "game": "memory_pair_matching",
            "total_pairs": total_pairs,
            "removed_pairs": removed_pairs,
            "known_singletons": known_singletons,
            "face_down_unknown": max(0, face_down_unknown),
            "targeting_known_singleton": bool(targeting_known_singleton),
            "conditional_on_correct_memory": True,
        },
    )

def categorical_entropy(probabilities: Sequence[float], *, base: float = 2.0) -> float:
    values = [probability("probability", value) for value in probabilities]
    if not values or not math.isclose(sum(values), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ProbabilityError("categorical probabilities must be non-empty and sum to one")
    base = finite_number("entropy base", base)
    if base <= 1:
        raise ProbabilityError("entropy base must exceed one")
    denominator = math.log(base)
    return -sum(value * math.log(value) / denominator for value in values if value > 0.0)

def surprisal_probability(
    event_probability: float,
    *,
    base: float = 2.0,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    p = probability("event_probability", event_probability)
    base = finite_number("surprisal base", base)
    if base <= 1:
        raise ProbabilityError("surprisal base must exceed one")
    surprise = math.inf if p == 0.0 else -math.log(p) / math.log(base)
    return ProbabilityAssessment(
        ProbabilityLens.SURPRISAL,
        AssessmentShape.POINT,
        estimate=p,
        lower=p,
        upper=p,
        provenance=tuple(provenance),
        metadata={"surprisal": "inf" if math.isinf(surprise) else surprise, "base": base},
    )

def expected_information_gain(
    prior: Sequence[float],
    posterior_scenarios: Sequence[tuple[float, Sequence[float]]],
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    prior_values = [probability("prior", value) for value in prior]
    if not prior_values or not math.isclose(sum(prior_values), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ProbabilityError("prior must be non-empty and sum to one")
    prior_entropy = categorical_entropy(prior_values)
    weighted_entropy = 0.0
    weight_total = 0.0
    for weight, posterior in posterior_scenarios:
        w = probability("scenario_weight", weight)
        posterior_values = [probability("posterior", value) for value in posterior]
        if len(posterior_values) != len(prior_values):
            raise ProbabilityError("posterior scenarios must use the same state space as the prior")
        if not posterior_values or not math.isclose(sum(posterior_values), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ProbabilityError("each posterior scenario must sum to one")
        weighted_entropy += w * categorical_entropy(posterior_values)
        weight_total += w
    if not math.isclose(weight_total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ProbabilityError("posterior scenario weights must sum to one")
    gain = max(0.0, prior_entropy - weighted_entropy)
    normalized = 0.0 if prior_entropy <= _EPS else min(1.0, gain / prior_entropy)
    return ProbabilityAssessment(
        ProbabilityLens.INFORMATION_GAIN,
        AssessmentShape.EVIDENCE_WEIGHT,
        estimate=normalized,
        provenance=tuple(provenance),
        metadata={
            "prior_entropy_bits": prior_entropy,
            "expected_posterior_entropy_bits": weighted_entropy,
            "information_gain_bits": gain,
            "normalized_information_gain": normalized,
        },
    )

def discrete_cvar(
    outcomes: Sequence[tuple[float, float]],
    *,
    alpha: float = 0.10,
    lower_tail: bool = True,
) -> float:
    """Conditional value at risk for a discrete utility distribution."""
    alpha = probability("alpha", alpha)
    if alpha <= 0.0:
        raise ProbabilityError("alpha must be positive")
    values: list[tuple[float, float]] = []
    total = 0.0
    for utility, weight in outcomes:
        u = finite_number("utility", utility)
        w = probability("weight", weight)
        values.append((u, w))
        total += w
    if not values or not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ProbabilityError("outcome weights must sum to one")
    values.sort(key=lambda item: item[0], reverse=not lower_tail)
    remaining = alpha
    accumulated = 0.0
    used = 0.0
    for utility, weight in values:
        take = min(weight, remaining)
        accumulated += take * utility
        used += take
        remaining -= take
        if remaining <= _EPS:
            break
    if used <= 0:
        raise ProbabilityError("empty CVaR tail")
    return accumulated / used

def ensemble_model_probability(
    assessments: Sequence[ProbabilityAssessment],
    *,
    weights: Sequence[float] | None = None,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    values = tuple(assessment for assessment in assessments if assessment.estimate is not None)
    if not values:
        raise ProbabilityError("ensemble requires point-like component estimates")
    if weights is None:
        raw_weights = [1.0] * len(values)
    else:
        if len(weights) != len(values):
            raise ProbabilityError("ensemble weight length mismatch")
        raw_weights = [_non_negative("ensemble weight", weight) for weight in weights]
    total = sum(raw_weights)
    if total <= 0.0:
        raise ProbabilityError("ensemble weights sum to zero")
    normalized = [weight / total for weight in raw_weights]
    component = [float(value.estimate) for value in values if value.estimate is not None]
    mean = sum(weight * value for weight, value in zip(normalized, component))
    variance = sum(weight * (value - mean) ** 2 for weight, value in zip(normalized, component))
    disagreement = math.sqrt(max(0.0, variance))
    radius = min(0.5, 1.959963984540054 * disagreement)
    return ProbabilityAssessment(
        ProbabilityLens.ENSEMBLE_MODEL,
        AssessmentShape.POINT,
        estimate=mean,
        lower=max(0.0, mean - radius),
        upper=min(1.0, mean + radius),
        provenance=tuple(provenance),
        metadata={
            "weights": normalized,
            "component_fingerprints": [value.fingerprint for value in values],
            "between_model_sd": disagreement,
            "effective_models": 1.0 / sum(weight * weight for weight in normalized),
        },
    )

def aleatoric_epistemic_assessment(
    predictive_variance: float,
    expected_noise_variance: float,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    total = _non_negative("predictive_variance", predictive_variance)
    aleatoric = _non_negative("expected_noise_variance", expected_noise_variance)
    epistemic = max(0.0, total - aleatoric)
    denominator = max(_EPS, total)
    epistemic_fraction = min(1.0, epistemic / denominator)
    return ProbabilityAssessment(
        ProbabilityLens.ALEATORIC_EPISTEMIC,
        AssessmentShape.EVIDENCE_WEIGHT,
        estimate=epistemic_fraction,
        provenance=tuple(provenance),
        metadata={
            "predictive_variance": total,
            "aleatoric_variance": min(total, aleatoric),
            "epistemic_variance": epistemic,
            "estimate_semantics": "fraction_of_predictive_variance_attributed_to_epistemic_uncertainty",
        },
    )

def conformal_coverage_assessment(
    covered: int,
    total: int,
    *,
    target_coverage: float,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    empirical = frequentist_probability(covered, total, provenance=provenance)
    target = probability("target_coverage", target_coverage)
    return ProbabilityAssessment(
        ProbabilityLens.CONFORMAL_COVERAGE,
        AssessmentShape.POINT,
        estimate=empirical.estimate,
        lower=empirical.lower,
        upper=empirical.upper,
        effective_samples=empirical.effective_samples,
        calibrated=True,
        provenance=empirical.provenance,
        metadata={
            "target_coverage": target,
            "coverage_gap": None if empirical.estimate is None else empirical.estimate - target,
            "exchangeability_required_for_nominal_guarantee": True,
            "interval": "wilson_95",
        },
    )

def hidden_state_binary_update(
    prior_state_probability: float,
    observation_likelihood_if_state: float,
    observation_likelihood_if_not_state: float,
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    prior = probability("prior_state_probability", prior_state_probability)
    yes = probability("observation_likelihood_if_state", observation_likelihood_if_state)
    no = probability("observation_likelihood_if_not_state", observation_likelihood_if_not_state)
    evidence = yes * prior + no * (1.0 - prior)
    if evidence <= 0.0:
        raise ProbabilityError("hidden-state observation has zero marginal probability")
    posterior = yes * prior / evidence
    return ProbabilityAssessment(
        ProbabilityLens.HIDDEN_STATE,
        AssessmentShape.POINT,
        estimate=posterior,
        provenance=tuple(provenance),
        metadata={
            "prior": prior,
            "likelihood_if_state": yes,
            "likelihood_if_not_state": no,
            "observation_probability": evidence,
        },
    )

def robust_bayes_envelope(
    posterior_probabilities: Sequence[float],
    *,
    provenance: Sequence[str] = (),
) -> ProbabilityAssessment:
    values = [probability("posterior_probability", value) for value in posterior_probabilities]
    if not values:
        raise ProbabilityError("robust Bayes envelope needs posterior candidates")
    lower = min(values)
    upper = max(values)
    return ProbabilityAssessment(
        ProbabilityLens.ROBUST_BAYES,
        AssessmentShape.INTERVAL,
        lower=lower,
        upper=upper,
        provenance=tuple(provenance),
        metadata={
            "candidate_count": len(values),
            "midpoint": (lower + upper) / 2.0,
            "width": upper - lower,
            "semantics": "posterior_envelope_across_admissible_models_or_priors",
        },
    )

class ProbabilityWorkbench:
    """Small façade exposing common predictive diagnostics and lens metadata."""

    @staticmethod
    def lenses() -> tuple[ProbabilityLens, ...]:
        return tuple(ProbabilityLens)

    @staticmethod
    def calibration_report(probabilities: Sequence[float], outcomes: Sequence[bool | int]) -> dict[str, float]:
        return {
            "brier": brier_score(probabilities, outcomes),
            "log_loss": log_loss(probabilities, outcomes),
            "ece_10": expected_calibration_error(probabilities, outcomes, bins=10),
        }

    @staticmethod
    def fingerprint() -> str:
        return stable_fingerprint([lens.value for lens in ProbabilityLens])
