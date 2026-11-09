"""Frontier uncertainty and sequential-inference contracts for Jeeves.

``probability_lenses`` provides the deliberately small 18-lens engineering
foundation. ``advanced_uncertainty`` adds calibration, semantic uncertainty,
conformal/risk, information and model-disagreement diagnostics.  This module is
the next layer: sequential validity, partial identification, distribution shift,
dependence, rare events, hierarchical uncertainty, transport, game probability,
and memory interference.

The guiding rule is semantic typing.  A p-value, e-value, confidence sequence,
posterior probability, identification interval, dependence coefficient, risk
functional and Monte-Carlo error are not interchangeable.  Every result states
what quantity it is and the assumptions under which it is meaningful.

Reference algorithms are intentionally dependency-free.  Lenses whose serious
production implementation requires specialized statistical/numerical machinery
are registered as adapter-required contracts rather than approximated with a
misleading scalar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .types import AgentContractError, finite_number, json_safe, positive_int, probability, stable_fingerprint

_EPS = 1e-15


class FrontierUncertaintyError(AgentContractError):
    pass


class QuantityKind(str, Enum):
    PROBABILITY = "probability"
    INTERVAL = "interval"
    POSTERIOR = "posterior"
    P_VALUE = "p_value"
    E_VALUE = "e_value"
    CONFIDENCE_SEQUENCE = "confidence_sequence"
    RISK = "risk"
    SCORE = "score"
    INFORMATION = "information"
    DEPENDENCE = "dependence"
    IDENTIFICATION_SET = "identification_set"
    SHIFT_DIAGNOSTIC = "shift_diagnostic"
    EFFECTIVE_SAMPLE_SIZE = "effective_sample_size"
    DECISION_DIAGNOSTIC = "decision_diagnostic"


class ImplementationStatus(str, Enum):
    REFERENCE = "reference"
    CONTRACT_ONLY = "contract_only"
    ADAPTER_REQUIRED = "adapter_required"


class FrontierLens(str, Enum):
    DIRICHLET_MULTINOMIAL = "dirichlet_multinomial"
    BETA_BINOMIAL_PREDICTIVE = "beta_binomial_predictive"
    HIERARCHICAL_BAYES_SHRINKAGE = "hierarchical_bayes_shrinkage"
    EMPIRICAL_BAYES = "empirical_bayes"
    BAYESIAN_BOOTSTRAP = "bayesian_bootstrap"
    BOOTSTRAP_INTERVAL = "bootstrap_interval"
    JACKKNIFE_INFLUENCE = "jackknife_influence"
    GAUSSIAN_PROCESS_PREDICTIVE = "gaussian_process_predictive"
    HIDDEN_MARKOV_FILTER = "hidden_markov_filter"
    PARTICLE_FILTER_ESS = "particle_filter_ess"
    SEQUENTIAL_LIKELIHOOD_RATIO = "sequential_likelihood_ratio"
    E_VALUE = "e_value"
    ANYTIME_CONFIDENCE_SEQUENCE = "anytime_confidence_sequence"
    E_CONFORMAL = "e_conformal"
    PREQUENTIAL_SCORE = "prequential_score"
    EXCHANGEABILITY_DIAGNOSTIC = "exchangeability_diagnostic"
    COVARIATE_SHIFT = "covariate_shift"
    LABEL_SHIFT = "label_shift"
    CONCEPT_SHIFT = "concept_shift"
    WASSERSTEIN_AMBIGUITY = "wasserstein_ambiguity"
    CREDAL_SET = "credal_set"
    MODEL_STACKING = "model_stacking"
    DECISION_WEIGHTED_CALIBRATION = "decision_weighted_calibration"
    PARTIAL_IDENTIFICATION = "partial_identification"
    MANSKI_BOUNDS = "manski_bounds"
    CAUSAL_SENSITIVITY = "causal_sensitivity"
    TRANSPORTABILITY = "transportability"
    MEDIATION_EFFECTS = "mediation_effects"
    INTERFERENCE_SPILLOVER = "interference_spillover"
    COPULA_DEPENDENCE = "copula_dependence"
    MUTUAL_INFORMATION_DEPENDENCE = "mutual_information_dependence"
    COMPETING_RISKS = "competing_risks"
    EXTREME_VALUE_TAIL = "extreme_value_tail"
    RARE_EVENT_IMPORTANCE_SAMPLING = "rare_event_importance_sampling"
    IMPORTANCE_WEIGHT_ESS = "importance_weight_ess"
    HYPERGEOMETRIC_GAME = "hypergeometric_game"
    HETEROGENEOUS_DICE = "heterogeneous_dice"
    MARKOV_HITTING_PROBABILITY = "markov_hitting_probability"
    BAYESIAN_OPPONENT_MODEL = "bayesian_opponent_model"
    MEMORY_FORGETTING_HAZARD = "memory_forgetting_hazard"
    MEMORY_CUE_COMPETITION = "memory_cue_competition"
    MEMORY_INTERFERENCE = "memory_interference"
    RETRIEVAL_PRACTICE_GAIN = "retrieval_practice_gain"


@dataclass(frozen=True, slots=True)
class FrontierLensContract:
    lens: FrontierLens
    quantity: QuantityKind
    lineage_year: int
    description: str
    use_when: str
    invalid_when: str
    implementation: ImplementationStatus
    assumptions: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.lens, FrontierLens):
            object.__setattr__(self, "lens", FrontierLens(str(self.lens)))
        if not isinstance(self.quantity, QuantityKind):
            object.__setattr__(self, "quantity", QuantityKind(str(self.quantity)))
        if not isinstance(self.implementation, ImplementationStatus):
            object.__setattr__(self, "implementation", ImplementationStatus(str(self.implementation)))
        if isinstance(self.lineage_year, bool) or not isinstance(self.lineage_year, int):
            raise FrontierUncertaintyError("lineage_year must be integer")
        object.__setattr__(self, "assumptions", tuple(str(x) for x in self.assumptions if str(x)))
        object.__setattr__(self, "tags", tuple(sorted({str(x).casefold() for x in self.tags if str(x).strip()})))


@dataclass(frozen=True, slots=True)
class FrontierMeasurement:
    lens: FrontierLens
    quantity: QuantityKind
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    valid: bool = True
    assumptions: tuple[str, ...] = ()
    sample_size: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.lens, FrontierLens):
            object.__setattr__(self, "lens", FrontierLens(str(self.lens)))
        if not isinstance(self.quantity, QuantityKind):
            object.__setattr__(self, "quantity", QuantityKind(str(self.quantity)))
        if self.value is not None:
            object.__setattr__(self, "value", finite_number("measurement value", self.value))
        if self.lower is not None:
            object.__setattr__(self, "lower", finite_number("measurement lower", self.lower))
        if self.upper is not None:
            object.__setattr__(self, "upper", finite_number("measurement upper", self.upper))
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise FrontierUncertaintyError("measurement lower exceeds upper")
        if self.sample_size is not None:
            n = finite_number("sample_size", self.sample_size)
            if n < 0:
                raise FrontierUncertaintyError("sample_size must be non-negative")
            object.__setattr__(self, "sample_size", n)
        object.__setattr__(self, "assumptions", tuple(str(x) for x in self.assumptions if str(x)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "lens": self.lens.value,
                "quantity": self.quantity.value,
                "value": self.value,
                "lower": self.lower,
                "upper": self.upper,
                "valid": self.valid,
                "assumptions": self.assumptions,
                "sample_size": self.sample_size,
                "metadata": self.metadata,
            }
        )


def _nonnegative(name: str, value: float) -> float:
    result = finite_number(name, value)
    if result < 0:
        raise FrontierUncertaintyError(f"{name} must be non-negative")
    return result


def _positive(name: str, value: float) -> float:
    result = finite_number(name, value)
    if result <= 0:
        raise FrontierUncertaintyError(f"{name} must be positive")
    return result


def _contract(
    lens: FrontierLens,
    quantity: QuantityKind,
    year: int,
    description: str,
    use_when: str,
    invalid_when: str,
    implementation: ImplementationStatus,
    assumptions: Sequence[str] = (),
    tags: Sequence[str] = (),
) -> FrontierLensContract:
    return FrontierLensContract(lens, quantity, year, description, use_when, invalid_when, implementation, tuple(assumptions), tuple(tags))


def frontier_lens_contracts() -> tuple[FrontierLensContract, ...]:
    return (
        _contract(FrontierLens.DIRICHLET_MULTINOMIAL, QuantityKind.POSTERIOR, 1920, "Posterior/predictive uncertainty for categorical outcomes.", "Repeated categorical outcomes with exchangeable counts.", "Categories or sampling regime change without modeling that change.", ImplementationStatus.REFERENCE, ("categorical exchangeability conditional on parameters",)),
        _contract(FrontierLens.BETA_BINOMIAL_PREDICTIVE, QuantityKind.POSTERIOR, 1940, "Posterior predictive count distribution for Bernoulli trials.", "Future success counts under uncertain Bernoulli rate.", "Trials have materially different rates or dependencies.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.HIERARCHICAL_BAYES_SHRINKAGE, QuantityKind.POSTERIOR, 1970, "Partial pooling across related groups.", "Groups share structure but are not identical.", "Pooling hierarchy is misspecified or groups are unrelated.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.EMPIRICAL_BAYES, QuantityKind.POSTERIOR, 1950, "Estimate prior hyperparameters from the ensemble of observed units.", "Many related estimation tasks exist.", "Using the same data for hyperparameter estimation is ignored in uncertainty claims.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.BAYESIAN_BOOTSTRAP, QuantityKind.POSTERIOR, 1981, "Dirichlet reweighting of empirical observations.", "A nonparametric Bayesian functional estimate is desired.", "Observation dependence invalidates the empirical support assumption.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.BOOTSTRAP_INTERVAL, QuantityKind.INTERVAL, 1979, "Resampling interval for a statistic.", "Sampling units are approximately exchangeable and statistic is bootstrap-regular.", "Strong dependence, tiny samples, or nonregular statistic without specialized bootstrap.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.JACKKNIFE_INFLUENCE, QuantityKind.DECISION_DIAGNOSTIC, 1958, "Leave-one-out sensitivity/influence diagnostic.", "Detecting observations that dominate an estimator.", "Dependence structure makes single-unit deletion meaningless.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.GAUSSIAN_PROCESS_PREDICTIVE, QuantityKind.POSTERIOR, 1990, "Function-space predictive posterior with kernel-defined similarity.", "Smooth structured function uncertainty is appropriate.", "Kernel/noise model is unjustified or scale makes exact inference infeasible.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.HIDDEN_MARKOV_FILTER, QuantityKind.POSTERIOR, 1966, "Filtering distribution over latent discrete states.", "Sequential observations depend on hidden Markov state.", "State process is materially non-Markov or emission model invalid.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.PARTICLE_FILTER_ESS, QuantityKind.EFFECTIVE_SAMPLE_SIZE, 1993, "Weight-degeneracy diagnostic for sequential Monte Carlo.", "Weighted particles approximate a filtering distribution.", "Weights are not normalized/importance-valid.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.SEQUENTIAL_LIKELIHOOD_RATIO, QuantityKind.SCORE, 1945, "Sequential evidence accumulation through likelihood ratios.", "Two explicit data-generating hypotheses are available.", "Likelihood models are misspecified or optional stopping validity is assumed without sequential design.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.E_VALUE, QuantityKind.E_VALUE, 2019, "Nonnegative evidence variable with expectation at most one under the null.", "Anytime-valid evidence under an e-process/e-value construction.", "Input is merely renamed likelihood/confidence without the null expectation guarantee.", ImplementationStatus.REFERENCE, ("valid e-factor/e-process under null",)),
        _contract(FrontierLens.ANYTIME_CONFIDENCE_SEQUENCE, QuantityKind.CONFIDENCE_SEQUENCE, 1960, "Sequence of intervals intended to cover the target simultaneously over time.", "Inference may be inspected/stopped adaptively.", "Per-time intervals are reused as if time-uniform without correction.", ImplementationStatus.REFERENCE, ("bounded independent observations for reference implementation",)),
        _contract(FrontierLens.E_CONFORMAL, QuantityKind.INTERVAL, 2025, "Conformal uncertainty built with e-value machinery for expanded sequential/batch settings.", "Conformal prediction needs anytime/batch flexibility.", "Required exchangeability/e-validity conditions are not established.", ImplementationStatus.CONTRACT_ONLY, tags=("2025", "conformal", "sequential")),
        _contract(FrontierLens.PREQUENTIAL_SCORE, QuantityKind.SCORE, 1984, "Evaluate forecasts in temporal order before outcomes are observed.", "Online predictive systems are compared without lookahead.", "Predictions were revised after seeing outcomes.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.EXCHANGEABILITY_DIAGNOSTIC, QuantityKind.SHIFT_DIAGNOSTIC, 1930, "Diagnostic for order/regime effects that threaten exchangeability-based guarantees.", "Conformal/bootstrap/IID claims depend on exchangeability.", "A diagnostic pass is mistaken for proof of exchangeability.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.COVARIATE_SHIFT, QuantityKind.SHIFT_DIAGNOSTIC, 1990, "Change in input distribution with approximately stable conditional outcome mechanism.", "Deployment inputs differ from training inputs.", "Conditional outcome mechanism changes too.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.LABEL_SHIFT, QuantityKind.SHIFT_DIAGNOSTIC, 1990, "Change in outcome prevalence with approximately stable class-conditional input distribution.", "Class priors change across domains.", "Class-conditional features also drift materially.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.CONCEPT_SHIFT, QuantityKind.SHIFT_DIAGNOSTIC, 1990, "Change in conditional outcome mechanism.", "The same inputs acquire different outcome mapping over time/domain.", "Only marginal input distribution changed.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.WASSERSTEIN_AMBIGUITY, QuantityKind.RISK, 2010, "Distributionally robust risk over a Wasserstein neighborhood.", "Robustness to nearby distributions is decision-relevant.", "Metric/radius has no domain justification.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.CREDAL_SET, QuantityKind.IDENTIFICATION_SET, 1980, "Set of plausible probability distributions rather than one precise distribution.", "Evidence justifies bounds/sets but not a unique prior/model.", "Set construction is arbitrary or too broad to be decision-useful.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.MODEL_STACKING, QuantityKind.POSTERIOR, 2010, "Combine predictive distributions using out-of-sample predictive performance.", "Multiple models have complementary predictive strengths.", "Weights are fit/evaluated on the same outcomes without correction.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.DECISION_WEIGHTED_CALIBRATION, QuantityKind.DECISION_DIAGNOSTIC, 2020, "Calibration error weighted by downstream decision relevance.", "Some probability regions matter more for action.", "Decision weights encode hidden preference manipulation or are unstable.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.PARTIAL_IDENTIFICATION, QuantityKind.IDENTIFICATION_SET, 1990, "Return all parameter values compatible with data and maintained assumptions.", "Point identification is unjustified.", "Bounds are presented as posterior/credible intervals.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.MANSKI_BOUNDS, QuantityKind.IDENTIFICATION_SET, 1989, "Worst-case bounds under missing/latent binary outcomes with minimal assumptions.", "Missing outcomes prevent point identification.", "Additional assumptions are silently introduced to narrow bounds.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.CAUSAL_SENSITIVITY, QuantityKind.IDENTIFICATION_SET, 1950, "Vary unobserved-confounding/selection assumptions and track causal effect stability.", "Causal conclusion depends on unverifiable assumptions.", "Sensitivity parameter lacks interpretable scale or plausible range.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.TRANSPORTABILITY, QuantityKind.IDENTIFICATION_SET, 2010, "Assess whether causal/predictive knowledge transfers across populations/environments.", "Source and target domains differ.", "Selection/mechanism differences are ignored.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.MEDIATION_EFFECTS, QuantityKind.IDENTIFICATION_SET, 1980, "Separate direct/indirect pathways under explicit causal assumptions.", "Mechanisms through mediators matter.", "Cross-world/identification assumptions are not defensible.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.INTERFERENCE_SPILLOVER, QuantityKind.IDENTIFICATION_SET, 1960, "Model outcomes depending on other units' treatments/actions.", "Network/social/game interactions violate no-interference assumptions.", "Units are assumed independent despite spillovers.", ImplementationStatus.CONTRACT_ONLY),
        _contract(FrontierLens.COPULA_DEPENDENCE, QuantityKind.DEPENDENCE, 1959, "Separate marginal distributions from multivariate dependence structure.", "Joint/tail dependence matters beyond marginal probabilities.", "Copula family is selected without adequacy checks.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.MUTUAL_INFORMATION_DEPENDENCE, QuantityKind.INFORMATION, 1948, "Information shared between discrete variables without requiring linear relation.", "General discrete dependence is relevant.", "Sparse contingency counts produce unstable plug-in estimates.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.COMPETING_RISKS, QuantityKind.PROBABILITY, 1970, "Event incidence when mutually exclusive failure/event types compete.", "Several terminal causes can preclude each other.", "Cause-specific hazard is misread as cumulative incidence.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.EXTREME_VALUE_TAIL, QuantityKind.PROBABILITY, 1928, "Tail/exceedance modeling for rare extremes.", "Extrapolation beyond ordinary observations is necessary.", "Threshold/asymptotic regime is unjustified or sample tail too small.", ImplementationStatus.ADAPTER_REQUIRED),
        _contract(FrontierLens.RARE_EVENT_IMPORTANCE_SAMPLING, QuantityKind.PROBABILITY, 1950, "Estimate rare-event probability with proposal reweighting.", "Naive Monte Carlo sees too few rare events.", "Proposal support misses target-event mass or weights are invalid.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.IMPORTANCE_WEIGHT_ESS, QuantityKind.EFFECTIVE_SAMPLE_SIZE, 1990, "Diagnose effective number of samples represented by unequal importance weights.", "Weighted Monte Carlo is used.", "ESS is mistaken for an accuracy guarantee.", ImplementationStatus.REFERENCE),
        _contract(FrontierLens.HYPERGEOMETRIC_GAME, QuantityKind.PROBABILITY, 1700, "Exact without-replacement draw probability.", "Cards/objects are sampled without replacement from known counts.", "Draws are adaptive/weighted or population composition is uncertain.", ImplementationStatus.REFERENCE, tags=("game", "exact")),
        _contract(FrontierLens.HETEROGENEOUS_DICE, QuantityKind.PROBABILITY, 1600, "Exact convolution for independent fair dice with differing side counts.", "Tabletop/dice mechanics need exact outcome distribution.", "Dice are loaded or dependent.", ImplementationStatus.REFERENCE, tags=("game", "dice", "exact")),
        _contract(FrontierLens.MARKOV_HITTING_PROBABILITY, QuantityKind.PROBABILITY, 1906, "Probability of reaching target states before/within a horizon in a finite Markov chain.", "Board games/workflows have state-transition structure.", "Transition dynamics depend on hidden history not included in state.", ImplementationStatus.REFERENCE, tags=("game", "markov")),
        _contract(FrontierLens.BAYESIAN_OPPONENT_MODEL, QuantityKind.POSTERIOR, 1950, "Posterior over discrete opponent/actor strategy types.", "Several explicit behavior models compete.", "Opponent adapts faster than the model or likelihoods are strategically endogenous.", ImplementationStatus.REFERENCE, tags=("game", "strategic")),
        _contract(FrontierLens.MEMORY_FORGETTING_HAZARD, QuantityKind.PROBABILITY, 1885, "Probability of retrieval failure as time since reinforcement grows.", "Scheduling recall/rehearsal under a forgetting model.", "Interference/context changes dominate the time-only model.", ImplementationStatus.REFERENCE, tags=("memory",)),
        _contract(FrontierLens.MEMORY_CUE_COMPETITION, QuantityKind.PROBABILITY, 1970, "Reduce target retrieval as competing associations share the same cue.", "Associative index has multiple cue-linked candidates.", "Competition coefficient is not learned/calibrated for the memory system.", ImplementationStatus.REFERENCE, tags=("memory", "interference")),
        _contract(FrontierLens.MEMORY_INTERFERENCE, QuantityKind.DECISION_DIAGNOSTIC, 1950, "Track proactive/retroactive interference separately from pure temporal decay.", "New/old similar memories interfere with recall.", "Similarity and temporal direction are not measured.", ImplementationStatus.REFERENCE, tags=("memory", "interference")),
        _contract(FrontierLens.RETRIEVAL_PRACTICE_GAIN, QuantityKind.DECISION_DIAGNOSTIC, 1990, "Observed improvement after successful active retrieval versus passive exposure.", "Choosing what to rehearse/store in the card index.", "Practice selection bias is ignored when claiming causal benefit.", ImplementationStatus.CONTRACT_ONLY, tags=("memory", "learning")),
    )


class FrontierLensRegistry:
    def __init__(self, contracts: Iterable[FrontierLensContract] = ()) -> None:
        self._contracts = {contract.lens: contract for contract in frontier_lens_contracts()}
        for contract in contracts:
            self._contracts[contract.lens] = contract

    def get(self, lens: FrontierLens) -> FrontierLensContract:
        return self._contracts[lens if isinstance(lens, FrontierLens) else FrontierLens(str(lens))]

    def all(self) -> tuple[FrontierLensContract, ...]:
        return tuple(sorted(self._contracts.values(), key=lambda item: (item.lineage_year, item.lens.value)))

    def by_quantity(self, quantity: QuantityKind) -> tuple[FrontierLensContract, ...]:
        if not isinstance(quantity, QuantityKind):
            quantity = QuantityKind(str(quantity))
        return tuple(item for item in self.all() if item.quantity is quantity)

    def reference_implemented(self) -> tuple[FrontierLensContract, ...]:
        return tuple(item for item in self.all() if item.implementation is ImplementationStatus.REFERENCE)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint([(item.lens.value, item.quantity.value, item.implementation.value) for item in self.all()])


class BayesianCategorical:
    @staticmethod
    def dirichlet_posterior(counts: Sequence[float], *, prior: Sequence[float] | None = None) -> FrontierMeasurement:
        if not counts:
            raise FrontierUncertaintyError("Dirichlet posterior requires counts")
        observed = [_nonnegative("count", value) for value in counts]
        if prior is None:
            alpha = [1.0] * len(observed)
        else:
            if len(prior) != len(observed):
                raise FrontierUncertaintyError("prior/count dimension mismatch")
            alpha = [_positive("prior concentration", value) for value in prior]
        posterior = [a + c for a, c in zip(alpha, observed)]
        total = sum(posterior)
        probabilities = [value / total for value in posterior]
        entropy = -sum(p * math.log(max(_EPS, p), 2) for p in probabilities)
        return FrontierMeasurement(
            FrontierLens.DIRICHLET_MULTINOMIAL,
            QuantityKind.POSTERIOR,
            value=entropy,
            sample_size=sum(observed),
            assumptions=("categorical exchangeability conditional on category probabilities",),
            metadata={"posterior_alpha": posterior, "posterior_mean": probabilities, "entropy_bits": entropy},
        )

    @staticmethod
    def beta_binomial_predictive(
        successes: float,
        failures: float,
        *,
        future_trials: int,
        alpha_prior: float = 1.0,
        beta_prior: float = 1.0,
    ) -> FrontierMeasurement:
        s = _nonnegative("successes", successes)
        f = _nonnegative("failures", failures)
        n = positive_int("future_trials", future_trials, maximum=1_000_000)
        alpha = _positive("alpha_prior", alpha_prior) + s
        beta = _positive("beta_prior", beta_prior) + f
        mean_count = n * alpha / (alpha + beta)
        variance = n * alpha * beta * (alpha + beta + n) / (((alpha + beta) ** 2) * (alpha + beta + 1.0))
        return FrontierMeasurement(
            FrontierLens.BETA_BINOMIAL_PREDICTIVE,
            QuantityKind.POSTERIOR,
            value=mean_count,
            sample_size=s + f,
            assumptions=("future Bernoulli trials share a latent rate with observed trials",),
            metadata={"future_trials": n, "alpha": alpha, "beta": beta, "predictive_variance": variance},
        )

    @staticmethod
    def opponent_posterior(prior: Sequence[float], action_likelihoods: Sequence[float]) -> FrontierMeasurement:
        if not prior or len(prior) != len(action_likelihoods):
            raise FrontierUncertaintyError("opponent posterior requires equal non-empty vectors")
        priors = [probability("opponent prior", p) for p in prior]
        if sum(priors) <= 0:
            raise FrontierUncertaintyError("opponent prior has zero mass")
        priors = [p / sum(priors) for p in priors]
        likelihoods = [probability("action likelihood", p) for p in action_likelihoods]
        weights = [p * l for p, l in zip(priors, likelihoods)]
        evidence = sum(weights)
        if evidence <= 0:
            raise FrontierUncertaintyError("observed action has zero likelihood under all opponent models")
        posterior = [w / evidence for w in weights]
        entropy = -sum(p * math.log(max(_EPS, p), 2) for p in posterior)
        return FrontierMeasurement(
            FrontierLens.BAYESIAN_OPPONENT_MODEL,
            QuantityKind.POSTERIOR,
            value=entropy,
            assumptions=("candidate strategy types and action likelihoods are specified",),
            metadata={"posterior": posterior, "marginal_action_probability": evidence, "entropy_bits": entropy},
        )


class SequentialInference:
    @staticmethod
    def likelihood_ratio(log_likelihood_alt: Sequence[float], log_likelihood_null: Sequence[float]) -> FrontierMeasurement:
        if not log_likelihood_alt or len(log_likelihood_alt) != len(log_likelihood_null):
            raise FrontierUncertaintyError("likelihood ratio requires equal non-empty sequences")
        log_lr = sum(finite_number("log likelihood alt", a) - finite_number("log likelihood null", n) for a, n in zip(log_likelihood_alt, log_likelihood_null))
        # Keep the stable log scale authoritative.  Value is clipped only for a
        # finite human-facing ratio; metadata retains exact log evidence.
        ratio = math.exp(min(700.0, max(-700.0, log_lr)))
        return FrontierMeasurement(
            FrontierLens.SEQUENTIAL_LIKELIHOOD_RATIO,
            QuantityKind.SCORE,
            value=ratio,
            sample_size=float(len(log_likelihood_alt)),
            assumptions=("per-observation likelihood contributions correspond to stated hypotheses",),
            metadata={"log_likelihood_ratio": log_lr, "ratio_clipped_for_float": abs(log_lr) > 700.0},
        )

    @staticmethod
    def e_value(e_factors: Sequence[float], *, alpha: float = 0.05) -> FrontierMeasurement:
        if not e_factors:
            raise FrontierUncertaintyError("e-value requires factors")
        alpha = probability("alpha", alpha)
        if alpha <= 0.0:
            raise FrontierUncertaintyError("alpha must be positive")
        log_e = 0.0
        for factor in e_factors:
            value = _nonnegative("e-factor", factor)
            if value == 0.0:
                log_e = float("-inf")
                break
            log_e += math.log(value)
        e_value = 0.0 if log_e == float("-inf") else math.exp(min(700.0, log_e))
        threshold = 1.0 / alpha
        return FrontierMeasurement(
            FrontierLens.E_VALUE,
            QuantityKind.E_VALUE,
            value=e_value,
            sample_size=float(len(e_factors)),
            assumptions=("factors form a valid e-process/e-value construction under the null",),
            metadata={"log_e_value": log_e, "alpha": alpha, "e_reject_threshold": threshold, "crosses_threshold": log_e >= math.log(threshold) if math.isfinite(log_e) else False},
        )

    @staticmethod
    def bounded_mean_confidence_sequence(values: Sequence[float], *, alpha: float = 0.05) -> tuple[FrontierMeasurement, ...]:
        """Simple time-uniform confidence sequence via Hoeffding + union bound.

        For observations in [0,1], assign per-time error
        ``delta_t = alpha/(t(t+1))``.  Because sum_t 1/(t(t+1)) = 1,
        a union bound over fixed-time Hoeffding intervals gives simultaneous
        coverage at least ``1-alpha`` under the maintained independence/bounded
        assumptions.  It is conservative but transparent and replayable.
        """
        if not values:
            raise FrontierUncertaintyError("confidence sequence requires observations")
        alpha = probability("alpha", alpha)
        if alpha <= 0.0 or alpha >= 1.0:
            raise FrontierUncertaintyError("alpha must lie in (0,1)")
        observations = [probability("bounded observation", value) for value in values]
        results: list[FrontierMeasurement] = []
        running = 0.0
        for index, value in enumerate(observations, start=1):
            running += value
            mean = running / index
            delta_t = alpha / (index * (index + 1.0))
            radius = math.sqrt(math.log(2.0 / delta_t) / (2.0 * index))
            results.append(
                FrontierMeasurement(
                    FrontierLens.ANYTIME_CONFIDENCE_SEQUENCE,
                    QuantityKind.CONFIDENCE_SEQUENCE,
                    value=mean,
                    lower=max(0.0, mean - radius),
                    upper=min(1.0, mean + radius),
                    sample_size=float(index),
                    assumptions=("independent observations", "observations bounded in [0,1]", "union-bound Hoeffding construction"),
                    metadata={"alpha": alpha, "per_time_delta": delta_t, "radius": radius, "time": index},
                )
            )
        return tuple(results)

    @staticmethod
    def prequential_log_score(probabilities: Sequence[float], outcomes: Sequence[bool | int]) -> FrontierMeasurement:
        if not probabilities or len(probabilities) != len(outcomes):
            raise FrontierUncertaintyError("prequential score requires equal non-empty sequences")
        total = 0.0
        for p, y in zip(probabilities, outcomes):
            p = min(1.0 - 1e-12, max(1e-12, probability("forecast probability", p)))
            if y not in {0, 1, False, True}:
                raise FrontierUncertaintyError("outcomes must be binary")
            total -= math.log(p if bool(y) else 1.0 - p)
        return FrontierMeasurement(
            FrontierLens.PREQUENTIAL_SCORE,
            QuantityKind.SCORE,
            value=total / len(probabilities),
            sample_size=float(len(probabilities)),
            assumptions=("each forecast was fixed before its corresponding outcome was observed",),
            metadata={"score": "mean_log_loss", "lower_is_better": True},
        )


class IdentificationDiagnostics:
    @staticmethod
    def manski_missing_binary(successes: int, failures: int, missing: int) -> FrontierMeasurement:
        for name, value in (("successes", successes), ("failures", failures), ("missing", missing)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FrontierUncertaintyError(f"{name} must be a non-negative integer")
        total = successes + failures + missing
        if total <= 0:
            raise FrontierUncertaintyError("Manski bounds require at least one unit")
        lower = successes / total
        upper = (successes + missing) / total
        return FrontierMeasurement(
            FrontierLens.MANSKI_BOUNDS,
            QuantityKind.IDENTIFICATION_SET,
            lower=lower,
            upper=upper,
            sample_size=float(total),
            assumptions=("missing binary outcomes may be arbitrarily 0 or 1",),
            metadata={"successes": successes, "failures": failures, "missing": missing, "width": upper - lower},
        )

    @staticmethod
    def credal_envelope(probability_vectors: Sequence[Sequence[float]], *, event_index: int) -> FrontierMeasurement:
        if not probability_vectors:
            raise FrontierUncertaintyError("credal envelope requires distributions")
        estimates: list[float] = []
        for vector in probability_vectors:
            if not vector or event_index < 0 or event_index >= len(vector):
                raise FrontierUncertaintyError("invalid event index/distribution")
            values = [probability("credal probability", p) for p in vector]
            if abs(sum(values) - 1.0) > 1e-8:
                raise FrontierUncertaintyError("credal distribution is not normalized")
            estimates.append(values[event_index])
        return FrontierMeasurement(
            FrontierLens.CREDAL_SET,
            QuantityKind.IDENTIFICATION_SET,
            lower=min(estimates),
            upper=max(estimates),
            sample_size=float(len(estimates)),
            assumptions=("input distributions define the maintained plausible set",),
            metadata={"event_index": event_index, "model_probabilities": estimates},
        )


class DependenceDiagnostics:
    @staticmethod
    def mutual_information(table: Sequence[Sequence[float]]) -> FrontierMeasurement:
        if not table or not table[0] or any(len(row) != len(table[0]) for row in table):
            raise FrontierUncertaintyError("mutual information requires rectangular non-empty table")
        counts = [[_nonnegative("contingency count", value) for value in row] for row in table]
        total = sum(sum(row) for row in counts)
        if total <= 0:
            raise FrontierUncertaintyError("contingency table has zero mass")
        row_sum = [sum(row) for row in counts]
        col_sum = [sum(counts[i][j] for i in range(len(counts))) for j in range(len(counts[0]))]
        mi = 0.0
        for i, row in enumerate(counts):
            for j, count in enumerate(row):
                if count <= 0:
                    continue
                pxy = count / total
                px = row_sum[i] / total
                py = col_sum[j] / total
                mi += pxy * math.log(pxy / (px * py), 2)
        return FrontierMeasurement(
            FrontierLens.MUTUAL_INFORMATION_DEPENDENCE,
            QuantityKind.INFORMATION,
            value=mi,
            sample_size=total,
            assumptions=("plug-in discrete contingency estimate",),
            metadata={"bits": mi, "rows": len(counts), "columns": len(counts[0]), "finite_sample_bias_uncorrected": True},
        )

    @staticmethod
    def categorical_total_variation(reference: Sequence[float], current: Sequence[float]) -> FrontierMeasurement:
        if not reference or len(reference) != len(current):
            raise FrontierUncertaintyError("shift diagnostic requires equal non-empty distributions")
        left = [probability("reference probability", p) for p in reference]
        right = [probability("current probability", p) for p in current]
        if abs(sum(left) - 1.0) > 1e-8 or abs(sum(right) - 1.0) > 1e-8:
            raise FrontierUncertaintyError("shift distributions must sum to one")
        tv = 0.5 * sum(abs(a - b) for a, b in zip(left, right))
        return FrontierMeasurement(
            FrontierLens.COVARIATE_SHIFT,
            QuantityKind.SHIFT_DIAGNOSTIC,
            value=tv,
            assumptions=("categorical marginals are comparable across regimes",),
            metadata={"metric": "total_variation", "reference": left, "current": right},
        )


class MonteCarloDiagnostics:
    @staticmethod
    def importance_weight_ess(weights: Sequence[float]) -> FrontierMeasurement:
        if not weights:
            raise FrontierUncertaintyError("ESS requires weights")
        values = [_nonnegative("importance weight", value) for value in weights]
        total = sum(values)
        if total <= 0:
            raise FrontierUncertaintyError("importance weights sum to zero")
        normalized = [value / total for value in values]
        ess = 1.0 / sum(value * value for value in normalized)
        return FrontierMeasurement(
            FrontierLens.IMPORTANCE_WEIGHT_ESS,
            QuantityKind.EFFECTIVE_SAMPLE_SIZE,
            value=ess,
            sample_size=float(len(values)),
            assumptions=("weights represent valid importance ratios up to common scale",),
            metadata={"relative_ess": ess / len(values), "max_normalized_weight": max(normalized)},
        )

    @staticmethod
    def rare_event_self_normalized(indicators: Sequence[bool | int], log_weights: Sequence[float]) -> FrontierMeasurement:
        if not indicators or len(indicators) != len(log_weights):
            raise FrontierUncertaintyError("rare-event importance estimate requires equal non-empty sequences")
        if any(value not in {0, 1, False, True} for value in indicators):
            raise FrontierUncertaintyError("rare-event indicators must be binary")
        logs = [finite_number("log importance weight", value) for value in log_weights]
        maximum = max(logs)
        weights = [math.exp(value - maximum) for value in logs]
        total = sum(weights)
        estimate = sum(weight * float(bool(event)) for weight, event in zip(weights, indicators)) / total
        normalized = [weight / total for weight in weights]
        ess = 1.0 / sum(weight * weight for weight in normalized)
        event_weight = sum(weight for weight, event in zip(normalized, indicators) if bool(event))
        return FrontierMeasurement(
            FrontierLens.RARE_EVENT_IMPORTANCE_SAMPLING,
            QuantityKind.PROBABILITY,
            value=estimate,
            lower=0.0,
            upper=1.0,
            sample_size=float(len(indicators)),
            assumptions=("proposal support covers target event", "provided log weights are valid target/proposal ratios up to scale"),
            metadata={"self_normalized": True, "ess": ess, "relative_ess": ess / len(indicators), "event_weight": event_weight, "unbiased": False},
        )


class GameProbability:
    @staticmethod
    def heterogeneous_dice_distribution(sides: Sequence[int]) -> tuple[float, ...]:
        if not sides:
            raise FrontierUncertaintyError("dice distribution requires dice")
        side_counts = [positive_int("die sides", int(value), maximum=10_000) for value in sides]
        if any(value < 2 for value in side_counts):
            raise FrontierUncertaintyError("each die must have at least two sides")
        counts = [1]
        minimum_sum = 0
        for die_sides in side_counts:
            next_counts = [0] * (len(counts) + die_sides)
            for current_sum, ways in enumerate(counts):
                for face in range(1, die_sides + 1):
                    next_counts[current_sum + face] += ways
            counts = next_counts
            minimum_sum += 1
        total = math.prod(side_counts)
        return tuple(count / total for count in counts)

    @staticmethod
    def dice_event(sides: Sequence[int], *, minimum_sum: int | None = None, maximum_sum: int | None = None) -> FrontierMeasurement:
        distribution = GameProbability.heterogeneous_dice_distribution(sides)
        low = len(sides) if minimum_sum is None else int(minimum_sum)
        high = sum(int(value) for value in sides) if maximum_sum is None else int(maximum_sum)
        if low > high:
            raise FrontierUncertaintyError("minimum_sum exceeds maximum_sum")
        estimate = sum(p for total, p in enumerate(distribution) if low <= total <= high)
        return FrontierMeasurement(
            FrontierLens.HETEROGENEOUS_DICE,
            QuantityKind.PROBABILITY,
            value=estimate,
            lower=estimate,
            upper=estimate,
            assumptions=("independent fair dice",),
            metadata={"sides": list(sides), "minimum_sum": low, "maximum_sum": high, "exact": True},
        )

    @staticmethod
    def hypergeometric_exact(population: int, successes: int, draws: int, *, exactly: int) -> FrontierMeasurement:
        n = positive_int("population", population, maximum=10_000_000)
        k = int(successes)
        d = int(draws)
        x = int(exactly)
        if k < 0 or k > n or d < 0 or d > n or x < 0 or x > d or x > k or d - x > n - k:
            estimate = 0.0
        else:
            estimate = math.comb(k, x) * math.comb(n - k, d - x) / math.comb(n, d)
        return FrontierMeasurement(
            FrontierLens.HYPERGEOMETRIC_GAME,
            QuantityKind.PROBABILITY,
            value=estimate,
            lower=estimate,
            upper=estimate,
            assumptions=("uniform sampling without replacement",),
            metadata={"population": n, "success_states": k, "draws": d, "exact_successes": x, "exact": True},
        )

    @staticmethod
    def markov_hitting_probability(
        transition: Sequence[Sequence[float]],
        *,
        start: int,
        targets: Sequence[int],
        horizon: int,
    ) -> FrontierMeasurement:
        if not transition or any(len(row) != len(transition) for row in transition):
            raise FrontierUncertaintyError("transition matrix must be non-empty and square")
        size = len(transition)
        if start < 0 or start >= size:
            raise FrontierUncertaintyError("invalid start state")
        target_set = {int(value) for value in targets}
        if not target_set or any(value < 0 or value >= size for value in target_set):
            raise FrontierUncertaintyError("invalid target states")
        steps = positive_int("horizon", horizon, maximum=1_000_000)
        matrix: list[list[float]] = []
        for row in transition:
            values = [probability("transition probability", p) for p in row]
            if abs(sum(values) - 1.0) > 1e-8:
                raise FrontierUncertaintyError("transition rows must sum to one")
            matrix.append(values)
        state = [0.0] * size
        state[start] = 1.0
        hit = 1.0 if start in target_set else 0.0
        if hit:
            state[start] = 0.0
        for _ in range(steps):
            next_state = [0.0] * size
            for source, mass in enumerate(state):
                if mass <= 0:
                    continue
                for destination, p in enumerate(matrix[source]):
                    moved = mass * p
                    if destination in target_set:
                        hit += moved
                    else:
                        next_state[destination] += moved
            state = next_state
        hit = min(1.0, max(0.0, hit))
        return FrontierMeasurement(
            FrontierLens.MARKOV_HITTING_PROBABILITY,
            QuantityKind.PROBABILITY,
            value=hit,
            lower=hit,
            upper=hit,
            assumptions=("time-homogeneous Markov transition matrix",),
            metadata={"start": start, "targets": sorted(target_set), "horizon": steps, "remaining_nonhit_mass": sum(state)},
        )


class MemoryUncertainty:
    @staticmethod
    def forgetting_hazard(*, elapsed: float, stability: float) -> FrontierMeasurement:
        elapsed = _nonnegative("elapsed", elapsed)
        stability = _positive("stability", stability)
        retrieval = math.exp(-elapsed / stability)
        failure = 1.0 - retrieval
        return FrontierMeasurement(
            FrontierLens.MEMORY_FORGETTING_HAZARD,
            QuantityKind.PROBABILITY,
            value=failure,
            lower=failure,
            upper=failure,
            assumptions=("exponential forgetting reference curve", "no explicit interference term"),
            metadata={"elapsed": elapsed, "stability": stability, "retrieval_probability": retrieval},
        )

    @staticmethod
    def cue_competition(
        base_retrieval_probability: float,
        competing_association_strengths: Sequence[float],
        *,
        competition_scale: float = 1.0,
    ) -> FrontierMeasurement:
        base = probability("base_retrieval_probability", base_retrieval_probability)
        scale = _nonnegative("competition_scale", competition_scale)
        strengths = [probability("association strength", value) for value in competing_association_strengths]
        burden = scale * sum(strengths)
        # Odds-domain competition: competitors reduce target odds rather than
        # subtracting probability linearly, keeping the result in [0,1].
        clipped = min(1.0 - 1e-12, max(1e-12, base))
        odds = clipped / (1.0 - clipped)
        adjusted_odds = odds / (1.0 + burden)
        adjusted = adjusted_odds / (1.0 + adjusted_odds)
        return FrontierMeasurement(
            FrontierLens.MEMORY_CUE_COMPETITION,
            QuantityKind.PROBABILITY,
            value=adjusted,
            lower=adjusted,
            upper=adjusted,
            assumptions=("competition scale calibrated for this retrieval system",),
            metadata={"base_probability": base, "competition_burden": burden, "competitor_count": len(strengths)},
        )

    @staticmethod
    def interference(
        *,
        target_similarity: float,
        proactive_similarity: float,
        retroactive_similarity: float,
        temporal_overlap: float,
    ) -> FrontierMeasurement:
        target = probability("target_similarity", target_similarity)
        proactive = probability("proactive_similarity", proactive_similarity)
        retroactive = probability("retroactive_similarity", retroactive_similarity)
        overlap = probability("temporal_overlap", temporal_overlap)
        proactive_risk = proactive * overlap
        retroactive_risk = retroactive * overlap
        # Similarity to the target can make interference more confusable; noisy
        # OR avoids cancellation between proactive and retroactive channels.
        risk = 1.0 - (1.0 - proactive_risk * target) * (1.0 - retroactive_risk * target)
        return FrontierMeasurement(
            FrontierLens.MEMORY_INTERFERENCE,
            QuantityKind.DECISION_DIAGNOSTIC,
            value=risk,
            assumptions=("similarity scores are calibrated comparably",),
            metadata={"proactive_risk": proactive_risk, "retroactive_risk": retroactive_risk, "target_similarity": target},
        )


class DecisionCalibration:
    @staticmethod
    def weighted_brier(probabilities: Sequence[float], outcomes: Sequence[bool | int], decision_weights: Sequence[float]) -> FrontierMeasurement:
        if not probabilities or len(probabilities) != len(outcomes) or len(probabilities) != len(decision_weights):
            raise FrontierUncertaintyError("weighted calibration requires equal non-empty sequences")
        weights = [_nonnegative("decision weight", value) for value in decision_weights]
        total = sum(weights)
        if total <= 0:
            raise FrontierUncertaintyError("decision weights sum to zero")
        loss = 0.0
        for p, y, weight in zip(probabilities, outcomes, weights):
            p = probability("forecast probability", p)
            if y not in {0, 1, False, True}:
                raise FrontierUncertaintyError("outcomes must be binary")
            loss += weight * (p - float(bool(y))) ** 2
        return FrontierMeasurement(
            FrontierLens.DECISION_WEIGHTED_CALIBRATION,
            QuantityKind.DECISION_DIAGNOSTIC,
            value=loss / total,
            sample_size=float(len(probabilities)),
            assumptions=("decision weights are fixed independently of the realized forecast errors",),
            metadata={"score": "weighted_brier", "weight_sum": total, "lower_is_better": True},
        )


class InfluenceDiagnostics:
    @staticmethod
    def jackknife_mean(values: Sequence[float]) -> FrontierMeasurement:
        if len(values) < 2:
            raise FrontierUncertaintyError("jackknife requires at least two observations")
        xs = [finite_number("observation", value) for value in values]
        total = sum(xs)
        estimates = [(total - value) / (len(xs) - 1) for value in xs]
        full = total / len(xs)
        influences = [full - estimate for estimate in estimates]
        maximum = max(abs(value) for value in influences)
        return FrontierMeasurement(
            FrontierLens.JACKKNIFE_INFLUENCE,
            QuantityKind.DECISION_DIAGNOSTIC,
            value=maximum,
            sample_size=float(len(xs)),
            assumptions=("observation deletion is a meaningful perturbation",),
            metadata={"full_mean": full, "leave_one_out_means": estimates, "influences": influences, "max_absolute_influence": maximum},
        )
