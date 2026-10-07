"""P1 benchmark registry, contamination controls, and improvement claims.

This module is measurement-only. It does not train, deploy, route production
traffic, or promote a candidate. It defines immutable benchmark identity and
requires explicit lineage, split contamination evidence, metric policy,
environment identity, reproducibility binding, and LEARN-01 experiment identity
before an improvement claim can become evidence.
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
from skeleton.contracts.reproducibility import ReproducibilityBundle
from skeleton.eval.experiment_registry import (
    ExperimentManifest,
    MetricDirection,
    TrafficMode,
)


BENCHMARK_REGISTRY_SCHEMA_VERSION = 1
BENCHMARK_REGISTRY_TASK_ID = "P1-LEARN-02"
BENCHMARK_REGISTRY_ACCOUNTABILITY_ID = "ACC-P1-LEARN-02"
_MAX_ITEMS = 512
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BenchmarkRegistryError(ValueError):
    """Benchmark metadata or evidence violates the governed contract."""


class BenchmarkSplitRole(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    HOLDOUT = "holdout"


class ContaminationStatus(str, Enum):
    CLEAN = "clean"
    UNKNOWN = "unknown"
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise BenchmarkRegistryError(
            f"{field} must be a canonical token"
        )
    return value


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkRegistryError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise BenchmarkRegistryError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise BenchmarkRegistryError(
            f"{field} must be lowercase sha256"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BenchmarkRegistryError(
            f"{field} must be a positive integer"
        )
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkRegistryError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise BenchmarkRegistryError(f"{field} must be finite numeric")
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
        raise BenchmarkRegistryError(
            "benchmark payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise BenchmarkRegistryError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not result and not allow_empty:
        raise BenchmarkRegistryError(f"{field} must be non-empty")
    if len(result) > _MAX_ITEMS:
        raise BenchmarkRegistryError(f"{field} exceeds item limit")
    return result


def _evidence(
    values: Iterable[EvidenceRef],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise BenchmarkRegistryError(
            f"{field} must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise BenchmarkRegistryError(
                f"{field} must contain EvidenceRef values"
            )
        _text(item.source, f"{field}.source")
        _sha256(item.digest, f"{field}.digest")
        _token(item.category, f"{field}.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key and not allow_empty:
        raise BenchmarkRegistryError(f"{field} must be non-empty")
    if len(by_key) > _MAX_ITEMS:
        raise BenchmarkRegistryError(f"{field} exceeds item limit")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    dataset_id: str
    version: str
    source_ref: str
    source_digest: str
    content_digest: str
    license_id: str
    parent_dataset_digest: str | None = None

    def __post_init__(self) -> None:
        for field in ("dataset_id", "version", "license_id"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "source_ref",
            _text(self.source_ref, "source_ref"),
        )
        object.__setattr__(
            self,
            "source_digest",
            _sha256(self.source_digest, "source_digest"),
        )
        object.__setattr__(
            self,
            "content_digest",
            _sha256(self.content_digest, "content_digest"),
        )
        if self.parent_dataset_digest is not None:
            object.__setattr__(
                self,
                "parent_dataset_digest",
                _sha256(
                    self.parent_dataset_digest,
                    "parent_dataset_digest",
                ),
            )
            if self.parent_dataset_digest == self.content_digest:
                raise BenchmarkRegistryError(
                    "dataset cannot parent itself"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "source_ref": self.source_ref,
            "source_digest": self.source_digest,
            "content_digest": self.content_digest,
            "license_id": self.license_id,
            "parent_dataset_digest": self.parent_dataset_digest,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class BenchmarkSplit:
    split_id: str
    role: BenchmarkSplitRole
    dataset_digest: str
    content_digest: str
    sample_count: int
    contamination_status: ContaminationStatus
    contamination_evidence: tuple[EvidenceRef, ...]
    contamination_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "split_id",
            _token(self.split_id, "split_id"),
        )
        try:
            object.__setattr__(
                self,
                "role",
                BenchmarkSplitRole(self.role),
            )
        except ValueError as exc:
            raise BenchmarkRegistryError("invalid split role") from exc
        object.__setattr__(
            self,
            "dataset_digest",
            _sha256(self.dataset_digest, "dataset_digest"),
        )
        object.__setattr__(
            self,
            "content_digest",
            _sha256(self.content_digest, "content_digest"),
        )
        object.__setattr__(
            self,
            "sample_count",
            _positive_int(self.sample_count, "sample_count"),
        )
        try:
            object.__setattr__(
                self,
                "contamination_status",
                ContaminationStatus(self.contamination_status),
            )
        except ValueError as exc:
            raise BenchmarkRegistryError(
                "invalid contamination status"
            ) from exc
        object.__setattr__(
            self,
            "contamination_evidence",
            _evidence(
                self.contamination_evidence,
                "contamination_evidence",
            ),
        )
        object.__setattr__(
            self,
            "contamination_sources",
            _tokens(
                self.contamination_sources,
                "contamination_sources",
                allow_empty=True,
            ),
        )
        if (
            self.contamination_status is ContaminationStatus.CLEAN
            and self.contamination_sources
        ):
            raise BenchmarkRegistryError(
                "clean split cannot declare contamination sources"
            )
        if (
            self.contamination_status
            in {
                ContaminationStatus.SUSPECTED,
                ContaminationStatus.CONFIRMED,
            }
            and not self.contamination_sources
        ):
            raise BenchmarkRegistryError(
                "suspected/confirmed contamination requires sources"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "split_id": self.split_id,
            "role": self.role.value,
            "dataset_digest": self.dataset_digest,
            "content_digest": self.content_digest,
            "sample_count": self.sample_count,
            "contamination_status": self.contamination_status.value,
            "contamination_evidence": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.contamination_evidence
            ],
            "contamination_sources": list(self.contamination_sources),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class BenchmarkMetric:
    metric_id: str
    direction: MetricDirection
    minimum_samples: int
    evaluator_id: str
    evaluator_digest: str
    independent: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric_id",
            _token(self.metric_id, "metric_id"),
        )
        try:
            object.__setattr__(
                self,
                "direction",
                MetricDirection(self.direction),
            )
        except ValueError as exc:
            raise BenchmarkRegistryError(
                "invalid metric direction"
            ) from exc
        object.__setattr__(
            self,
            "minimum_samples",
            _positive_int(
                self.minimum_samples,
                "minimum_samples",
            ),
        )
        object.__setattr__(
            self,
            "evaluator_id",
            _token(self.evaluator_id, "evaluator_id"),
        )
        object.__setattr__(
            self,
            "evaluator_digest",
            _sha256(self.evaluator_digest, "evaluator_digest"),
        )
        if self.independent is not True:
            raise BenchmarkRegistryError(
                "benchmark evaluator must be independent"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "direction": self.direction.value,
            "minimum_samples": self.minimum_samples,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "independent": self.independent,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class BenchmarkEnvironment:
    environment_id: str
    environment_digest: str
    runner_digest: str
    dependency_lock_digest: str
    source_date_epoch: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "environment_id",
            _token(self.environment_id, "environment_id"),
        )
        for field in (
            "environment_digest",
            "runner_digest",
            "dependency_lock_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "source_date_epoch",
            _positive_int(
                self.source_date_epoch,
                "source_date_epoch",
            ),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "environment_digest": self.environment_digest,
            "runner_digest": self.runner_digest,
            "dependency_lock_digest": self.dependency_lock_digest,
            "source_date_epoch": self.source_date_epoch,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class BenchmarkManifest:
    benchmark_id: str
    version: str
    datasets: tuple[BenchmarkDataset, ...]
    splits: tuple[BenchmarkSplit, ...]
    metrics: tuple[BenchmarkMetric, ...]
    primary_metric_id: str
    environment: BenchmarkEnvironment
    experiment_manifest_digest: str
    reproducibility_bundle_digest: str
    tags: tuple[str, ...] = ()
    schema_version: int = BENCHMARK_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "benchmark_id",
            _token(self.benchmark_id, "benchmark_id"),
        )
        object.__setattr__(
            self,
            "version",
            _token(self.version, "version"),
        )
        if not isinstance(self.datasets, tuple) or not self.datasets:
            raise BenchmarkRegistryError(
                "datasets must be a non-empty tuple"
            )
        if any(
            not isinstance(item, BenchmarkDataset)
            for item in self.datasets
        ):
            raise BenchmarkRegistryError(
                "datasets must contain BenchmarkDataset"
            )
        if not isinstance(self.splits, tuple) or not self.splits:
            raise BenchmarkRegistryError(
                "splits must be a non-empty tuple"
            )
        if any(
            not isinstance(item, BenchmarkSplit)
            for item in self.splits
        ):
            raise BenchmarkRegistryError(
                "splits must contain BenchmarkSplit"
            )
        if not isinstance(self.metrics, tuple) or not self.metrics:
            raise BenchmarkRegistryError(
                "metrics must be a non-empty tuple"
            )
        if any(
            not isinstance(item, BenchmarkMetric)
            for item in self.metrics
        ):
            raise BenchmarkRegistryError(
                "metrics must contain BenchmarkMetric"
            )
        if not isinstance(self.environment, BenchmarkEnvironment):
            raise BenchmarkRegistryError(
                "environment must be BenchmarkEnvironment"
            )
        if self.schema_version != BENCHMARK_REGISTRY_SCHEMA_VERSION:
            raise BenchmarkRegistryError(
                "unsupported benchmark schema version"
            )

        dataset_digests = [item.digest for item in self.datasets]
        if len(dataset_digests) != len(set(dataset_digests)):
            raise BenchmarkRegistryError(
                "dataset identities must be unique"
            )
        dataset_content = {
            item.content_digest: item for item in self.datasets
        }
        for item in self.datasets:
            parent = item.parent_dataset_digest
            if parent is not None and parent not in dataset_content:
                raise BenchmarkRegistryError(
                    f"{item.dataset_id}: unknown parent dataset digest"
                )

        split_ids = [item.split_id for item in self.splits]
        if len(split_ids) != len(set(split_ids)):
            raise BenchmarkRegistryError(
                "split IDs must be unique"
            )
        split_content = [item.content_digest for item in self.splits]
        if len(split_content) != len(set(split_content)):
            raise BenchmarkRegistryError(
                "split content digests must be unique"
            )
        known_datasets = set(dataset_digests)
        for split in self.splits:
            if split.dataset_digest not in known_datasets:
                raise BenchmarkRegistryError(
                    f"{split.split_id}: unknown dataset digest"
                )
        if not any(
            item.role in {
                BenchmarkSplitRole.TEST,
                BenchmarkSplitRole.HOLDOUT,
            }
            for item in self.splits
        ):
            raise BenchmarkRegistryError(
                "benchmark requires test or holdout split"
            )

        metric_ids = [item.metric_id for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise BenchmarkRegistryError(
                "metric IDs must be unique"
            )
        object.__setattr__(
            self,
            "primary_metric_id",
            _token(
                self.primary_metric_id,
                "primary_metric_id",
            ),
        )
        if self.primary_metric_id not in set(metric_ids):
            raise BenchmarkRegistryError(
                "primary metric must exist in metric policy"
            )
        object.__setattr__(
            self,
            "experiment_manifest_digest",
            _sha256(
                self.experiment_manifest_digest,
                "experiment_manifest_digest",
            ),
        )
        object.__setattr__(
            self,
            "reproducibility_bundle_digest",
            _sha256(
                self.reproducibility_bundle_digest,
                "reproducibility_bundle_digest",
            ),
        )
        object.__setattr__(
            self,
            "tags",
            _tokens(self.tags, "tags", allow_empty=True),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": BENCHMARK_REGISTRY_TASK_ID,
            "accountability_id": BENCHMARK_REGISTRY_ACCOUNTABILITY_ID,
            "benchmark_id": self.benchmark_id,
            "version": self.version,
            "datasets": [
                item.payload()
                for item in sorted(
                    self.datasets,
                    key=lambda row: (row.dataset_id, row.version),
                )
            ],
            "splits": [
                item.payload()
                for item in sorted(
                    self.splits,
                    key=lambda row: row.split_id,
                )
            ],
            "metrics": [
                item.payload()
                for item in sorted(
                    self.metrics,
                    key=lambda row: row.metric_id,
                )
            ],
            "primary_metric_id": self.primary_metric_id,
            "environment": self.environment.payload(),
            "experiment_manifest_digest": self.experiment_manifest_digest,
            "reproducibility_bundle_digest": self.reproducibility_bundle_digest,
            "tags": list(self.tags),
            "production_authority": False,
        }

    @property
    def manifest_digest(self) -> str:
        return _canonical_digest(self.payload())

    def registry_evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            source=(
                f"p1:learn-02:benchmark:"
                f"{self.benchmark_id}:{self.version}"
            ),
            digest=self.manifest_digest,
            category="benchmark_manifest",
        )

    def split(self, split_id: str) -> BenchmarkSplit:
        key = _token(split_id, "split_id")
        for item in self.splits:
            if item.split_id == key:
                return item
        raise KeyError(key)

    def metric(self, metric_id: str) -> BenchmarkMetric:
        key = _token(metric_id, "metric_id")
        for item in self.metrics:
            if item.metric_id == key:
                return item
        raise KeyError(key)


@dataclass(frozen=True, slots=True)
class BenchmarkRegistry:
    manifests: tuple[BenchmarkManifest, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.manifests, tuple):
            raise BenchmarkRegistryError(
                "registry manifests must be a tuple"
            )
        if any(
            not isinstance(item, BenchmarkManifest)
            for item in self.manifests
        ):
            raise BenchmarkRegistryError(
                "registry entries must be BenchmarkManifest"
            )
        keys = [
            (item.benchmark_id, item.version)
            for item in self.manifests
        ]
        if len(keys) != len(set(keys)):
            raise BenchmarkRegistryError(
                "benchmark id/version keys must be unique"
            )

    @property
    def registry_digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": BENCHMARK_REGISTRY_SCHEMA_VERSION,
                "task_id": BENCHMARK_REGISTRY_TASK_ID,
                "accountability_id": (
                    BENCHMARK_REGISTRY_ACCOUNTABILITY_ID
                ),
                "manifests": [
                    item.payload()
                    for item in sorted(
                        self.manifests,
                        key=lambda row: (
                            row.benchmark_id,
                            row.version,
                        ),
                    )
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class BenchmarkQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    benchmark_manifest_digest: str
    experiment_manifest_digest: str
    reproducibility_bundle_digest: str
    evaluated_split_ids: tuple[str, ...]
    task_id: str = BENCHMARK_REGISTRY_TASK_ID
    accountability_id: str = BENCHMARK_REGISTRY_ACCOUNTABILITY_ID
    schema_version: int = BENCHMARK_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise BenchmarkRegistryError(
                "accepted must be boolean"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise BenchmarkRegistryError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "benchmark_manifest_digest",
            "experiment_manifest_digest",
            "reproducibility_bundle_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "evaluated_split_ids",
            _tokens(
                self.evaluated_split_ids,
                "evaluated_split_ids",
            ),
        )
        if self.task_id != BENCHMARK_REGISTRY_TASK_ID:
            raise BenchmarkRegistryError("task_id drift")
        if self.accountability_id != BENCHMARK_REGISTRY_ACCOUNTABILITY_ID:
            raise BenchmarkRegistryError(
                "accountability_id drift"
            )
        if self.schema_version != BENCHMARK_REGISTRY_SCHEMA_VERSION:
            raise BenchmarkRegistryError(
                "unsupported qualification schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "benchmark_manifest_digest": self.benchmark_manifest_digest,
            "experiment_manifest_digest": self.experiment_manifest_digest,
            "reproducibility_bundle_digest": self.reproducibility_bundle_digest,
            "evaluated_split_ids": list(self.evaluated_split_ids),
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:learn-02:benchmark-qualification",
    ) -> EvidenceRef:
        if not self.accepted:
            raise BenchmarkRegistryError(
                "rejected benchmark cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="benchmark_qualification",
        )


def qualify_benchmark(
    *,
    manifest: BenchmarkManifest,
    experiment: ExperimentManifest,
    reproducibility: ReproducibilityBundle,
    evaluated_split_ids: Iterable[str],
) -> BenchmarkQualificationDecision:
    if not isinstance(manifest, BenchmarkManifest):
        raise TypeError("manifest must be BenchmarkManifest")
    if not isinstance(experiment, ExperimentManifest):
        raise TypeError("experiment must be ExperimentManifest")
    if not isinstance(reproducibility, ReproducibilityBundle):
        raise TypeError(
            "reproducibility must be ReproducibilityBundle"
        )

    split_ids = _tokens(
        evaluated_split_ids,
        "evaluated_split_ids",
    )
    reasons: list[str] = []

    if (
        manifest.experiment_manifest_digest
        != experiment.manifest_digest
    ):
        reasons.append("experiment-manifest-digest-mismatch")
    if (
        manifest.reproducibility_bundle_digest
        != reproducibility.bundle_digest
    ):
        reasons.append("reproducibility-bundle-digest-mismatch")
    if (
        manifest.environment.environment_id
        != experiment.environment_id
    ):
        reasons.append("experiment-environment-id-mismatch")
    if experiment.source_commit != reproducibility.commit_sha:
        reasons.append("experiment-source-commit-mismatch")
    if (
        manifest.environment.environment_digest
        != reproducibility.environment_digest
    ):
        reasons.append("environment-digest-mismatch")
    if (
        manifest.environment.runner_digest
        != reproducibility.runner_digest
    ):
        reasons.append("runner-digest-mismatch")
    if (
        manifest.environment.source_date_epoch
        != reproducibility.source_date_epoch
    ):
        reasons.append("source-date-epoch-mismatch")
    if experiment.eligibility.traffic_mode is not TrafficMode.OFFLINE:
        reasons.append("benchmark-experiment-must-be-offline")

    benchmark_metrics = {
        item.metric_id: item
        for item in manifest.metrics
    }
    experiment_metrics = {
        item.metric_id: item
        for item in experiment.metrics
    }
    for metric_id, exp_metric in experiment_metrics.items():
        benchmark_metric = benchmark_metrics.get(metric_id)
        if benchmark_metric is None:
            reasons.append(
                f"experiment-metric-missing:{metric_id}"
            )
            continue
        if benchmark_metric.direction is not exp_metric.direction:
            reasons.append(
                f"metric-direction-mismatch:{metric_id}"
            )
        if (
            benchmark_metric.minimum_samples
            < exp_metric.minimum_samples
        ):
            reasons.append(
                f"metric-minimum-samples-too-low:{metric_id}"
            )

    selected: list[BenchmarkSplit] = []
    for split_id in split_ids:
        try:
            split = manifest.split(split_id)
        except KeyError:
            reasons.append(f"unknown-evaluation-split:{split_id}")
            continue
        selected.append(split)
        if split.role not in {
            BenchmarkSplitRole.TEST,
            BenchmarkSplitRole.HOLDOUT,
        }:
            reasons.append(
                f"non-evaluation-split-selected:{split_id}"
            )
        if split.contamination_status is not ContaminationStatus.CLEAN:
            reasons.append(
                f"contamination-not-clean:{split_id}:"
                f"{split.contamination_status.value}"
            )
        if not split.contamination_evidence:
            reasons.append(
                f"contamination-evidence-missing:{split_id}"
            )

    if not selected:
        reasons.append("no-evaluation-split-selected")

    normalized = tuple(sorted(set(reasons)))
    return BenchmarkQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        benchmark_manifest_digest=manifest.manifest_digest,
        experiment_manifest_digest=experiment.manifest_digest,
        reproducibility_bundle_digest=reproducibility.bundle_digest,
        evaluated_split_ids=split_ids,
    )


@dataclass(frozen=True, slots=True)
class BenchmarkScoreObservation:
    benchmark_manifest_digest: str
    split_id: str
    metric_id: str
    candidate_ref: str
    score: float
    sample_count: int
    evaluator_id: str
    evaluator_digest: str
    independent: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "benchmark_manifest_digest",
            _sha256(
                self.benchmark_manifest_digest,
                "benchmark_manifest_digest",
            ),
        )
        for field in (
            "split_id",
            "metric_id",
            "candidate_ref",
            "evaluator_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "score",
            _finite(self.score, "score"),
        )
        object.__setattr__(
            self,
            "sample_count",
            _positive_int(self.sample_count, "sample_count"),
        )
        object.__setattr__(
            self,
            "evaluator_digest",
            _sha256(self.evaluator_digest, "evaluator_digest"),
        )
        if self.independent is not True:
            raise BenchmarkRegistryError(
                "score observation must be independent"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "benchmark_manifest_digest": self.benchmark_manifest_digest,
            "split_id": self.split_id,
            "metric_id": self.metric_id,
            "candidate_ref": self.candidate_ref,
            "score": self.score,
            "sample_count": self.sample_count,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "independent": self.independent,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ImprovementClaimDecision:
    accepted: bool
    reasons: tuple[str, ...]
    benchmark_qualification_digest: str
    baseline_observation_digest: str
    candidate_observation_digest: str
    metric_id: str
    split_id: str
    improvement: float
    task_id: str = BENCHMARK_REGISTRY_TASK_ID
    accountability_id: str = BENCHMARK_REGISTRY_ACCOUNTABILITY_ID
    schema_version: int = BENCHMARK_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise BenchmarkRegistryError(
                "accepted must be boolean"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise BenchmarkRegistryError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "benchmark_qualification_digest",
            "baseline_observation_digest",
            "candidate_observation_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "metric_id",
            _token(self.metric_id, "metric_id"),
        )
        object.__setattr__(
            self,
            "split_id",
            _token(self.split_id, "split_id"),
        )
        object.__setattr__(
            self,
            "improvement",
            _finite(self.improvement, "improvement"),
        )
        if self.task_id != BENCHMARK_REGISTRY_TASK_ID:
            raise BenchmarkRegistryError("task_id drift")
        if self.accountability_id != BENCHMARK_REGISTRY_ACCOUNTABILITY_ID:
            raise BenchmarkRegistryError(
                "accountability_id drift"
            )
        if self.schema_version != BENCHMARK_REGISTRY_SCHEMA_VERSION:
            raise BenchmarkRegistryError(
                "unsupported claim schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "benchmark_qualification_digest": (
                self.benchmark_qualification_digest
            ),
            "baseline_observation_digest": (
                self.baseline_observation_digest
            ),
            "candidate_observation_digest": (
                self.candidate_observation_digest
            ),
            "metric_id": self.metric_id,
            "split_id": self.split_id,
            "improvement": self.improvement,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:learn-02:improvement-claim",
    ) -> EvidenceRef:
        if not self.accepted:
            raise BenchmarkRegistryError(
                "rejected improvement claim cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="benchmark_improvement_claim",
        )


def evaluate_improvement_claim(
    *,
    manifest: BenchmarkManifest,
    qualification: BenchmarkQualificationDecision,
    experiment: ExperimentManifest,
    baseline: BenchmarkScoreObservation,
    candidate: BenchmarkScoreObservation,
) -> ImprovementClaimDecision:
    if not isinstance(manifest, BenchmarkManifest):
        raise TypeError("manifest must be BenchmarkManifest")
    if not isinstance(
        qualification,
        BenchmarkQualificationDecision,
    ):
        raise TypeError(
            "qualification must be BenchmarkQualificationDecision"
        )
    if not isinstance(experiment, ExperimentManifest):
        raise TypeError("experiment must be ExperimentManifest")
    if not isinstance(baseline, BenchmarkScoreObservation):
        raise TypeError("baseline must be BenchmarkScoreObservation")
    if not isinstance(candidate, BenchmarkScoreObservation):
        raise TypeError("candidate must be BenchmarkScoreObservation")

    reasons: list[str] = []
    if not qualification.accepted:
        reasons.append("benchmark-qualification-rejected")
    if (
        qualification.benchmark_manifest_digest
        != manifest.manifest_digest
    ):
        reasons.append("qualification-manifest-digest-mismatch")
    if (
        qualification.experiment_manifest_digest
        != experiment.manifest_digest
    ):
        reasons.append("qualification-experiment-digest-mismatch")

    for name, observation in (
        ("baseline", baseline),
        ("candidate", candidate),
    ):
        if observation.benchmark_manifest_digest != manifest.manifest_digest:
            reasons.append(
                f"{name}-benchmark-digest-mismatch"
            )
    if baseline.split_id != candidate.split_id:
        reasons.append("score-split-mismatch")
    if baseline.metric_id != candidate.metric_id:
        reasons.append("score-metric-mismatch")
    if candidate.candidate_ref != experiment.candidate_ref:
        reasons.append("candidate-ref-mismatch")
    if baseline.candidate_ref == candidate.candidate_ref:
        reasons.append("baseline-and-candidate-identical")

    split_id = candidate.split_id
    metric_id = candidate.metric_id
    try:
        split = manifest.split(split_id)
    except KeyError:
        split = None
        reasons.append("score-split-not-registered")
    try:
        metric = manifest.metric(metric_id)
    except KeyError:
        metric = None
        reasons.append("score-metric-not-registered")

    if split is not None:
        if split_id not in qualification.evaluated_split_ids:
            reasons.append("score-split-not-qualified")
        if split.contamination_status is not ContaminationStatus.CLEAN:
            reasons.append("score-split-contaminated")
        if not split.contamination_evidence:
            reasons.append("score-split-contamination-evidence-missing")

    if metric is not None:
        if baseline.evaluator_id != metric.evaluator_id:
            reasons.append("baseline-evaluator-id-mismatch")
        if candidate.evaluator_id != metric.evaluator_id:
            reasons.append("candidate-evaluator-id-mismatch")
        if baseline.evaluator_digest != metric.evaluator_digest:
            reasons.append("baseline-evaluator-digest-mismatch")
        if candidate.evaluator_digest != metric.evaluator_digest:
            reasons.append("candidate-evaluator-digest-mismatch")
        if baseline.sample_count < metric.minimum_samples:
            reasons.append("baseline-sample-count-too-low")
        if candidate.sample_count < metric.minimum_samples:
            reasons.append("candidate-sample-count-too-low")

    improvement = 0.0
    if metric is not None:
        if metric.direction is MetricDirection.MAXIMIZE:
            improvement = candidate.score - baseline.score
        else:
            improvement = baseline.score - candidate.score
        if improvement <= 0.0:
            reasons.append("candidate-did-not-improve")

    normalized = tuple(sorted(set(reasons)))
    return ImprovementClaimDecision(
        accepted=not normalized,
        reasons=normalized,
        benchmark_qualification_digest=qualification.decision_digest,
        baseline_observation_digest=baseline.digest,
        candidate_observation_digest=candidate.digest,
        metric_id=metric_id,
        split_id=split_id,
        improvement=improvement,
    )


__all__ = [
    "BENCHMARK_REGISTRY_ACCOUNTABILITY_ID",
    "BENCHMARK_REGISTRY_SCHEMA_VERSION",
    "BENCHMARK_REGISTRY_TASK_ID",
    "BenchmarkDataset",
    "BenchmarkEnvironment",
    "BenchmarkManifest",
    "BenchmarkMetric",
    "BenchmarkQualificationDecision",
    "BenchmarkRegistry",
    "BenchmarkRegistryError",
    "BenchmarkScoreObservation",
    "BenchmarkSplit",
    "BenchmarkSplitRole",
    "ContaminationStatus",
    "ImprovementClaimDecision",
    "evaluate_improvement_claim",
    "qualify_benchmark",
]
