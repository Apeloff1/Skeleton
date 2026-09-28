"""P1 forecasting and cost-anomaly qualification.

This module is deliberately non-executing. It cannot scale workers, mutate
budgets, acknowledge incidents, or change production routing. It turns
versioned demand/capacity/cost observations into deterministic forecasts and
backtests, classifies cost anomalies, and requires accountable workflow
evidence when an anomaly needs action.

The terminal DIST-06 qualification binds accepted DIST-04 capacity evidence,
accepted DIST-05 durable budget-accounting evidence, three reproducible
forecast backtests, and the exact cost-anomaly/action decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from statistics import fmean
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.mesh.capacity_qualification import CapacityQualificationDecision
from skeleton.observability.budget_accounting import BudgetAccountingDecision


FORECASTING_SCHEMA_VERSION = 1
FORECASTING_TASK_ID = "P1-DIST-06"
FORECASTING_ACCOUNTABILITY_ID = "ACC-P1-DIST-06"
_MAX_POINTS = 4096
_MAX_EVIDENCE = 256
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,255}$")


class ForecastingError(ValueError):
    """Forecasting or anomaly evidence is malformed or unsafe."""


class ForecastMetric(str, Enum):
    DEMAND = "demand"
    CAPACITY = "capacity"
    COST = "cost"


class ForecastModelKind(str, Enum):
    TRAILING_MEAN = "trailing_mean"
    LINEAR_TREND = "linear_trend"


class AnomalySeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionDisposition(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForecastingError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ForecastingError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise ForecastingError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ForecastingError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastingError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ForecastingError(f"{field} must be finite numeric")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0:
        raise ForecastingError(f"{field} must be non-negative")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0.0:
        raise ForecastingError(f"{field} must be positive")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ForecastingError(f"{field} must be a positive integer")
    return value


def _unit_interval(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0 or result > 1.0:
        raise ForecastingError(f"{field} must be between 0 and 1")
    return result


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ForecastingError(
            "forecasting payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _evidence(
    values: Iterable[EvidenceRef],
    *,
    allow_empty: bool = False,
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise ForecastingError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise ForecastingError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence source")
        _sha256(item.digest, "evidence digest")
        _token(item.category, "evidence category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key and not allow_empty:
        raise ForecastingError("evidence_refs must be non-empty")
    if len(by_key) > _MAX_EVIDENCE:
        raise ForecastingError("evidence_refs exceeds item limit")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class ForecastObservation:
    observed_at: float
    value: float
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "value",
            _nonnegative(self.value, "value"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at,
            "value": self.value,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
        }

    @property
    def observation_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ForecastSeries:
    series_id: str
    metric: ForecastMetric
    unit: str
    observations: tuple[ForecastObservation, ...]
    interval_s: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "series_id",
            _token(self.series_id, "series_id"),
        )
        try:
            object.__setattr__(
                self,
                "metric",
                ForecastMetric(self.metric),
            )
        except ValueError as exc:
            raise ForecastingError("invalid forecast metric") from exc
        object.__setattr__(
            self,
            "unit",
            _token(self.unit, "unit", maximum=64),
        )
        object.__setattr__(
            self,
            "interval_s",
            _positive(self.interval_s, "interval_s"),
        )
        if (
            not isinstance(self.observations, tuple)
            or len(self.observations) < 2
            or len(self.observations) > _MAX_POINTS
        ):
            raise ForecastingError(
                "observations must be a bounded tuple with at least two points"
            )
        if any(
            not isinstance(item, ForecastObservation)
            for item in self.observations
        ):
            raise ForecastingError(
                "observations must contain ForecastObservation"
            )
        timestamps = [item.observed_at for item in self.observations]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(
            timestamps
        ):
            raise ForecastingError(
                "observation timestamps must be unique and increasing"
            )
        tolerance = max(1e-9, self.interval_s * 1e-9)
        for left, right in zip(timestamps, timestamps[1:]):
            if abs((right - left) - self.interval_s) > tolerance:
                raise ForecastingError(
                    "observation cadence must match interval_s"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "metric": self.metric.value,
            "unit": self.unit,
            "interval_s": self.interval_s,
            "observations": [
                item.payload() for item in self.observations
            ],
        }

    @property
    def series_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ForecastPolicy:
    policy_id: str
    version: int
    model_kind: ForecastModelKind
    training_window: int
    min_backtest_points: int
    horizon_steps: int
    max_mape: float
    max_absolute_error: float
    anomaly_relative_error: float
    high_anomaly_relative_error: float
    critical_anomaly_relative_error: float
    require_action_from: AnomalySeverity = AnomalySeverity.HIGH

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id"),
        )
        object.__setattr__(
            self,
            "version",
            _positive_int(self.version, "version"),
        )
        try:
            object.__setattr__(
                self,
                "model_kind",
                ForecastModelKind(self.model_kind),
            )
            object.__setattr__(
                self,
                "require_action_from",
                AnomalySeverity(self.require_action_from),
            )
        except ValueError as exc:
            raise ForecastingError("invalid forecast policy enum") from exc
        object.__setattr__(
            self,
            "training_window",
            _positive_int(self.training_window, "training_window"),
        )
        object.__setattr__(
            self,
            "min_backtest_points",
            _positive_int(
                self.min_backtest_points,
                "min_backtest_points",
            ),
        )
        object.__setattr__(
            self,
            "horizon_steps",
            _positive_int(self.horizon_steps, "horizon_steps"),
        )
        object.__setattr__(
            self,
            "max_mape",
            _unit_interval(self.max_mape, "max_mape"),
        )
        object.__setattr__(
            self,
            "max_absolute_error",
            _nonnegative(
                self.max_absolute_error,
                "max_absolute_error",
            ),
        )
        for field in (
            "anomaly_relative_error",
            "high_anomaly_relative_error",
            "critical_anomaly_relative_error",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative(getattr(self, field), field),
            )
        if not (
            0.0
            < self.anomaly_relative_error
            <= self.high_anomaly_relative_error
            <= self.critical_anomaly_relative_error
        ):
            raise ForecastingError(
                "anomaly relative-error thresholds must be ordered"
            )
        if self.min_backtest_points < 1:
            raise ForecastingError(
                "min_backtest_points must be positive"
            )
        if self.training_window < 2:
            raise ForecastingError(
                "training_window must be at least two"
            )
        if self.require_action_from is AnomalySeverity.NONE:
            raise ForecastingError(
                "require_action_from cannot be none"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "model_kind": self.model_kind.value,
            "training_window": self.training_window,
            "min_backtest_points": self.min_backtest_points,
            "horizon_steps": self.horizon_steps,
            "max_mape": self.max_mape,
            "max_absolute_error": self.max_absolute_error,
            "anomaly_relative_error": self.anomaly_relative_error,
            "high_anomaly_relative_error": (
                self.high_anomaly_relative_error
            ),
            "critical_anomaly_relative_error": (
                self.critical_anomaly_relative_error
            ),
            "require_action_from": self.require_action_from.value,
        }

    @property
    def policy_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    step: int
    expected_at: float
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step",
            _positive_int(self.step, "step"),
        )
        object.__setattr__(
            self,
            "expected_at",
            _nonnegative(self.expected_at, "expected_at"),
        )
        object.__setattr__(
            self,
            "value",
            _nonnegative(self.value, "value"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "expected_at": self.expected_at,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ForecastBacktestDecision:
    accepted: bool
    reasons: tuple[str, ...]
    metric: ForecastMetric
    series_digest: str
    policy_digest: str
    model_digest: str
    backtest_points: int
    mape: float
    mean_absolute_error: float
    max_absolute_error: float
    forecast: tuple[ForecastPoint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ForecastingError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ForecastingError(
                "reasons must contain non-empty strings"
            )
        try:
            object.__setattr__(
                self,
                "metric",
                ForecastMetric(self.metric),
            )
        except ValueError as exc:
            raise ForecastingError("invalid backtest metric") from exc
        for field in (
            "series_digest",
            "policy_digest",
            "model_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "backtest_points",
            _positive_int(self.backtest_points, "backtest_points"),
        )
        for field in (
            "mape",
            "mean_absolute_error",
            "max_absolute_error",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative(getattr(self, field), field),
            )
        if not isinstance(self.forecast, tuple) or not self.forecast:
            raise ForecastingError("forecast must be a non-empty tuple")
        if any(
            not isinstance(item, ForecastPoint)
            for item in self.forecast
        ):
            raise ForecastingError(
                "forecast must contain ForecastPoint"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "metric": self.metric.value,
            "series_digest": self.series_digest,
            "policy_digest": self.policy_digest,
            "model_digest": self.model_digest,
            "backtest_points": self.backtest_points,
            "mape": self.mape,
            "mean_absolute_error": self.mean_absolute_error,
            "max_absolute_error": self.max_absolute_error,
            "forecast": [item.payload() for item in self.forecast],
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AccountableActionReceipt:
    action_id: str
    owner_id: str
    workflow_ref: str
    incident_ref: str
    anomaly_digest: str
    created_at: float
    due_at: float
    disposition: ActionDisposition
    evidence_refs: tuple[EvidenceRef, ...]
    independent: bool = True

    def __post_init__(self) -> None:
        for field in (
            "action_id",
            "owner_id",
            "workflow_ref",
            "incident_ref",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "anomaly_digest",
            _sha256(self.anomaly_digest, "anomaly_digest"),
        )
        object.__setattr__(
            self,
            "created_at",
            _nonnegative(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "due_at",
            _positive(self.due_at, "due_at"),
        )
        if self.due_at <= self.created_at:
            raise ForecastingError("action due_at must follow created_at")
        try:
            object.__setattr__(
                self,
                "disposition",
                ActionDisposition(self.disposition),
            )
        except ValueError as exc:
            raise ForecastingError(
                "invalid action disposition"
            ) from exc
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        if self.independent is not True:
            raise ForecastingError(
                "accountable action receipt must be independent"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "owner_id": self.owner_id,
            "workflow_ref": self.workflow_ref,
            "incident_ref": self.incident_ref,
            "anomaly_digest": self.anomaly_digest,
            "created_at": self.created_at,
            "due_at": self.due_at,
            "disposition": self.disposition.value,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "independent": self.independent,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class CostAnomalyDecision:
    severity: AnomalySeverity
    expected_cost: float
    observed_cost: float
    absolute_error: float
    relative_error: float
    cost_backtest_digest: str
    policy_digest: str
    action_required: bool
    action_receipt_digest: str | None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "severity",
                AnomalySeverity(self.severity),
            )
        except ValueError as exc:
            raise ForecastingError("invalid anomaly severity") from exc
        for field in (
            "expected_cost",
            "observed_cost",
            "absolute_error",
            "relative_error",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative(getattr(self, field), field),
            )
        for field in ("cost_backtest_digest", "policy_digest"):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if not isinstance(self.action_required, bool):
            raise ForecastingError("action_required must be boolean")
        if self.action_receipt_digest is not None:
            object.__setattr__(
                self,
                "action_receipt_digest",
                _sha256(
                    self.action_receipt_digest,
                    "action_receipt_digest",
                ),
            )
        if self.action_required and self.action_receipt_digest is None:
            raise ForecastingError(
                "actionable anomaly requires action receipt"
            )
        if (
            not self.action_required
            and self.action_receipt_digest is not None
        ):
            raise ForecastingError(
                "non-actionable anomaly cannot carry action receipt"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "expected_cost": self.expected_cost,
            "observed_cost": self.observed_cost,
            "absolute_error": self.absolute_error,
            "relative_error": self.relative_error,
            "cost_backtest_digest": self.cost_backtest_digest,
            "policy_digest": self.policy_digest,
            "action_required": self.action_required,
            "action_receipt_digest": self.action_receipt_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ForecastingQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    capacity_decision_digest: str
    budget_decision_digest: str
    demand_backtest_digest: str
    capacity_backtest_digest: str
    cost_backtest_digest: str
    anomaly_decision_digest: str
    task_id: str = FORECASTING_TASK_ID
    accountability_id: str = FORECASTING_ACCOUNTABILITY_ID
    schema_version: int = FORECASTING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ForecastingError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ForecastingError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "capacity_decision_digest",
            "budget_decision_digest",
            "demand_backtest_digest",
            "capacity_backtest_digest",
            "cost_backtest_digest",
            "anomaly_decision_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.task_id != FORECASTING_TASK_ID:
            raise ForecastingError("task_id drift")
        if self.accountability_id != FORECASTING_ACCOUNTABILITY_ID:
            raise ForecastingError("accountability_id drift")
        if self.schema_version != FORECASTING_SCHEMA_VERSION:
            raise ForecastingError(
                "unsupported forecasting decision schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "capacity_decision_digest": self.capacity_decision_digest,
            "budget_decision_digest": self.budget_decision_digest,
            "demand_backtest_digest": self.demand_backtest_digest,
            "capacity_backtest_digest": self.capacity_backtest_digest,
            "cost_backtest_digest": self.cost_backtest_digest,
            "anomaly_decision_digest": self.anomaly_decision_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:dist-06:forecast-anomaly",
    ) -> EvidenceRef:
        if not self.accepted:
            raise ForecastingError(
                "rejected forecasting qualification cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="forecast_anomaly_qualification",
        )


def _predict(values: list[float], model: ForecastModelKind) -> float:
    if len(values) < 2:
        raise ForecastingError("forecast model requires at least two values")
    if model is ForecastModelKind.TRAILING_MEAN:
        return max(0.0, fmean(values))
    n = len(values)
    xs = list(range(n))
    x_mean = fmean(xs)
    y_mean = fmean(values)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0.0:
        return max(0.0, y_mean)
    slope = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in zip(xs, values)
    ) / denominator
    intercept = y_mean - slope * x_mean
    return max(0.0, intercept + slope * n)


def backtest_forecast(
    *,
    series: ForecastSeries,
    policy: ForecastPolicy,
) -> ForecastBacktestDecision:
    if not isinstance(series, ForecastSeries):
        raise TypeError("series must be ForecastSeries")
    if not isinstance(policy, ForecastPolicy):
        raise TypeError("policy must be ForecastPolicy")
    needed = policy.training_window + policy.min_backtest_points
    if len(series.observations) < needed:
        raise ForecastingError(
            "series does not contain enough history for backtest"
        )

    errors: list[float] = []
    percentage_errors: list[float] = []
    start = len(series.observations) - policy.min_backtest_points
    for index in range(start, len(series.observations)):
        training_start = max(0, index - policy.training_window)
        training = [
            item.value
            for item in series.observations[training_start:index]
        ]
        expected = _predict(training, policy.model_kind)
        observed = series.observations[index].value
        error = abs(observed - expected)
        errors.append(error)
        denominator = max(abs(observed), 1e-12)
        percentage_errors.append(error / denominator)

    mape = fmean(percentage_errors)
    mae = fmean(errors)
    max_error = max(errors)
    reasons: list[str] = []
    if mape > policy.max_mape:
        reasons.append("mape-exceeds-policy")
    if max_error > policy.max_absolute_error:
        reasons.append("absolute-error-exceeds-policy")

    values = [
        item.value
        for item in series.observations[-policy.training_window :]
    ]
    last_at = series.observations[-1].observed_at
    forecast: list[ForecastPoint] = []
    rolling = list(values)
    for step in range(1, policy.horizon_steps + 1):
        value = _predict(rolling[-policy.training_window :], policy.model_kind)
        forecast.append(
            ForecastPoint(
                step=step,
                expected_at=last_at + step * series.interval_s,
                value=value,
            )
        )
        rolling.append(value)

    model_digest = _canonical_digest(
        {
            "kind": policy.model_kind.value,
            "training_window": policy.training_window,
            "series_metric": series.metric.value,
            "unit": series.unit,
        }
    )
    normalized = tuple(sorted(set(reasons)))
    return ForecastBacktestDecision(
        accepted=not normalized,
        reasons=normalized,
        metric=series.metric,
        series_digest=series.series_digest,
        policy_digest=policy.policy_digest,
        model_digest=model_digest,
        backtest_points=policy.min_backtest_points,
        mape=mape,
        mean_absolute_error=mae,
        max_absolute_error=max_error,
        forecast=tuple(forecast),
    )


def _severity_rank(value: AnomalySeverity) -> int:
    order = {
        AnomalySeverity.NONE: 0,
        AnomalySeverity.LOW: 1,
        AnomalySeverity.MEDIUM: 2,
        AnomalySeverity.HIGH: 3,
        AnomalySeverity.CRITICAL: 4,
    }
    return order[value]


def classify_cost_anomaly(
    *,
    cost_backtest: ForecastBacktestDecision,
    policy: ForecastPolicy,
    observed_cost: float,
    action_receipt: AccountableActionReceipt | None = None,
) -> CostAnomalyDecision:
    if not isinstance(cost_backtest, ForecastBacktestDecision):
        raise TypeError(
            "cost_backtest must be ForecastBacktestDecision"
        )
    if not isinstance(policy, ForecastPolicy):
        raise TypeError("policy must be ForecastPolicy")
    if cost_backtest.metric is not ForecastMetric.COST:
        raise ForecastingError("cost_backtest must have cost metric")
    if cost_backtest.policy_digest != policy.policy_digest:
        raise ForecastingError("cost backtest policy digest mismatch")
    if not cost_backtest.accepted:
        raise ForecastingError(
            "rejected cost backtest cannot classify anomaly"
        )
    observed = _nonnegative(observed_cost, "observed_cost")
    expected = cost_backtest.forecast[0].value
    error = abs(observed - expected)
    relative = error / max(abs(expected), 1e-12)

    if relative >= policy.critical_anomaly_relative_error:
        severity = AnomalySeverity.CRITICAL
    elif relative >= policy.high_anomaly_relative_error:
        severity = AnomalySeverity.HIGH
    elif relative >= policy.anomaly_relative_error:
        severity = AnomalySeverity.MEDIUM
    elif error > 0.0:
        severity = AnomalySeverity.LOW
    else:
        severity = AnomalySeverity.NONE

    action_required = (
        _severity_rank(severity)
        >= _severity_rank(policy.require_action_from)
    )
    provisional = {
        "severity": severity.value,
        "expected_cost": expected,
        "observed_cost": observed,
        "absolute_error": error,
        "relative_error": relative,
        "cost_backtest_digest": cost_backtest.decision_digest,
        "policy_digest": policy.policy_digest,
        "action_required": action_required,
    }
    anomaly_digest = _canonical_digest(provisional)

    receipt_digest: str | None = None
    if action_required:
        if not isinstance(action_receipt, AccountableActionReceipt):
            raise ForecastingError(
                "actionable anomaly requires AccountableActionReceipt"
            )
        if action_receipt.anomaly_digest != anomaly_digest:
            raise ForecastingError(
                "action receipt anomaly digest mismatch"
            )
        receipt_digest = action_receipt.receipt_digest
    elif action_receipt is not None:
        raise ForecastingError(
            "non-actionable anomaly cannot carry action receipt"
        )

    return CostAnomalyDecision(
        severity=severity,
        expected_cost=expected,
        observed_cost=observed,
        absolute_error=error,
        relative_error=relative,
        cost_backtest_digest=cost_backtest.decision_digest,
        policy_digest=policy.policy_digest,
        action_required=action_required,
        action_receipt_digest=receipt_digest,
    )


def cost_anomaly_identity(
    *,
    cost_backtest: ForecastBacktestDecision,
    policy: ForecastPolicy,
    observed_cost: float,
) -> str:
    """Return the digest an AccountableActionReceipt must bind."""

    if not isinstance(cost_backtest, ForecastBacktestDecision):
        raise TypeError(
            "cost_backtest must be ForecastBacktestDecision"
        )
    if not isinstance(policy, ForecastPolicy):
        raise TypeError("policy must be ForecastPolicy")
    observed = _nonnegative(observed_cost, "observed_cost")
    expected = cost_backtest.forecast[0].value
    error = abs(observed - expected)
    relative = error / max(abs(expected), 1e-12)
    if relative >= policy.critical_anomaly_relative_error:
        severity = AnomalySeverity.CRITICAL
    elif relative >= policy.high_anomaly_relative_error:
        severity = AnomalySeverity.HIGH
    elif relative >= policy.anomaly_relative_error:
        severity = AnomalySeverity.MEDIUM
    elif error > 0.0:
        severity = AnomalySeverity.LOW
    else:
        severity = AnomalySeverity.NONE
    action_required = (
        _severity_rank(severity)
        >= _severity_rank(policy.require_action_from)
    )
    return _canonical_digest(
        {
            "severity": severity.value,
            "expected_cost": expected,
            "observed_cost": observed,
            "absolute_error": error,
            "relative_error": relative,
            "cost_backtest_digest": cost_backtest.decision_digest,
            "policy_digest": policy.policy_digest,
            "action_required": action_required,
        }
    )


def qualify_forecasting_loop(
    *,
    capacity_decision: CapacityQualificationDecision,
    budget_decision: BudgetAccountingDecision,
    demand_backtest: ForecastBacktestDecision,
    capacity_backtest: ForecastBacktestDecision,
    cost_backtest: ForecastBacktestDecision,
    anomaly_decision: CostAnomalyDecision,
) -> ForecastingQualificationDecision:
    if not isinstance(
        capacity_decision,
        CapacityQualificationDecision,
    ):
        raise TypeError(
            "capacity_decision must be CapacityQualificationDecision"
        )
    if not isinstance(budget_decision, BudgetAccountingDecision):
        raise TypeError(
            "budget_decision must be BudgetAccountingDecision"
        )
    for name, value in (
        ("demand_backtest", demand_backtest),
        ("capacity_backtest", capacity_backtest),
        ("cost_backtest", cost_backtest),
    ):
        if not isinstance(value, ForecastBacktestDecision):
            raise TypeError(
                f"{name} must be ForecastBacktestDecision"
            )
    if not isinstance(anomaly_decision, CostAnomalyDecision):
        raise TypeError(
            "anomaly_decision must be CostAnomalyDecision"
        )

    reasons: list[str] = []
    if not capacity_decision.accepted:
        reasons.append("capacity-qualification-rejected")
    if not budget_decision.accepted:
        reasons.append("budget-accounting-rejected")

    required = {
        ForecastMetric.DEMAND: demand_backtest,
        ForecastMetric.CAPACITY: capacity_backtest,
        ForecastMetric.COST: cost_backtest,
    }
    for metric, decision in required.items():
        if decision.metric is not metric:
            reasons.append(
                f"{metric.value}-backtest-metric-mismatch"
            )
        if not decision.accepted:
            reasons.append(
                f"{metric.value}-forecast-backtest-rejected"
            )

    policy_digests = {
        demand_backtest.policy_digest,
        capacity_backtest.policy_digest,
        cost_backtest.policy_digest,
        anomaly_decision.policy_digest,
    }
    if len(policy_digests) != 1:
        reasons.append("forecast-policy-digest-mismatch")
    if (
        anomaly_decision.cost_backtest_digest
        != cost_backtest.decision_digest
    ):
        reasons.append("anomaly-cost-backtest-digest-mismatch")
    if (
        anomaly_decision.action_required
        and anomaly_decision.action_receipt_digest is None
    ):
        reasons.append("accountable-anomaly-action-missing")

    normalized = tuple(sorted(set(reasons)))
    return ForecastingQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        capacity_decision_digest=capacity_decision.decision_digest,
        budget_decision_digest=budget_decision.decision_digest,
        demand_backtest_digest=demand_backtest.decision_digest,
        capacity_backtest_digest=capacity_backtest.decision_digest,
        cost_backtest_digest=cost_backtest.decision_digest,
        anomaly_decision_digest=anomaly_decision.decision_digest,
    )


__all__ = [
    "FORECASTING_ACCOUNTABILITY_ID",
    "FORECASTING_SCHEMA_VERSION",
    "FORECASTING_TASK_ID",
    "AccountableActionReceipt",
    "ActionDisposition",
    "AnomalySeverity",
    "CostAnomalyDecision",
    "ForecastBacktestDecision",
    "ForecastMetric",
    "ForecastModelKind",
    "ForecastObservation",
    "ForecastPoint",
    "ForecastPolicy",
    "ForecastSeries",
    "ForecastingError",
    "ForecastingQualificationDecision",
    "backtest_forecast",
    "classify_cost_anomaly",
    "cost_anomaly_identity",
    "qualify_forecasting_loop",
]
