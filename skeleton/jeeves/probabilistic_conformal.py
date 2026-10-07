"""Leakage-safe adaptive conformal calibration for Jeeves forecasts.

This module adds a model-agnostic uncertainty layer on top of predictive
forecasts.  It does not alter an underlying model's mean or variance.  Instead,
it learns a sequence of completed nonconformity scores and converts them into
finite-sample prediction intervals for later targets.

For target ``t`` the interval is constructed exclusively from scores belonging
to targets strictly before ``t``.  The realized target may enter the calibration
window only after its interval has been scored.  Adaptive miscoverage control is
likewise updated after scoring, so future observations cannot leak into an
already-issued interval.

The guarantees of ordinary split conformal prediction rely on exchangeability;
rolling and adaptive time-series use weakens that classical guarantee.  Jeeves
therefore records empirical coverage, width, interval score, effective alpha,
and the exact calibration state rather than treating nominal coverage as fact.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Protocol, Sequence

from .probabilistic_state_space import StateSpaceError


class ConformalPredictiveDistribution(Protocol):
    """Minimal predictive contract required by conformal calibration."""

    horizon: int
    mean: float
    variance: float


@dataclass(frozen=True, slots=True)
class ConformalConfig:
    """Configuration for rolling prequential conformal calibration."""

    alpha: float = 0.10
    min_calibration: int = 20
    calibration_window: int = 128
    adaptive_rate: float = 0.02
    min_alpha: float = 0.01
    max_alpha: float = 0.40
    normalized: bool = True
    min_scale: float = 1e-8

    def __post_init__(self) -> None:
        alpha = _open_interval("alpha", self.alpha, 0.0, 1.0)
        if (
            isinstance(self.min_calibration, bool)
            or not isinstance(self.min_calibration, int)
            or self.min_calibration < 4
        ):
            raise StateSpaceError(
                "min_calibration must be an integer >= 4",
                context={
                    "reason": "invalid_conformal_config",
                    "field": "min_calibration",
                },
            )
        if (
            isinstance(self.calibration_window, bool)
            or not isinstance(self.calibration_window, int)
            or self.calibration_window < self.min_calibration
        ):
            raise StateSpaceError(
                "calibration_window must be >= min_calibration",
                context={
                    "reason": "invalid_conformal_config",
                    "field": "calibration_window",
                },
            )
        _closed_interval("adaptive_rate", self.adaptive_rate, 0.0, 1.0)
        minimum = _open_interval("min_alpha", self.min_alpha, 0.0, 1.0)
        maximum = _open_interval("max_alpha", self.max_alpha, 0.0, 1.0)
        if not minimum < alpha < maximum:
            raise StateSpaceError(
                "min_alpha < alpha < max_alpha is required",
                context={
                    "reason": "invalid_conformal_config",
                    "field": "alpha_bounds",
                },
            )
        _positive("min_scale", self.min_scale)
        if not isinstance(self.normalized, bool):
            raise StateSpaceError(
                "normalized must be a boolean",
                context={
                    "reason": "invalid_conformal_config",
                    "field": "normalized",
                },
            )


@dataclass(frozen=True, slots=True)
class ForecastObservation:
    """One realized target paired with its pre-target predictive distribution."""

    target_index: int
    actual: float
    predictive: ConformalPredictiveDistribution

    def __post_init__(self) -> None:
        if (
            isinstance(self.target_index, bool)
            or not isinstance(self.target_index, int)
            or self.target_index < 1
        ):
            raise StateSpaceError(
                "target_index must be a positive integer",
                context={"reason": "invalid_conformal_observation"},
            )
        _finite("actual", self.actual)
        _validate_predictive(self.predictive)


@dataclass(frozen=True, slots=True)
class ConformalInterval:
    """A prediction interval issued before observing its target."""

    target_index: int
    horizon: int
    center: float
    lower: float
    upper: float
    radius: float
    quantile: float
    effective_alpha: float
    calibration_size: int
    scale: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.target_index, bool)
            or not isinstance(self.target_index, int)
            or self.target_index < 1
            or isinstance(self.horizon, bool)
            or not isinstance(self.horizon, int)
            or self.horizon < 1
        ):
            raise StateSpaceError(
                "conformal interval indices must be positive integers",
                context={"reason": "invalid_conformal_interval"},
            )
        for name in (
            "center",
            "lower",
            "upper",
            "radius",
            "quantile",
            "effective_alpha",
            "scale",
        ):
            _finite(name, getattr(self, name))
        if self.lower > self.center or self.center > self.upper:
            raise StateSpaceError(
                "conformal interval must contain its center",
                context={"reason": "invalid_conformal_interval"},
            )
        if self.radius < 0.0 or self.quantile < 0.0 or self.scale <= 0.0:
            raise StateSpaceError(
                "conformal interval geometry must be non-negative",
                context={"reason": "invalid_conformal_interval"},
            )
        if not 0.0 < self.effective_alpha < 1.0:
            raise StateSpaceError(
                "effective_alpha must lie in (0, 1)",
                context={"reason": "invalid_conformal_interval"},
            )
        if (
            isinstance(self.calibration_size, bool)
            or not isinstance(self.calibration_size, int)
            or self.calibration_size < 1
        ):
            raise StateSpaceError(
                "calibration_size must be a positive integer",
                context={"reason": "invalid_conformal_interval"},
            )

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, actual: float) -> bool:
        actual = _finite("actual", actual)
        return self.lower <= actual <= self.upper


@dataclass(frozen=True, slots=True)
class ConformalStep:
    """One interval scored before its target updates calibration state."""

    actual: float
    interval: ConformalInterval
    nonconformity_score: float
    missed: bool
    interval_score: float

    def __post_init__(self) -> None:
        _finite("actual", self.actual)
        score = _finite("nonconformity_score", self.nonconformity_score)
        interval_score = _finite("interval_score", self.interval_score)
        if score < 0.0 or interval_score < 0.0:
            raise StateSpaceError(
                "conformal scores must be non-negative",
                context={"reason": "invalid_conformal_step"},
            )
        if not isinstance(self.missed, bool):
            raise StateSpaceError(
                "missed must be a boolean",
                context={"reason": "invalid_conformal_step"},
            )
        if self.missed == self.interval.contains(self.actual):
            raise StateSpaceError(
                "missed flag disagrees with interval geometry",
                context={"reason": "invalid_conformal_step"},
            )


@dataclass(frozen=True, slots=True)
class ConformalReport:
    """Auditable prequential conformal evidence and reusable final state."""

    config: ConformalConfig
    configuration_fingerprint: str
    warmup_count: int
    steps: tuple[ConformalStep, ...]
    empirical_coverage: float
    mean_width: float
    median_width: float
    mean_interval_score: float
    mean_nonconformity: float
    final_effective_alpha: float
    final_calibration_scores: tuple[float, ...]
    fingerprint: str

    @property
    def target_coverage(self) -> float:
        return 1.0 - self.config.alpha

    @property
    def coverage_gap(self) -> float:
        return self.empirical_coverage - self.target_coverage

    @property
    def miss_rate(self) -> float:
        return 1.0 - self.empirical_coverage


def conformal_quantile(scores: Sequence[float], alpha: float) -> float:
    """Return the conservative finite-sample conformal quantile.

    The rank is ``ceil((n + 1) * (1 - alpha))`` and is clipped to ``n``.
    No interpolation is performed because interpolation can silently make a
    finite-sample conformal interval less conservative.
    """

    alpha = _open_interval("alpha", alpha, 0.0, 1.0)
    if not scores:
        raise StateSpaceError(
            "at least one calibration score is required",
            context={"reason": "empty_conformal_calibration"},
        )
    ordered = sorted(_non_negative("score", score) for score in scores)
    rank = math.ceil((len(ordered) + 1) * (1.0 - alpha))
    index = min(len(ordered), max(1, rank)) - 1
    return ordered[index]


def nonconformity_score(
    actual: float,
    predictive: ConformalPredictiveDistribution,
    *,
    normalized: bool = True,
    min_scale: float = 1e-8,
) -> float:
    """Measure realized forecast error using only the completed target."""

    actual = _finite("actual", actual)
    _validate_predictive(predictive)
    min_scale = _positive("min_scale", min_scale)
    if not isinstance(normalized, bool):
        raise StateSpaceError(
            "normalized must be a boolean",
            context={"reason": "invalid_conformal_score"},
        )
    scale = _predictive_scale(predictive, normalized=normalized, min_scale=min_scale)
    return abs(actual - predictive.mean) / scale


def conformal_interval(
    predictive: ConformalPredictiveDistribution,
    calibration_scores: Sequence[float],
    *,
    config: ConformalConfig | None = None,
    target_index: int,
    effective_alpha: float | None = None,
) -> ConformalInterval:
    """Construct an interval from already-completed calibration scores."""

    config = config or ConformalConfig()
    _validate_predictive(predictive)
    if (
        isinstance(target_index, bool)
        or not isinstance(target_index, int)
        or target_index < 1
    ):
        raise StateSpaceError(
            "target_index must be a positive integer",
            context={"reason": "invalid_conformal_interval"},
        )
    if len(calibration_scores) < config.min_calibration:
        raise StateSpaceError(
            "insufficient completed calibration scores",
            context={
                "reason": "insufficient_conformal_calibration",
                "required": config.min_calibration,
                "actual": len(calibration_scores),
            },
        )
    alpha = (
        config.alpha
        if effective_alpha is None
        else _open_interval("effective_alpha", effective_alpha, 0.0, 1.0)
    )
    if not config.min_alpha <= alpha <= config.max_alpha:
        raise StateSpaceError(
            "effective_alpha is outside configured bounds",
            context={"reason": "invalid_conformal_alpha"},
        )
    window = tuple(calibration_scores[-config.calibration_window :])
    quantile = conformal_quantile(window, alpha)
    scale = _predictive_scale(
        predictive,
        normalized=config.normalized,
        min_scale=config.min_scale,
    )
    radius = quantile * scale
    return ConformalInterval(
        target_index=target_index,
        horizon=predictive.horizon,
        center=predictive.mean,
        lower=predictive.mean - radius,
        upper=predictive.mean + radius,
        radius=radius,
        quantile=quantile,
        effective_alpha=alpha,
        calibration_size=len(window),
        scale=scale,
    )


def evaluate_prequential_conformal(
    observations: Sequence[ForecastObservation],
    *,
    config: ConformalConfig | None = None,
) -> ConformalReport:
    """Evaluate rolling conformal intervals without target-time leakage."""

    config = config or ConformalConfig()
    _validate_observation_order(observations)
    if len(observations) <= config.min_calibration:
        raise StateSpaceError(
            "not enough observations for conformal evaluation",
            context={"reason": "insufficient_conformal_history"},
        )

    calibration: list[float] = []
    steps: list[ConformalStep] = []
    effective_alpha = config.alpha

    for observation in observations:
        score = nonconformity_score(
            observation.actual,
            observation.predictive,
            normalized=config.normalized,
            min_scale=config.min_scale,
        )

        if len(calibration) >= config.min_calibration:
            interval = conformal_interval(
                observation.predictive,
                calibration,
                config=config,
                target_index=observation.target_index,
                effective_alpha=effective_alpha,
            )
            missed = not interval.contains(observation.actual)
            steps.append(
                ConformalStep(
                    actual=observation.actual,
                    interval=interval,
                    nonconformity_score=score,
                    missed=missed,
                    interval_score=_interval_score(
                        lower=interval.lower,
                        upper=interval.upper,
                        actual=observation.actual,
                        alpha=interval.effective_alpha,
                    ),
                )
            )
            effective_alpha = _adaptive_alpha_update(
                effective_alpha,
                missed=missed,
                config=config,
            )

        calibration.append(score)
        if len(calibration) > config.calibration_window:
            del calibration[: len(calibration) - config.calibration_window]

    if not steps:
        raise StateSpaceError(
            "conformal evaluation produced no scored intervals",
            context={"reason": "insufficient_conformal_history"},
        )

    coverage = statistics.fmean(0.0 if step.missed else 1.0 for step in steps)
    widths = [step.interval.width for step in steps]
    configuration_fingerprint = _configuration_fingerprint(config)
    fingerprint = _report_fingerprint(
        configuration_fingerprint=configuration_fingerprint,
        warmup_count=config.min_calibration,
        steps=steps,
        final_effective_alpha=effective_alpha,
        final_calibration_scores=calibration,
    )
    return ConformalReport(
        config=config,
        configuration_fingerprint=configuration_fingerprint,
        warmup_count=config.min_calibration,
        steps=tuple(steps),
        empirical_coverage=coverage,
        mean_width=statistics.fmean(widths),
        median_width=statistics.median(widths),
        mean_interval_score=statistics.fmean(step.interval_score for step in steps),
        mean_nonconformity=statistics.fmean(
            step.nonconformity_score for step in steps
        ),
        final_effective_alpha=effective_alpha,
        final_calibration_scores=tuple(calibration),
        fingerprint=fingerprint,
    )


def evaluate_cross_family_conformal(
    report: object,
    *,
    config: ConformalConfig | None = None,
) -> ConformalReport:
    """Conformalize a completed cross-family arbitration report.

    A structural protocol is used intentionally: the conformal layer consumes
    only pre-target forecast objects plus realized targets and does not gain
    authority over the arbitrator or its learning state.
    """

    steps = getattr(report, "steps", None)
    if steps is None:
        raise StateSpaceError(
            "cross-family report must expose steps",
            context={"reason": "invalid_conformal_source_report"},
        )
    observations: list[ForecastObservation] = []
    for step in steps:
        try:
            observations.append(
                ForecastObservation(
                    target_index=step.target_index,
                    actual=step.actual,
                    predictive=step.predictive,
                )
            )
        except AttributeError as exc:
            raise StateSpaceError(
                "cross-family report step is missing required fields",
                context={"reason": "invalid_conformal_source_report"},
            ) from exc
    return evaluate_prequential_conformal(observations, config=config)


def conformalize_next_forecast(
    predictive: ConformalPredictiveDistribution,
    report: ConformalReport,
    *,
    target_index: int,
) -> ConformalInterval:
    """Issue the next interval from a completed, integrity-checked report."""

    _validate_report_identity(report)
    return conformal_interval(
        predictive,
        report.final_calibration_scores,
        config=report.config,
        target_index=target_index,
        effective_alpha=report.final_effective_alpha,
    )


def _adaptive_alpha_update(
    current: float,
    *,
    missed: bool,
    config: ConformalConfig,
) -> float:
    if config.adaptive_rate == 0.0:
        return current
    error = 1.0 if missed else 0.0
    updated = current + config.adaptive_rate * (config.alpha - error)
    return min(config.max_alpha, max(config.min_alpha, updated))


def _interval_score(*, lower: float, upper: float, actual: float, alpha: float) -> float:
    width = upper - lower
    penalty = 0.0
    if actual < lower:
        penalty = (2.0 / alpha) * (lower - actual)
    elif actual > upper:
        penalty = (2.0 / alpha) * (actual - upper)
    return width + penalty


def _predictive_scale(
    predictive: ConformalPredictiveDistribution,
    *,
    normalized: bool,
    min_scale: float,
) -> float:
    if not normalized:
        return 1.0
    return max(min_scale, math.sqrt(predictive.variance))


def _validate_predictive(predictive: ConformalPredictiveDistribution) -> None:
    horizon = getattr(predictive, "horizon", None)
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise StateSpaceError(
            "predictive horizon must be a positive integer",
            context={"reason": "invalid_conformal_predictive"},
        )
    _finite("predictive_mean", predictive.mean)
    variance = _finite("predictive_variance", predictive.variance)
    if variance <= 0.0:
        raise StateSpaceError(
            "predictive variance must be positive",
            context={"reason": "invalid_conformal_predictive"},
        )


def _validate_observation_order(observations: Sequence[ForecastObservation]) -> None:
    if not observations:
        raise StateSpaceError(
            "conformal observations cannot be empty",
            context={"reason": "empty_conformal_observations"},
        )
    previous: int | None = None
    for observation in observations:
        if not isinstance(observation, ForecastObservation):
            raise StateSpaceError(
                "all conformal observations must be ForecastObservation values",
                context={"reason": "invalid_conformal_observation"},
            )
        if previous is not None and observation.target_index <= previous:
            raise StateSpaceError(
                "conformal target indices must be strictly increasing",
                context={"reason": "non_monotonic_conformal_targets"},
            )
        previous = observation.target_index


def _validate_report_identity(report: ConformalReport) -> None:
    if not isinstance(report, ConformalReport):
        raise StateSpaceError(
            "report must be a ConformalReport",
            context={"reason": "invalid_conformal_report"},
        )
    expected_configuration = _configuration_fingerprint(report.config)
    if report.configuration_fingerprint != expected_configuration:
        raise StateSpaceError(
            "conformal report configuration fingerprint mismatch",
            context={"reason": "conformal_report_identity_mismatch"},
        )
    if report.warmup_count != report.config.min_calibration:
        raise StateSpaceError(
            "conformal report warmup state is inconsistent",
            context={"reason": "conformal_report_identity_mismatch"},
        )
    if not report.steps:
        raise StateSpaceError(
            "conformal report has no scored steps",
            context={"reason": "invalid_conformal_report"},
        )
    if not (
        report.config.min_calibration
        <= len(report.final_calibration_scores)
        <= report.config.calibration_window
    ):
        raise StateSpaceError(
            "conformal report calibration state is out of bounds",
            context={"reason": "conformal_report_identity_mismatch"},
        )
    for score in report.final_calibration_scores:
        _non_negative("final_calibration_score", score)
    if not (
        report.config.min_alpha
        <= report.final_effective_alpha
        <= report.config.max_alpha
    ):
        raise StateSpaceError(
            "conformal report effective alpha is out of bounds",
            context={"reason": "conformal_report_identity_mismatch"},
        )
    expected_report = _report_fingerprint(
        configuration_fingerprint=report.configuration_fingerprint,
        warmup_count=report.warmup_count,
        steps=report.steps,
        final_effective_alpha=report.final_effective_alpha,
        final_calibration_scores=report.final_calibration_scores,
    )
    if report.fingerprint != expected_report:
        raise StateSpaceError(
            "conformal report state fingerprint mismatch",
            context={"reason": "conformal_report_identity_mismatch"},
        )


def _configuration_fingerprint(config: ConformalConfig) -> str:
    payload = {
        "adaptive_rate": config.adaptive_rate,
        "alpha": config.alpha,
        "calibration_window": config.calibration_window,
        "max_alpha": config.max_alpha,
        "min_alpha": config.min_alpha,
        "min_calibration": config.min_calibration,
        "min_scale": config.min_scale,
        "normalized": config.normalized,
        "schema": "jeeves.conformal.config.v1",
    }
    return _digest(payload)


def _report_fingerprint(
    *,
    configuration_fingerprint: str,
    warmup_count: int,
    steps: Sequence[ConformalStep],
    final_effective_alpha: float,
    final_calibration_scores: Sequence[float],
) -> str:
    payload = {
        "configuration_fingerprint": configuration_fingerprint,
        "final_calibration_scores": list(final_calibration_scores),
        "final_effective_alpha": final_effective_alpha,
        "schema": "jeeves.conformal.report.v1",
        "steps": [
            {
                "actual": step.actual,
                "effective_alpha": step.interval.effective_alpha,
                "interval_score": step.interval_score,
                "lower": step.interval.lower,
                "missed": step.missed,
                "nonconformity_score": step.nonconformity_score,
                "quantile": step.interval.quantile,
                "target_index": step.interval.target_index,
                "upper": step.interval.upper,
            }
            for step in steps
        ],
        "warmup_count": warmup_count,
    }
    return _digest(payload)


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    result = float(value)
    if not math.isfinite(result):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


def _non_negative(name: str, value: float) -> float:
    result = _finite(name, value)
    if result < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


def _positive(name: str, value: float) -> float:
    result = _finite(name, value)
    if result <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


def _open_interval(name: str, value: float, low: float, high: float) -> float:
    result = _finite(name, value)
    if not low < result < high:
        raise StateSpaceError(
            f"{name} must lie in ({low}, {high})",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


def _closed_interval(name: str, value: float, low: float, high: float) -> float:
    result = _finite(name, value)
    if not low <= result <= high:
        raise StateSpaceError(
            f"{name} must lie in [{low}, {high}]",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result
