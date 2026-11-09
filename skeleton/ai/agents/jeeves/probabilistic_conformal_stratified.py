"""Hierarchical, leakage-safe conformal calibration for Jeeves forecasts.

The base conformal layer maintains one rolling calibration sequence.  This
module adds a hierarchy that separates errors by forecast horizon and, when a
pre-target regime label is available, by ``(horizon, regime)``.

Every completed target contributes to its horizon bucket.  A labeled target also
contributes to its finer horizon/regime bucket.  For target ``t`` an interval is
issued from the finest bucket that already contains enough completed scores; a
horizon-only bucket may be used as a configured fallback.  The score belonging
to target ``t`` is appended only after the interval for ``t`` has been scored.

Regime labels are treated as caller-supplied pre-target context.  This module
never derives a regime from the realized target and therefore cannot silently
turn an ex-post classification into ex-ante calibration evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence

from .probabilistic_conformal import (
    ConformalConfig,
    ConformalInterval,
    ConformalPredictiveDistribution,
    conformal_interval,
    nonconformity_score,
)
from .probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class ConformalStratumKey:
    """Identity for one calibration bucket."""

    horizon: int
    regime: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.horizon, bool)
            or not isinstance(self.horizon, int)
            or self.horizon < 1
        ):
            raise StateSpaceError(
                "stratum horizon must be a positive integer",
                context={"reason": "invalid_conformal_stratum"},
            )
        _validate_regime(self.regime, field="stratum_regime")

    @property
    def is_regime_specific(self) -> bool:
        return self.regime is not None


@dataclass(frozen=True, slots=True)
class StratifiedConformalConfig:
    """Hierarchy policy wrapped around the base conformal configuration."""

    conformal: ConformalConfig = field(default_factory=ConformalConfig)
    condition_on_regime: bool = True
    fallback_to_horizon: bool = True
    max_regimes: int = 32

    def __post_init__(self) -> None:
        if not isinstance(self.conformal, ConformalConfig):
            raise StateSpaceError(
                "conformal must be a ConformalConfig",
                context={"reason": "invalid_stratified_conformal_config"},
            )
        if not isinstance(self.condition_on_regime, bool):
            raise StateSpaceError(
                "condition_on_regime must be a boolean",
                context={"reason": "invalid_stratified_conformal_config"},
            )
        if not isinstance(self.fallback_to_horizon, bool):
            raise StateSpaceError(
                "fallback_to_horizon must be a boolean",
                context={"reason": "invalid_stratified_conformal_config"},
            )
        if (
            isinstance(self.max_regimes, bool)
            or not isinstance(self.max_regimes, int)
            or self.max_regimes < 1
        ):
            raise StateSpaceError(
                "max_regimes must be a positive integer",
                context={"reason": "invalid_stratified_conformal_config"},
            )


@dataclass(frozen=True, slots=True)
class StratifiedForecastObservation:
    """A realized target plus the predictive state that existed before it."""

    target_index: int
    actual: float
    predictive: ConformalPredictiveDistribution
    regime: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.target_index, bool)
            or not isinstance(self.target_index, int)
            or self.target_index < 1
        ):
            raise StateSpaceError(
                "target_index must be a positive integer",
                context={"reason": "invalid_stratified_observation"},
            )
        _finite("actual", self.actual)
        _validate_predictive(self.predictive)
        _validate_regime(self.regime, field="regime")


@dataclass(frozen=True, slots=True)
class StratifiedConformalStep:
    """One interval issued from a selected pre-target calibration stratum."""

    actual: float
    interval: ConformalInterval
    stratum: ConformalStratumKey
    requested_regime: str | None
    used_fallback: bool
    nonconformity_score: float
    missed: bool
    interval_score: float

    def __post_init__(self) -> None:
        _finite("actual", self.actual)
        _non_negative("nonconformity_score", self.nonconformity_score)
        _non_negative("interval_score", self.interval_score)
        _validate_regime(self.requested_regime, field="requested_regime")
        if not isinstance(self.used_fallback, bool) or not isinstance(self.missed, bool):
            raise StateSpaceError(
                "stratified conformal flags must be booleans",
                context={"reason": "invalid_stratified_step"},
            )
        if self.interval.horizon != self.stratum.horizon:
            raise StateSpaceError(
                "interval horizon must match selected stratum",
                context={"reason": "invalid_stratified_step"},
            )
        if self.missed == self.interval.contains(self.actual):
            raise StateSpaceError(
                "missed flag disagrees with interval geometry",
                context={"reason": "invalid_stratified_step"},
            )
        expected_fallback = (
            self.requested_regime is not None and self.stratum.regime is None
        )
        if self.used_fallback != expected_fallback:
            raise StateSpaceError(
                "fallback flag disagrees with selected stratum",
                context={"reason": "invalid_stratified_step"},
            )


@dataclass(frozen=True, slots=True)
class ConformalBucketState:
    """Retained calibration state for one horizon or horizon/regime bucket."""

    key: ConformalStratumKey
    effective_alpha: float
    calibration_scores: tuple[float, ...]
    issued_intervals: int
    misses: int
    fingerprint: str

    def __post_init__(self) -> None:
        _open_interval("effective_alpha", self.effective_alpha, 0.0, 1.0)
        if (
            isinstance(self.issued_intervals, bool)
            or not isinstance(self.issued_intervals, int)
            or self.issued_intervals < 0
            or isinstance(self.misses, bool)
            or not isinstance(self.misses, int)
            or self.misses < 0
            or self.misses > self.issued_intervals
        ):
            raise StateSpaceError(
                "bucket usage counts are invalid",
                context={"reason": "invalid_conformal_bucket"},
            )
        for score in self.calibration_scores:
            _non_negative("calibration_score", score)
        if not isinstance(self.fingerprint, str) or len(self.fingerprint) != 64:
            raise StateSpaceError(
                "bucket fingerprint must be a sha256 hex digest",
                context={"reason": "invalid_conformal_bucket"},
            )
        try:
            int(self.fingerprint, 16)
        except ValueError as exc:
            raise StateSpaceError(
                "bucket fingerprint must be hexadecimal",
                context={"reason": "invalid_conformal_bucket"},
            ) from exc

    @property
    def empirical_coverage(self) -> float | None:
        if self.issued_intervals == 0:
            return None
        return 1.0 - self.misses / self.issued_intervals


@dataclass(frozen=True, slots=True)
class StratifiedConformalReport:
    """Hierarchical conformal evidence plus reusable final bucket states."""

    config: StratifiedConformalConfig
    configuration_fingerprint: str
    steps: tuple[StratifiedConformalStep, ...]
    buckets: tuple[ConformalBucketState, ...]
    empirical_coverage: float
    mean_width: float
    median_width: float
    mean_interval_score: float
    fallback_rate: float
    fingerprint: str

    @property
    def target_coverage(self) -> float:
        return 1.0 - self.config.conformal.alpha

    @property
    def coverage_gap(self) -> float:
        return self.empirical_coverage - self.target_coverage

    @property
    def miss_rate(self) -> float:
        return 1.0 - self.empirical_coverage

    def bucket(self, *, horizon: int, regime: str | None = None) -> ConformalBucketState:
        key = ConformalStratumKey(horizon=horizon, regime=regime)
        for state in self.buckets:
            if state.key == key:
                return state
        raise StateSpaceError(
            "requested conformal bucket is absent",
            context={
                "reason": "missing_conformal_bucket",
                "horizon": horizon,
                "regime": regime,
            },
        )


@dataclass(frozen=True, slots=True)
class StratifiedForecastInterval:
    """A future interval plus the calibration stratum that authorized it."""

    interval: ConformalInterval
    stratum: ConformalStratumKey
    requested_regime: str | None
    used_fallback: bool

    def __post_init__(self) -> None:
        _validate_regime(self.requested_regime, field="requested_regime")
        if not isinstance(self.used_fallback, bool):
            raise StateSpaceError(
                "used_fallback must be a boolean",
                context={"reason": "invalid_stratified_forecast"},
            )
        if self.interval.horizon != self.stratum.horizon:
            raise StateSpaceError(
                "future interval horizon must match selected stratum",
                context={"reason": "invalid_stratified_forecast"},
            )
        expected_fallback = (
            self.requested_regime is not None and self.stratum.regime is None
        )
        if self.used_fallback != expected_fallback:
            raise StateSpaceError(
                "future interval fallback flag disagrees with selected stratum",
                context={"reason": "invalid_stratified_forecast"},
            )


@dataclass(slots=True)
class _MutableBucket:
    scores: list[float]
    effective_alpha: float
    issued_intervals: int = 0
    misses: int = 0


def evaluate_stratified_conformal(
    observations: Sequence[StratifiedForecastObservation],
    *,
    config: StratifiedConformalConfig | None = None,
) -> StratifiedConformalReport:
    """Evaluate horizon/regime conformal intervals without target-time leakage."""

    actual_config = config or StratifiedConformalConfig()
    _validate_observations(observations, config=actual_config)

    buckets: dict[ConformalStratumKey, _MutableBucket] = {}
    steps: list[StratifiedConformalStep] = []

    for observation in observations:
        score = nonconformity_score(
            observation.actual,
            observation.predictive,
            normalized=actual_config.conformal.normalized,
            min_scale=actual_config.conformal.min_scale,
        )
        candidate_keys = _candidate_keys(observation, config=actual_config)
        selected = _select_eligible_bucket(
            candidate_keys,
            buckets,
            minimum=actual_config.conformal.min_calibration,
        )

        if selected is not None:
            bucket = buckets[selected]
            interval = conformal_interval(
                observation.predictive,
                bucket.scores,
                config=actual_config.conformal,
                target_index=observation.target_index,
                effective_alpha=bucket.effective_alpha,
            )
            missed = not interval.contains(observation.actual)
            requested_regime = (
                observation.regime if actual_config.condition_on_regime else None
            )
            steps.append(
                StratifiedConformalStep(
                    actual=observation.actual,
                    interval=interval,
                    stratum=selected,
                    requested_regime=requested_regime,
                    used_fallback=(
                        requested_regime is not None and selected.regime is None
                    ),
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
            bucket.issued_intervals += 1
            bucket.misses += int(missed)
            bucket.effective_alpha = _adaptive_alpha_update(
                bucket.effective_alpha,
                missed=missed,
                config=actual_config.conformal,
            )

        for key in _storage_keys(observation, config=actual_config):
            bucket = buckets.setdefault(
                key,
                _MutableBucket(
                    scores=[],
                    effective_alpha=actual_config.conformal.alpha,
                ),
            )
            bucket.scores.append(score)
            overflow = len(bucket.scores) - actual_config.conformal.calibration_window
            if overflow > 0:
                del bucket.scores[:overflow]

    if not steps:
        raise StateSpaceError(
            "stratified conformal evaluation produced no scored intervals",
            context={"reason": "insufficient_stratified_conformal_history"},
        )

    final_buckets = tuple(
        _freeze_bucket(key, state, config=actual_config)
        for key, state in sorted(
            buckets.items(),
            key=lambda item: (
                item[0].horizon,
                item[0].regime is not None,
                item[0].regime or "",
            ),
        )
    )
    widths = [step.interval.width for step in steps]
    coverage = statistics.fmean(0.0 if step.missed else 1.0 for step in steps)
    fallback_rate = statistics.fmean(1.0 if step.used_fallback else 0.0 for step in steps)
    configuration_fingerprint = _configuration_fingerprint(actual_config)
    mean_width = statistics.fmean(widths)
    median_width = statistics.median(widths)
    mean_interval_score = statistics.fmean(step.interval_score for step in steps)
    fingerprint = _report_fingerprint(
        configuration_fingerprint=configuration_fingerprint,
        steps=steps,
        buckets=final_buckets,
        empirical_coverage=coverage,
        mean_width=mean_width,
        median_width=median_width,
        mean_interval_score=mean_interval_score,
        fallback_rate=fallback_rate,
    )
    return StratifiedConformalReport(
        config=actual_config,
        configuration_fingerprint=configuration_fingerprint,
        steps=tuple(steps),
        buckets=final_buckets,
        empirical_coverage=coverage,
        mean_width=mean_width,
        median_width=median_width,
        mean_interval_score=mean_interval_score,
        fallback_rate=fallback_rate,
        fingerprint=fingerprint,
    )


def conformalize_next_stratified_forecast(
    predictive: ConformalPredictiveDistribution,
    report: StratifiedConformalReport,
    *,
    target_index: int,
    regime: str | None = None,
) -> StratifiedForecastInterval:
    """Issue the next interval from an integrity-checked hierarchical report."""

    validate_stratified_conformal_report(report)
    _validate_predictive(predictive)
    if (
        isinstance(target_index, bool)
        or not isinstance(target_index, int)
        or target_index < 1
    ):
        raise StateSpaceError(
            "target_index must be a positive integer",
            context={"reason": "invalid_stratified_forecast"},
        )
    _validate_regime(regime, field="regime")
    if (
        report.config.condition_on_regime
        and not report.config.fallback_to_horizon
        and regime is None
    ):
        raise StateSpaceError(
            "a pre-target regime is required when horizon fallback is disabled",
            context={"reason": "missing_pre_target_regime"},
        )

    state_by_key = {state.key: state for state in report.buckets}
    candidates = _candidate_keys_for_values(
        horizon=predictive.horizon,
        regime=regime,
        config=report.config,
    )
    selected: ConformalBucketState | None = None
    for key in candidates:
        candidate = state_by_key.get(key)
        if (
            candidate is not None
            and len(candidate.calibration_scores)
            >= report.config.conformal.min_calibration
        ):
            selected = candidate
            break
    if selected is None:
        raise StateSpaceError(
            "no calibrated stratum is available for the next forecast",
            context={
                "reason": "insufficient_stratified_conformal_calibration",
                "horizon": predictive.horizon,
                "regime": regime,
            },
        )

    requested_regime = regime if report.config.condition_on_regime else None
    interval = conformal_interval(
        predictive,
        selected.calibration_scores,
        config=report.config.conformal,
        target_index=target_index,
        effective_alpha=selected.effective_alpha,
    )
    return StratifiedForecastInterval(
        interval=interval,
        stratum=selected.key,
        requested_regime=requested_regime,
        used_fallback=(requested_regime is not None and selected.key.regime is None),
    )


def validate_stratified_conformal_report(report: StratifiedConformalReport) -> None:
    """Fail closed if retained hierarchical calibration evidence was altered."""

    if not isinstance(report, StratifiedConformalReport):
        raise StateSpaceError(
            "report must be a StratifiedConformalReport",
            context={"reason": "invalid_stratified_conformal_report"},
        )
    expected_config = _configuration_fingerprint(report.config)
    if report.configuration_fingerprint != expected_config:
        raise StateSpaceError(
            "stratified conformal configuration fingerprint mismatch",
            context={"reason": "stratified_conformal_identity_mismatch"},
        )
    if not report.steps or not report.buckets:
        raise StateSpaceError(
            "stratified conformal report must contain steps and buckets",
            context={"reason": "invalid_stratified_conformal_report"},
        )

    seen_keys: set[ConformalStratumKey] = set()
    for state in report.buckets:
        if state.key in seen_keys:
            raise StateSpaceError(
                "stratified conformal report contains duplicate bucket keys",
                context={"reason": "stratified_conformal_identity_mismatch"},
            )
        seen_keys.add(state.key)
        if len(state.calibration_scores) > report.config.conformal.calibration_window:
            raise StateSpaceError(
                "stratified conformal bucket exceeds calibration window",
                context={"reason": "stratified_conformal_identity_mismatch"},
            )
        if not (
            report.config.conformal.min_alpha
            <= state.effective_alpha
            <= report.config.conformal.max_alpha
        ):
            raise StateSpaceError(
                "stratified conformal bucket alpha is outside configured bounds",
                context={"reason": "stratified_conformal_identity_mismatch"},
            )
        bucket_steps = tuple(step for step in report.steps if step.stratum == state.key)
        if state.issued_intervals != len(bucket_steps):
            raise StateSpaceError(
                "stratified conformal bucket issuance count disagrees with steps",
                context={"reason": "stratified_conformal_identity_mismatch"},
            )
        if state.misses != sum(int(step.missed) for step in bucket_steps):
            raise StateSpaceError(
                "stratified conformal bucket miss count disagrees with steps",
                context={"reason": "stratified_conformal_identity_mismatch"},
            )
        expected_bucket = _bucket_fingerprint(
            key=state.key,
            effective_alpha=state.effective_alpha,
            calibration_scores=state.calibration_scores,
            issued_intervals=state.issued_intervals,
            misses=state.misses,
            configuration_fingerprint=report.configuration_fingerprint,
        )
        if state.fingerprint != expected_bucket:
            raise StateSpaceError(
                "stratified conformal bucket fingerprint mismatch",
                context={"reason": "stratified_conformal_identity_mismatch"},
            )

    if any(step.stratum not in seen_keys for step in report.steps):
        raise StateSpaceError(
            "stratified conformal step references an absent bucket",
            context={"reason": "stratified_conformal_identity_mismatch"},
        )

    calculated_coverage = statistics.fmean(
        0.0 if step.missed else 1.0 for step in report.steps
    )
    widths = [step.interval.width for step in report.steps]
    calculated_mean_width = statistics.fmean(widths)
    calculated_median_width = statistics.median(widths)
    calculated_score = statistics.fmean(step.interval_score for step in report.steps)
    calculated_fallback = statistics.fmean(
        1.0 if step.used_fallback else 0.0 for step in report.steps
    )
    for name, actual, expected in (
        ("empirical_coverage", report.empirical_coverage, calculated_coverage),
        ("mean_width", report.mean_width, calculated_mean_width),
        ("median_width", report.median_width, calculated_median_width),
        ("mean_interval_score", report.mean_interval_score, calculated_score),
        ("fallback_rate", report.fallback_rate, calculated_fallback),
    ):
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise StateSpaceError(
                f"stratified conformal {name} is inconsistent with steps",
                context={"reason": "stratified_conformal_identity_mismatch"},
            )

    expected_report = _report_fingerprint(
        configuration_fingerprint=report.configuration_fingerprint,
        steps=report.steps,
        buckets=report.buckets,
        empirical_coverage=report.empirical_coverage,
        mean_width=report.mean_width,
        median_width=report.median_width,
        mean_interval_score=report.mean_interval_score,
        fallback_rate=report.fallback_rate,
    )
    if report.fingerprint != expected_report:
        raise StateSpaceError(
            "stratified conformal report fingerprint mismatch",
            context={"reason": "stratified_conformal_identity_mismatch"},
        )


def _candidate_keys(
    observation: StratifiedForecastObservation,
    *,
    config: StratifiedConformalConfig,
) -> tuple[ConformalStratumKey, ...]:
    return _candidate_keys_for_values(
        horizon=observation.predictive.horizon,
        regime=observation.regime,
        config=config,
    )


def _candidate_keys_for_values(
    *,
    horizon: int,
    regime: str | None,
    config: StratifiedConformalConfig,
) -> tuple[ConformalStratumKey, ...]:
    horizon_key = ConformalStratumKey(horizon=horizon)
    if not config.condition_on_regime:
        return (horizon_key,)
    if regime is None:
        if config.fallback_to_horizon:
            return (horizon_key,)
        return ()
    fine = ConformalStratumKey(horizon=horizon, regime=regime)
    if config.fallback_to_horizon:
        return fine, horizon_key
    return (fine,)


def _storage_keys(
    observation: StratifiedForecastObservation,
    *,
    config: StratifiedConformalConfig,
) -> tuple[ConformalStratumKey, ...]:
    horizon_key = ConformalStratumKey(horizon=observation.predictive.horizon)
    if config.condition_on_regime and observation.regime is not None:
        return (
            horizon_key,
            ConformalStratumKey(
                horizon=observation.predictive.horizon,
                regime=observation.regime,
            ),
        )
    return (horizon_key,)


def _select_eligible_bucket(
    candidate_keys: Sequence[ConformalStratumKey],
    buckets: dict[ConformalStratumKey, _MutableBucket],
    *,
    minimum: int,
) -> ConformalStratumKey | None:
    for key in candidate_keys:
        bucket = buckets.get(key)
        if bucket is not None and len(bucket.scores) >= minimum:
            return key
    return None


def _freeze_bucket(
    key: ConformalStratumKey,
    state: _MutableBucket,
    *,
    config: StratifiedConformalConfig,
) -> ConformalBucketState:
    configuration_fingerprint = _configuration_fingerprint(config)
    scores = tuple(state.scores)
    fingerprint = _bucket_fingerprint(
        key=key,
        effective_alpha=state.effective_alpha,
        calibration_scores=scores,
        issued_intervals=state.issued_intervals,
        misses=state.misses,
        configuration_fingerprint=configuration_fingerprint,
    )
    return ConformalBucketState(
        key=key,
        effective_alpha=state.effective_alpha,
        calibration_scores=scores,
        issued_intervals=state.issued_intervals,
        misses=state.misses,
        fingerprint=fingerprint,
    )


def _validate_observations(
    observations: Sequence[StratifiedForecastObservation],
    *,
    config: StratifiedConformalConfig,
) -> None:
    if not observations:
        raise StateSpaceError(
            "stratified conformal observations cannot be empty",
            context={"reason": "empty_stratified_conformal_observations"},
        )
    previous: int | None = None
    regimes: set[str] = set()
    for observation in observations:
        if not isinstance(observation, StratifiedForecastObservation):
            raise StateSpaceError(
                "all observations must be StratifiedForecastObservation values",
                context={"reason": "invalid_stratified_observation"},
            )
        if previous is not None and observation.target_index <= previous:
            raise StateSpaceError(
                "stratified conformal target indices must be strictly increasing",
                context={"reason": "non_monotonic_stratified_targets"},
            )
        previous = observation.target_index
        if observation.regime is not None:
            regimes.add(observation.regime)
        if (
            config.condition_on_regime
            and not config.fallback_to_horizon
            and observation.regime is None
        ):
            raise StateSpaceError(
                "pre-target regime is required when horizon fallback is disabled",
                context={"reason": "missing_pre_target_regime"},
            )
    if len(regimes) > config.max_regimes:
        raise StateSpaceError(
            "observed regime cardinality exceeds configured maximum",
            context={
                "reason": "too_many_conformal_regimes",
                "observed": len(regimes),
                "maximum": config.max_regimes,
            },
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
    if actual < lower:
        return width + (2.0 / alpha) * (lower - actual)
    if actual > upper:
        return width + (2.0 / alpha) * (actual - upper)
    return width


def _configuration_fingerprint(config: StratifiedConformalConfig) -> str:
    base = config.conformal
    payload = {
        "schema": "jeeves.stratified-conformal.config.v1",
        "condition_on_regime": config.condition_on_regime,
        "fallback_to_horizon": config.fallback_to_horizon,
        "max_regimes": config.max_regimes,
        "conformal": {
            "adaptive_rate": base.adaptive_rate,
            "alpha": base.alpha,
            "calibration_window": base.calibration_window,
            "max_alpha": base.max_alpha,
            "min_alpha": base.min_alpha,
            "min_calibration": base.min_calibration,
            "min_scale": base.min_scale,
            "normalized": base.normalized,
        },
    }
    return _digest(payload)


def _bucket_fingerprint(
    *,
    key: ConformalStratumKey,
    effective_alpha: float,
    calibration_scores: Sequence[float],
    issued_intervals: int,
    misses: int,
    configuration_fingerprint: str,
) -> str:
    return _digest(
        {
            "schema": "jeeves.stratified-conformal.bucket.v1",
            "configuration_fingerprint": configuration_fingerprint,
            "horizon": key.horizon,
            "regime": key.regime,
            "effective_alpha": effective_alpha,
            "calibration_scores": list(calibration_scores),
            "issued_intervals": issued_intervals,
            "misses": misses,
        }
    )


def _report_fingerprint(
    *,
    configuration_fingerprint: str,
    steps: Sequence[StratifiedConformalStep],
    buckets: Sequence[ConformalBucketState],
    empirical_coverage: float,
    mean_width: float,
    median_width: float,
    mean_interval_score: float,
    fallback_rate: float,
) -> str:
    return _digest(
        {
            "schema": "jeeves.stratified-conformal.report.v1",
            "configuration_fingerprint": configuration_fingerprint,
            "empirical_coverage": empirical_coverage,
            "mean_width": mean_width,
            "median_width": median_width,
            "mean_interval_score": mean_interval_score,
            "fallback_rate": fallback_rate,
            "bucket_fingerprints": [bucket.fingerprint for bucket in buckets],
            "steps": [
                {
                    "target_index": step.interval.target_index,
                    "horizon": step.interval.horizon,
                    "regime": step.stratum.regime,
                    "requested_regime": step.requested_regime,
                    "used_fallback": step.used_fallback,
                    "lower": step.interval.lower,
                    "upper": step.interval.upper,
                    "effective_alpha": step.interval.effective_alpha,
                    "calibration_size": step.interval.calibration_size,
                    "actual": step.actual,
                    "score": step.nonconformity_score,
                    "missed": step.missed,
                    "interval_score": step.interval_score,
                }
                for step in steps
            ],
        }
    )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_predictive(predictive: ConformalPredictiveDistribution) -> None:
    horizon = getattr(predictive, "horizon", None)
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise StateSpaceError(
            "predictive horizon must be a positive integer",
            context={"reason": "invalid_stratified_predictive"},
        )
    _finite("predictive_mean", getattr(predictive, "mean", None))
    variance = _finite("predictive_variance", getattr(predictive, "variance", None))
    if variance <= 0.0:
        raise StateSpaceError(
            "predictive variance must be positive",
            context={"reason": "invalid_stratified_predictive"},
        )


def _validate_regime(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise StateSpaceError(
            f"{field} must be a non-empty string when supplied",
            context={"reason": "invalid_stratified_regime", "field": field},
        )
    if value != value.strip():
        raise StateSpaceError(
            f"{field} must not contain surrounding whitespace",
            context={"reason": "invalid_stratified_regime", "field": field},
        )
    if len(value) > 128:
        raise StateSpaceError(
            f"{field} must be at most 128 characters",
            context={"reason": "invalid_stratified_regime", "field": field},
        )
    return value


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_stratified_numeric", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_stratified_numeric", "field": name},
        )
    return number


def _non_negative(name: str, value: object) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_stratified_numeric", "field": name},
        )
    return number


def _open_interval(name: str, value: object, low: float, high: float) -> float:
    number = _finite(name, value)
    if not low < number < high:
        raise StateSpaceError(
            f"{name} must lie in ({low}, {high})",
            context={"reason": "invalid_stratified_numeric", "field": name},
        )
    return number


__all__ = [
    "ConformalBucketState",
    "ConformalStratumKey",
    "StratifiedConformalConfig",
    "StratifiedConformalReport",
    "StratifiedConformalStep",
    "StratifiedForecastInterval",
    "StratifiedForecastObservation",
    "conformalize_next_stratified_forecast",
    "evaluate_stratified_conformal",
    "validate_stratified_conformal_report",
]
