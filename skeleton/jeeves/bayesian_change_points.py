"""Bayesian online change-point detection for Jeeves historical modeling.

Implements a bounded Adams-MacKay style run-length posterior using a
Normal-Inverse-Gamma conjugate model and Student-t one-step predictive density.
All updates are causal: observation t changes only posterior state available to
forecasts and change-point probabilities after t is observed.
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
    if maximum == -math.inf:
        return maximum
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


@dataclass(frozen=True, slots=True)
class ChangePointConfig:
    """Prior, hazard, and bounded-complexity configuration."""

    hazard_probability: float = 0.025
    max_hypotheses: int = 256
    prior_mean: float = 0.0
    prior_kappa: float = 1e-3
    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    minimum_probability: float = 1e-15
    event_threshold: float = 0.25
    min_event_separation: int = 3

    def __post_init__(self) -> None:
        hazard = _finite("hazard_probability", self.hazard_probability)
        if not 0.0 < hazard < 1.0:
            raise HistoricalModeError(
                "hazard_probability must be strictly between zero and one",
                context={"reason": "invalid_change_point_config"},
            )
        _positive_int("max_hypotheses", self.max_hypotheses)
        _finite("prior_mean", self.prior_mean)
        _positive("prior_kappa", self.prior_kappa)
        _positive("prior_alpha", self.prior_alpha)
        _positive("prior_beta", self.prior_beta)
        floor = _positive("minimum_probability", self.minimum_probability)
        if floor >= 1.0:
            raise HistoricalModeError(
                "minimum_probability must be less than one",
                context={"reason": "invalid_change_point_config"},
            )
        threshold = _finite("event_threshold", self.event_threshold)
        if not 0.0 < threshold < 1.0:
            raise HistoricalModeError(
                "event_threshold must be strictly between zero and one",
                context={"reason": "invalid_change_point_config"},
            )
        _positive_int("min_event_separation", self.min_event_separation)


@dataclass(frozen=True, slots=True)
class NIGState:
    """Normal-Inverse-Gamma posterior parameters for one run hypothesis."""

    mean: float
    kappa: float
    alpha: float
    beta: float

    def __post_init__(self) -> None:
        _finite("mean", self.mean)
        _positive("kappa", self.kappa)
        _positive("alpha", self.alpha)
        _positive("beta", self.beta)

    def updated(self, observation: float) -> "NIGState":
        value = _finite("observation", observation)
        next_kappa = self.kappa + 1.0
        delta = value - self.mean
        next_mean = (self.kappa * self.mean + value) / next_kappa
        next_alpha = self.alpha + 0.5
        next_beta = self.beta + 0.5 * self.kappa * delta * delta / next_kappa
        return NIGState(next_mean, next_kappa, next_alpha, max(next_beta, _EPS))

    def predictive(self) -> "StudentTPredictive":
        degrees = 2.0 * self.alpha
        scale_squared = self.beta * (self.kappa + 1.0) / (self.alpha * self.kappa)
        return StudentTPredictive(
            degrees_of_freedom=degrees,
            location=self.mean,
            scale=math.sqrt(max(scale_squared, _EPS)),
        )


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
            - ((degrees + 1.0) / 2.0) * math.log1p((z * z) / degrees)
        )

    @property
    def variance(self) -> float:
        if self.degrees_of_freedom <= 2.0:
            return math.inf
        return self.scale * self.scale * self.degrees_of_freedom / (
            self.degrees_of_freedom - 2.0
        )


@dataclass(frozen=True, slots=True)
class RunLengthHypothesis:
    run_length: int
    probability: float
    state: NIGState

    def __post_init__(self) -> None:
        if isinstance(self.run_length, bool) or not isinstance(self.run_length, int) or self.run_length <= 0:
            raise HistoricalModeError(
                "run_length must be a positive integer",
                context={"reason": "invalid_run_length"},
            )
        probability = _finite("probability", self.probability)
        if not 0.0 <= probability <= 1.0:
            raise HistoricalModeError(
                "run-length probability must be between zero and one",
                context={"reason": "invalid_run_length_probability"},
            )


@dataclass(frozen=True, slots=True)
class ChangePointForecast:
    mean: float
    variance: float
    change_probability: float
    modal_run_length: int
    expected_run_length: float
    run_length_entropy: float
    effective_hypotheses: float

    def __post_init__(self) -> None:
        _finite("mean", self.mean)
        _positive("variance", self.variance)
        probability = _finite("change_probability", self.change_probability)
        if not 0.0 <= probability <= 1.0:
            raise HistoricalModeError(
                "change_probability must be between zero and one",
                context={"reason": "invalid_change_probability"},
            )
        _positive_int("modal_run_length", self.modal_run_length)
        _positive("expected_run_length", self.expected_run_length)
        if self.run_length_entropy < 0.0 or self.effective_hypotheses < 1.0:
            raise HistoricalModeError(
                "invalid posterior diagnostics",
                context={"reason": "invalid_change_point_diagnostics"},
            )


@dataclass(frozen=True, slots=True)
class ChangePointObservation:
    index: int
    value: float
    prior_predictive_log_probability: float
    change_probability: float
    modal_run_length: int
    expected_run_length: float
    run_length_entropy: float
    effective_hypotheses: float


@dataclass(frozen=True, slots=True)
class ChangePointEvent:
    index: int
    value: float
    probability: float
    previous_modal_run_length: int
    new_modal_run_length: int


@dataclass(frozen=True, slots=True)
class ChangePointReport:
    series_label: str
    observations: tuple[ChangePointObservation, ...]
    events: tuple[ChangePointEvent, ...]
    final_forecast: ChangePointForecast
    fingerprint: str

    def as_payload(self) -> dict[str, object]:
        return {
            "series_label": self.series_label,
            "observations": len(self.observations),
            "events": len(self.events),
            "change_probability": self.final_forecast.change_probability,
            "modal_run_length": self.final_forecast.modal_run_length,
            "expected_run_length": self.final_forecast.expected_run_length,
            "run_length_entropy": self.final_forecast.run_length_entropy,
            "fingerprint": self.fingerprint,
        }


class BayesianOnlineChangePointDetector:
    """Causal bounded run-length posterior with conjugate predictive evidence."""

    def __init__(
        self,
        first_value: float,
        *,
        config: ChangePointConfig | None = None,
    ) -> None:
        self.config = config or ChangePointConfig()
        self._prior = NIGState(
            self.config.prior_mean,
            self.config.prior_kappa,
            self.config.prior_alpha,
            self.config.prior_beta,
        )
        first = _finite("first_value", first_value)
        first_state = self._prior.updated(first)
        self.hypotheses = [RunLengthHypothesis(1, 1.0, first_state)]
        self.observations = 1
        self.last_change_probability = self.config.hazard_probability
        self.cumulative_log_predictive = self._prior.predictive().logpdf(first)

    @classmethod
    def fit(
        cls,
        values: Iterable[float],
        *,
        config: ChangePointConfig | None = None,
    ) -> "BayesianOnlineChangePointDetector":
        clean = tuple(_finite("value", value) for value in values)
        if not clean:
            raise HistoricalModeError(
                "change-point fit requires observations",
                context={"reason": "empty_series"},
            )
        detector = cls(clean[0], config=config)
        for value in clean[1:]:
            detector.update(value)
        return detector

    def prior_predictive_logpdf(self, observation: float) -> float:
        actual = _finite("observation", observation)
        terms = [
            math.log(max(item.probability, self.config.minimum_probability))
            + item.state.predictive().logpdf(actual)
            for item in self.hypotheses
        ]
        return _logsumexp(terms)

    def update(self, observation: float) -> float:
        actual = _finite("observation", observation)
        hazard = self.config.hazard_probability
        floor = self.config.minimum_probability

        predictive_logs = [item.state.predictive().logpdf(actual) for item in self.hypotheses]
        previous_log_probs = [math.log(max(item.probability, floor)) for item in self.hypotheses]
        total_predictive_log = _logsumexp(
            [probability + evidence for probability, evidence in zip(previous_log_probs, predictive_logs)]
        )

        change_log_probability = _logsumexp(
            [
                probability + math.log(hazard) + evidence
                for probability, evidence in zip(previous_log_probs, predictive_logs)
            ]
        )
        change_state = self._prior.updated(actual)
        candidates: list[tuple[int, float, NIGState]] = [
            (1, change_log_probability, change_state)
        ]

        growth_log_hazard = math.log1p(-hazard)
        for item, log_probability, evidence in zip(
            self.hypotheses,
            previous_log_probs,
            predictive_logs,
        ):
            candidates.append(
                (
                    item.run_length + 1,
                    log_probability + growth_log_hazard + evidence,
                    item.state.updated(actual),
                )
            )

        normalizer = _logsumexp([candidate[1] for candidate in candidates])
        normalized = [
            (run_length, math.exp(log_probability - normalizer), state)
            for run_length, log_probability, state in candidates
        ]
        normalized.sort(key=lambda item: (-item[1], item[0]))
        normalized = normalized[: self.config.max_hypotheses]
        retained_total = sum(item[1] for item in normalized)
        self.hypotheses = [
            RunLengthHypothesis(run_length, probability / retained_total, state)
            for run_length, probability, state in sorted(normalized, key=lambda item: item[0])
        ]
        self.last_change_probability = next(
            item.probability for item in self.hypotheses if item.run_length == 1
        ) if any(item.run_length == 1 for item in self.hypotheses) else 0.0
        self.cumulative_log_predictive += total_predictive_log
        self.observations += 1
        return self.last_change_probability

    def forecast(self) -> ChangePointForecast:
        means: list[tuple[float, float, float]] = []
        for hypothesis in self.hypotheses:
            predictive = hypothesis.state.predictive()
            variance = predictive.variance
            if not math.isfinite(variance):
                variance = predictive.scale * predictive.scale * 100.0
            means.append((hypothesis.probability, predictive.location, max(variance, _EPS)))

        mean = sum(weight * location for weight, location, _ in means)
        second = sum(
            weight * (variance + location * location)
            for weight, location, variance in means
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
        return ChangePointForecast(
            mean=mean,
            variance=variance,
            change_probability=self.last_change_probability,
            modal_run_length=modal.run_length,
            expected_run_length=expected,
            run_length_entropy=entropy,
            effective_hypotheses=effective,
        )

    def posterior(self) -> tuple[RunLengthHypothesis, ...]:
        return tuple(self.hypotheses)


def detect_change_points(
    series: HistoricalSeries,
    *,
    config: ChangePointConfig | None = None,
) -> ChangePointReport:
    actual_config = config or ChangePointConfig()
    values = series.values
    if not values:
        raise HistoricalModeError(
            "change-point detection requires observations",
            context={"reason": "empty_series"},
        )

    detector = BayesianOnlineChangePointDetector(values[0], config=actual_config)
    first_forecast = detector.forecast()
    observations: list[ChangePointObservation] = [
        ChangePointObservation(
            index=0,
            value=values[0],
            prior_predictive_log_probability=detector.cumulative_log_predictive,
            change_probability=first_forecast.change_probability,
            modal_run_length=first_forecast.modal_run_length,
            expected_run_length=first_forecast.expected_run_length,
            run_length_entropy=first_forecast.run_length_entropy,
            effective_hypotheses=first_forecast.effective_hypotheses,
        )
    ]
    events: list[ChangePointEvent] = []
    last_event_index = -actual_config.min_event_separation
    previous_modal = first_forecast.modal_run_length

    for index, value in enumerate(values[1:], start=1):
        prior_log_probability = detector.prior_predictive_logpdf(value)
        probability = detector.update(value)
        forecast = detector.forecast()
        observations.append(
            ChangePointObservation(
                index=index,
                value=value,
                prior_predictive_log_probability=prior_log_probability,
                change_probability=probability,
                modal_run_length=forecast.modal_run_length,
                expected_run_length=forecast.expected_run_length,
                run_length_entropy=forecast.run_length_entropy,
                effective_hypotheses=forecast.effective_hypotheses,
            )
        )
        if (
            probability >= actual_config.event_threshold
            and index - last_event_index >= actual_config.min_event_separation
        ):
            events.append(
                ChangePointEvent(
                    index=index,
                    value=value,
                    probability=probability,
                    previous_modal_run_length=previous_modal,
                    new_modal_run_length=forecast.modal_run_length,
                )
            )
            last_event_index = index
        previous_modal = forecast.modal_run_length

    final_forecast = detector.forecast()
    fingerprint = _report_fingerprint(
        series,
        actual_config,
        observations,
        events,
        final_forecast,
    )
    return ChangePointReport(
        series_label=series.label,
        observations=tuple(observations),
        events=tuple(events),
        final_forecast=final_forecast,
        fingerprint=fingerprint,
    )


def _report_fingerprint(
    series: HistoricalSeries,
    config: ChangePointConfig,
    observations: Sequence[ChangePointObservation],
    events: Sequence[ChangePointEvent],
    final_forecast: ChangePointForecast,
) -> str:
    parts = [
        "jeeves-bocpd-v1",
        series.label,
        ",".join(format(value, ".17g") for value in series.values),
        repr(config),
        format(final_forecast.change_probability, ".17g"),
        str(final_forecast.modal_run_length),
    ]
    for observation in observations:
        parts.extend(
            (
                str(observation.index),
                format(observation.change_probability, ".17g"),
                str(observation.modal_run_length),
                format(observation.expected_run_length, ".17g"),
            )
        )
    for event in events:
        parts.extend(
            (
                "event",
                str(event.index),
                format(event.probability, ".17g"),
                str(event.previous_modal_run_length),
                str(event.new_modal_run_length),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


__all__ = [
    "BayesianOnlineChangePointDetector",
    "ChangePointConfig",
    "ChangePointEvent",
    "ChangePointForecast",
    "ChangePointObservation",
    "ChangePointReport",
    "NIGState",
    "RunLengthHypothesis",
    "StudentTPredictive",
    "detect_change_points",
]
