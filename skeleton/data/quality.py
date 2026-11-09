"""Data quality gates retaining raw finite observations."""
from __future__ import annotations

from dataclasses import dataclass
import math


class DataQualityError(ValueError):
    pass


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


@dataclass(frozen=True, slots=True)
class DataQualityRule:
    rule_id: str
    metric: str
    comparator: str
    threshold: float
    critical: bool = True


@dataclass(frozen=True, slots=True)
class QualityObservation:
    metric: str
    value: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class QualityFailure:
    rule_id: str
    metric: str
    critical: bool
    reason: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    dataset_id: str
    version: int
    observations: tuple[QualityObservation, ...]
    failures: tuple[QualityFailure, ...]
    promotion_allowed: bool


class DataQualityEngine:
    def __init__(self, rules) -> None:
        self.rules = tuple(rules)
        if not self.rules or any(not isinstance(rule, DataQualityRule) for rule in self.rules):
            raise DataQualityError("invalid rules")
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise DataQualityError("duplicate rule identity")
        for rule in self.rules:
            if (
                not isinstance(rule.rule_id, str)
                or not rule.rule_id
                or not isinstance(rule.metric, str)
                or not rule.metric
                or rule.comparator not in {"gte", "lte", "eq"}
                or not _finite_number(rule.threshold)
                or not isinstance(rule.critical, bool)
            ):
                raise DataQualityError("invalid rule")

    def evaluate(
        self,
        *,
        dataset_id: str,
        version: int,
        observations,
    ) -> QualityReport:
        if not isinstance(dataset_id, str) or not dataset_id:
            raise DataQualityError("invalid dataset")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise DataQualityError("invalid dataset version")

        observed = tuple(observations)
        if any(not isinstance(item, QualityObservation) for item in observed):
            raise DataQualityError("invalid observations")
        by_metric: dict[str, QualityObservation] = {}
        for item in observed:
            if (
                not isinstance(item.metric, str)
                or not item.metric
                or not _finite_number(item.value)
                or isinstance(item.sample_count, bool)
                or not isinstance(item.sample_count, int)
                or item.sample_count < 1
                or item.metric in by_metric
            ):
                raise DataQualityError("invalid observations")
            by_metric[item.metric] = item

        failures: list[QualityFailure] = []
        for rule in self.rules:
            observation = by_metric.get(rule.metric)
            if observation is None:
                failures.append(
                    QualityFailure(
                        rule.rule_id,
                        rule.metric,
                        rule.critical,
                        "missing_observation",
                    )
                )
                continue
            ok = {
                "gte": observation.value >= rule.threshold,
                "lte": observation.value <= rule.threshold,
                "eq": observation.value == rule.threshold,
            }[rule.comparator]
            if not ok:
                failures.append(
                    QualityFailure(
                        rule.rule_id,
                        rule.metric,
                        rule.critical,
                        "threshold_violation",
                    )
                )

        return QualityReport(
            dataset_id,
            version,
            observed,
            tuple(failures),
            not any(failure.critical for failure in failures),
        )
