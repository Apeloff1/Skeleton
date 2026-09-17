"""Leakage-safe adaptive conformal calibration for Jeeves forecasts.

This module adds a model-agnostic uncertainty layer on top of predictive
forecasts. It does not alter an underlying model's mean or variance. Instead, it
learns completed nonconformity scores and converts them into finite-sample
prediction intervals for later targets.

For target ``t`` the interval is constructed exclusively from scores belonging
to targets strictly before ``t``. The realized target may enter the calibration
window only after its interval has been scored. Adaptive miscoverage control is
likewise updated after scoring, so future observations cannot leak into an
already-issued interval.

Finite calibration sets have finite coverage resolution. With ``n`` scores the
smallest finite split-conformal miscoverage is ``1/(n+1)``. Jeeves never clips an
impossible rank to the largest observed score while claiming the smaller alpha:
low-level quantile requests fail closed, while interval issuance raises alpha to
the attainable floor and records that effective value explicitly.

The guarantees of ordinary split conformal prediction rely on exchangeability;
rolling and adaptive time-series use weakens that classical guarantee. Jeeves
therefore records empirical coverage, width, interval score, effective alpha,
and exact calibration state rather than treating nominal coverage as fact.
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
        _positive_index("target_index", self.target_index)
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
        _positive_index("target_index", self.target_index)
        _positive_index("horizon", self.horizon)
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
        _open_interval("effective_alpha", self.effective_alpha, 0.0, 1.0)
        if (
            isinstance(self.calibration_size, bool)
            or not isinstance(self.calibration_size, int)
            or self.calibration_size < 1
        ):
            raise StateSpaceError(
                "calibration_size must be a positive integer",
                context={"reason": "invalid_conformal_interval"},
            )
        expected_floor = attainable_alpha_floor(self.calibration_size)
        if self.effective_alpha + 1e-15 < expected_floor:
            raise StateSpaceError(
                "effective_alpha is unattainable for calibration size",
                context={
                    "reason": "invalid_conformal_interval",
                    "attainable_alpha_floor": expected_floor,
                },
            )
        tolerance = max(1e-9, 1e-12 * max(1.0, abs(self.radius)))
        if abs((self.center - self.lower) - self.radius) > tolerance:
            raise StateSpaceError(
                "lower interval radius is inconsistent",
                context={"reason": "invalid_conformal_interval"},
            )
        if abs((self.upper - self.center) - self.radius) > tolerance:
            raise StateSpaceError(
                "upper interval radius is inconsistent",
                context={"reason": "invalid_conformal_interval"},
            )

    @property
    def width(self) -> float:
        return _finite_result("interval_width", self.upper - self.lower)

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


def attainable_alpha_floor(calibration_size: int) -> float:
    """Smallest finite split-conformal alpha supported by a score set."""

    if (
        isinstance(calibration_size, bool)
        or not isinstance(calibration_size, int)
        or calibration_size < 1
    ):
        raise StateSpaceError(
            "calibration_size must be a positive integer",
            context={"reason": "invalid_conformal_calibration_size"},
        )
    return 1.0 / (calibration_size + 1.0)


def required_calibration_size(alpha: float) -> int:
    """Minimum number of scores required for a finite interval at ``alpha``."""

    alpha = _open_interval("alpha", alpha, 0.0, 1.0)
    return max(1, math.ceil((1.0 / alpha) - 1.0 - 1e-12))


def conformal_quantile(scores: Sequence[float], alpha: float) -> float:
    """Return the finite-sample conformal order statistic.

    The rank is ``ceil((n + 1) * (1 - alpha))``. Requests below the
    finite-sample alpha floor fail closed instead of clipping rank to ``n`` and
    overstating the requested coverage.
    """

    alpha = _open_interval("alpha", alpha, 0.0, 1.0)
    try:
        raw_scores = tuple(scores)
    except TypeError as exc:
        raise StateSpaceError(
            "calibration scores must be iterable",
            context={"reason": "invalid_conformal_calibration"},
        ) from exc
    if not raw_scores:
        raise StateSpaceError(
            "at least one calibration score is required",
            context={"reason": "empty_conformal_calibration"},
        )
    ordered = sorted(_non_negative("score", score) for score in raw_scores)
    floor = attainable_alpha_floor(len(ordered))
    if alpha + 1e-15 < floor:
        raise StateSpaceError(
            "requested conformal alpha is unattainable with available scores",
            context={
                "reason": "unattainable_conformal_alpha",
                "requested_alpha": alpha,
                "attainable_alpha_floor": floor,
                "calibration_size": len(ordered),
                "required_calibration_size": required_calibration_size(alpha),
            },
        )
    rank = math.ceil((len(ordered) + 1) * (1.0 - alpha))
    if rank < 1 or rank > len(ordered):
        raise StateSpaceError(
            "conformal rank escaped finite score support",
            context={"reason": "conformal_numerical_instability", "rank": rank},
        )
    return ordered[rank - 1]


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
    scale = _predictive_scale(
        predictive,
        normalized=normalized,
        min_scale=min_scale,
    )
    residual = _finite_result("absolute_residual", abs(actual - predictive.mean))
    return _finite_result("nonconformity_score", residual / scale)


def conformal_interval(
    predictive: ConformalPredictiveDistribution,
    calibration_scores: Sequence[float],
    *,
    config: ConformalConfig | None = None,
    target_index: int,
    effective_alpha: float | None = None,
) -> ConformalInterval:
    """Construct an interval from already-completed calibration scores.

    If adaptive state asks for alpha below the score set's finite resolution,
    issuance uses the attainable floor and records it in ``effective_alpha``.
    """

    config = config or ConformalConfig()
    _validate_predictive(predictive)
    _positive_index("target_index", target_index)
    try:
        raw_scores = tuple(calibration_scores)
    except TypeError as exc:
        raise StateSpaceError(
            "calibration scores must be iterable",
            context={"reason": "invalid_conformal_calibration"},
        ) from exc
    if len(raw_scores) < config.min_calibration:
        raise StateSpaceError(
            "insufficient completed calibration scores",
            context={
                "reason": "insufficient_conformal_calibration",
                "required": config.min_calibration,
                "actual": len(raw_scores),
            },
        )
    requested_alpha = (
        config.alpha
        if effective_alpha is None
        else _open_interval("effective_alpha", effective_alpha, 0.0, 1.0)
    )
    if not config.min_alpha <= requested_alpha <= config.max_alpha:
        raise StateSpaceError(
            "effective_alpha is outside configured bounds",
            context={"reason": "invalid_conformal_alpha"},
        )
    window = tuple(raw_scores[-config.calibration_window :])
    clean_window = tuple(_non_negative("calibration_score", score) for score in window)
    alpha = max(requested_alpha, attainable_alpha_floor(len(clean_window)))
    quantile = conformal_quantile(clean_window, alpha)
    scale = _predictive_scale(
        predictive,
        normalized=config.normalized,
        min_scale=config.min_scale,
    )
    radius = _finite_result("conformal_radius", quantile * scale)
    lower = _finite_result("conformal_lower", predictive.mean - radius)
    upper = _finite_result("conformal_upper", predictive.mean + radius)
    return ConformalInterval(
        target_index=target_index,
        horizon=predictive.horizon,
        center=predictive.mean,
        lower=lower,
        upper=upper,
        radius=radius,
        quantile=quantile,
        effective_alpha=alpha,
        calibration_size=len(clean_window),
        scale=scale,
    )


def evaluate_prequential_conformal(
    observations: Sequence[ForecastObservation],
    *,
    config: ConformalConfig | None = None,
) -> ConformalReport:
    """Evaluate rolling conformal intervals without target-time leakage."""

    config = config or ConformalConfig()
    try:
        values = tuple(observations)
    except TypeError as exc:
        raise StateSpaceError(
            "conformal observations must be iterable",
            context={"reason": "invalid_conformal_observation"},
        ) from exc
    _validate_observation_order(values)
    if len(values) <= config.min_calibration:
        raise StateSpaceError(
            "not enough observations for conformal evaluation",
            context={"reason": "insufficient_conformal_history"},
        )

    calibration: list[float] = []
    steps: list[ConformalStep] = []
    effective_alpha = config.alpha

    for observation in values:
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

        if len(calibration) >= config.min_calibration:
            effective_alpha = max(
                effective_alpha,
                attainable_alpha_floor(len(calibration)),
            )

    if not steps:
        raise StateSpaceError(
            "conformal evaluation produced no scored intervals",
            context={"reason": "insufficient_conformal_history"},
        )

    coverage = statistics.fmean(0.0 if step.missed else 1.0 for step in steps)
    widths = [step.interval.width for step in steps]
    mean_width = statistics.fmean(widths)
    median_width = statistics.median(widths)
    mean_interval_score = statistics.fmean(step.interval_score for step in steps)
    mean_nonconformity = statistics.fmean(
        step.nonconformity_score for step in steps
    )
    configuration_fingerprint = _configuration_fingerprint(config)
    fingerprint = _report_fingerprint(
        configuration_fingerprint=configuration_fingerprint,
        warmup_count=config.min_calibration,
        steps=steps,
        empirical_coverage=coverage,
        mean_width=mean_width,
        median_width=median_width,
        mean_interval_score=mean_interval_score,
        mean_nonconformity=mean_nonconformity,
        final_effective_alpha=effective_alpha,
        final_calibration_scores=calibration,
    )
    return ConformalReport(
        config=config,
        configuration_fingerprint=configuration_fingerprint,
        warmup_count=config.min_calibration,
        steps=tuple(steps),
        empirical_coverage=coverage,
        mean_width=mean_width,
        median_width=median_width,
        mean_interval_score=mean_interval_score,
        mean_nonconformity=mean_nonconformity,
        final_effective_alpha=effective_alpha,
        final_calibration_scores=tuple(calibration),
        fingerprint=fingerprint,
    )


def evaluate_cross_family_conformal(
    report: object,
    *,
    config: ConformalConfig | None = None,
) -> ConformalReport:
    """Conformalize a completed cross-family arbitration report."""

    steps = getattr(report, "steps", None)
    if steps is None:
        raise StateSpaceError(
            "cross-family report must expose steps",
            context={"reason": "invalid_conformal_source_report"},
        )
    try:
        raw_steps = tuple(steps)
    except TypeError as exc:
        raise StateSpaceError(
            "cross-family report steps must be iterable",
            context={"reason": "invalid_conformal_source_report"},
        ) from exc
    if not raw_steps:
        raise StateSpaceError(
            "cross-family report steps cannot be empty",
            context={"reason": "invalid_conformal_source_report"},
        )
    observations: list[ForecastObservation] = []
    for step in raw_steps:
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
    width = _finite_result("interval_width", upper - lower)
    penalty = 0.0
    if actual < lower:
        penalty = _finite_result(
            "interval_penalty",
            (2.0 / alpha) * (lower - actual),
        )
    elif actual > upper:
        penalty = _finite_result(
            "interval_penalty",
            (2.0 / alpha) * (actual - upper),
        )
    return _finite_result("interval_score", width + penalty)


def _predictive_scale(
    predictive: ConformalPredictiveDistribution,
    *,
    normalized: bool,
    min_scale: float,
) -> float:
    if not normalized:
        return 1.0
    scale = _finite_result("predictive_scale", math.sqrt(predictive.variance))
    return max(min_scale, scale)


def _validate_predictive(predictive: ConformalPredictiveDistribution) -> None:
    try:
        horizon = getattr(predictive, "horizon")
        mean = getattr(predictive, "mean")
        variance = getattr(predictive, "variance")
    except (AttributeError, TypeError) as exc:
        raise StateSpaceError(
            "predictive object does not satisfy conformal contract",
            context={"reason": "invalid_conformal_predictive"},
        ) from exc
    _positive_index("predictive_horizon", horizon)
    _finite("predictive_mean", mean)
    if _finite("predictive_variance", variance) <= 0.0:
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
    horizon: int | None = None
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
        if horizon is None:
            horizon = observation.predictive.horizon
        elif observation.predictive.horizon != horizon:
            raise StateSpaceError(
                "conformal calibration cannot pool forecast horizons",
                context={"reason": "conformal_horizon_mismatch"},
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
    attainable = attainable_alpha_floor(len(report.final_calibration_scores))
    if report.final_effective_alpha + 1e-15 < attainable:
        raise StateSpaceError(
            "conformal report effective alpha is unattainable for final state",
            context={"reason": "conformal_report_identity_mismatch"},
        )

    coverage = statistics.fmean(0.0 if step.missed else 1.0 for step in report.steps)
    widths = [step.interval.width for step in report.steps]
    expected_metrics = {
        "empirical_coverage": coverage,
        "mean_width": statistics.fmean(widths),
        "median_width": statistics.median(widths),
        "mean_interval_score": statistics.fmean(
            step.interval_score for step in report.steps
        ),
        "mean_nonconformity": statistics.fmean(
            step.nonconformity_score for step in report.steps
        ),
    }
    for field, expected in expected_metrics.items():
        actual = _finite(field, getattr(report, field))
        tolerance = max(1e-12, 1e-12 * max(1.0, abs(expected)))
        if abs(actual - expected) > tolerance:
            raise StateSpaceError(
                "conformal report aggregate metrics are inconsistent",
                context={
                    "reason": "conformal_report_identity_mismatch",
                    "field": field,
                },
            )

    expected_report = _report_fingerprint(
        configuration_fingerprint=report.configuration_fingerprint,
        warmup_count=report.warmup_count,
        steps=report.steps,
        empirical_coverage=report.empirical_coverage,
        mean_width=report.mean_width,
        median_width=report.median_width,
        mean_interval_score=report.mean_interval_score,
        mean_nonconformity=report.mean_nonconformity,
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
        "schema": "jeeves.conformal.config.v2",
    }
    return _digest(payload)


def _report_fingerprint(
    *,
    configuration_fingerprint: str,
    warmup_count: int,
    steps: Sequence[ConformalStep],
    empirical_coverage: float,
    mean_width: float,
    median_width: float,
    mean_interval_score: float,
    mean_nonconformity: float,
    final_effective_alpha: float,
    final_calibration_scores: Sequence[float],
) -> str:
    payload = {
        "configuration_fingerprint": configuration_fingerprint,
        "empirical_coverage": empirical_coverage,
        "final_calibration_scores": list(final_calibration_scores),
        "final_effective_alpha": final_effective_alpha,
        "mean_interval_score": mean_interval_score,
        "mean_nonconformity": mean_nonconformity,
        "mean_width": mean_width,
        "median_width": median_width,
        "schema": "jeeves.conformal.report.v2",
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


def _positive_index(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StateSpaceError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_conformal_index", "field": name},
        )
    return value


def _finite(name: str, value: object) -> float:
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


def _finite_result(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise StateSpaceError(
            f"{name} overflowed or became non-finite",
            context={
                "reason": "conformal_numerical_instability",
                "field": name,
            },
        )
    return value


def _non_negative(name: str, value: object) -> float:
    result = _finite(name, value)
    if result < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


def _positive(name: str, value: object) -> float:
    result = _finite(name, value)
    if result <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


def _open_interval(name: str, value: object, low: float, high: float) -> float:
    result = _finite(name, value)
    if not low < result < high:
        raise StateSpaceError(
            f"{name} must lie in ({low}, {high})",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


def _closed_interval(name: str, value: object, low: float, high: float) -> float:
    result = _finite(name, value)
    if not low <= result <= high:
        raise StateSpaceError(
            f"{name} must lie in [{low}, {high}]",
            context={"reason": "invalid_conformal_numeric", "field": name},
        )
    return result


__all__ = [
    "ConformalConfig",
    "ConformalInterval",
    "ConformalPredictiveDistribution",
    "ConformalReport",
    "ConformalStep",
    "ForecastObservation",
    "attainable_alpha_floor",
    "conformal_interval",
    "conformal_quantile",
    "conformalize_next_forecast",
    "evaluate_cross_family_conformal",
    "evaluate_prequential_conformal",
    "nonconformity_score",
    "required_calibration_size",
]
