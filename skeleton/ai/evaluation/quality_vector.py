"""Multi-dimensional quality evidence and non-compensable promotion policy.

VOL-070 keeps raw measurements, units, uncertainty, suite ownership, and
per-dimension verdicts visible. Aggregate scores are advisory for soft
trade-offs only: a hard dimension failure can never be compensated by strong
scores elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Iterable

QUALITY_VECTOR_SCHEMA = "skeleton.evaluation.quality-vector.v1"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_DIMENSIONS = 128


class QualityContractError(ValueError):
    """Quality evidence or promotion policy violated the contract."""


class QualityDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise QualityContractError(
            f"{field_name} must be a canonical lowercase identifier"
        )
    return value


def _finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualityContractError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise QualityContractError(f"{field_name} must be finite")
    return result


def _unit_interval(value: object, field_name: str) -> float:
    result = _finite(value, field_name)
    if not 0.0 <= result <= 1.0:
        raise QualityContractError(f"{field_name} must be within [0, 1]")
    return result


def _digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise QualityContractError(
            f"{field_name} must be lowercase canonical sha256"
        )
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise QualityContractError(
            f"{field_name} must be timezone-aware RFC3339"
        )
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise QualityContractError(f"{field_name} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise QualityContractError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise QualityContractError("evaluation time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _canonical_json(value: object, field_name: str) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise QualityContractError(
            f"{field_name} must be deterministic JSON"
        ) from exc


def _payload_digest(value: object, field_name: str = "payload") -> str:
    return sha256(_canonical_json(value, field_name)).hexdigest()


@dataclass(frozen=True, slots=True)
class QualityDimensionPolicy:
    dimension_id: str
    unit: str
    direction: QualityDirection
    threshold: float
    quality_best: float
    quality_worst: float
    evaluation_owner_id: str
    evaluation_suite_id: str
    max_uncertainty: float
    max_age_seconds: int
    weight: float
    hard_failure: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dimension_id", _identifier(self.dimension_id, "dimension_id")
        )
        object.__setattr__(self, "unit", _identifier(self.unit, "unit"))
        if not isinstance(self.direction, QualityDirection):
            raise QualityContractError("direction must be QualityDirection")
        threshold = _finite(self.threshold, "threshold")
        best = _finite(self.quality_best, "quality_best")
        worst = _finite(self.quality_worst, "quality_worst")
        if self.direction is QualityDirection.HIGHER_IS_BETTER:
            if not worst < threshold <= best:
                raise QualityContractError(
                    "higher-is-better policy requires worst < threshold <= best"
                )
        else:
            if not best <= threshold < worst:
                raise QualityContractError(
                    "lower-is-better policy requires best <= threshold < worst"
                )
        object.__setattr__(self, "threshold", threshold)
        object.__setattr__(self, "quality_best", best)
        object.__setattr__(self, "quality_worst", worst)
        object.__setattr__(
            self,
            "evaluation_owner_id",
            _identifier(self.evaluation_owner_id, "evaluation_owner_id"),
        )
        object.__setattr__(
            self,
            "evaluation_suite_id",
            _identifier(self.evaluation_suite_id, "evaluation_suite_id"),
        )
        uncertainty = _finite(self.max_uncertainty, "max_uncertainty")
        if uncertainty < 0.0:
            raise QualityContractError("max_uncertainty must be non-negative")
        object.__setattr__(self, "max_uncertainty", uncertainty)
        if (
            isinstance(self.max_age_seconds, bool)
            or not isinstance(self.max_age_seconds, int)
            or self.max_age_seconds <= 0
        ):
            raise QualityContractError("max_age_seconds must be positive integer")
        weight = _finite(self.weight, "weight")
        if weight <= 0.0:
            raise QualityContractError("weight must be positive")
        object.__setattr__(self, "weight", weight)
        if not isinstance(self.hard_failure, bool):
            raise QualityContractError("hard_failure must be boolean")

    def to_wire(self) -> dict[str, object]:
        return {
            "dimension_id": self.dimension_id,
            "unit": self.unit,
            "direction": self.direction.value,
            "threshold": self.threshold,
            "quality_best": self.quality_best,
            "quality_worst": self.quality_worst,
            "evaluation_owner_id": self.evaluation_owner_id,
            "evaluation_suite_id": self.evaluation_suite_id,
            "max_uncertainty": self.max_uncertainty,
            "max_age_seconds": self.max_age_seconds,
            "weight": self.weight,
            "hard_failure": self.hard_failure,
        }


@dataclass(frozen=True, slots=True)
class QualityMeasurement:
    measurement_id: str
    dimension_id: str
    raw_value: float
    uncertainty: float
    unit: str
    measured_at: str
    evaluation_owner_id: str
    evaluation_suite_id: str
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "measurement_id",
            _identifier(self.measurement_id, "measurement_id"),
        )
        object.__setattr__(
            self, "dimension_id", _identifier(self.dimension_id, "dimension_id")
        )
        object.__setattr__(
            self, "raw_value", _finite(self.raw_value, "raw_value")
        )
        uncertainty = _finite(self.uncertainty, "uncertainty")
        if uncertainty < 0.0:
            raise QualityContractError("uncertainty must be non-negative")
        object.__setattr__(self, "uncertainty", uncertainty)
        object.__setattr__(self, "unit", _identifier(self.unit, "unit"))
        _timestamp(self.measured_at, "measured_at")
        object.__setattr__(
            self,
            "evaluation_owner_id",
            _identifier(self.evaluation_owner_id, "evaluation_owner_id"),
        )
        object.__setattr__(
            self,
            "evaluation_suite_id",
            _identifier(self.evaluation_suite_id, "evaluation_suite_id"),
        )
        object.__setattr__(
            self,
            "evidence_digest",
            _digest(self.evidence_digest, "evidence_digest"),
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "measurement_id": self.measurement_id,
            "dimension_id": self.dimension_id,
            "raw_value": self.raw_value,
            "uncertainty": self.uncertainty,
            "unit": self.unit,
            "measured_at": self.measured_at,
            "evaluation_owner_id": self.evaluation_owner_id,
            "evaluation_suite_id": self.evaluation_suite_id,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class QualityDimensionResult:
    dimension_id: str
    raw_value: float | None
    uncertainty: float | None
    unit: str
    conservative_value: float | None
    normalized_score: float
    passed: bool
    hard_failure: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dimension_id", _identifier(self.dimension_id, "dimension_id")
        )
        object.__setattr__(self, "unit", _identifier(self.unit, "unit"))
        if self.raw_value is not None:
            object.__setattr__(
                self, "raw_value", _finite(self.raw_value, "raw_value")
            )
        if self.uncertainty is not None:
            uncertainty = _finite(self.uncertainty, "uncertainty")
            if uncertainty < 0:
                raise QualityContractError("uncertainty must be non-negative")
            object.__setattr__(self, "uncertainty", uncertainty)
        if self.conservative_value is not None:
            object.__setattr__(
                self,
                "conservative_value",
                _finite(self.conservative_value, "conservative_value"),
            )
        object.__setattr__(
            self,
            "normalized_score",
            _unit_interval(self.normalized_score, "normalized_score"),
        )
        if not isinstance(self.passed, bool) or not isinstance(
            self.hard_failure, bool
        ):
            raise QualityContractError(
                "passed and hard_failure must be boolean"
            )
        reasons = tuple(sorted(self.reasons))
        if len(reasons) != len(set(reasons)):
            raise QualityContractError("dimension result reasons contain duplicates")
        for reason in reasons:
            _identifier(reason, "reason")
        object.__setattr__(self, "reasons", reasons)
        if self.passed and self.reasons:
            raise QualityContractError("passed dimension cannot carry failures")
        if not self.passed and not self.reasons:
            raise QualityContractError("failed dimension requires a reason")

    def to_wire(self) -> dict[str, object]:
        return {
            "dimension_id": self.dimension_id,
            "raw_value": self.raw_value,
            "uncertainty": self.uncertainty,
            "unit": self.unit,
            "conservative_value": self.conservative_value,
            "normalized_score": self.normalized_score,
            "passed": self.passed,
            "hard_failure": self.hard_failure,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class QualityVector:
    evaluated_at: str
    policy_digest: str
    dimensions: tuple[QualityDimensionResult, ...]
    aggregate_score: float
    minimum_aggregate_score: float
    hard_failures: tuple[str, ...]
    promotion_eligible: bool
    receipt_digest: str

    def __post_init__(self) -> None:
        _timestamp(self.evaluated_at, "evaluated_at")
        object.__setattr__(
            self, "policy_digest", _digest(self.policy_digest, "policy_digest")
        )
        if not isinstance(self.dimensions, tuple) or not self.dimensions:
            raise QualityContractError(
                "quality vector requires dimension results"
            )
        dimension_ids = [item.dimension_id for item in self.dimensions]
        if dimension_ids != sorted(dimension_ids):
            raise QualityContractError(
                "quality vector dimensions must be canonically sorted"
            )
        if len(dimension_ids) != len(set(dimension_ids)):
            raise QualityContractError(
                "quality vector contains duplicate dimensions"
            )
        object.__setattr__(
            self,
            "aggregate_score",
            _unit_interval(self.aggregate_score, "aggregate_score"),
        )
        object.__setattr__(
            self,
            "minimum_aggregate_score",
            _unit_interval(
                self.minimum_aggregate_score,
                "minimum_aggregate_score",
            ),
        )
        hard = tuple(sorted(self.hard_failures))
        if len(hard) != len(set(hard)):
            raise QualityContractError("hard_failures contains duplicates")
        for dimension_id in hard:
            _identifier(dimension_id, "hard_failure")
        object.__setattr__(self, "hard_failures", hard)
        if not isinstance(self.promotion_eligible, bool):
            raise QualityContractError(
                "promotion_eligible must be boolean"
            )
        if self.promotion_eligible and self.hard_failures:
            raise QualityContractError(
                "hard failure cannot be compensated into eligibility"
            )
        object.__setattr__(
            self, "receipt_digest", _digest(self.receipt_digest, "receipt_digest")
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "evaluated_at": self.evaluated_at,
            "policy_digest": self.policy_digest,
            "dimensions": [item.to_wire() for item in self.dimensions],
            "aggregate_score": self.aggregate_score,
            "minimum_aggregate_score": self.minimum_aggregate_score,
            "hard_failures": list(self.hard_failures),
            "promotion_eligible": self.promotion_eligible,
            "receipt_digest": self.receipt_digest,
        }


class QualityPolicy:
    """Bind each quality dimension to exact suite ownership and thresholds."""

    def __init__(
        self,
        dimensions: Iterable[QualityDimensionPolicy],
        *,
        minimum_aggregate_score: float,
        max_future_skew_seconds: int = 5,
    ) -> None:
        items = tuple(dimensions)
        if not items:
            raise QualityContractError("quality policy requires dimensions")
        if len(items) > _MAX_DIMENSIONS:
            raise QualityContractError("quality policy exceeds dimension limit")
        by_id: dict[str, QualityDimensionPolicy] = {}
        for item in items:
            if not isinstance(item, QualityDimensionPolicy):
                raise QualityContractError(
                    "dimensions must contain QualityDimensionPolicy"
                )
            if item.dimension_id in by_id:
                raise QualityContractError("duplicate quality dimension")
            by_id[item.dimension_id] = item
        self._dimensions = dict(sorted(by_id.items()))
        self.minimum_aggregate_score = _unit_interval(
            minimum_aggregate_score, "minimum_aggregate_score"
        )
        if (
            isinstance(max_future_skew_seconds, bool)
            or not isinstance(max_future_skew_seconds, int)
            or not 0 <= max_future_skew_seconds <= 300
        ):
            raise QualityContractError(
                "max_future_skew_seconds must be in [0, 300]"
            )
        self.max_future_skew_seconds = max_future_skew_seconds

    @property
    def dimension_ids(self) -> tuple[str, ...]:
        return tuple(self._dimensions)

    @property
    def digest(self) -> str:
        return _payload_digest(
            {
                "schema": QUALITY_VECTOR_SCHEMA,
                "kind": "quality-policy",
                "dimensions": [
                    item.to_wire() for item in self._dimensions.values()
                ],
                "minimum_aggregate_score": self.minimum_aggregate_score,
                "max_future_skew_seconds": self.max_future_skew_seconds,
            },
            "quality policy",
        )

    def evaluate(
        self,
        measurements: Iterable[QualityMeasurement],
        *,
        now: datetime,
    ) -> QualityVector:
        evaluated_at = _canonical_timestamp(now)
        items = tuple(measurements)
        by_dimension: dict[str, QualityMeasurement] = {}
        measurement_ids: set[str] = set()
        for item in items:
            if not isinstance(item, QualityMeasurement):
                raise QualityContractError(
                    "measurements must contain QualityMeasurement"
                )
            if item.measurement_id in measurement_ids:
                raise QualityContractError("duplicate measurement_id")
            measurement_ids.add(item.measurement_id)
            if item.dimension_id in by_dimension:
                raise QualityContractError(
                    f"duplicate measurement for {item.dimension_id}"
                )
            if item.dimension_id not in self._dimensions:
                raise QualityContractError(
                    f"measurement references unknown dimension {item.dimension_id}"
                )
            by_dimension[item.dimension_id] = item

        results: list[QualityDimensionResult] = []
        weighted_score = 0.0
        total_weight = 0.0
        hard_failures: list[str] = []
        for dimension_id, policy in self._dimensions.items():
            measurement = by_dimension.get(dimension_id)
            result = self._evaluate_dimension(
                policy,
                measurement,
                now=now.astimezone(timezone.utc),
            )
            results.append(result)
            weighted_score += result.normalized_score * policy.weight
            total_weight += policy.weight
            if result.hard_failure and not result.passed:
                hard_failures.append(dimension_id)

        aggregate = weighted_score / total_weight
        promotion_eligible = (
            not hard_failures
            and aggregate >= self.minimum_aggregate_score
        )
        payload = {
            "schema": QUALITY_VECTOR_SCHEMA,
            "kind": "quality-vector",
            "evaluated_at": evaluated_at,
            "policy_digest": self.digest,
            "dimensions": [item.to_wire() for item in results],
            "aggregate_score": aggregate,
            "minimum_aggregate_score": self.minimum_aggregate_score,
            "hard_failures": sorted(hard_failures),
            "promotion_eligible": promotion_eligible,
        }
        return QualityVector(
            evaluated_at=evaluated_at,
            policy_digest=self.digest,
            dimensions=tuple(results),
            aggregate_score=aggregate,
            minimum_aggregate_score=self.minimum_aggregate_score,
            hard_failures=tuple(sorted(hard_failures)),
            promotion_eligible=promotion_eligible,
            receipt_digest=_payload_digest(payload, "quality vector"),
        )

    def verify(self, vector: QualityVector) -> None:
        if not isinstance(vector, QualityVector):
            raise TypeError("vector must be QualityVector")
        if vector.policy_digest != self.digest:
            raise QualityContractError("quality-vector policy digest drift")
        payload = vector.to_wire()
        receipt = payload.pop("receipt_digest")
        expected = _payload_digest(
            {
                "schema": QUALITY_VECTOR_SCHEMA,
                "kind": "quality-vector",
                **payload,
            },
            "quality vector",
        )
        if receipt != expected:
            raise QualityContractError(
                "quality-vector receipt failed integrity verification"
            )
        expected_hard = tuple(
            result.dimension_id
            for result in vector.dimensions
            if result.hard_failure and not result.passed
        )
        if vector.hard_failures != expected_hard:
            raise QualityContractError("hard-failure ledger drift")
        expected_eligible = (
            not expected_hard
            and vector.aggregate_score >= vector.minimum_aggregate_score
        )
        if vector.promotion_eligible != expected_eligible:
            raise QualityContractError(
                "promotion eligibility violates hard-failure policy"
            )

    def _evaluate_dimension(
        self,
        policy: QualityDimensionPolicy,
        measurement: QualityMeasurement | None,
        *,
        now: datetime,
    ) -> QualityDimensionResult:
        if measurement is None:
            return QualityDimensionResult(
                dimension_id=policy.dimension_id,
                raw_value=None,
                uncertainty=None,
                unit=policy.unit,
                conservative_value=None,
                normalized_score=0.0,
                passed=False,
                hard_failure=policy.hard_failure,
                reasons=("missing-measurement",),
            )

        reasons: list[str] = []
        if measurement.unit != policy.unit:
            reasons.append("unit-mismatch")
        if measurement.evaluation_owner_id != policy.evaluation_owner_id:
            reasons.append("evaluation-owner-mismatch")
        if measurement.evaluation_suite_id != policy.evaluation_suite_id:
            reasons.append("evaluation-suite-mismatch")
        if measurement.uncertainty > policy.max_uncertainty:
            reasons.append("uncertainty-above-limit")

        measured_at = _timestamp(measurement.measured_at, "measured_at")
        age = (now - measured_at).total_seconds()
        if age < -self.max_future_skew_seconds:
            reasons.append("measurement-from-future")
        elif age > policy.max_age_seconds:
            reasons.append("stale-measurement")

        if policy.direction is QualityDirection.HIGHER_IS_BETTER:
            conservative = measurement.raw_value - measurement.uncertainty
            threshold_passed = conservative >= policy.threshold
            normalized = (
                conservative - policy.quality_worst
            ) / (policy.quality_best - policy.quality_worst)
        else:
            conservative = measurement.raw_value + measurement.uncertainty
            threshold_passed = conservative <= policy.threshold
            normalized = (
                policy.quality_worst - conservative
            ) / (policy.quality_worst - policy.quality_best)
        normalized = min(1.0, max(0.0, normalized))
        if not threshold_passed:
            reasons.append("threshold-failure")
        canonical_reasons = tuple(sorted(set(reasons)))
        return QualityDimensionResult(
            dimension_id=policy.dimension_id,
            raw_value=measurement.raw_value,
            uncertainty=measurement.uncertainty,
            unit=policy.unit,
            conservative_value=conservative,
            normalized_score=normalized if not canonical_reasons else min(normalized, 0.5),
            passed=not canonical_reasons,
            hard_failure=policy.hard_failure,
            reasons=canonical_reasons,
        )


__all__ = [
    "QUALITY_VECTOR_SCHEMA",
    "QualityContractError",
    "QualityDimensionPolicy",
    "QualityDimensionResult",
    "QualityDirection",
    "QualityMeasurement",
    "QualityPolicy",
    "QualityVector",
]
