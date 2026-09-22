"""Strict durable manifests for Jeeves historical benchmark evidence.

Manifests provide a reproducible serialization format for historical benchmark
snapshots without loading arbitrary Python objects. The decoder is deliberately
small and fail-closed: schema version, keys, enum values, counts, JSON size,
provenance, fingerprints, and duplicate constraints are all revalidated before
records can enter a historical registry.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable, Final

from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelError,
    HistoricalModelRegistry,
    MetricDirection,
    ModelIdentity,
    canonical_fingerprint,
)
from skeleton.learning.evidence import EvidenceProvenance


MANIFEST_SCHEMA_VERSION: Final = 1
MAX_MANIFEST_BYTES: Final = 4 * 1024 * 1024
MAX_MANIFEST_SNAPSHOTS: Final = 10_000
MAX_TEXT_CHARS: Final = 2_048


class HistoricalManifestError(HistoricalModelError):
    code = "JVS.HISTORICAL_MANIFEST"
    http_status = 422


def _text(name: str, value: object, maximum: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalManifestError(
            f"{name} must be a non-empty string",
            context={"reason": "invalid_text", "field": name},
        )
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalManifestError(
            f"{name} is too long",
            context={"reason": "too_long", "field": name, "max_chars": maximum},
        )
    return cleaned


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalManifestError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalManifestError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalManifestError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_integer", "field": name},
        )
    return value


def _exact_keys(name: str, value: object, expected: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise HistoricalManifestError(
            f"{name} must be an object",
            context={"reason": "invalid_object", "field": name},
        )
    actual = set(value)
    if actual != expected:
        raise HistoricalManifestError(
            f"{name} has unexpected or missing keys",
            context={
                "reason": "schema_keys",
                "field": name,
                "missing": sorted(expected - actual),
                "unexpected": sorted(actual - expected),
            },
        )
    return value


@dataclass(frozen=True, slots=True)
class HistoricalBenchmarkManifest:
    dataset_id: str
    created_at: float
    snapshots: tuple[BenchmarkSnapshot, ...]
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id, 160))
        created_at = _finite("created_at", self.created_at)
        if created_at < 0.0:
            raise HistoricalManifestError(
                "created_at must be non-negative",
                context={"reason": "invalid_timestamp"},
            )
        object.__setattr__(self, "created_at", created_at)
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise HistoricalManifestError(
                "unsupported manifest schema version",
                context={"reason": "unsupported_schema", "schema_version": self.schema_version},
            )
        snapshots = tuple(self.snapshots)
        if len(snapshots) > MAX_MANIFEST_SNAPSHOTS:
            raise HistoricalManifestError(
                "manifest contains too many snapshots",
                context={"reason": "too_many_snapshots", "max_snapshots": MAX_MANIFEST_SNAPSHOTS},
            )
        if any(not isinstance(snapshot, BenchmarkSnapshot) for snapshot in snapshots):
            raise HistoricalManifestError(
                "snapshots must contain BenchmarkSnapshot values",
                context={"reason": "invalid_snapshot"},
            )
        ids = [snapshot.snapshot_id for snapshot in snapshots]
        if len(ids) != len(set(ids)):
            raise HistoricalManifestError(
                "manifest snapshot IDs must be unique",
                context={"reason": "duplicate_snapshot_id"},
            )
        object.__setattr__(
            self,
            "snapshots",
            tuple(sorted(snapshots, key=lambda item: (item.measured_at, item.snapshot_id))),
        )

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(self.to_payload(include_fingerprint=False))

    def to_payload(self, *, include_fingerprint: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "created_at": self.created_at,
            "snapshots": [_snapshot_to_payload(snapshot) for snapshot in self.snapshots],
        }
        if include_fingerprint:
            payload["manifest_fingerprint"] = canonical_fingerprint(payload)
        return payload


def _snapshot_to_payload(snapshot: BenchmarkSnapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "model": {
            "provider": snapshot.model.provider,
            "model": snapshot.model.model,
            "revision": snapshot.model.revision,
        },
        "benchmark": {
            "benchmark_id": snapshot.benchmark.benchmark_id,
            "revision": snapshot.benchmark.revision,
            "domain": snapshot.benchmark.domain.value,
            "raw_min": snapshot.benchmark.raw_min,
            "raw_max": snapshot.benchmark.raw_max,
            "direction": snapshot.benchmark.direction.value,
            "weight_hint": snapshot.benchmark.weight_hint,
        },
        "raw_score": snapshot.raw_score,
        "sample_count": snapshot.sample_count,
        "measured_at": snapshot.measured_at,
        "provenance": {
            "source_id": snapshot.provenance.source_id,
            "source_kind": snapshot.provenance.source_kind,
            "observed_at": snapshot.provenance.observed_at,
            "clock_version": snapshot.provenance.clock_version,
            "fingerprint": snapshot.provenance.fingerprint,
            "parent_ids": list(snapshot.provenance.parent_ids),
            "uri": snapshot.provenance.uri,
        },
        "notes": snapshot.notes,
    }


def dumps_manifest(manifest: HistoricalBenchmarkManifest) -> str:
    if not isinstance(manifest, HistoricalBenchmarkManifest):
        raise HistoricalManifestError(
            "manifest must be HistoricalBenchmarkManifest",
            context={"reason": "invalid_manifest"},
        )
    encoded = json.dumps(
        manifest.to_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise HistoricalManifestError(
            "manifest exceeds serialized size limit",
            context={"reason": "manifest_too_large", "max_bytes": MAX_MANIFEST_BYTES},
        )
    return encoded


def loads_manifest(raw: str | bytes) -> HistoricalBenchmarkManifest:
    if isinstance(raw, bytes):
        if len(raw) > MAX_MANIFEST_BYTES:
            raise HistoricalManifestError(
                "manifest exceeds serialized size limit",
                context={"reason": "manifest_too_large", "max_bytes": MAX_MANIFEST_BYTES},
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HistoricalManifestError(
                "manifest must be UTF-8 JSON",
                context={"reason": "invalid_encoding"},
                cause=exc,
            ) from exc
    elif isinstance(raw, str):
        text = raw
        if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise HistoricalManifestError(
                "manifest exceeds serialized size limit",
                context={"reason": "manifest_too_large", "max_bytes": MAX_MANIFEST_BYTES},
            )
    else:
        raise HistoricalManifestError(
            "manifest input must be str or bytes",
            context={"reason": "invalid_manifest_input"},
        )

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HistoricalManifestError(
            "manifest is not valid JSON",
            context={"reason": "invalid_json"},
            cause=exc,
        ) from exc

    root = _exact_keys(
        "manifest",
        decoded,
        {"schema_version", "dataset_id", "created_at", "snapshots", "manifest_fingerprint"},
    )
    schema_version = _positive_int("schema_version", root["schema_version"])
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise HistoricalManifestError(
            "unsupported manifest schema version",
            context={"reason": "unsupported_schema", "schema_version": schema_version},
        )
    snapshots_raw = root["snapshots"]
    if not isinstance(snapshots_raw, list):
        raise HistoricalManifestError(
            "snapshots must be an array",
            context={"reason": "invalid_snapshots"},
        )
    if len(snapshots_raw) > MAX_MANIFEST_SNAPSHOTS:
        raise HistoricalManifestError(
            "manifest contains too many snapshots",
            context={"reason": "too_many_snapshots", "max_snapshots": MAX_MANIFEST_SNAPSHOTS},
        )

    expected_fingerprint = _text("manifest_fingerprint", root["manifest_fingerprint"], 128)
    unsigned = {
        "schema_version": root["schema_version"],
        "dataset_id": root["dataset_id"],
        "created_at": root["created_at"],
        "snapshots": snapshots_raw,
    }
    if canonical_fingerprint(unsigned) != expected_fingerprint:
        raise HistoricalManifestError(
            "manifest fingerprint does not match content",
            context={"reason": "manifest_fingerprint_mismatch"},
        )

    snapshots = tuple(_snapshot_from_payload(item, index=index) for index, item in enumerate(snapshots_raw))
    manifest = HistoricalBenchmarkManifest(
        dataset_id=_text("dataset_id", root["dataset_id"], 160),
        created_at=_finite("created_at", root["created_at"]),
        snapshots=snapshots,
        schema_version=schema_version,
    )
    if manifest.fingerprint != expected_fingerprint:
        raise HistoricalManifestError(
            "decoded manifest canonical form differs from fingerprinted content",
            context={"reason": "noncanonical_manifest"},
        )
    return manifest


def _snapshot_from_payload(value: object, *, index: int) -> BenchmarkSnapshot:
    prefix = f"snapshots[{index}]"
    obj = _exact_keys(
        prefix,
        value,
        {"snapshot_id", "model", "benchmark", "raw_score", "sample_count", "measured_at", "provenance", "notes"},
    )
    model_obj = _exact_keys(f"{prefix}.model", obj["model"], {"provider", "model", "revision"})
    benchmark_obj = _exact_keys(
        f"{prefix}.benchmark",
        obj["benchmark"],
        {"benchmark_id", "revision", "domain", "raw_min", "raw_max", "direction", "weight_hint"},
    )
    provenance_obj = _exact_keys(
        f"{prefix}.provenance",
        obj["provenance"],
        {"source_id", "source_kind", "observed_at", "clock_version", "fingerprint", "parent_ids", "uri"},
    )
    try:
        domain = BenchmarkDomain(_text(f"{prefix}.benchmark.domain", benchmark_obj["domain"], 64))
        direction = MetricDirection(_text(f"{prefix}.benchmark.direction", benchmark_obj["direction"], 64))
    except ValueError as exc:
        raise HistoricalManifestError(
            "manifest contains an unknown benchmark enum value",
            context={"reason": "invalid_enum", "index": index},
            cause=exc,
        ) from exc

    parents = provenance_obj["parent_ids"]
    if not isinstance(parents, list) or any(not isinstance(item, str) for item in parents):
        raise HistoricalManifestError(
            "provenance parent_ids must be an array of strings",
            context={"reason": "invalid_parent_ids", "index": index},
        )
    uri_value = provenance_obj["uri"]
    if uri_value is not None and not isinstance(uri_value, str):
        raise HistoricalManifestError(
            "provenance uri must be null or string",
            context={"reason": "invalid_uri", "index": index},
        )
    notes_value = obj["notes"]
    if not isinstance(notes_value, str):
        raise HistoricalManifestError(
            "notes must be a string",
            context={"reason": "invalid_notes", "index": index},
        )

    model = ModelIdentity(
        provider=_text(f"{prefix}.model.provider", model_obj["provider"], 160),
        model=_text(f"{prefix}.model.model", model_obj["model"], 160),
        revision=_text(f"{prefix}.model.revision", model_obj["revision"], 160),
    )
    benchmark = BenchmarkDefinition(
        benchmark_id=_text(f"{prefix}.benchmark.benchmark_id", benchmark_obj["benchmark_id"], 160),
        revision=_text(f"{prefix}.benchmark.revision", benchmark_obj["revision"], 160),
        domain=domain,
        raw_min=_finite(f"{prefix}.benchmark.raw_min", benchmark_obj["raw_min"]),
        raw_max=_finite(f"{prefix}.benchmark.raw_max", benchmark_obj["raw_max"]),
        direction=direction,
        weight_hint=_finite(f"{prefix}.benchmark.weight_hint", benchmark_obj["weight_hint"]),
    )
    provenance = EvidenceProvenance(
        source_id=_text(f"{prefix}.provenance.source_id", provenance_obj["source_id"], 256),
        source_kind=_text(f"{prefix}.provenance.source_kind", provenance_obj["source_kind"], 128),
        observed_at=_finite(f"{prefix}.provenance.observed_at", provenance_obj["observed_at"]),
        clock_version=_positive_int(f"{prefix}.provenance.clock_version", provenance_obj["clock_version"]),
        fingerprint=_text(f"{prefix}.provenance.fingerprint", provenance_obj["fingerprint"], 128),
        parent_ids=tuple(parents),
        uri=uri_value,
    )
    return BenchmarkSnapshot(
        snapshot_id=_text(f"{prefix}.snapshot_id", obj["snapshot_id"], 160),
        model=model,
        benchmark=benchmark,
        raw_score=_finite(f"{prefix}.raw_score", obj["raw_score"]),
        sample_count=_positive_int(f"{prefix}.sample_count", obj["sample_count"]),
        measured_at=_finite(f"{prefix}.measured_at", obj["measured_at"]),
        provenance=provenance,
        notes=notes_value,
    )


def manifest_from_registry(
    registry: HistoricalModelRegistry,
    *,
    dataset_id: str,
    created_at: float,
) -> HistoricalBenchmarkManifest:
    if not isinstance(registry, HistoricalModelRegistry):
        raise HistoricalManifestError(
            "registry must be HistoricalModelRegistry",
            context={"reason": "invalid_registry"},
        )
    return HistoricalBenchmarkManifest(
        dataset_id=dataset_id,
        created_at=created_at,
        snapshots=registry.snapshots(),
    )


def registry_from_manifest(
    manifest: HistoricalBenchmarkManifest,
    *,
    clock: Callable[[], float],
    max_snapshots_per_benchmark: int = 32,
) -> HistoricalModelRegistry:
    if not isinstance(manifest, HistoricalBenchmarkManifest):
        raise HistoricalManifestError(
            "manifest must be HistoricalBenchmarkManifest",
            context={"reason": "invalid_manifest"},
        )
    registry = HistoricalModelRegistry(
        clock=clock,
        max_snapshots_per_benchmark=max_snapshots_per_benchmark,
    )
    for snapshot in manifest.snapshots:
        registry.ingest(snapshot)
    return registry