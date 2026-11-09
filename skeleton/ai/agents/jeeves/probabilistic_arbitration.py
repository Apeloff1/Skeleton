"""Cross-family probabilistic arbitration for Jeeves.

This layer compares structurally different forecasting families under one
prequential custody rule. It combines state-space, exact Bayesian trend,
multiscale spectral, and hidden-Markov regime forecasts without pretending that
their internal assumptions are interchangeable.

Weights used for target ``t`` are fixed before observing ``t``. Only after the
realized target has been scored may evidence update weights for later targets.
The update is tempered and bounded so one numerically overconfident forecast
cannot irreversibly erase model diversity.

Reports bind both the arbitration policy and every expert-model configuration.
A report therefore cannot be replayed against silently changed model assumptions.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol, Sequence

from .probabilistic_bayes import BayesianTrendConfig, fit_bayesian_trend
from .probabilistic_regimes import RegimeHMMConfig, fit_regime_hmm
from .probabilistic_spectral import SpectralConfig, fit_spectral_model
from .probabilistic_state_space import (
    SeriesValues,
    StateSpaceConfig,
    StateSpaceError,
    StateSpaceFamily,
    fit_state_space,
)

_EPSILON = 1e-15


class PredictiveDistribution(Protocol):
    """Minimal contract needed by cross-family probabilistic arbitration."""

    horizon: int
    mean: float
    variance: float

    def log_density(self, actual: float) -> float: ...


class ExpertKind(str, Enum):
    """Built-in heterogeneous forecast experts."""

    LOCAL_LEVEL = "state_space_local_level"
    LOCAL_LINEAR_TREND = "state_space_local_linear_trend"
    ROBUST_LOCAL_LINEAR_TREND = "state_space_robust_local_linear_trend"
    BAYESIAN_TREND = "bayesian_trend"
    SPECTRAL = "multiscale_spectral"
    REGIME_HMM = "regime_hmm"


@dataclass(frozen=True, slots=True)
class CrossFamilyConfig:
    """Controls leakage-safe cross-family evidence accumulation."""

    min_train_size: int = 32
    step: int = 1
    learning_rate: float = 0.75
    forgetting_factor: float = 0.99
    prior_strength: float = 0.02
    min_weight: float = 1e-4
    max_log_score_gap: float = 30.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_train_size, bool)
            or not isinstance(self.min_train_size, int)
            or self.min_train_size < 8
        ):
            raise StateSpaceError(
                "min_train_size must be an integer >= 8",
                context={
                    "reason": "invalid_cross_family_config",
                    "field": "min_train_size",
                },
            )
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step <= 0:
            raise StateSpaceError(
                "step must be a positive integer",
                context={"reason": "invalid_cross_family_config", "field": "step"},
            )
        _closed_interval("learning_rate", self.learning_rate, 0.0, 8.0)
        _open_closed_interval(
            "forgetting_factor",
            self.forgetting_factor,
            0.0,
            1.0,
        )
        _closed_interval("prior_strength", self.prior_strength, 0.0, 1.0)
        _closed_interval("min_weight", self.min_weight, 0.0, 0.20)
        gap = _positive("max_log_score_gap", self.max_log_score_gap)
        if gap > 1_000.0:
            raise StateSpaceError(
                "max_log_score_gap must be <= 1000",
                context={
                    "reason": "invalid_cross_family_config",
                    "field": "max_log_score_gap",
                },
            )


@dataclass(frozen=True, slots=True)
class ExpertComponent:
    """One pre-target expert distribution and its arbitration weight."""

    expert: ExpertKind
    weight: float
    predictive: PredictiveDistribution

    def __post_init__(self) -> None:
        if not math.isfinite(self.weight) or not 0.0 <= self.weight <= 1.0:
            raise StateSpaceError(
                "expert weight must be finite and in [0, 1]",
                context={"reason": "invalid_cross_family_weight"},
            )
        if self.predictive.horizon <= 0:
            raise StateSpaceError(
                "expert forecast horizon must be positive",
                context={"reason": "invalid_cross_family_forecast"},
            )
        _finite("expert_mean", self.predictive.mean)
        variance = _finite("expert_variance", self.predictive.variance)
        if variance <= 0.0:
            raise StateSpaceError(
                "expert predictive variance must be positive",
                context={"reason": "invalid_cross_family_forecast"},
            )


@dataclass(frozen=True, slots=True)
class ArbitratedForecast:
    """Mixture over heterogeneous predictive model families."""

    horizon: int
    components: tuple[ExpertComponent, ...]

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise StateSpaceError(
                "arbitrated forecast horizon must be positive",
                context={"reason": "invalid_horizon"},
            )
        if not self.components:
            raise StateSpaceError(
                "arbitrated forecast requires at least one expert",
                context={"reason": "empty_cross_family_mixture"},
            )
        if len({component.expert for component in self.components}) != len(self.components):
            raise StateSpaceError(
                "cross-family experts must be unique",
                context={"reason": "duplicate_cross_family_expert"},
            )
        if any(component.predictive.horizon != self.horizon for component in self.components):
            raise StateSpaceError(
                "cross-family experts must share a forecast horizon",
                context={"reason": "horizon_mismatch"},
            )
        if abs(sum(component.weight for component in self.components) - 1.0) > 1e-9:
            raise StateSpaceError(
                "cross-family weights must sum to one",
                context={"reason": "invalid_cross_family_weight"},
            )

    @property
    def mean(self) -> float:
        return sum(
            component.weight * component.predictive.mean
            for component in self.components
        )

    @property
    def aleatoric_variance(self) -> float:
        return sum(
            component.weight * component.predictive.variance
            for component in self.components
        )

    @property
    def epistemic_variance(self) -> float:
        mean = self.mean
        return sum(
            component.weight * (component.predictive.mean - mean) ** 2
            for component in self.components
        )

    @property
    def variance(self) -> float:
        return max(_EPSILON, self.aleatoric_variance + self.epistemic_variance)

    @property
    def entropy_of_weights(self) -> float:
        return -sum(
            component.weight * math.log(max(_EPSILON, component.weight))
            for component in self.components
        )

    @property
    def effective_expert_count(self) -> float:
        return math.exp(self.entropy_of_weights)

    @property
    def dominant_expert(self) -> ExpertKind:
        return max(
            self.components,
            key=lambda component: (component.weight, component.expert.value),
        ).expert

    def log_density(self, actual: float) -> float:
        actual = _finite("actual", actual)
        terms = [
            math.log(max(_EPSILON, component.weight))
            + component.predictive.log_density(actual)
            for component in self.components
        ]
        return _logsumexp(terms)

    def moment_interval(self, z: float = 1.959963984540054) -> tuple[float, float]:
        z = _positive("z", z)
        radius = z * math.sqrt(self.variance)
        return self.mean - radius, self.mean + radius


@dataclass(frozen=True, slots=True)
class CrossFamilyStep:
    """One target scored before posterior expert weights are updated."""

    target_index: int
    actual: float
    predictive: ArbitratedForecast
    prior_weights: tuple[tuple[ExpertKind, float], ...]
    posterior_weights: tuple[tuple[ExpertKind, float], ...]
    component_log_scores: tuple[tuple[ExpertKind, float], ...]
    mixture_log_score: float
    absolute_error: float
    squared_error: float
    epistemic_share: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.target_index, bool)
            or not isinstance(self.target_index, int)
            or self.target_index < 1
        ):
            raise StateSpaceError(
                "target_index must be positive",
                context={"reason": "invalid_cross_family_step"},
            )
        for name in (
            "actual",
            "mixture_log_score",
            "absolute_error",
            "squared_error",
            "epistemic_share",
        ):
            _finite(name, getattr(self, name))
        if self.absolute_error < 0.0 or self.squared_error < 0.0:
            raise StateSpaceError(
                "cross-family error metrics must be non-negative",
                context={"reason": "invalid_cross_family_step"},
            )
        if not 0.0 <= self.epistemic_share <= 1.0:
            raise StateSpaceError(
                "epistemic_share must be in [0, 1]",
                context={"reason": "invalid_cross_family_step"},
            )


@dataclass(frozen=True, slots=True)
class CrossFamilyReport:
    """Complete heterogeneous prequential arbitration evidence."""

    config: CrossFamilyConfig
    experts: tuple[ExpertKind, ...]
    configuration_fingerprint: str
    steps: tuple[CrossFamilyStep, ...]
    final_weights: tuple[tuple[ExpertKind, float], ...]
    mean_log_score: float
    mae: float
    rmse: float
    average_effective_expert_count: float
    average_epistemic_share: float
    fingerprint: str

    @property
    def selected_expert(self) -> ExpertKind:
        return max(
            self.final_weights,
            key=lambda item: (item[1], item[0].value),
        )[0]

    def weight_for(self, expert: ExpertKind) -> float:
        for current, weight in self.final_weights:
            if current is expert:
                return weight
        raise StateSpaceError(
            "expert is absent from cross-family report",
            context={
                "reason": "missing_cross_family_expert",
                "expert": expert.value,
            },
        )


class CrossFamilyArbitrator:
    """Online log-score arbitration across incompatible forecasting assumptions."""

    def __init__(
        self,
        *,
        experts: Sequence[ExpertKind] | None = None,
        config: CrossFamilyConfig | None = None,
        state_space_config: StateSpaceConfig | None = None,
        bayesian_config: BayesianTrendConfig | None = None,
        spectral_config: SpectralConfig | None = None,
        regime_config: RegimeHMMConfig | None = None,
        prior_weights: Mapping[ExpertKind, float] | None = None,
    ) -> None:
        self.config = config or CrossFamilyConfig()
        self.state_space_config = state_space_config or StateSpaceConfig()
        self.bayesian_config = bayesian_config or BayesianTrendConfig()
        self.spectral_config = spectral_config or SpectralConfig()
        self.regime_config = regime_config or RegimeHMMConfig()
        self.experts = tuple(
            experts
            or (
                ExpertKind.LOCAL_LEVEL,
                ExpertKind.ROBUST_LOCAL_LINEAR_TREND,
                ExpertKind.SPECTRAL,
                ExpertKind.REGIME_HMM,
            )
        )
        if not self.experts or len(set(self.experts)) != len(self.experts):
            raise StateSpaceError(
                "cross-family experts must be non-empty and unique",
                context={"reason": "invalid_cross_family_experts"},
            )
        if self.config.min_weight * len(self.experts) >= 1.0:
            raise StateSpaceError(
                "min_weight is too large for the number of experts",
                context={
                    "reason": "invalid_cross_family_config",
                    "field": "min_weight",
                },
            )
        self._initial_weights = _normalize_prior(self.experts, prior_weights)
        self._configuration_fingerprint = _configuration_fingerprint(
            config=self.config,
            experts=self.experts,
            state_space_config=self.state_space_config,
            bayesian_config=self.bayesian_config,
            spectral_config=self.spectral_config,
            regime_config=self.regime_config,
        )

    @property
    def configuration_fingerprint(self) -> str:
        """Identity of all policy and expert-model assumptions."""

        return self._configuration_fingerprint

    def evaluate(self, series: SeriesValues | Sequence[float]) -> CrossFamilyReport:
        """Evaluate experts prequentially with target-time custody."""

        values = _coerce_values(series)
        if len(values) <= self.config.min_train_size:
            raise StateSpaceError(
                "series is too short for cross-family arbitration",
                context={"reason": "insufficient_history"},
            )

        weights = dict(self._initial_weights)
        steps: list[CrossFamilyStep] = []
        for target_index in range(
            self.config.min_train_size,
            len(values),
            self.config.step,
        ):
            training = values[:target_index]
            prior_weights = _sorted_weights(weights)
            predictive = self._forecast_with_weights(
                training,
                horizon=1,
                weights=weights,
            )
            actual = values[target_index]
            component_scores = {
                component.expert: component.predictive.log_density(actual)
                for component in predictive.components
            }
            posterior = _posterior_weights(
                prior=weights,
                log_scores=component_scores,
                config=self.config,
            )
            error = predictive.mean - actual
            epistemic_share = (
                predictive.epistemic_variance / max(_EPSILON, predictive.variance)
            )
            steps.append(
                CrossFamilyStep(
                    target_index=target_index,
                    actual=actual,
                    predictive=predictive,
                    prior_weights=prior_weights,
                    posterior_weights=_sorted_weights(posterior),
                    component_log_scores=_sorted_scores(component_scores),
                    mixture_log_score=predictive.log_density(actual),
                    absolute_error=abs(error),
                    squared_error=error * error,
                    epistemic_share=min(1.0, max(0.0, epistemic_share)),
                )
            )
            weights = posterior

        final_weights = _sorted_weights(weights)
        fingerprint = _report_fingerprint(
            configuration_fingerprint=self.configuration_fingerprint,
            steps=steps,
            final_weights=final_weights,
        )
        return CrossFamilyReport(
            config=self.config,
            experts=self.experts,
            configuration_fingerprint=self.configuration_fingerprint,
            steps=tuple(steps),
            final_weights=final_weights,
            mean_log_score=statistics.fmean(
                step.mixture_log_score for step in steps
            ),
            mae=statistics.fmean(step.absolute_error for step in steps),
            rmse=math.sqrt(statistics.fmean(step.squared_error for step in steps)),
            average_effective_expert_count=statistics.fmean(
                step.predictive.effective_expert_count for step in steps
            ),
            average_epistemic_share=statistics.fmean(
                step.epistemic_share for step in steps
            ),
            fingerprint=fingerprint,
        )

    def forecast(
        self,
        series: SeriesValues | Sequence[float],
        *,
        horizon: int = 1,
        weights: Mapping[ExpertKind, float] | None = None,
    ) -> ArbitratedForecast:
        """Forecast with supplied fixed weights or the configured prior."""

        values = _coerce_values(series)
        actual_weights = dict(
            _normalize_prior(self.experts, weights)
            if weights is not None
            else self._initial_weights
        )
        return self._forecast_with_weights(
            values,
            horizon=horizon,
            weights=actual_weights,
        )

    def forecast_from_report(
        self,
        series: SeriesValues | Sequence[float],
        report: CrossFamilyReport,
        *,
        horizon: int = 1,
    ) -> ArbitratedForecast:
        """Use posterior weights only when the full model identity still matches."""

        if (
            report.experts != self.experts
            or report.config != self.config
            or report.configuration_fingerprint != self.configuration_fingerprint
        ):
            raise StateSpaceError(
                "cross-family report does not match arbitrator configuration",
                context={"reason": "cross_family_report_mismatch"},
            )
        return self.forecast(
            series,
            horizon=horizon,
            weights=dict(report.final_weights),
        )

    def _forecast_with_weights(
        self,
        values: Sequence[float],
        *,
        horizon: int,
        weights: Mapping[ExpertKind, float],
    ) -> ArbitratedForecast:
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
            raise StateSpaceError(
                "forecast horizon must be a positive integer",
                context={"reason": "invalid_horizon"},
            )
        components = tuple(
            ExpertComponent(
                expert=expert,
                weight=weights[expert],
                predictive=self._expert_distribution(
                    expert,
                    values,
                    horizon=horizon,
                ),
            )
            for expert in self.experts
        )
        return ArbitratedForecast(horizon=horizon, components=components)

    def _expert_distribution(
        self,
        expert: ExpertKind,
        values: Sequence[float],
        *,
        horizon: int,
    ) -> PredictiveDistribution:
        family = _state_space_family(expert)
        if family is not None:
            fit = fit_state_space(
                values,
                config=_state_space_family_config(
                    self.state_space_config,
                    family,
                ),
            )
            return fit.forecast(horizon)
        if expert is ExpertKind.BAYESIAN_TREND:
            return fit_bayesian_trend(
                values,
                config=self.bayesian_config,
            ).forecast(horizon)
        if expert is ExpertKind.SPECTRAL:
            return fit_spectral_model(
                values,
                config=self.spectral_config,
            ).forecast(horizon)
        if expert is ExpertKind.REGIME_HMM:
            return fit_regime_hmm(
                values,
                config=self.regime_config,
            ).forecast(horizon)
        raise StateSpaceError(
            "unsupported cross-family expert",
            context={
                "reason": "unsupported_cross_family_expert",
                "expert": str(expert),
            },
        )


def _state_space_family(expert: ExpertKind) -> StateSpaceFamily | None:
    mapping = {
        ExpertKind.LOCAL_LEVEL: StateSpaceFamily.LOCAL_LEVEL,
        ExpertKind.LOCAL_LINEAR_TREND: StateSpaceFamily.LOCAL_LINEAR_TREND,
        ExpertKind.ROBUST_LOCAL_LINEAR_TREND: (
            StateSpaceFamily.ROBUST_LOCAL_LINEAR_TREND
        ),
    }
    return mapping.get(expert)


def _state_space_family_config(
    template: StateSpaceConfig,
    family: StateSpaceFamily,
) -> StateSpaceConfig:
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


def _configuration_fingerprint(
    *,
    config: CrossFamilyConfig,
    experts: Sequence[ExpertKind],
    state_space_config: StateSpaceConfig,
    bayesian_config: BayesianTrendConfig,
    spectral_config: SpectralConfig,
    regime_config: RegimeHMMConfig,
) -> str:
    parts = (
        "jeeves-cross-family-configuration-v2",
        repr(config),
        ",".join(expert.value for expert in experts),
        repr(state_space_config),
        repr(bayesian_config),
        repr(spectral_config),
        repr(regime_config),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _posterior_weights(
    *,
    prior: Mapping[ExpertKind, float],
    log_scores: Mapping[ExpertKind, float],
    config: CrossFamilyConfig,
) -> dict[ExpertKind, float]:
    if set(prior) != set(log_scores):
        raise StateSpaceError(
            "cross-family update requires one score per expert",
            context={"reason": "incomplete_cross_family_update"},
        )

    best_score = max(log_scores.values())
    score_floor = best_score - config.max_log_score_gap
    uniform = 1.0 / len(prior)
    logits: dict[ExpertKind, float] = {}
    for expert, weight in prior.items():
        score = max(
            score_floor,
            _finite("component_log_score", log_scores[expert]),
        )
        blended = (
            (1.0 - config.prior_strength) * weight
            + config.prior_strength * uniform
        )
        remembered = config.forgetting_factor * math.log(
            max(_EPSILON, blended)
        )
        logits[expert] = remembered + config.learning_rate * score

    normalizer = _logsumexp(tuple(logits.values()))
    raw = {
        expert: math.exp(value - normalizer)
        for expert, value in logits.items()
    }
    return _apply_weight_floor(raw, config.min_weight)


def _apply_weight_floor(
    weights: Mapping[ExpertKind, float],
    floor: float,
) -> dict[ExpertKind, float]:
    if floor * len(weights) >= 1.0:
        raise StateSpaceError(
            "min_weight is too large for the number of experts",
            context={
                "reason": "invalid_cross_family_config",
                "field": "min_weight",
            },
        )
    total = sum(weights.values())
    if not math.isfinite(total) or total <= _EPSILON:
        raise StateSpaceError(
            "cross-family weights lost all probability mass",
            context={"reason": "numerical_instability"},
        )
    normalized = {
        expert: weight / total
        for expert, weight in weights.items()
    }
    if floor <= 0.0:
        return normalized
    free_mass = 1.0 - floor * len(weights)
    return {
        expert: floor + free_mass * normalized[expert]
        for expert in normalized
    }


def _normalize_prior(
    experts: Sequence[ExpertKind],
    supplied: Mapping[ExpertKind, float] | None,
) -> tuple[tuple[ExpertKind, float], ...]:
    if supplied is None:
        uniform = 1.0 / len(experts)
        return tuple((expert, uniform) for expert in experts)
    if set(supplied) != set(experts):
        raise StateSpaceError(
            "prior weights must exactly match cross-family experts",
            context={"reason": "invalid_cross_family_prior"},
        )
    clean: dict[ExpertKind, float] = {}
    for expert in experts:
        value = _finite("prior_weight", supplied[expert])
        if value < 0.0:
            raise StateSpaceError(
                "prior weights must be non-negative",
                context={"reason": "invalid_cross_family_prior"},
            )
        clean[expert] = value
    total = sum(clean.values())
    if total <= _EPSILON:
        raise StateSpaceError(
            "prior weights must contain positive mass",
            context={"reason": "invalid_cross_family_prior"},
        )
    return tuple(
        (expert, clean[expert] / total)
        for expert in experts
    )


def _sorted_weights(
    weights: Mapping[ExpertKind, float],
) -> tuple[tuple[ExpertKind, float], ...]:
    return tuple(sorted(weights.items(), key=lambda item: item[0].value))


def _sorted_scores(
    scores: Mapping[ExpertKind, float],
) -> tuple[tuple[ExpertKind, float], ...]:
    return tuple(sorted(scores.items(), key=lambda item: item[0].value))


def _report_fingerprint(
    *,
    configuration_fingerprint: str,
    steps: Sequence[CrossFamilyStep],
    final_weights: Sequence[tuple[ExpertKind, float]],
) -> str:
    parts = [
        "jeeves-cross-family-arbitration-v2",
        configuration_fingerprint,
    ]
    for step in steps:
        parts.extend(
            (
                str(step.target_index),
                format(step.actual, ".17g"),
                format(step.predictive.mean, ".17g"),
                format(step.predictive.variance, ".17g"),
                format(step.mixture_log_score, ".17g"),
                format(step.epistemic_share, ".17g"),
                ",".join(
                    f"{expert.value}:{format(weight, '.17g')}"
                    for expert, weight in step.prior_weights
                ),
                ",".join(
                    f"{expert.value}:{format(weight, '.17g')}"
                    for expert, weight in step.posterior_weights
                ),
                ",".join(
                    f"{expert.value}:{format(score, '.17g')}"
                    for expert, score in step.component_log_scores
                ),
            )
        )
    parts.append(
        ",".join(
            f"{expert.value}:{format(weight, '.17g')}"
            for expert, weight in final_weights
        )
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "cross-family series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "cross-family series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "cross-family series cannot be empty",
            context={"reason": "empty_series"},
        )
    return tuple(_finite("value", value) for value in values)


def _logsumexp(values: Sequence[float]) -> float:
    if not values:
        raise StateSpaceError(
            "logsumexp requires at least one value",
            context={"reason": "empty_numeric_sequence"},
        )
    maximum = max(values)
    if not math.isfinite(maximum):
        raise StateSpaceError(
            "cross-family log weights became non-finite",
            context={"reason": "numerical_instability"},
        )
    return maximum + math.log(
        sum(math.exp(value - maximum) for value in values)
    )


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


def _positive(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _closed_interval(
    name: str,
    value: object,
    minimum: float,
    maximum: float,
) -> float:
    number = _finite(name, value)
    if not minimum <= number <= maximum:
        raise StateSpaceError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_cross_family_config", "field": name},
        )
    return number


def _open_closed_interval(
    name: str,
    value: object,
    minimum: float,
    maximum: float,
) -> float:
    number = _finite(name, value)
    if not minimum < number <= maximum:
        raise StateSpaceError(
            f"{name} must be > {minimum} and <= {maximum}",
            context={"reason": "invalid_cross_family_config", "field": name},
        )
    return number


__all__ = [
    "ArbitratedForecast",
    "CrossFamilyArbitrator",
    "CrossFamilyConfig",
    "CrossFamilyReport",
    "CrossFamilyStep",
    "ExpertComponent",
    "ExpertKind",
    "PredictiveDistribution",
]
