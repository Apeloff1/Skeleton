"""Online Bayesian predictive mixtures for Jeeves.

The state-space engine exposes calibrated Gaussian component forecasts. This module
combines those distributions with leakage-safe, prequential Bayesian model
averaging. Component weights are updated only *after* a target is observed, so a
forecast can never use its own realization to choose its weight.

The module also implements proper probabilistic scoring rules for Gaussian
mixtures, including exact log score and closed-form CRPS. These are preferable to
ranking models only by point-error metrics because they reward both sharpness and
honest uncertainty.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Mapping, Sequence

from .probabilistic_state_space import (
    GaussianForecast,
    SeriesValues,
    StateSpaceConfig,
    StateSpaceError,
    StateSpaceFamily,
    fit_state_space,
)

_EPSILON = 1e-15


@dataclass(frozen=True, slots=True)
class BayesianEnsembleConfig:
    """Controls online model-weight adaptation."""

    min_train_size: int = 16
    step: int = 1
    learning_rate: float = 1.0
    forgetting_factor: float = 0.985
    min_weight: float = 1e-4
    prior_strength: float = 0.02

    def __post_init__(self) -> None:
        if isinstance(self.min_train_size, bool) or not isinstance(self.min_train_size, int) or self.min_train_size < 3:
            raise StateSpaceError(
                "min_train_size must be an integer >= 3",
                context={"reason": "invalid_ensemble_config", "field": "min_train_size"},
            )
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step <= 0:
            raise StateSpaceError(
                "step must be a positive integer",
                context={"reason": "invalid_ensemble_config", "field": "step"},
            )
        _closed_interval("learning_rate", self.learning_rate, 0.0, 8.0)
        _open_closed_interval("forgetting_factor", self.forgetting_factor, 0.0, 1.0)
        _closed_interval("min_weight", self.min_weight, 0.0, 0.20)
        _closed_interval("prior_strength", self.prior_strength, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class WeightedForecast:
    """One component predictive distribution and its pre-target ensemble weight."""

    family: StateSpaceFamily
    weight: float
    forecast: GaussianForecast

    def __post_init__(self) -> None:
        if not math.isfinite(self.weight) or not 0.0 <= self.weight <= 1.0:
            raise StateSpaceError(
                "component weight must be in [0, 1]",
                context={"reason": "invalid_ensemble_weight"},
            )


@dataclass(frozen=True, slots=True)
class MixtureForecast:
    """Finite Gaussian mixture forecast."""

    horizon: int
    components: tuple[WeightedForecast, ...]

    def __post_init__(self) -> None:
        if not self.components:
            raise StateSpaceError(
                "mixture requires at least one component",
                context={"reason": "empty_mixture"},
            )
        if len({component.family for component in self.components}) != len(self.components):
            raise StateSpaceError(
                "mixture component families must be unique",
                context={"reason": "duplicate_component"},
            )
        if any(component.forecast.horizon != self.horizon for component in self.components):
            raise StateSpaceError(
                "mixture components must share a forecast horizon",
                context={"reason": "horizon_mismatch"},
            )
        if abs(sum(component.weight for component in self.components) - 1.0) > 1e-9:
            raise StateSpaceError(
                "mixture weights must sum to one",
                context={"reason": "invalid_ensemble_weight"},
            )

    @property
    def mean(self) -> float:
        return sum(component.weight * component.forecast.mean for component in self.components)

    @property
    def variance(self) -> float:
        mean = self.mean
        return sum(
            component.weight
            * (
                component.forecast.variance
                + (component.forecast.mean - mean) * (component.forecast.mean - mean)
            )
            for component in self.components
        )

    @property
    def standard_deviation(self) -> float:
        return math.sqrt(max(_EPSILON, self.variance))

    @property
    def entropy_of_weights(self) -> float:
        return -sum(
            component.weight * math.log(max(_EPSILON, component.weight))
            for component in self.components
        )

    @property
    def effective_model_count(self) -> float:
        return math.exp(self.entropy_of_weights)

    def log_density(self, actual: float) -> float:
        actual = _finite("actual", actual)
        terms = [
            math.log(max(_EPSILON, component.weight))
            + component.forecast.log_density(actual)
            for component in self.components
        ]
        return _logsumexp(terms)

    def crps(self, actual: float) -> float:
        return gaussian_mixture_crps(self, actual)

    def moment_interval(self, z: float = 1.959963984540054) -> tuple[float, float]:
        """Moment-matched Gaussian interval for display, not an exact mixture quantile."""

        z = _positive_finite("z", z)
        radius = z * self.standard_deviation
        return self.mean - radius, self.mean + radius


@dataclass(frozen=True, slots=True)
class EnsembleStep:
    """One leakage-safe prequential ensemble forecast and posterior update."""

    target_index: int
    actual: float
    predictive: MixtureForecast
    prior_weights: tuple[tuple[StateSpaceFamily, float], ...]
    posterior_weights: tuple[tuple[StateSpaceFamily, float], ...]
    log_score: float
    crps: float
    absolute_error: float
    squared_error: float

    def __post_init__(self) -> None:
        if isinstance(self.target_index, bool) or not isinstance(self.target_index, int) or self.target_index < 1:
            raise StateSpaceError(
                "target_index must be positive",
                context={"reason": "invalid_ensemble_step"},
            )
        for name in ("actual", "log_score", "crps", "absolute_error", "squared_error"):
            _finite(name, getattr(self, name))
        if self.crps < 0.0 or self.absolute_error < 0.0 or self.squared_error < 0.0:
            raise StateSpaceError(
                "ensemble loss metrics must be non-negative where defined",
                context={"reason": "invalid_ensemble_step"},
            )


@dataclass(frozen=True, slots=True)
class BayesianEnsembleReport:
    """Complete online ensemble evaluation."""

    config: BayesianEnsembleConfig
    families: tuple[StateSpaceFamily, ...]
    steps: tuple[EnsembleStep, ...]
    final_weights: tuple[tuple[StateSpaceFamily, float], ...]
    mean_log_score: float
    mean_crps: float
    mae: float
    rmse: float
    fingerprint: str

    @property
    def selected_family(self) -> StateSpaceFamily:
        return max(self.final_weights, key=lambda item: (item[1], item[0].value))[0]

    @property
    def average_effective_model_count(self) -> float:
        return statistics.fmean(step.predictive.effective_model_count for step in self.steps)

    def weight_for(self, family: StateSpaceFamily) -> float:
        for current, weight in self.final_weights:
            if current is family:
                return weight
        raise StateSpaceError(
            "family is absent from ensemble",
            context={"reason": "missing_family", "family": family.value},
        )


class OnlineBayesianEnsemble:
    """Sequential log-score model averaging with bounded forgetting."""

    def __init__(
        self,
        *,
        families: Sequence[StateSpaceFamily] | None = None,
        config: BayesianEnsembleConfig | None = None,
        state_space_config: StateSpaceConfig | None = None,
        prior_weights: Mapping[StateSpaceFamily, float] | None = None,
    ) -> None:
        self.config = config or BayesianEnsembleConfig()
        self.state_space_config = state_space_config or StateSpaceConfig()
        self.families = tuple(
            families
            or (
                StateSpaceFamily.LOCAL_LEVEL,
                StateSpaceFamily.LOCAL_LINEAR_TREND,
                StateSpaceFamily.ROBUST_LOCAL_LINEAR_TREND,
            )
        )
        if not self.families or len(set(self.families)) != len(self.families):
            raise StateSpaceError(
                "ensemble families must be non-empty and unique",
                context={"reason": "invalid_family_set"},
            )
        self._initial_weights = _normalize_prior(self.families, prior_weights)

    def evaluate(self, series: SeriesValues | Sequence[float]) -> BayesianEnsembleReport:
        values = _coerce_values(series)
        if len(values) <= self.config.min_train_size:
            raise StateSpaceError(
                "series is too short for Bayesian ensemble evaluation",
                context={"reason": "insufficient_history"},
            )

        weights = dict(self._initial_weights)
        steps: list[EnsembleStep] = []
        for target_index in range(self.config.min_train_size, len(values), self.config.step):
            training = values[:target_index]
            prior_weights = _sorted_weights(weights)
            components: list[WeightedForecast] = []
            component_log_scores: dict[StateSpaceFamily, float] = {}

            for family in self.families:
                family_config = _family_config(self.state_space_config, family)
                fit = fit_state_space(training, config=family_config)
                forecast = fit.forecast(1)
                components.append(
                    WeightedForecast(
                        family=family,
                        weight=weights[family],
                        forecast=forecast,
                    )
                )

            predictive = MixtureForecast(horizon=1, components=tuple(components))
            actual = values[target_index]
            for component in components:
                component_log_scores[component.family] = component.forecast.log_density(actual)

            posterior = _posterior_weights(
                prior=weights,
                log_scores=component_log_scores,
                config=self.config,
            )
            error = predictive.mean - actual
            steps.append(
                EnsembleStep(
                    target_index=target_index,
                    actual=actual,
                    predictive=predictive,
                    prior_weights=prior_weights,
                    posterior_weights=_sorted_weights(posterior),
                    log_score=predictive.log_density(actual),
                    crps=predictive.crps(actual),
                    absolute_error=abs(error),
                    squared_error=error * error,
                )
            )
            weights = posterior

        final_weights = _sorted_weights(weights)
        fingerprint = _report_fingerprint(
            config=self.config,
            families=self.families,
            steps=steps,
            final_weights=final_weights,
        )
        return BayesianEnsembleReport(
            config=self.config,
            families=self.families,
            steps=tuple(steps),
            final_weights=final_weights,
            mean_log_score=statistics.fmean(step.log_score for step in steps),
            mean_crps=statistics.fmean(step.crps for step in steps),
            mae=statistics.fmean(step.absolute_error for step in steps),
            rmse=math.sqrt(statistics.fmean(step.squared_error for step in steps)),
            fingerprint=fingerprint,
        )

    def forecast(
        self,
        series: SeriesValues | Sequence[float],
        *,
        horizon: int = 1,
        weights: Mapping[StateSpaceFamily, float] | None = None,
    ) -> MixtureForecast:
        """Fit all components on the supplied history and combine fixed weights."""

        values = _coerce_values(series)
        actual_weights = dict(
            _normalize_prior(self.families, weights) if weights is not None else self._initial_weights
        )
        components: list[WeightedForecast] = []
        for family in self.families:
            fit = fit_state_space(values, config=_family_config(self.state_space_config, family))
            components.append(
                WeightedForecast(
                    family=family,
                    weight=actual_weights[family],
                    forecast=fit.forecast(horizon),
                )
            )
        return MixtureForecast(horizon=horizon, components=tuple(components))


def gaussian_mixture_crps(mixture: MixtureForecast, actual: float) -> float:
    """Exact CRPS for a finite Gaussian mixture.

    Uses the identity
    CRPS(F, y) = sum_i w_i A(y-mu_i, sigma_i^2)
                 - 1/2 sum_i sum_j w_i w_j A(mu_i-mu_j, sigma_i^2+sigma_j^2)
    where A(a, v) = E|N(a, v)|.
    """

    actual = _finite("actual", actual)
    first = 0.0
    for component in mixture.components:
        variance = component.forecast.variance
        first += component.weight * _expected_abs_normal(actual - component.forecast.mean, variance)

    second = 0.0
    for left in mixture.components:
        for right in mixture.components:
            delta = left.forecast.mean - right.forecast.mean
            variance = left.forecast.variance + right.forecast.variance
            second += left.weight * right.weight * _expected_abs_normal(delta, variance)
    return max(0.0, first - 0.5 * second)


def probability_integral_transform(mixture: MixtureForecast, actual: float) -> float:
    """Return the Gaussian-mixture CDF at ``actual`` for calibration diagnostics."""

    actual = _finite("actual", actual)
    probability = 0.0
    for component in mixture.components:
        z = (actual - component.forecast.mean) / math.sqrt(component.forecast.variance)
        probability += component.weight * _normal_cdf(z)
    return min(1.0, max(0.0, probability))


def _posterior_weights(
    *,
    prior: Mapping[StateSpaceFamily, float],
    log_scores: Mapping[StateSpaceFamily, float],
    config: BayesianEnsembleConfig,
) -> dict[StateSpaceFamily, float]:
    """Update model probabilities in log space after one target is observed."""

    logits: dict[StateSpaceFamily, float] = {}
    uniform = 1.0 / len(prior)
    for family, weight in prior.items():
        if family not in log_scores:
            raise StateSpaceError(
                "missing component log score",
                context={"reason": "incomplete_ensemble_update", "family": family.value},
            )
        blended_prior = (1.0 - config.prior_strength) * weight + config.prior_strength * uniform
        remembered_log_weight = config.forgetting_factor * math.log(max(_EPSILON, blended_prior))
        logits[family] = remembered_log_weight + config.learning_rate * log_scores[family]

    normalizer = _logsumexp(list(logits.values()))
    raw = {family: math.exp(logit - normalizer) for family, logit in logits.items()}
    return _apply_weight_floor(raw, config.min_weight)


def _apply_weight_floor(
    weights: Mapping[StateSpaceFamily, float],
    floor: float,
) -> dict[StateSpaceFamily, float]:
    if floor * len(weights) >= 1.0:
        raise StateSpaceError(
            "min_weight is too large for the number of models",
            context={"reason": "invalid_ensemble_config", "field": "min_weight"},
        )
    if floor <= 0.0:
        total = sum(weights.values())
        return {family: weight / total for family, weight in weights.items()}

    free_mass = 1.0 - floor * len(weights)
    total = sum(weights.values())
    if total <= _EPSILON:
        scaled = {family: 1.0 / len(weights) for family in weights}
    else:
        scaled = {family: weight / total for family, weight in weights.items()}
    return {family: floor + free_mass * scaled[family] for family in weights}


def _normalize_prior(
    families: Sequence[StateSpaceFamily],
    supplied: Mapping[StateSpaceFamily, float] | None,
) -> tuple[tuple[StateSpaceFamily, float], ...]:
    if supplied is None:
        weight = 1.0 / len(families)
        return tuple((family, weight) for family in families)

    if set(supplied) != set(families):
        raise StateSpaceError(
            "prior weights must exactly match ensemble families",
            context={"reason": "invalid_prior_weights"},
        )
    clean: dict[StateSpaceFamily, float] = {}
    for family in families:
        value = _finite("prior_weight", supplied[family])
        if value < 0.0:
            raise StateSpaceError(
                "prior weights must be non-negative",
                context={"reason": "invalid_prior_weights"},
            )
        clean[family] = value
    total = sum(clean.values())
    if total <= _EPSILON:
        raise StateSpaceError(
            "prior weights must contain positive mass",
            context={"reason": "invalid_prior_weights"},
        )
    return tuple((family, clean[family] / total) for family in families)


def _family_config(template: StateSpaceConfig, family: StateSpaceFamily) -> StateSpaceConfig:
    return StateSpaceConfig(
        family=family,
        observation_variance=template.observation_variance,
        level_variance=template.level_variance,
        trend_variance=template.trend_variance,
        initial_variance=template.initial_variance,
        robust_clip_sigma=template.robust_clip_sigma,
        regime_window=template.regime_window,
        scale_variances=template.scale_variances,
    )


def _expected_abs_normal(delta: float, variance: float) -> float:
    variance = max(_EPSILON, variance)
    sigma = math.sqrt(variance)
    z = delta / sigma
    phi = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return 2.0 * sigma * phi + delta * (2.0 * _normal_cdf(z) - 1.0)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _logsumexp(values: Sequence[float]) -> float:
    if not values:
        raise StateSpaceError(
            "logsumexp requires at least one value",
            context={"reason": "empty_numeric_sequence"},
        )
    maximum = max(values)
    if not math.isfinite(maximum):
        raise StateSpaceError(
            "log weights became non-finite",
            context={"reason": "numerical_instability"},
        )
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


def _sorted_weights(weights: Mapping[StateSpaceFamily, float]) -> tuple[tuple[StateSpaceFamily, float], ...]:
    return tuple(sorted(weights.items(), key=lambda item: item[0].value))


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "ensemble series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "ensemble series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "ensemble series cannot be empty",
            context={"reason": "empty_series"},
        )
    return tuple(_finite("value", value) for value in values)


def _report_fingerprint(
    *,
    config: BayesianEnsembleConfig,
    families: Sequence[StateSpaceFamily],
    steps: Sequence[EnsembleStep],
    final_weights: Sequence[tuple[StateSpaceFamily, float]],
) -> str:
    parts = [
        "jeeves-bayesian-ensemble-v1",
        repr(config),
        ",".join(family.value for family in families),
    ]
    for step in steps:
        parts.extend(
            (
                str(step.target_index),
                format(step.actual, ".17g"),
                format(step.predictive.mean, ".17g"),
                format(step.predictive.variance, ".17g"),
                format(step.log_score, ".17g"),
                format(step.crps, ".17g"),
                ",".join(
                    f"{family.value}:{format(weight, '.17g')}"
                    for family, weight in step.prior_weights
                ),
                ",".join(
                    f"{family.value}:{format(weight, '.17g')}"
                    for family, weight in step.posterior_weights
                ),
            )
        )
    parts.append(
        ",".join(
            f"{family.value}:{format(weight, '.17g')}"
            for family, weight in final_weights
        )
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _positive_finite(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    number = _finite(name, value)
    if not minimum <= number <= maximum:
        raise StateSpaceError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_ensemble_config", "field": name},
        )
    return number


def _open_closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    number = _finite(name, value)
    if not minimum < number <= maximum:
        raise StateSpaceError(
            f"{name} must be > {minimum} and <= {maximum}",
            context={"reason": "invalid_ensemble_config", "field": name},
        )
    return number


__all__ = [
    "BayesianEnsembleConfig",
    "BayesianEnsembleReport",
    "EnsembleStep",
    "MixtureForecast",
    "OnlineBayesianEnsemble",
    "WeightedForecast",
    "gaussian_mixture_crps",
    "probability_integral_transform",
]
