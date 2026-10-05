"""Canonical provenance-bound project metrics for VOL-117.

Project metrics are diagnostic evidence only. They may describe activity,
throughput, quality, risk, and outcomes, but they never become completion or
promotion authority. Observations are bound to exact metric-definition revisions
and authoritative source digests. Ratio/count values are recomputed from their
integer provenance fields to prevent decorative percentages from replacing
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Iterable, Mapping

PROJECT_METRICS_SCHEMA = "skeleton.contracts.project_metrics.v1"
_MAX_DEFINITIONS = 10_000
_MAX_OBSERVATIONS = 100_000
_MAX_TEXT = 2_048
_MAX_TICK = 2_147_483_647
_MAX_VALUE = 9_007_199_254_740_991
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_.:/-]{0,127}$")


class MetricError(ValueError):
    """Project-metric state is malformed, contradictory, or non-diagnostic."""


class MetricClass(str, Enum):
    ACTIVITY = "activity"
    THROUGHPUT = "throughput"
    QUALITY = "quality"
    RISK = "risk"
    OUTCOME = "outcome"


class MetricFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    FUTURE = "future"


def _stable_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise MetricError(f"{field} must be stable identifier")
    return value


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise MetricError(f"{field} must be canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise MetricError(f"{field} must be lowercase sha256")
    return value


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_TEXT
    ):
        raise MetricError(f"{field} must be bounded canonical text")
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise MetricError(f"{field} contains control characters")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetricError(f"{field} must be nonnegative integer")
    if not 0 <= value <= _MAX_VALUE:
        raise MetricError(f"{field} must be nonnegative integer")
    return value


def _tick(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetricError(f"{field} must be nonnegative integer")
    if not 0 <= value <= _MAX_TICK:
        raise MetricError(f"{field} must be nonnegative integer")
    return value


def _positive_tick(value: object, field: str) -> int:
    value = _tick(value, field)
    if value < 1:
        raise MetricError(f"{field} must be positive integer")
    return value


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricError(f"{field} must be finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise MetricError(f"{field} must be finite number")
    return normalized


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MetricError("metric state must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    metric_class: MetricClass
    unit: str
    source_kind: str
    completion_authority: bool = False
    owner_id: str = "OWNER.METRICS"
    description: str = "diagnostic project metric"
    max_age_ticks: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric_id",
            _stable_id(self.metric_id, "metric_id"),
        )
        if not isinstance(self.metric_class, MetricClass):
            raise MetricError("metric_class must be MetricClass")
        object.__setattr__(self, "unit", _token(self.unit, "unit"))
        object.__setattr__(
            self,
            "source_kind",
            _token(self.source_kind, "source_kind"),
        )
        if not isinstance(self.completion_authority, bool):
            raise MetricError("completion_authority must be bool")
        if self.completion_authority:
            raise MetricError("diagnostic metric cannot be completion authority")
        object.__setattr__(
            self,
            "owner_id",
            _stable_id(self.owner_id, "owner_id"),
        )
        object.__setattr__(
            self,
            "description",
            _text(self.description, "description"),
        )
        object.__setattr__(
            self,
            "max_age_ticks",
            _positive_tick(self.max_age_ticks, "max_age_ticks"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                PROJECT_METRICS_SCHEMA,
                self.metric_id,
                self.metric_class.value,
                self.unit,
                self.source_kind,
                self.completion_authority,
                self.owner_id,
                self.description,
                self.max_age_ticks,
            ]
        )


@dataclass(frozen=True, slots=True)
class MetricObservation:
    metric_id: str
    value: float
    numerator: int
    denominator: int
    source_digest: str
    observed_tick: int
    definition_digest: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    producer_id: str | None = None
    complete: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric_id",
            _stable_id(self.metric_id, "metric_id"),
        )
        object.__setattr__(self, "value", _finite_number(self.value, "value"))
        object.__setattr__(
            self,
            "numerator",
            _nonnegative_int(self.numerator, "numerator"),
        )
        object.__setattr__(
            self,
            "denominator",
            _nonnegative_int(self.denominator, "denominator"),
        )
        if self.denominator < 1:
            raise MetricError("denominator must be positive")
        object.__setattr__(
            self,
            "source_digest",
            _sha(self.source_digest, "source_digest"),
        )
        object.__setattr__(
            self,
            "observed_tick",
            _tick(self.observed_tick, "observed_tick"),
        )
        if self.definition_digest is not None:
            object.__setattr__(
                self,
                "definition_digest",
                _sha(self.definition_digest, "definition_digest"),
            )
        if self.source_kind is not None:
            object.__setattr__(
                self,
                "source_kind",
                _token(self.source_kind, "source_kind"),
            )
        if self.source_id is not None:
            object.__setattr__(
                self,
                "source_id",
                _stable_id(self.source_id, "source_id"),
            )
        if self.producer_id is not None:
            object.__setattr__(
                self,
                "producer_id",
                _stable_id(self.producer_id, "producer_id"),
            )
        if not isinstance(self.complete, bool):
            raise MetricError("complete must be bool")

    @property
    def bound(self) -> bool:
        return (
            self.definition_digest is not None
            and self.source_kind is not None
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                PROJECT_METRICS_SCHEMA,
                self.metric_id,
                self.value,
                self.numerator,
                self.denominator,
                self.source_digest,
                self.observed_tick,
                self.definition_digest,
                self.source_kind,
                self.source_id,
                self.producer_id,
                self.complete,
            ]
        )


@dataclass(frozen=True, slots=True)
class ProjectMetric:
    definition: MetricDefinition
    observation: MetricObservation

    def __post_init__(self) -> None:
        if not isinstance(self.definition, MetricDefinition):
            raise TypeError("definition must be MetricDefinition")
        if not isinstance(self.observation, MetricObservation):
            raise TypeError("observation must be MetricObservation")
        if self.definition.metric_id != self.observation.metric_id:
            raise MetricError("definition/observation mismatch")
        if self.observation.definition_digest != self.definition.digest:
            raise MetricError("observation definition revision mismatch")
        if self.observation.source_kind != self.definition.source_kind:
            raise MetricError("observation source kind mismatch")
        if not self.observation.complete:
            raise MetricError("incomplete observation cannot become project metric")
        self._validate_value_semantics()

    def _validate_value_semantics(self) -> None:
        unit = self.definition.unit
        observation = self.observation
        if unit in {"ratio", "fraction"}:
            if observation.numerator > observation.denominator:
                raise MetricError("ratio numerator cannot exceed denominator")
            expected = observation.numerator / observation.denominator
            if not math.isclose(
                observation.value,
                expected,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise MetricError(
                    "ratio value does not match numerator/denominator provenance"
                )
        elif unit == "percent":
            if observation.numerator > observation.denominator:
                raise MetricError("percent numerator cannot exceed denominator")
            expected = (
                observation.numerator / observation.denominator
            ) * 100.0
            if not math.isclose(
                observation.value,
                expected,
                rel_tol=0.0,
                abs_tol=1e-10,
            ):
                raise MetricError(
                    "percent value does not match numerator/denominator provenance"
                )
        elif unit == "count":
            if observation.denominator != 1:
                raise MetricError("count metric denominator must equal one")
            if not math.isclose(
                observation.value,
                float(observation.numerator),
                rel_tol=0.0,
                abs_tol=0.0,
            ):
                raise MetricError(
                    "count value does not match numerator provenance"
                )

    @property
    def digest(self) -> str:
        return _digest(
            [
                PROJECT_METRICS_SCHEMA,
                self.definition.digest,
                self.observation.digest,
            ]
        )

    def freshness(self, current_tick: int) -> MetricFreshness:
        current_tick = _tick(current_tick, "current_tick")
        if current_tick < self.observation.observed_tick:
            return MetricFreshness.FUTURE
        age = current_tick - self.observation.observed_tick
        if age > self.definition.max_age_ticks:
            return MetricFreshness.STALE
        return MetricFreshness.FRESH


@dataclass(frozen=True, slots=True)
class MetricClassSummary:
    metric_class: MetricClass
    total: int
    fresh: int
    stale: int
    missing: int

    def __post_init__(self) -> None:
        if not isinstance(self.metric_class, MetricClass):
            raise MetricError("metric_class must be MetricClass")
        for field in ("total", "fresh", "stale", "missing"):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        if self.fresh + self.stale + self.missing != self.total:
            raise MetricError("metric class summary counts do not reconcile")


@dataclass(frozen=True, slots=True)
class ProjectMetricSnapshot:
    registry_digest: str
    current_tick: int
    metrics: tuple[ProjectMetric, ...]
    missing_metric_ids: tuple[str, ...]
    stale_metric_ids: tuple[str, ...]
    class_summaries: tuple[MetricClassSummary, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registry_digest",
            _sha(self.registry_digest, "registry_digest"),
        )
        object.__setattr__(
            self,
            "current_tick",
            _tick(self.current_tick, "current_tick"),
        )

    @property
    def diagnostic_only(self) -> bool:
        return True

    @property
    def digest(self) -> str:
        return _digest(
            [
                PROJECT_METRICS_SCHEMA,
                self.registry_digest,
                self.current_tick,
                [item.digest for item in self.metrics],
                list(self.missing_metric_ids),
                list(self.stale_metric_ids),
                [
                    (
                        item.metric_class.value,
                        item.total,
                        item.fresh,
                        item.stale,
                        item.missing,
                    )
                    for item in self.class_summaries
                ],
                self.diagnostic_only,
            ]
        )


@dataclass(frozen=True, slots=True)
class MetricTrend:
    metric_id: str
    first_tick: int
    last_tick: int
    first_value: float
    last_value: float
    delta: float
    observation_digests: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest(
            [
                PROJECT_METRICS_SCHEMA,
                self.metric_id,
                self.first_tick,
                self.last_tick,
                self.first_value,
                self.last_value,
                self.delta,
                list(self.observation_digests),
            ]
        )


class MetricRegistry:
    """Registry that binds observations and builds diagnostic snapshots."""

    def __init__(self, definitions: Iterable[MetricDefinition]) -> None:
        materialized = tuple(definitions)
        if not materialized:
            raise MetricError("definitions must be non-empty")
        if len(materialized) > _MAX_DEFINITIONS:
            raise MetricError("definition count exceeds safety bound")
        if any(
            not isinstance(item, MetricDefinition)
            for item in materialized
        ):
            raise TypeError("definitions must contain MetricDefinition")
        ids = [item.metric_id for item in materialized]
        if len(ids) != len(set(ids)):
            raise MetricError("duplicate metric definition")
        self.definitions = {
            item.metric_id: item
            for item in sorted(
                materialized,
                key=lambda item: item.metric_id,
            )
        }

    @property
    def digest(self) -> str:
        return _digest(
            [
                PROJECT_METRICS_SCHEMA,
                [item.digest for item in self.definitions.values()],
            ]
        )

    def definition(self, metric_id: str) -> MetricDefinition:
        metric_id = _stable_id(metric_id, "metric_id")
        try:
            return self.definitions[metric_id]
        except KeyError as exc:
            raise MetricError("unknown metric") from exc

    def observe(self, observation: MetricObservation) -> ProjectMetric:
        if not isinstance(observation, MetricObservation):
            raise TypeError("observation must be MetricObservation")
        definition = self.definition(observation.metric_id)

        if (
            observation.definition_digest is not None
            and observation.definition_digest != definition.digest
        ):
            raise MetricError("observation definition revision mismatch")
        if (
            observation.source_kind is not None
            and observation.source_kind != definition.source_kind
        ):
            raise MetricError("observation source kind mismatch")

        bound = replace(
            observation,
            definition_digest=definition.digest,
            source_kind=definition.source_kind,
        )
        return ProjectMetric(definition, bound)

    def stale(
        self,
        metric: ProjectMetric,
        current_tick: int,
        max_age: int | None = None,
    ) -> bool:
        if not isinstance(metric, ProjectMetric):
            raise MetricError("metric must be ProjectMetric")
        current_tick = _tick(current_tick, "current_tick")
        if max_age is None:
            max_age = metric.definition.max_age_ticks
        else:
            max_age = _tick(max_age, "max_age")
        if current_tick < metric.observation.observed_tick:
            raise MetricError("current_tick predates observation")
        return (
            current_tick - metric.observation.observed_tick
            > max_age
        )

    def snapshot(
        self,
        observations: Iterable[MetricObservation],
        *,
        current_tick: int,
    ) -> ProjectMetricSnapshot:
        current_tick = _tick(current_tick, "current_tick")
        materialized = tuple(observations)
        if len(materialized) > _MAX_OBSERVATIONS:
            raise MetricError("observation count exceeds safety bound")
        if any(
            not isinstance(item, MetricObservation)
            for item in materialized
        ):
            raise TypeError("observations must contain MetricObservation")

        by_metric: dict[str, MetricObservation] = {}
        for observation in materialized:
            if observation.metric_id in by_metric:
                raise MetricError(
                    "snapshot contains duplicate metric observation"
                )
            by_metric[observation.metric_id] = observation

        metrics: list[ProjectMetric] = []
        missing: list[str] = []
        stale: list[str] = []

        for metric_id in self.definitions:
            observation = by_metric.get(metric_id)
            if observation is None:
                missing.append(metric_id)
                continue
            metric = self.observe(observation)
            freshness = metric.freshness(current_tick)
            if freshness is MetricFreshness.FUTURE:
                raise MetricError("snapshot contains future observation")
            if freshness is MetricFreshness.STALE:
                stale.append(metric_id)
            metrics.append(metric)

        unknown = sorted(set(by_metric) - set(self.definitions))
        if unknown:
            raise MetricError(
                "snapshot contains unknown metric: " + ",".join(unknown)
            )

        summaries: list[MetricClassSummary] = []
        for metric_class in MetricClass:
            ids = [
                definition.metric_id
                for definition in self.definitions.values()
                if definition.metric_class is metric_class
            ]
            fresh_count = sum(
                1
                for metric in metrics
                if metric.definition.metric_class is metric_class
                and metric.definition.metric_id not in stale
            )
            stale_count = sum(
                1
                for metric_id in stale
                if self.definitions[metric_id].metric_class is metric_class
            )
            missing_count = sum(
                1
                for metric_id in missing
                if self.definitions[metric_id].metric_class is metric_class
            )
            summaries.append(
                MetricClassSummary(
                    metric_class=metric_class,
                    total=len(ids),
                    fresh=fresh_count,
                    stale=stale_count,
                    missing=missing_count,
                )
            )

        return ProjectMetricSnapshot(
            registry_digest=self.digest,
            current_tick=current_tick,
            metrics=tuple(
                sorted(
                    metrics,
                    key=lambda item: item.definition.metric_id,
                )
            ),
            missing_metric_ids=tuple(sorted(missing)),
            stale_metric_ids=tuple(sorted(stale)),
            class_summaries=tuple(summaries),
        )

    def trend(
        self,
        metric_id: str,
        observations: Iterable[MetricObservation],
    ) -> MetricTrend:
        definition = self.definition(metric_id)
        materialized = tuple(observations)
        if not materialized:
            raise MetricError("trend requires observations")
        if len(materialized) > _MAX_OBSERVATIONS:
            raise MetricError("observation count exceeds safety bound")

        metrics = tuple(self.observe(item) for item in materialized)
        if any(
            item.definition.metric_id != definition.metric_id
            for item in metrics
        ):
            raise MetricError("trend contains foreign metric observation")

        ordered = tuple(
            sorted(
                metrics,
                key=lambda item: (
                    item.observation.observed_tick,
                    item.observation.digest,
                ),
            )
        )
        ticks = [item.observation.observed_tick for item in ordered]
        if len(ticks) != len(set(ticks)):
            raise MetricError("trend contains duplicate observation tick")

        first = ordered[0].observation
        last = ordered[-1].observation
        return MetricTrend(
            metric_id=definition.metric_id,
            first_tick=first.observed_tick,
            last_tick=last.observed_tick,
            first_value=first.value,
            last_value=last.value,
            delta=last.value - first.value,
            observation_digests=tuple(
                item.observation.digest for item in ordered
            ),
        )


__all__ = [
    "PROJECT_METRICS_SCHEMA",
    "MetricClass",
    "MetricClassSummary",
    "MetricDefinition",
    "MetricError",
    "MetricFreshness",
    "MetricObservation",
    "MetricRegistry",
    "MetricTrend",
    "ProjectMetric",
    "ProjectMetricSnapshot",
]
