"""Strict external benchmark-corpus ingestion for Jeeves historical evidence.

External benchmark data enters Jeeves through a narrow normalized record
contract. Callers provide a trusted catalog of benchmark definitions; corpus
rows may reference those definitions but cannot redefine normalization bounds,
directions, or domains.

The adapter validates field sets, record counts, duplicate IDs, numeric bounds,
UTF-8/JSONL shape, provenance inputs, and then delegates every snapshot to the
historical registry so future-time, contradiction, duplicate, and history-limit
protections remain authoritative. Batch admission is staged against a clone of
the current registry before the real registry is mutated, preventing partial
imports when a later row violates a registry-level contract.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    canonical_fingerprint,
    make_benchmark_provenance,
)


MAX_CORPUS_RECORDS: Final = 100_000
MAX_CORPUS_BYTES: Final = 32 * 1024 * 1024
MAX_TEXT: Final = 1_024
_REQUIRED_FIELDS: Final = frozenset(
    {
        "record_id",
        "provider",
        "model",
        "revision",
        "benchmark",
        "raw_score",
        "sample_count",
        "measured_at",
        "clock_version",
    }
)
_OPTIONAL_FIELDS: Final = frozenset({"uri", "notes"})
_ALLOWED_FIELDS: Final = _REQUIRED_FIELDS | _OPTIONAL_FIELDS


class HistoricalCorpusError(ValueError):
    """Fail-closed external corpus contract violation."""


def _text(name: str, value: object, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalCorpusError(f"{name} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalCorpusError(f"{name} exceeds {maximum} characters")
    return cleaned


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalCorpusError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalCorpusError(f"{name} must be finite")
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalCorpusError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class CorpusImportPolicy:
    source_id: str
    source_kind: str = "benchmark_corpus"
    max_records: int = MAX_CORPUS_RECORDS
    require_uri: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id, 160))
        object.__setattr__(self, "source_kind", _text("source_kind", self.source_kind, 80))
        if isinstance(self.max_records, bool) or not isinstance(self.max_records, int) or self.max_records <= 0:
            raise HistoricalCorpusError("max_records must be a positive integer")
        if self.max_records > MAX_CORPUS_RECORDS:
            raise HistoricalCorpusError(f"max_records cannot exceed {MAX_CORPUS_RECORDS}")
        if not isinstance(self.require_uri, bool):
            raise HistoricalCorpusError("require_uri must be boolean")


@dataclass(frozen=True, slots=True)
class CorpusImportReport:
    record_count: int
    model_count: int
    benchmark_count: int
    models: tuple[ModelIdentity, ...]
    benchmark_keys: tuple[str, ...]
    record_ids: tuple[str, ...]
    evidence_fingerprint: str


class BenchmarkCatalog:
    """Trusted immutable benchmark-definition lookup."""

    def __init__(self, definitions: Iterable[BenchmarkDefinition]) -> None:
        items = tuple(definitions)
        if not items:
            raise HistoricalCorpusError("benchmark catalog must not be empty")
        if any(not isinstance(item, BenchmarkDefinition) for item in items):
            raise HistoricalCorpusError("catalog must contain BenchmarkDefinition values")
        by_key: dict[str, BenchmarkDefinition] = {}
        for item in items:
            if item.key in by_key:
                raise HistoricalCorpusError(f"duplicate benchmark definition: {item.key}")
            by_key[item.key] = item
        self._by_key = by_key

    def get(self, key: str) -> BenchmarkDefinition:
        key = _text("benchmark", key, 320)
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise HistoricalCorpusError(f"unknown benchmark definition: {key}") from exc

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_key))

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            [
                {
                    "key": item.key,
                    "domain": item.domain.value,
                    "raw_min": item.raw_min,
                    "raw_max": item.raw_max,
                    "direction": item.direction.value,
                    "weight_hint": item.weight_hint,
                }
                for item in sorted(self._by_key.values(), key=lambda value: value.key)
            ]
        )


class HistoricalCorpusAdapter:
    """Normalize validated external rows into provenance-bound snapshots."""

    def __init__(
        self,
        *,
        registry: HistoricalModelRegistry,
        catalog: BenchmarkCatalog,
        policy: CorpusImportPolicy,
    ) -> None:
        if not isinstance(registry, HistoricalModelRegistry):
            raise HistoricalCorpusError("registry must be HistoricalModelRegistry")
        if not isinstance(catalog, BenchmarkCatalog):
            raise HistoricalCorpusError("catalog must be BenchmarkCatalog")
        if not isinstance(policy, CorpusImportPolicy):
            raise HistoricalCorpusError("policy must be CorpusImportPolicy")
        self.registry = registry
        self.catalog = catalog
        self.policy = policy

    def import_rows(self, rows: Iterable[Mapping[str, object]]) -> CorpusImportReport:
        normalized = tuple(rows)
        if not normalized:
            raise HistoricalCorpusError("corpus rows must not be empty")
        if len(normalized) > self.policy.max_records:
            raise HistoricalCorpusError("corpus record limit exceeded")
        seen_ids: set[str] = set()
        snapshots: list[BenchmarkSnapshot] = []
        for index, row in enumerate(normalized, start=1):
            snapshots.append(self._row_to_snapshot(row, index=index, seen_ids=seen_ids))

        # Validate the full batch against a staged copy of current registry state
        # before mutating the authoritative registry. A late contradictory or
        # future snapshot therefore cannot leave an earlier row partially admitted.
        staging = HistoricalModelRegistry(
            clock=self.registry.clock,
            max_snapshots_per_benchmark=self.registry.max_snapshots_per_benchmark,
        )
        for existing in self.registry.snapshots():
            staging.ingest(existing)
        for snapshot in snapshots:
            staging.ingest(snapshot)

        for snapshot in snapshots:
            self.registry.ingest(snapshot)

        models = tuple(sorted({snapshot.model for snapshot in snapshots}))
        benchmark_keys = tuple(sorted({snapshot.benchmark.key for snapshot in snapshots}))
        record_ids = tuple(sorted(snapshot.snapshot_id for snapshot in snapshots))
        payload = {
            "source_id": self.policy.source_id,
            "source_kind": self.policy.source_kind,
            "catalog_fingerprint": self.catalog.fingerprint,
            "record_ids": record_ids,
            "snapshot_fingerprints": sorted(snapshot.provenance.fingerprint for snapshot in snapshots),
        }
        return CorpusImportReport(
            record_count=len(snapshots),
            model_count=len(models),
            benchmark_count=len(benchmark_keys),
            models=models,
            benchmark_keys=benchmark_keys,
            record_ids=record_ids,
            evidence_fingerprint=canonical_fingerprint(payload),
        )

    def import_jsonl(self, payload: str | bytes) -> CorpusImportReport:
        if isinstance(payload, bytes):
            if len(payload) > MAX_CORPUS_BYTES:
                raise HistoricalCorpusError("corpus payload exceeds byte limit")
            try:
                text = payload.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise HistoricalCorpusError("corpus payload must be valid UTF-8") from exc
        elif isinstance(payload, str):
            if len(payload.encode("utf-8")) > MAX_CORPUS_BYTES:
                raise HistoricalCorpusError("corpus payload exceeds byte limit")
            text = payload
        else:
            raise HistoricalCorpusError("JSONL payload must be str or bytes")

        rows: list[Mapping[str, object]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if len(rows) >= self.policy.max_records:
                raise HistoricalCorpusError("corpus record limit exceeded")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HistoricalCorpusError(f"invalid JSON on line {line_number}") from exc
            if not isinstance(value, dict):
                raise HistoricalCorpusError(f"JSONL line {line_number} must be an object")
            rows.append(value)
        return self.import_rows(rows)

    def _row_to_snapshot(
        self,
        row: Mapping[str, object],
        *,
        index: int,
        seen_ids: set[str],
    ) -> BenchmarkSnapshot:
        if not isinstance(row, Mapping):
            raise HistoricalCorpusError(f"row {index} must be a mapping")
        keys = frozenset(row.keys())
        missing = _REQUIRED_FIELDS - keys
        extra = keys - _ALLOWED_FIELDS
        if missing:
            raise HistoricalCorpusError(f"row {index} missing fields: {sorted(missing)}")
        if extra:
            raise HistoricalCorpusError(f"row {index} contains unknown fields: {sorted(extra)}")

        record_id = _text("record_id", row["record_id"], 160)
        if record_id in seen_ids:
            raise HistoricalCorpusError(f"duplicate record_id: {record_id}")
        seen_ids.add(record_id)
        benchmark = self.catalog.get(_text("benchmark", row["benchmark"], 320))
        model = ModelIdentity(
            provider=_text("provider", row["provider"], 160),
            model=_text("model", row["model"], 160),
            revision=_text("revision", row["revision"], 160),
        )
        raw_score = _finite("raw_score", row["raw_score"])
        benchmark.normalize(raw_score)
        sample_count = _positive_int("sample_count", row["sample_count"])
        measured_at = _finite("measured_at", row["measured_at"])
        if measured_at < 0.0:
            raise HistoricalCorpusError("measured_at must be non-negative")
        clock_version = _positive_int("clock_version", row["clock_version"])
        uri_value = row.get("uri")
        uri = None if uri_value is None else _text("uri", uri_value, MAX_TEXT)
        if self.policy.require_uri and uri is None:
            raise HistoricalCorpusError(f"row {index} requires uri")
        notes_value = row.get("notes", "")
        notes = "" if notes_value in (None, "") else _text("notes", notes_value, 2_048)
        provenance = make_benchmark_provenance(
            source_id=f"{self.policy.source_id}:{record_id}",
            source_kind=self.policy.source_kind,
            measured_at=measured_at,
            clock_version=clock_version,
            snapshot_id=record_id,
            model=model,
            benchmark=benchmark,
            raw_score=raw_score,
            sample_count=sample_count,
            uri=uri,
        )
        return BenchmarkSnapshot(
            snapshot_id=record_id,
            model=model,
            benchmark=benchmark,
            raw_score=raw_score,
            sample_count=sample_count,
            measured_at=measured_at,
            provenance=provenance,
            notes=notes,
        )


def summarize_import(report: CorpusImportReport) -> dict[str, object]:
    return {
        "record_count": report.record_count,
        "model_count": report.model_count,
        "benchmark_count": report.benchmark_count,
        "models": [model.key for model in report.models],
        "benchmark_keys": list(report.benchmark_keys),
        "record_ids": list(report.record_ids),
        "evidence_fingerprint": report.evidence_fingerprint,
    }