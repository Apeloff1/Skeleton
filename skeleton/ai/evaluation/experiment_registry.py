"""Immutable P1 experiment registry contracts.

The registry describes experiments and their admissible data/traffic envelope.
It never changes production routing, promotes a candidate, or grants authority.
Those actions remain separate governed control-plane decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef


EXPERIMENT_SCHEMA_VERSION = 1
EXPERIMENT_TASK_ID = "P1-LEARN-01"
EXPERIMENT_ACCOUNTABILITY_ID = "ACC-P1-LEARN-01"
_MAX_ITEMS = 256
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ExperimentRegistryError(ValueError):
    """Experiment metadata violates the governed registry contract."""


class MetricDirection(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class TrafficMode(str, Enum):
    OFFLINE = "offline"
    SHADOW = "shadow"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise ExperimentRegistryError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ExperimentRegistryError(f"{field} must be normalized non-empty text")
    if len(value) > max_length:
        raise ExperimentRegistryError(f"{field} exceeds maximum length")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ExperimentRegistryError(f"{field} must be a lowercase 40-character git SHA")
    return value


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentRegistryError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ExperimentRegistryError(f"{field} must be finite and non-negative")
    return result


def _bounded_fraction(value: object, field: str) -> float:
    result = _finite_nonnegative(value, field)
    if result > 1.0:
        raise ExperimentRegistryError(f"{field} must be within [0, 1]")
    return result


def _tokens(values: Iterable[str], field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ExperimentRegistryError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not result and not allow_empty:
        raise ExperimentRegistryError(f"{field} must be non-empty")
    if len(result) > _MAX_ITEMS:
        raise ExperimentRegistryError(f"{field} exceeds item limit")
    return result


def _digest(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExperimentRegistryError("experiment payload must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperimentBudget:
    max_samples: int
    max_tokens: int
    max_cost_units: float
    max_wall_time_s: float

    def __post_init__(self) -> None:
        for field in ("max_samples", "max_tokens"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ExperimentRegistryError(f"{field} must be a positive integer")
        for field in ("max_cost_units", "max_wall_time_s"):
            value = _finite_nonnegative(getattr(self, field), field)
            if value <= 0:
                raise ExperimentRegistryError(f"{field} must be positive")
            object.__setattr__(self, field, value)

    def payload(self) -> dict[str, Any]:
        return {
            "max_samples": self.max_samples,
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
        }


@dataclass(frozen=True, slots=True)
class ExperimentEligibility:
    traffic_mode: TrafficMode
    max_traffic_fraction: float
    allowed_data_classes: tuple[str, ...]
    tenant_ids: tuple[str, ...] = ()
    external_side_effects_allowed: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "traffic_mode", TrafficMode(self.traffic_mode))
        except ValueError as exc:
            raise ExperimentRegistryError("invalid traffic_mode") from exc
        fraction = _bounded_fraction(self.max_traffic_fraction, "max_traffic_fraction")
        object.__setattr__(self, "max_traffic_fraction", fraction)
        object.__setattr__(
            self,
            "allowed_data_classes",
            _tokens(self.allowed_data_classes, "allowed_data_classes"),
        )
        object.__setattr__(
            self,
            "tenant_ids",
            _tokens(self.tenant_ids, "tenant_ids", allow_empty=True),
        )
        if not isinstance(self.external_side_effects_allowed, bool):
            raise ExperimentRegistryError("external_side_effects_allowed must be boolean")
        if self.external_side_effects_allowed:
            raise ExperimentRegistryError("experiments may not authorize external side effects")
        if self.traffic_mode is TrafficMode.OFFLINE and fraction != 0.0:
            raise ExperimentRegistryError("offline experiments must have zero traffic fraction")
        if self.traffic_mode is TrafficMode.SHADOW and not 0.0 < fraction <= 1.0:
            raise ExperimentRegistryError("shadow experiments require positive bounded traffic fraction")
        if (
            self.traffic_mode is TrafficMode.SHADOW
            and any(item != "public" for item in self.allowed_data_classes)
            and not self.tenant_ids
        ):
            raise ExperimentRegistryError(
                "shadow experiments using non-public data require tenant scope"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "traffic_mode": self.traffic_mode.value,
            "max_traffic_fraction": self.max_traffic_fraction,
            "allowed_data_classes": list(self.allowed_data_classes),
            "tenant_ids": list(self.tenant_ids),
            "external_side_effects_allowed": self.external_side_effects_allowed,
        }


@dataclass(frozen=True, slots=True)
class ExperimentMetric:
    metric_id: str
    direction: MetricDirection
    minimum_samples: int
    source: str
    independent: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _token(self.metric_id, "metric_id"))
        try:
            object.__setattr__(self, "direction", MetricDirection(self.direction))
        except ValueError as exc:
            raise ExperimentRegistryError("invalid metric direction") from exc
        if (
            isinstance(self.minimum_samples, bool)
            or not isinstance(self.minimum_samples, int)
            or self.minimum_samples < 1
        ):
            raise ExperimentRegistryError("minimum_samples must be a positive integer")
        object.__setattr__(self, "source", _token(self.source, "metric source"))
        if self.independent is not True:
            raise ExperimentRegistryError(
                "experiment metrics must be independently produced"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "direction": self.direction.value,
            "minimum_samples": self.minimum_samples,
            "source": self.source,
            "independent": self.independent,
        }


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    experiment_id: str
    hypothesis: str
    owner: str
    source_commit: str
    environment_id: str
    candidate_ref: str
    eligibility: ExperimentEligibility
    budget: ExperimentBudget
    metrics: tuple[ExperimentMetric, ...]
    parent_experiment_id: str | None = None
    tags: tuple[str, ...] = ()
    schema_version: int = EXPERIMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "experiment_id", _token(self.experiment_id, "experiment_id"))
        object.__setattr__(self, "hypothesis", _text(self.hypothesis, "hypothesis", max_length=4096))
        object.__setattr__(self, "owner", _token(self.owner, "owner"))
        object.__setattr__(self, "source_commit", _sha(self.source_commit, "source_commit"))
        object.__setattr__(self, "environment_id", _token(self.environment_id, "environment_id"))
        object.__setattr__(self, "candidate_ref", _token(self.candidate_ref, "candidate_ref"))
        if not isinstance(self.eligibility, ExperimentEligibility):
            raise ExperimentRegistryError("eligibility must be ExperimentEligibility")
        if not isinstance(self.budget, ExperimentBudget):
            raise ExperimentRegistryError("budget must be ExperimentBudget")
        if not isinstance(self.metrics, tuple) or not self.metrics:
            raise ExperimentRegistryError("metrics must be a non-empty tuple")
        if any(not isinstance(metric, ExperimentMetric) for metric in self.metrics):
            raise ExperimentRegistryError("metrics must contain ExperimentMetric")
        metric_ids = [metric.metric_id for metric in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ExperimentRegistryError("metric IDs must be unique")
        if self.parent_experiment_id is not None:
            object.__setattr__(
                self,
                "parent_experiment_id",
                _token(self.parent_experiment_id, "parent_experiment_id"),
            )
            if self.parent_experiment_id == self.experiment_id:
                raise ExperimentRegistryError("experiment cannot parent itself")
        object.__setattr__(self, "tags", _tokens(self.tags, "tags", allow_empty=True))
        if self.schema_version != EXPERIMENT_SCHEMA_VERSION:
            raise ExperimentRegistryError("unsupported experiment schema version")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "owner": self.owner,
            "source_commit": self.source_commit,
            "environment_id": self.environment_id,
            "candidate_ref": self.candidate_ref,
            "eligibility": self.eligibility.payload(),
            "budget": self.budget.payload(),
            "metrics": [metric.payload() for metric in sorted(self.metrics, key=lambda item: item.metric_id)],
            "parent_experiment_id": self.parent_experiment_id,
            "tags": list(self.tags),
            "production_authority": False,
        }

    @property
    def manifest_digest(self) -> str:
        return _digest(self.identity_payload())

    def registry_evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            source=f"p1:learn-01:experiment:{self.experiment_id}",
            digest=self.manifest_digest,
            category="experiment_manifest",
        )


@dataclass(frozen=True, slots=True)
class ExperimentRegistry:
    manifests: tuple[ExperimentManifest, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.manifests, tuple):
            raise ExperimentRegistryError("registry manifests must be a tuple")
        if any(not isinstance(item, ExperimentManifest) for item in self.manifests):
            raise ExperimentRegistryError("registry entries must be ExperimentManifest")
        by_id = {item.experiment_id: item for item in self.manifests}
        if len(by_id) != len(self.manifests):
            raise ExperimentRegistryError("experiment IDs must be unique")
        for item in self.manifests:
            parent = item.parent_experiment_id
            if parent is not None and parent not in by_id:
                raise ExperimentRegistryError(
                    f"{item.experiment_id}: unknown parent experiment {parent}"
                )
        for start in by_id:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    raise ExperimentRegistryError("experiment lineage contains a cycle")
                seen.add(current)
                current = by_id[current].parent_experiment_id

    @property
    def registry_digest(self) -> str:
        return _digest(
            {
                "schema_version": EXPERIMENT_SCHEMA_VERSION,
                "task_id": EXPERIMENT_TASK_ID,
                "accountability_id": EXPERIMENT_ACCOUNTABILITY_ID,
                "manifests": [
                    item.identity_payload()
                    for item in sorted(self.manifests, key=lambda item: item.experiment_id)
                ],
            }
        )

    def get(self, experiment_id: str) -> ExperimentManifest:
        key = _token(experiment_id, "experiment_id")
        for item in self.manifests:
            if item.experiment_id == key:
                return item
        raise KeyError(key)


__all__ = [
    "EXPERIMENT_ACCOUNTABILITY_ID",
    "EXPERIMENT_SCHEMA_VERSION",
    "EXPERIMENT_TASK_ID",
    "ExperimentBudget",
    "ExperimentEligibility",
    "ExperimentManifest",
    "ExperimentMetric",
    "ExperimentRegistry",
    "ExperimentRegistryError",
    "MetricDirection",
    "TrafficMode",
]
