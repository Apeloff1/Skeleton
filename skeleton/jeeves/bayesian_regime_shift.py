"""Evidence-sensitive Bayesian online regime-shift inference.

This is a bounded run-length posterior for scalar time series. Each active run
uses a Normal-Inverse-Gamma posterior and Student-t one-step predictive density.
A change hypothesis scores the new observation against the fresh-run prior,
while growth hypotheses score it against their own learned run distributions.
That distinction makes posterior change probability respond to evidence rather
than collapse to the constant hazard rate.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .historical_modes import HistoricalModeError, HistoricalSeries

_EPS = 1e-15
_LOG_PI = math.log(math.pi)


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalModeError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _positive(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise HistoricalModeError(
            f"{name} must be positive",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalModeError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_number", "field": name},
        )
    return value


def _logsumexp(values: Sequence[float]) -> float:
    if not values:
        raise HistoricalModeError(
            "logsumexp requires values",
            context={"reason": "empty_numeric_sequence"},
        )
    maximum = max(values)
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


@dataclass(frozen=True, slots=True)
class RegimeShiftConfig:
    hazard_probability: float = 0.02
    max_hypotheses: int = 192
    prior_mean: float = 0.0
    prior_kappa: float = 0.01
    prior_alpha: float = 2.0
    prior_beta: float = 2.0
    probability_floor: float = 1e-15
    event_threshold: float = 0.35
    min_event_separation: int = 3

    def __post_init__(self) -> None:
        hazard = _finite("hazard_probability", self.hazard_probability)
        if not 0.0 < hazard < 1.0:
            raise HistoricalModeError(
                "hazard_probability must be strictly between zero and one",
                context={"reason": "invalid_regime_shift_config"},
            )
        _positive_int("max_hypotheses", self.max_hypotheses)
        _finite("prior_mean", self.prior_mean)
        _positive("prior_kappa", self.prior_kappa)
        _positive("prior_alpha", self.prior_alpha)
        _positive("prior_beta", self.prior_beta)
        floor = _positive("probability_floor", self.probability_floor)
        if floor >= 1.0:
            raise HistoricalModeError(
                "probability_floor must be below one",
                context={"reason": "invalid_regime_shift_config"},
            )
        threshold = _finite("event_threshold", self.event_threshold)
        if not 0.0 < threshold < 1.0:
            raise HistoricalModeError(
                "event_threshold must be strictly between zero and one",
                context={"reason": "invalid_regime_shift_config"},
            )
        _positive_int("min_event_separation", self.min_event_separation)


@dataclass(frozen=True, slots=True)
class NormalInverseGamma:
    mean: float
    kappa: float
    alpha: float
    beta: float

    def __post_init__(self) -> None:
        _finite("mean", self.mean)
        _positive("kappa", self.kappa)
        _positive("alpha", self.alpha)
        _positive("beta", self.beta)

    def updated(self, observation: float) -> "NormalInverseGamma":
        value = _finite("observation", observation)
        next_kappa = self.kappa + 1.0
        delta = value - self.mean
        next_mean = (self.kappa * self.mean + value) / next_kappa
        next_alpha = self.alpha + 0.5
        next_beta = self.beta + 0.5 * self.kappa * delta * delta / next_kappa
        return NormalInverseGamma(next_mean, next_kappa, next_alpha, max(next_beta, _EPS))

    def predictive(self) -> "StudentTPredictive":
        degrees = 2.0 * self.alpha
        scale_squared = self.beta * (self.kappa + 1.0) / (self.alpha * self.kappa)
        return StudentTPredictive(degrees, self.mean, math.sqrt(max(scale_squared, _EPS)))


@dataclass(frozen=True, slots=True)
class StudentTPredictive:
    degrees_of_freedom: float
    location: float
    scale: float

    def __post_init__(self) -> None:
        _positive("degrees_of_freedom", self.degrees_of_freedom)
        _finite("location", self.location)
        _positive("scale", self.scale)

    def logpdf(self, value: float) -> float:
        actual = _finite("value", value)
        degrees = self.degrees_of_freedom
        z = (actual - self.location) / self.scale
        return (
            math.lgamma((degrees + 1.0) / 2.0)
            - math.lgamma(degrees / 2.0)
            - 0.5 * (math.log(degrees) + _LOG_PI)
            - math.log(self.scale)
            - 0.5 * (degrees + 1.0) * math.log1p(z * z / degrees)
        )

    @property
    def variance(self) -> float:
        if self.degrees_of_freedom <= 2.0:
            return math.inf
        return self.scale * self.scale * self.degrees_of_freedom / (
            self.degrees_of_freedom - 2.0
        )


@dataclass(frozen=True, slots=True)
class RunHypothesis:
    run_length: int
    probability: float
    posterior: NormalInverseGamma


@dataclass(frozen=True, slots=True)
class RegimeShiftForecast:
    mean: float
    variance: float
    change_probability: float
    modal_run_length: int
    expected_run_length: float
    entropy: float
    effective_hypotheses: float


@dataclass(frozen=True, slots=True)
class RegimeShiftObservation:
    index: int
    value: float
    prior_log_predictive: float
    change_probability: float
    modal_run_length: int
    expected_run_length: float
    entropy: float
    effective_hypotheses: float


@dataclass(frozen=True, slots=True)
class RegimeShiftEvent:
    index: int
    value: float
    probability: float
    previous_modal_run_length: int
    new_modal_run_length: int


@dataclass(frozen=True, slots=True)
class RegimeShiftReport:
    series_label: str
    observations: tuple[RegimeShiftObservation, ...]
    events: tuple[RegimeShiftEvent, ...]
    final_forecast: RegimeShiftForecast
    fingerprint: str

    def as_payload(self) -> dict[str, object]:
        return {
            "series_label": self.series_label,
            "observations": len(self.observations),
            "events": len(self.events),
            "change_probability": self.final_forecast.change_probability,
            "modal_run_length": self.final_forecast.modal_run_length,
            "expected_run_length": self.final_forecast.expected_run_length,
            "entropy": self.final_forecast.entropy,
            "fingerprint": self.fingerprint,
        }


class BayesianRegimeShiftDetector:
    """Bounded Bayesian online change-point detector with causal updates."""

    def __init__(self, first_value: float, *, config: RegimeShiftConfig | None = None) -> None:
        self.config = config or RegimeShiftConfig()
        self._prior = NormalInverseGamma(
            self.config.prior_mean,
            self.config.prior_kappa,
            self.config.prior_alpha,
            self.config.prior_beta,
        )
        first = _finite("first_value", first_value)
        self.hypotheses = [RunHypothesis(1, 1.0, self._prior.updated(first))]
        self.observations = 1
        self.last_change_probability = self.config.hazard_probability
        self.cumulative_log_predictive = self._prior.predictive().logpdf(first)

    @classmethod
    def fit(
        cls,
        values: Iterable[float],
        *,
        config: RegimeShiftConfig | None = None,
    ) -> "BayesianRegimeShiftDetector":
        clean = tuple(_finite("value", value) for value in values)
        if not clean:
            raise HistoricalModeError(
                "regime-shift fit requires observations",
                context={"reason": "empty_series"},
            )
        detector = cls(clean[0], config=config)
        for value in clean[1:]:
            detector.update(value)
        return detector

    def prior_predictive_logpdf(self, observation: float) -> float:
        actual = _finite("observation", observation)
        return _logsumexp(
            [
                math.log(max(item.probability, self.config.probability_floor))
                + item.posterior.predictive().logpdf(actual)
                for item in self.hypotheses
            ]
        )

    def update(self, observation: float) -> float:
        actual = _finite("observation", observation)
        hazard = self.config.hazard_probability
        floor = self.config.probability_floor
        previous = [math.log(max(item.probability, floor)) for item in self.hypotheses]
        growth_predictive = [item.posterior.predictive().logpdf(actual) for item in self.hypotheses]

        # A newly started run must explain x_t under the fresh-run prior.
        fresh_predictive = self._prior.predictive().logpdf(actual)
        change_log_joint = math.log(hazard) + fresh_predictive + _logsumexp(previous)
        candidates: list[tuple[int, float, NormalInverseGamma]] = [
            (1, change_log_joint, self._prior.updated(actual))
        ]

        log_survival = math.log1p(-hazard)
        for item, log_prior, log_evidence in zip(self.hypotheses, previous, growth_predictive):
            candidates.append(
                (
                    item.run_length + 1,
                    log_prior + log_survival + log_evidence,
                    item.posterior.updated(actual),
                )
            )

        predictive_log_probability = _logsumexp([item[1] for item in candidates])
        normalized = [
            (run_length, math.exp(log_joint - predictive_log_probability), posterior)
            for run_length, log_joint, posterior in candidates
        ]
        normalized.sort(key=lambda item: (-item[1], item[0]))
        retained = normalized[: self.config.max_hypotheses]
        retained_mass = sum(item[1] for item in retained)
        self.hypotheses = [
            RunHypothesis(run_length, probability / retained_mass, posterior)
            for run_length, probability, posterior in sorted(retained, key=lambda item: item[0])
        ]
        self.last_change_probability = next(
            (item.probability for item in self.hypotheses if item.run_length == 1),
            0.0,
        )
        self.cumulative_log_predictive += predictive_log_probability
        self.observations += 1
        return self.last_change_probability

    def forecast(self) -> RegimeShiftForecast:
        predictive_components: list[tuple[float, float, float]] = []
        for item in self.hypotheses:
            predictive = item.posterior.predictive()
            variance = predictive.variance
            if not math.isfinite(variance):
                variance = predictive.scale * predictive.scale * 100.0
            predictive_components.append(
                (item.probability, predictive.location, max(variance, _EPS))
            )
        mean = sum(weight * location for weight, location, _ in predictive_components)
        second = sum(
            weight * (variance + location * location)
            for weight, location, variance in predictive_components
        )
        variance = max(_EPS, second - mean * mean)
        modal = max(self.hypotheses, key=lambda item: (item.probability, -item.run_length))
        expected = sum(item.probability * item.run_length for item in self.hypotheses)
        entropy = -sum(
            item.probability * math.log(item.probability)
            for item in self.hypotheses
            if item.probability > _EPS
        )
        effective = 1.0 / max(_EPS, sum(item.probability**2 for item in self.hypotheses))
        return RegimeShiftForecast(
            mean=mean,
            variance=variance,
            change_probability=self.last_change_probability,
            modal_run_length=modal.run_length,
            expected_run_length=expected,
            entropy=entropy,
            effective_hypotheses=effective,
        )

    def posterior(self) -> tuple[RunHypothesis, ...]:
        return tuple(self.hypotheses)


def detect_regime_shifts(
    series: HistoricalSeries,
    *,
    config: RegimeShiftConfig | None = None,
) -> RegimeShiftReport:
    actual_config = config or RegimeShiftConfig()
    detector = BayesianRegimeShiftDetector(series.values[0], config=actual_config)
    first = detector.forecast()
    observations = [
        RegimeShiftObservation(
            0,
            series.values[0],
            detector.cumulative_log_predictive,
            first.change_probability,
            first.modal_run_length,
            first.expected_run_length,
            first.entropy,
            first.effective_hypotheses,
        )
    ]
    events: list[RegimeShiftEvent] = []
    last_event = -actual_config.min_event_separation
    previous_modal = first.modal_run_length

    for index, value in enumerate(series.values[1:], start=1):
        prior_log = detector.prior_predictive_logpdf(value)
        probability = detector.update(value)
        forecast = detector.forecast()
        observations.append(
            RegimeShiftObservation(
                index,
                value,
                prior_log,
                probability,
                forecast.modal_run_length,
                forecast.expected_run_length,
                forecast.entropy,
                forecast.effective_hypotheses,
            )
        )
        if (
            probability >= actual_config.event_threshold
            and index - last_event >= actual_config.min_event_separation
        ):
            events.append(
                RegimeShiftEvent(
                    index,
                    value,
                    probability,
                    previous_modal,
                    forecast.modal_run_length,
                )
            )
            last_event = index
        previous_modal = forecast.modal_run_length

    final = detector.forecast()
    parts = [
        "jeeves-regime-shift-v1",
        series.label,
        ",".join(format(value, ".17g") for value in series.values),
        repr(actual_config),
    ]
    for item in observations:
        parts.extend(
            (
                str(item.index),
                format(item.change_probability, ".17g"),
                str(item.modal_run_length),
                format(item.expected_run_length, ".17g"),
            )
        )
    fingerprint = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return RegimeShiftReport(
        series.label,
        tuple(observations),
        tuple(events),
        final,
        fingerprint,
    )


__all__ = [
    "BayesianRegimeShiftDetector",
    "NormalInverseGamma",
    "RegimeShiftConfig",
    "RegimeShiftEvent",
    "RegimeShiftForecast",
    "RegimeShiftObservation",
    "RegimeShiftReport",
    "RunHypothesis",
    "StudentTPredictive",
    "detect_regime_shifts",
]
