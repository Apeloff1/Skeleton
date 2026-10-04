"""Governed, content-addressed data plane for native model training.

The training plane must not accept anonymous bytes.  Every dataset version is
immutable, content-addressed, rights/classification-aware, quality-gated and
lineage-linked before it can become a training input.

This module deliberately has no network dependency.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_MAX_IDENTITY_BYTES = 16 * 1024 * 1024


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_digest(value: str, *, field: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


def _utc(value: datetime | None = None) -> str:
    instant = value or datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return instant.astimezone(UTC).isoformat()


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _references(values: Sequence[str], *, field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field} must be an ordered reference sequence")
    if len(values) > 65536:
        raise ValueError(f"{field} exceeds reference count bound")
    refs = tuple(_text(values[index], field=field) for index in range(len(values)))
    if any(len(reference) > 4096 for reference in refs):
        raise ValueError(f"{field} exceeds text bound")
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field} must be unique")
    return refs


def _documents(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("documents must be an ordered text sequence")
    count = len(values)
    if not 1 <= count <= 4096:
        raise ValueError("document count must be in [1, 4096]")
    result = tuple(values[index] for index in range(count))
    if any(not isinstance(value, str) or len(value) > 1024 * 1024 for value in result):
        raise ValueError("document type/character bound exceeded")
    if any(not value.strip() for value in result):
        raise ValueError("documents must contain non-empty text")
    sizes = [len(value.encode("utf-8")) for value in result]
    if any(size > 1024 * 1024 for size in sizes) or sum(sizes) > 64 * 1024 * 1024:
        raise ValueError("documents exceed configured materialization byte bounds")
    return result


def _bounded_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    remaining = 250_000

    def visit(node: object, depth: int = 0) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 32:
            raise ValueError("source evidence exceeds structural bounds")
        if isinstance(node, str):
            if len(node) > 1024 * 1024:
                raise ValueError("source evidence string exceeds bound")
        elif isinstance(node, Mapping):
            if len(node) > 4096:
                raise ValueError("source evidence mapping exceeds bound")
            for key, child in node.items():
                if not isinstance(key, str):
                    raise TypeError("source evidence keys must be text")
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(node, (list, tuple)):
            if len(node) > 4096:
                raise ValueError("source evidence sequence exceeds bound")
            for child in node:
                visit(child, depth + 1)
        elif node is not None and not isinstance(node, (int, float, bool)):
            raise ValueError("source evidence must be deterministic JSON")

    visit(value)
    encoded = _canonical(dict(value))
    if len(encoded.encode("utf-8")) > _MAX_EVIDENCE_BYTES:
        raise ValueError("source evidence exceeds encoded byte bound")
    return json.loads(encoded)


def document_sequence_digest(documents: Sequence[str]) -> str:
    """Exact sequence identity, including document boundaries and order."""
    return _sha256(list(_documents(documents)))


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    name: str
    digest: str
    record_count: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("dataset split name must be non-empty")
        object.__setattr__(self, "digest", _require_digest(self.digest, field="split digest"))
        if (
            isinstance(self.record_count, bool)
            or not isinstance(self.record_count, int)
            or self.record_count < 0
        ):
            raise ValueError("record_count must be a non-negative integer")

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name.strip(),
            "digest": self.digest,
            "record_count": self.record_count,
        }


@dataclass(frozen=True, slots=True)
class IngestEnvelope:
    source_id: str
    content_digest: str
    acquired_at: str
    parser_version: str
    classification: str
    rights: tuple[str, ...]
    trusted: bool
    quarantine_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.parser_version.strip():
            raise ValueError("source_id and parser_version must be non-empty")
        object.__setattr__(
            self, "content_digest", _require_digest(self.content_digest, field="content_digest")
        )
        if self.classification not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("unsupported classification")
        rights = tuple(dict.fromkeys(item.strip() for item in self.rights if item.strip()))
        if not rights:
            raise ValueError("ingest rights must be explicit")
        object.__setattr__(self, "rights", rights)
        if not isinstance(self.trusted, bool):
            raise TypeError("trusted must be boolean")
        if self.trusted and self.quarantine_reason:
            raise ValueError("trusted ingest may not carry quarantine_reason")
        if not self.trusted and not (self.quarantine_reason and self.quarantine_reason.strip()):
            raise ValueError("untrusted ingest requires quarantine_reason")

    @classmethod
    def from_bytes(
        cls,
        *,
        source_id: str,
        payload: bytes,
        parser_version: str,
        classification: str,
        rights: Sequence[str],
        trusted: bool,
        quarantine_reason: str | None = None,
        acquired_at: datetime | None = None,
    ) -> IngestEnvelope:
        return cls(
            source_id=source_id,
            content_digest=hashlib.sha256(payload).hexdigest(),
            acquired_at=_utc(acquired_at),
            parser_version=parser_version,
            classification=classification,
            rights=tuple(rights),
            trusted=trusted,
            quarantine_reason=quarantine_reason,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "content_digest": self.content_digest,
            "acquired_at": self.acquired_at,
            "parser_version": self.parser_version,
            "classification": self.classification,
            "rights": list(self.rights),
            "trusted": self.trusted,
            "quarantine_reason": self.quarantine_reason,
        }


@dataclass(frozen=True, slots=True)
class SyntheticDataReceipt:
    generator_id: str
    generator_config_digest: str
    source_dataset_digests: tuple[str, ...]
    seed: int
    generated_record_count: int

    def __post_init__(self) -> None:
        if not self.generator_id.strip():
            raise ValueError("generator_id must be non-empty")
        object.__setattr__(
            self,
            "generator_config_digest",
            _require_digest(self.generator_config_digest, field="generator_config_digest"),
        )
        object.__setattr__(
            self,
            "source_dataset_digests",
            tuple(
                _require_digest(item, field="source_dataset_digest") for item in self.source_dataset_digests
            ),
        )
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")  # noqa: TRY004 - legacy constructor contract
        if (
            isinstance(self.generated_record_count, bool)
            or not isinstance(self.generated_record_count, int)
            or self.generated_record_count < 0
        ):
            raise ValueError("generated_record_count must be non-negative")

    @property
    def digest(self) -> str:
        return _sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "generator_id": self.generator_id,
            "generator_config_digest": self.generator_config_digest,
            "source_dataset_digests": list(self.source_dataset_digests),
            "seed": self.seed,
            "generated_record_count": self.generated_record_count,
        }


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    version: str
    splits: tuple[DatasetSplit, ...]
    source_ingest_digests: tuple[str, ...]
    classification: str
    permitted_uses: tuple[str, ...]
    retention_class: str
    parser_versions: tuple[str, ...]
    synthetic_receipt: SyntheticDataReceipt | None = None
    pii_present: bool = False
    contamination_labels: tuple[str, ...] = ()
    materialization_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.dataset_id.strip() or not self.version.strip():
            raise ValueError("dataset_id and version must be non-empty")
        if self.classification not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("unsupported dataset classification")
        if not self.retention_class.strip():
            raise ValueError("retention_class must be explicit")
        if not self.splits:
            raise ValueError("dataset requires at least one split")
        names = [item.name for item in self.splits]
        if len(names) != len(set(names)):
            raise ValueError("dataset split names must be unique")
        ingest = tuple(
            _require_digest(item, field="source_ingest_digest") for item in self.source_ingest_digests
        )
        if not ingest:
            raise ValueError("dataset requires source ingest identity")
        object.__setattr__(self, "source_ingest_digests", ingest)
        uses = tuple(dict.fromkeys(item.strip().lower() for item in self.permitted_uses if item.strip()))
        if not uses:
            raise ValueError("dataset permitted_uses must be explicit")
        object.__setattr__(self, "permitted_uses", uses)
        parsers = tuple(dict.fromkeys(item.strip() for item in self.parser_versions if item.strip()))
        if not parsers:
            raise ValueError("dataset parser_versions must be explicit")
        object.__setattr__(self, "parser_versions", parsers)
        labels = tuple(
            dict.fromkeys(item.strip().lower() for item in self.contamination_labels if item.strip())
        )
        object.__setattr__(self, "contamination_labels", labels)
        if self.materialization_digest is not None:
            object.__setattr__(
                self,
                "materialization_digest",
                _require_digest(self.materialization_digest, field="materialization_digest"),
            )

    @property
    def digest(self) -> str:
        return _sha256(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "splits": [item.as_dict() for item in self.splits],
            "source_ingest_digests": list(self.source_ingest_digests),
            "classification": self.classification,
            "permitted_uses": list(self.permitted_uses),
            "retention_class": self.retention_class,
            "parser_versions": list(self.parser_versions),
            "synthetic_receipt": None if self.synthetic_receipt is None else self.synthetic_receipt.as_dict(),
            "pii_present": self.pii_present,
            "contamination_labels": list(self.contamination_labels),
        }
        if include_digest:
            payload["dataset_digest"] = self.digest
        if self.materialization_digest is not None:
            payload["materialization_digest"] = self.materialization_digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DatasetManifest:
        synthetic = payload.get("synthetic_receipt")
        receipt = None
        if isinstance(synthetic, Mapping):
            receipt = SyntheticDataReceipt(
                generator_id=str(synthetic["generator_id"]),
                generator_config_digest=str(synthetic["generator_config_digest"]),
                source_dataset_digests=tuple(map(str, synthetic.get("source_dataset_digests", []))),
                seed=int(synthetic["seed"]),
                generated_record_count=int(synthetic["generated_record_count"]),
            )
        manifest = cls(
            dataset_id=str(payload["dataset_id"]),
            version=str(payload["version"]),
            splits=tuple(
                DatasetSplit(
                    name=str(item["name"]),
                    digest=str(item["digest"]),
                    record_count=int(item["record_count"]),
                )
                for item in payload.get("splits", [])
            ),
            source_ingest_digests=tuple(map(str, payload.get("source_ingest_digests", []))),
            classification=str(payload["classification"]),
            permitted_uses=tuple(map(str, payload.get("permitted_uses", []))),
            retention_class=str(payload["retention_class"]),
            parser_versions=tuple(map(str, payload.get("parser_versions", []))),
            synthetic_receipt=receipt,
            pii_present=bool(payload.get("pii_present", False)),
            contamination_labels=tuple(map(str, payload.get("contamination_labels", []))),
            materialization_digest=payload.get("materialization_digest"),
        )
        claimed = payload.get("dataset_digest")
        if claimed is not None and str(claimed) != manifest.digest:
            raise ValueError("dataset digest mismatch")
        return manifest


@dataclass(frozen=True, slots=True)
class LineageReceipt:
    transform_id: str
    input_digests: tuple[str, ...]
    output_digest: str
    environment_digest: str
    code_digest: str
    created_at: str

    def __post_init__(self) -> None:
        if not self.transform_id.strip():
            raise ValueError("transform_id must be non-empty")
        object.__setattr__(
            self, "input_digests", tuple(_require_digest(x, field="input_digest") for x in self.input_digests)
        )
        if not self.input_digests:
            raise ValueError("lineage requires at least one input")
        object.__setattr__(self, "output_digest", _require_digest(self.output_digest, field="output_digest"))
        object.__setattr__(
            self, "environment_digest", _require_digest(self.environment_digest, field="environment_digest")
        )
        object.__setattr__(self, "code_digest", _require_digest(self.code_digest, field="code_digest"))

    @property
    def digest(self) -> str:
        return _sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "transform_id": self.transform_id,
            "input_digests": list(self.input_digests),
            "output_digest": self.output_digest,
            "environment_digest": self.environment_digest,
            "code_digest": self.code_digest,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class DataQualityRule:
    rule_id: str
    metric: str
    operator: str
    threshold: float
    critical: bool = True

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.metric.strip():
            raise ValueError("quality rule identifiers must be non-empty")
        if self.operator not in {"<", "<=", "==", ">=", ">"}:
            raise ValueError("unsupported quality operator")
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)):
            raise TypeError("quality threshold must be numeric")
        if not math.isfinite(float(self.threshold)):
            raise ValueError("quality threshold must be finite")
        if not isinstance(self.critical, bool):
            raise ValueError("quality rule critical flag must be boolean")  # noqa: TRY004 - legacy contract

    def evaluate(self, metrics: Mapping[str, float]) -> bool:
        if self.metric not in metrics:
            return False
        value = float(metrics[self.metric])
        target = float(self.threshold)
        return {
            "<": value < target,
            "<=": value <= target,
            "==": value == target,
            ">=": value >= target,
            ">": value > target,
        }[self.operator]

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
            "critical": self.critical,
        }


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    dataset_digest: str
    rules: tuple[DataQualityRule, ...]
    metrics: Mapping[str, float]
    passed_rule_ids: tuple[str, ...]
    failed_rule_ids: tuple[str, ...]
    observation_digest: str | None = None
    split_sequence_digests: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dataset_digest", _require_digest(self.dataset_digest, field="dataset_digest")
        )
        rules = tuple(self.rules)
        if not rules:
            raise ValueError("quality report requires at least one rule")
        rule_ids = [rule.rule_id for rule in rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("quality rule ids must be unique")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in self.metrics.values()):
            raise ValueError("quality metrics must be numeric")
        values = {str(k): float(v) for k, v in self.metrics.items()}
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("quality metrics must be finite")

        expected_passed = []
        expected_failed = []
        for rule in rules:
            (expected_passed if rule.evaluate(values) else expected_failed).append(rule.rule_id)

        passed = tuple(self.passed_rule_ids)
        failed = tuple(self.failed_rule_ids)
        if passed != tuple(expected_passed) or failed != tuple(expected_failed):
            raise ValueError("quality report outcome does not match rules and metrics")

        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "metrics", values)
        object.__setattr__(self, "passed_rule_ids", passed)
        object.__setattr__(self, "failed_rule_ids", failed)
        if self.observation_digest is not None:
            object.__setattr__(
                self,
                "observation_digest",
                _require_digest(self.observation_digest, field="observation_digest"),
            )
        object.__setattr__(
            self,
            "split_sequence_digests",
            {
                str(name): _require_digest(value, field="split_sequence_digest")
                for name, value in self.split_sequence_digests.items()
            },
        )

    @classmethod
    def evaluate(
        cls,
        dataset_digest: str,
        rules: Sequence[DataQualityRule],
        metrics: Mapping[str, float],
        *,
        observation_digest: str | None = None,
        split_sequence_digests: Mapping[str, str] | None = None,
    ) -> DataQualityReport:
        passed = []
        failed = []
        for rule in rules:
            (passed if rule.evaluate(metrics) else failed).append(rule.rule_id)
        return cls(
            dataset_digest=dataset_digest,
            rules=tuple(rules),
            metrics=metrics,
            passed_rule_ids=tuple(passed),
            failed_rule_ids=tuple(failed),
            observation_digest=observation_digest,
            split_sequence_digests=split_sequence_digests or {},
        )

    @property
    def critical_failures(self) -> tuple[str, ...]:
        critical = {rule.rule_id for rule in self.rules if rule.critical}
        return tuple(item for item in self.failed_rule_ids if item in critical)

    @property
    def passed(self) -> bool:
        return not self.critical_failures

    @property
    def digest(self) -> str:
        return _sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        payload = {
            "dataset_digest": self.dataset_digest,
            "rules": [item.as_dict() for item in self.rules],
            "metrics": dict(sorted(self.metrics.items())),
            "passed_rule_ids": list(self.passed_rule_ids),
            "failed_rule_ids": list(self.failed_rule_ids),
            "critical_failures": list(self.critical_failures),
            "passed": self.passed,
        }
        if self.observation_digest is not None:
            payload["observation_digest"] = self.observation_digest
            payload["split_sequence_digests"] = dict(self.split_sequence_digests)
        return payload


@dataclass(frozen=True, slots=True)
class MaterializedTrainingSource:
    """Real immutable source bytes with an explicit deterministic text parser."""

    envelope: IngestEnvelope
    payload: bytes
    format: str
    rights_refs: tuple[str, ...]
    lineage_refs: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, IngestEnvelope):
            raise TypeError("envelope must be IngestEnvelope")
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be immutable bytes")
        if len(self.payload) > _MAX_SOURCE_BYTES:
            raise ValueError("materialized source exceeds raw byte bound")
        if hashlib.sha256(self.payload).hexdigest() != self.envelope.content_digest:
            raise ValueError("materialized source bytes do not match ingest content digest")
        if not self.envelope.trusted or self.envelope.quarantine_reason:
            raise PermissionError("materialized source remains quarantined")
        if self.format not in {"utf8_text", "json_documents", "multimodal_projection"}:
            raise ValueError("unsupported materialized source format")
        refs = _references(self.rights_refs, field="rights_ref")
        if not refs:
            raise ValueError("materialized source requires rights references")
        object.__setattr__(self, "rights_refs", refs)
        object.__setattr__(self, "lineage_refs", _references(self.lineage_refs, field="lineage_ref"))
        object.__setattr__(self, "evidence", _bounded_evidence(self.evidence))
        self.documents()

    def documents(self) -> tuple[str, ...]:
        if len(self.payload) > _MAX_SOURCE_BYTES:
            raise ValueError("materialized source exceeds raw byte bound")
        if hashlib.sha256(self.payload).hexdigest() != self.envelope.content_digest:
            raise ValueError("materialized source content integrity failure")
        try:
            text = self.payload.decode("utf-8")
            parsed = (text,) if self.format == "utf8_text" else json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("materialized source is not valid UTF-8 text/documents") from exc
        if self.format == "json_documents" and not isinstance(parsed, list):
            raise ValueError("json_documents source must be a JSON string array")
        if self.format == "multimodal_projection":
            if not isinstance(parsed, dict) or set(parsed) != {"manifest", "documents"}:
                raise ValueError("multimodal projection source envelope is invalid")
            export = _projection_manifest(parsed["manifest"])
            export.validate_documents(parsed["documents"])
            rights = tuple(dict.fromkeys(ref for sample in export.samples for ref in sample.rights_refs))
            lineage = tuple(
                dict.fromkeys(
                    (
                        export.digest,
                        *(
                            ref
                            for sample in export.samples
                            for ref in (
                                *sample.lineage_refs,
                                sample.record_digest,
                                sample.asset_digest,
                                sample.projection_digest,
                            )
                        ),
                    )
                )
            )
            if (
                self.envelope.source_id != "multimodal-export:" + export.digest
                or self.envelope.parser_version != "multimodal-text-projection@1"
                or self.envelope.rights != (export.purpose,)
                or self.rights_refs != rights
                or self.lineage_refs != lineage
                or self.evidence.get("multimodal_manifest") != parsed["manifest"]
                or self.evidence.get("multimodal_manifest_digest") != export.digest
            ):
                raise ValueError("multimodal materialized source provenance mismatch")
            parsed = parsed["documents"]
        return _documents(parsed)

    def as_dict(self) -> dict[str, object]:
        return {
            "envelope": self.envelope.as_dict(),
            "format": self.format,
            "rights_refs": list(self.rights_refs),
            "lineage_refs": list(self.lineage_refs),
            "evidence": dict(self.evidence),
            "document_sequence_digest": document_sequence_digest(self.documents()),
        }


@dataclass(frozen=True, slots=True)
class MaterializedDatasetReceipt:
    manifest: DatasetManifest
    ingestion_id: str
    request_digest: str
    observation_digest: str
    quality_report_digest: str

    @property
    def dataset_digest(self) -> str:
        return self.manifest.digest

    @property
    def digest(self) -> str:
        return _sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_digest": self.dataset_digest,
            "ingestion_id": self.ingestion_id,
            "request_digest": self.request_digest,
            "observation_digest": self.observation_digest,
            "quality_report_digest": self.quality_report_digest,
        }


def _observations(corpora: Mapping[str, tuple[str, ...]]) -> dict[str, object]:
    metrics: dict[str, float] = {}
    splits: dict[str, object] = {}
    all_documents: list[str] = []
    for name, documents in corpora.items():
        checked = _documents(documents)
        sizes = [len(document.encode("utf-8")) for document in checked]
        unique = len(set(checked))
        local = {
            "record_count": float(len(checked)),
            "text_bytes": float(sum(sizes)),
            "valid_fraction": 1.0,
            "duplicate_fraction": (len(checked) - unique) / len(checked),
        }
        metrics.update({f"{name}.{key}": value for key, value in local.items()})
        splits[name] = {
            "document_sequence_digest": document_sequence_digest(checked),
            "legacy_split_digest": hashlib.sha256("\n".join(checked).encode("utf-8")).hexdigest(),
            "record_count": len(checked),
            "document_digests": [
                hashlib.sha256(document.encode("utf-8")).hexdigest() for document in checked
            ],
            "total_bytes": sum(sizes),
        }
        all_documents.extend(checked)
    checked_all = _documents(all_documents)
    metrics.update(
        {
            "record_count": float(len(checked_all)),
            "text_bytes": float(sum(len(document.encode("utf-8")) for document in checked_all)),
            "valid_fraction": 1.0,
            "duplicate_fraction": (len(checked_all) - len(set(checked_all))) / len(checked_all),
        }
    )
    return {"schema_version": "training_observations.v1", "splits": splits, "metrics": metrics}


def _baseline_rules(permitted_uses: Sequence[str]) -> tuple[DataQualityRule, ...]:
    rules = [
        DataQualityRule("observed.nonempty", "valid_fraction", "==", 1.0),
        DataQualityRule("observed.records", "record_count", ">=", 1.0),
    ]
    if "training" in permitted_uses:
        rules.append(DataQualityRule("observed.training_split", "train.record_count", ">=", 1.0))
    return tuple(rules)


def _projection_manifest(payload: Mapping[str, Any]):
    # Lazy loading avoids the learning_foundation/training package initializer
    # cycle and leaves multimodal original-asset ownership with its corpus.
    from skeleton.ai.runtime.learning_foundation.multimodal import (
        LearningModality,
        MultimodalTrainingManifest,
        MultimodalTrainingSample,
    )

    if payload.get("schema_version") != "skeleton.ai.multimodal_training_projection.v1":
        raise ValueError("unsupported multimodal projection schema")
    samples = tuple(
        MultimodalTrainingSample(
            **{
                **sample,
                "modality": LearningModality(sample["modality"]),
                "source_refs": tuple(sample["source_refs"]),
                "rights_refs": tuple(sample["rights_refs"]),
                "lineage_refs": tuple(sample["lineage_refs"]),
            }
        )
        for sample in payload["samples"]
    )
    return MultimodalTrainingManifest(
        **{key: value for key, value in payload.items() if key not in {"schema_version", "samples"}},
        samples=samples,
    )


_CLASSIFICATION_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


class DatasetRegistry:
    """SQLite-backed immutable dataset/lineage/quality authority."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS dataset_manifest (
                dataset_digest TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                version TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                UNIQUE(dataset_id, version)
            );
            CREATE TABLE IF NOT EXISTS ingest_envelope (
                content_digest TEXT PRIMARY KEY,
                envelope_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lineage_receipt (
                receipt_digest TEXT PRIMARY KEY,
                output_digest TEXT NOT NULL,
                receipt_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quality_report (
                report_digest TEXT PRIMARY KEY,
                dataset_digest TEXT NOT NULL,
                report_json TEXT NOT NULL,
                passed INTEGER NOT NULL,
                FOREIGN KEY(dataset_digest) REFERENCES dataset_manifest(dataset_digest)
            );
            CREATE TABLE IF NOT EXISTS materialized_source (
                content_digest TEXT PRIMARY KEY,
                source_json TEXT NOT NULL,
                payload BLOB NOT NULL,
                FOREIGN KEY(content_digest) REFERENCES ingest_envelope(content_digest)
            );
            CREATE TABLE IF NOT EXISTS materialized_dataset (
                dataset_digest TEXT PRIMARY KEY,
                materialization_json TEXT NOT NULL,
                observation_digest TEXT NOT NULL,
                observation_json TEXT NOT NULL,
                FOREIGN KEY(dataset_digest) REFERENCES dataset_manifest(dataset_digest)
            );
            CREATE TABLE IF NOT EXISTS materialized_document (
                dataset_digest TEXT NOT NULL,
                split_name TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                source_content_digest TEXT NOT NULL,
                source_ordinal INTEGER NOT NULL,
                document_digest TEXT NOT NULL,
                document_bytes BLOB NOT NULL,
                PRIMARY KEY(dataset_digest, split_name, ordinal),
                FOREIGN KEY(dataset_digest) REFERENCES dataset_manifest(dataset_digest),
                FOREIGN KEY(source_content_digest) REFERENCES ingest_envelope(content_digest)
            );
            CREATE TABLE IF NOT EXISTS materialized_ingestion (
                ingestion_id TEXT PRIMARY KEY,
                request_digest TEXT NOT NULL,
                dataset_digest TEXT NOT NULL,
                receipt_digest TEXT NOT NULL,
                receipt_json TEXT NOT NULL,
                FOREIGN KEY(dataset_digest) REFERENCES dataset_manifest(dataset_digest)
            );
            CREATE TABLE IF NOT EXISTS dataset_authority (
                dataset_digest TEXT PRIMARY KEY,
                epoch INTEGER NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(dataset_digest) REFERENCES dataset_manifest(dataset_digest)
            );
            CREATE TABLE IF NOT EXISTS source_authority (
                content_digest TEXT PRIMARY KEY,
                metadata_digest TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                status TEXT NOT NULL,
                revoked_uses_json TEXT NOT NULL,
                FOREIGN KEY(content_digest) REFERENCES ingest_envelope(content_digest)
            );
            CREATE TABLE IF NOT EXISTS dataset_authority_event (
                command_id TEXT PRIMARY KEY,
                resource_kind TEXT NOT NULL,
                resource_digest TEXT NOT NULL,
                new_epoch INTEGER NOT NULL,
                request_json TEXT NOT NULL,
                event_json TEXT NOT NULL,
                event_digest TEXT NOT NULL,
                UNIQUE(resource_kind, resource_digest, new_epoch)
            );
            """)
        self._db.execute(
            "INSERT OR IGNORE INTO dataset_authority SELECT dataset_digest, 0, 'active' FROM dataset_manifest"
        )
        for digest, encoded in self._db.execute(
            "SELECT content_digest,envelope_json FROM ingest_envelope"
        ).fetchall():
            self._db.execute(
                "INSERT OR IGNORE INTO source_authority VALUES (?, ?, 0, 'active', '[]')",
                (digest, _sha256(json.loads(encoded))),
            )
        self._db.commit()

    def register_ingest(self, envelope: IngestEnvelope) -> None:
        if not isinstance(envelope, IngestEnvelope):
            raise TypeError("envelope must be IngestEnvelope")
        encoded = _canonical(envelope.as_dict())
        with self._lock:
            row = self._db.execute(
                "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?",
                (envelope.content_digest,),
            ).fetchone()
            if row is not None and row[0] != encoded:
                raise ValueError("content digest already registered with different ingest metadata")
            self._db.execute(
                "INSERT OR IGNORE INTO ingest_envelope(content_digest,envelope_json) VALUES (?,?)",
                (envelope.content_digest, encoded),
            )
            self._db.execute(
                "INSERT OR IGNORE INTO source_authority VALUES (?, ?, 0, 'active', '[]')",
                (envelope.content_digest, _sha256(envelope.as_dict())),
            )
            self._db.commit()

    def register_dataset(self, manifest: DatasetManifest) -> str:
        if not isinstance(manifest, DatasetManifest):
            raise TypeError("manifest must be DatasetManifest")
        with self._lock:
            for digest in manifest.source_ingest_digests:
                row = self._db.execute(
                    "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?",
                    (digest,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"dataset source ingest not registered: {digest}")
                ingest = json.loads(row[0])
                if not ingest.get("trusted"):
                    raise ValueError(f"dataset source remains quarantined: {digest}")

                source_rights = {
                    str(item).strip().lower() for item in ingest.get("rights", []) if str(item).strip()
                }
                undelegated = set(manifest.permitted_uses) - source_rights
                if undelegated:
                    raise PermissionError(
                        "dataset may not escalate source ingest rights: " + ",".join(sorted(undelegated))
                    )

                source_classification = str(ingest.get("classification", ""))
                if (
                    source_classification not in _CLASSIFICATION_RANK
                    or _CLASSIFICATION_RANK[manifest.classification]
                    < _CLASSIFICATION_RANK[source_classification]
                ):
                    raise PermissionError(
                        "dataset classification may not downgrade " "source ingest classification"
                    )

                parser_version = str(ingest.get("parser_version", ""))
                if parser_version not in manifest.parser_versions:
                    raise ValueError(f"dataset parser_versions omit source parser: {parser_version}")
            encoded = _canonical(manifest.as_dict())
            row = self._db.execute(
                "SELECT dataset_digest,manifest_json FROM dataset_manifest WHERE dataset_id=? AND version=?",
                (manifest.dataset_id, manifest.version),
            ).fetchone()
            if row is not None:
                if row[0] != manifest.digest or row[1] != encoded:
                    raise ValueError("dataset id/version is immutable and already bound to different content")
                return manifest.digest
            self._db.execute(
                "INSERT INTO dataset_manifest(dataset_digest,dataset_id,version,manifest_json) VALUES (?,?,?,?)",
                (manifest.digest, manifest.dataset_id, manifest.version, encoded),
            )
            self._db.execute("INSERT INTO dataset_authority VALUES (?, 0, 'active')", (manifest.digest,))
            self._db.commit()
        return manifest.digest

    def dataset(self, digest: str) -> DatasetManifest:
        digest = _require_digest(digest, field="dataset_digest")
        row = self._db.execute(
            "SELECT manifest_json FROM dataset_manifest WHERE dataset_digest=?",
            (digest,),
        ).fetchone()
        if row is None:
            raise KeyError(digest)
        manifest = DatasetManifest.from_dict(json.loads(row[0]))
        if manifest.digest != digest:
            raise ValueError("stored dataset manifest digest does not match registry key")
        return manifest

    def record_lineage(self, receipt: LineageReceipt) -> str:
        if not isinstance(receipt, LineageReceipt):
            raise TypeError("receipt must be LineageReceipt")
        with self._lock:
            for digest in receipt.input_digests:
                known = self._db.execute(
                    "SELECT 1 FROM dataset_manifest WHERE dataset_digest=?",
                    (digest,),
                ).fetchone()
                if known is None:
                    raise ValueError(f"lineage input is not a registered dataset: {digest}")
            encoded = _canonical(receipt.as_dict())
            self._db.execute(
                "INSERT OR IGNORE INTO lineage_receipt(receipt_digest,output_digest,receipt_json) VALUES (?,?,?)",
                (receipt.digest, receipt.output_digest, encoded),
            )
            self._db.commit()
        return receipt.digest

    def record_quality(self, report: DataQualityReport) -> str:
        if not isinstance(report, DataQualityReport):
            raise TypeError("report must be DataQualityReport")
        manifest = self.dataset(report.dataset_digest)
        self._authority_epoch(
            manifest,
            purpose="training" if "training" in manifest.permitted_uses else manifest.permitted_uses[0],
        )
        if manifest.materialization_digest is not None:
            self._materialized_documents(manifest, report=report)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._authority_epoch(
                    manifest,
                    purpose=(
                        "training" if "training" in manifest.permitted_uses else manifest.permitted_uses[0]
                    ),
                )
                cursor = self._db.execute(
                    "INSERT OR IGNORE INTO quality_report(report_digest,dataset_digest,report_json,passed) VALUES (?,?,?,?)",
                    (
                        report.digest,
                        report.dataset_digest,
                        _canonical(report.as_dict()),
                        1 if report.passed else 0,
                    ),
                )
                if cursor.rowcount:
                    self._write_authority_event(
                        "dataset",
                        manifest.digest,
                        "quality",
                        (),
                        "quality evidence changed",
                        "quality:" + report.digest,
                    )
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
        return report.digest

    def latest_quality(self, dataset_digest: str) -> DataQualityReport | None:
        digest = _require_digest(dataset_digest, field="dataset_digest")
        row = self._db.execute(
            "SELECT report_digest,report_json,passed FROM quality_report "
            "WHERE dataset_digest=? ORDER BY rowid DESC LIMIT 1",
            (digest,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[1])
        rules = tuple(
            DataQualityRule(
                rule_id=str(item["rule_id"]),
                metric=str(item["metric"]),
                operator=str(item["operator"]),
                threshold=item["threshold"],
                critical=item["critical"],
            )
            for item in payload["rules"]
        )
        report = DataQualityReport(
            dataset_digest=str(payload["dataset_digest"]),
            rules=rules,
            metrics=payload["metrics"],
            passed_rule_ids=tuple(map(str, payload["passed_rule_ids"])),
            failed_rule_ids=tuple(map(str, payload["failed_rule_ids"])),
            observation_digest=payload.get("observation_digest"),
            split_sequence_digests=payload.get("split_sequence_digests", {}),
        )
        if report.dataset_digest != digest:
            raise ValueError("stored quality report dataset identity drift")
        if report.digest != str(row[0]):
            raise ValueError("stored quality report digest mismatch")
        if (1 if report.passed else 0) != int(row[2]):
            raise ValueError("stored quality report pass flag mismatch")
        return report

    def require_training_ready(self, dataset_digest: str) -> DatasetManifest:
        manifest = self.dataset(dataset_digest)
        self._authority_epoch(manifest, purpose="training")
        if "training" not in manifest.permitted_uses:
            raise PermissionError("dataset is not permitted for training")
        if manifest.contamination_labels:
            raise PermissionError("dataset has unresolved contamination labels")
        report = self.latest_quality(dataset_digest)
        if report is None:
            raise RuntimeError("dataset has no quality report")
        if not report.passed:
            raise RuntimeError("dataset failed critical quality gates")
        if manifest.materialization_digest is not None:
            self._materialized_documents(manifest, report=report)
        return manifest

    def _authority_state(self, kind: str, digest: str) -> tuple[int, str, tuple[str, ...]]:
        if kind == "source":
            row = self._db.execute(
                "SELECT epoch,status,revoked_uses_json,metadata_digest FROM source_authority WHERE content_digest=?",
                (digest,),
            ).fetchone()
            original = self._db.execute(
                "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?", (digest,)
            ).fetchone()
            if row is None or original is None or _sha256(json.loads(original[0])) != row[3]:
                raise ValueError("stored source authority/metadata integrity failure")
            revoked = _references(json.loads(row[2]), field="revoked_use")
        else:
            row = self._db.execute(
                "SELECT epoch,status FROM dataset_authority WHERE dataset_digest=?", (digest,)
            ).fetchone()
            if row is None:
                raise ValueError("stored dataset authority is missing")
            revoked = ()
        epoch, status = row[0], row[1]
        if not isinstance(epoch, int) or epoch < 0 or status not in {"active", "deleted"}:
            raise ValueError("stored authority state is invalid")
        latest = self._db.execute(
            "SELECT event_json,event_digest,new_epoch FROM dataset_authority_event WHERE resource_kind=? AND resource_digest=? ORDER BY new_epoch DESC LIMIT 1",
            (kind, digest),
        ).fetchone()
        if latest is None:
            if epoch != 0 or status != "active" or revoked:
                raise ValueError("authority state has no matching lifecycle evidence")
        else:
            payload = json.loads(latest[0])
            if (
                _sha256(payload) != latest[1]
                or payload.get("resource_digest") != digest
                or payload.get("resource_kind") != kind
                or payload.get("new_epoch") != latest[2]
                or latest[2] != epoch
                or payload.get("status") != status
                or tuple(payload.get("revoked_uses", ())) != revoked
            ):
                raise ValueError("stored authority lifecycle evidence mismatch")
        return epoch, status, revoked

    def _authority_epoch(self, manifest: DatasetManifest, *, purpose: str | None = None) -> int:
        epoch, status, _ = self._authority_state("dataset", manifest.digest)
        if purpose is not None and status != "active":
            raise PermissionError("dataset is deleted and unavailable")
        for digest in manifest.source_ingest_digests:
            source_epoch, source_status, revoked = self._authority_state("source", digest)
            epoch += source_epoch
            if purpose is not None and (source_status != "active" or purpose in revoked):
                raise PermissionError("source rights revoked or source deleted")
        return epoch

    def dataset_authority_epoch(self, dataset_digest: str) -> int:
        with self._lock:
            return self._authority_epoch(self.dataset(dataset_digest))

    def assert_dataset_authority(self, dataset_digest: str, expected_epoch: int) -> None:
        if isinstance(expected_epoch, bool) or not isinstance(expected_epoch, int) or expected_epoch < 0:
            raise ValueError("expected authority epoch must be a non-negative integer")
        with self._lock:
            manifest = self.dataset(dataset_digest)
            actual = self._authority_epoch(manifest, purpose="training")
            if actual != expected_epoch:
                raise PermissionError("dataset authority epoch changed")
            self.require_training_ready(dataset_digest)

    def latest_materialized_version(self, dataset_id: str) -> int:
        did = _text(dataset_id, field="dataset_id")
        with self._lock:
            rows = self._db.execute(
                "SELECT dataset_digest,version FROM dataset_manifest WHERE dataset_id=?", (did,)
            ).fetchall()
            latest = 0
            for digest, version in rows:
                manifest = self.dataset(digest)
                if manifest.materialization_digest is None:
                    raise ValueError("dataset namespace contains legacy versions")
                self._authority_epoch(manifest)
                if self._authority_state("dataset", digest)[1] != "active":
                    raise PermissionError("deleted dataset namespace cannot be reused")
                if not version.isdecimal() or str(int(version)) != version or int(version) <= 0:
                    raise ValueError("materialized dataset version is invalid")
                latest = max(latest, int(version))
            return latest

    def source_envelope(self, content_digest: str) -> IngestEnvelope | None:
        digest = _require_digest(content_digest, field="content_digest")
        with self._lock:
            row = self._db.execute(
                "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?", (digest,)
            ).fetchone()
            if row is None:
                return None
            _, status, revoked = self._authority_state("source", digest)
            if status != "active" or revoked:
                raise PermissionError("source rights revoked or source deleted")
            payload = json.loads(row[0])
            return IngestEnvelope(**{**payload, "rights": tuple(payload["rights"])})

    def _source_blob(self, digest: str) -> tuple[str, bytes] | None:
        dimensions = self._db.execute(
            "SELECT length(CAST(source_json AS BLOB)),length(payload) FROM materialized_source WHERE content_digest=?",
            (digest,),
        ).fetchone()
        if dimensions is None:
            return None
        if dimensions[0] > _MAX_IDENTITY_BYTES or dimensions[1] > _MAX_SOURCE_BYTES:
            raise ValueError("stored materialized source exceeds byte bounds")
        encoded, payload = self._db.execute(
            "SELECT source_json,payload FROM materialized_source WHERE content_digest=?", (digest,)
        ).fetchone()
        return encoded, bytes(payload)

    def validate_training_corpus(
        self, dataset_digest: str, corpus: Sequence[str], *, split_name: str = "train"
    ) -> None:
        documents = _documents(corpus)
        manifest = self.require_training_ready(dataset_digest)
        split = next((item for item in manifest.splits if item.name == split_name), None)
        if split is None:
            raise ValueError("dataset split not found")
        if (
            split.record_count != len(documents)
            or split.digest != hashlib.sha256("\n".join(documents).encode("utf-8")).hexdigest()
        ):
            raise ValueError("training corpus does not match registered split")
        if manifest.materialization_digest is not None:
            stored = self._materialized_documents(manifest)
            if documents != stored[split_name]:
                raise ValueError("training corpus exact document sequence mismatch")

    def training_corpus(self, dataset_digest: str, *, split_name: str = "train") -> tuple[str, ...]:
        manifest = self.require_training_ready(dataset_digest)
        if manifest.materialization_digest is None:
            raise RuntimeError("legacy dataset has no materialized corpus bytes")
        try:
            return self._materialized_documents(manifest)[split_name]
        except KeyError as exc:
            raise ValueError("dataset split not found") from exc

    def _materialized_documents(
        self,
        manifest: DatasetManifest,
        *,
        report: DataQualityReport | None = None,
    ) -> dict[str, tuple[str, ...]]:
        dimensions = self._db.execute(
            "SELECT length(CAST(materialization_json AS BLOB)),length(CAST(observation_json AS BLOB)) FROM materialized_dataset WHERE dataset_digest=?",
            (manifest.digest,),
        ).fetchone()
        if dimensions is not None and any(size > _MAX_IDENTITY_BYTES for size in dimensions):
            raise ValueError("stored materialization identity exceeds byte bounds")
        row = self._db.execute(
            "SELECT materialization_json,observation_digest,observation_json FROM materialized_dataset WHERE dataset_digest=?",
            (manifest.digest,),
        ).fetchone()
        if row is None:
            raise RuntimeError("materialized dataset content is unavailable")
        materialization = json.loads(row[0])
        if (
            _sha256(materialization) != manifest.materialization_digest
            or materialization.get("dataset_id") != manifest.dataset_id
            or str(materialization.get("version")) != manifest.version
        ):
            raise ValueError("stored materialization identity mismatch")
        sources: dict[str, tuple[str, ...]] = {}
        if set(materialization["sources"]) != set(manifest.source_ingest_digests):
            raise ValueError("materialized source coverage mismatch")
        for digest, source_identity in materialization["sources"].items():
            stored = self._source_blob(digest)
            original = self._db.execute(
                "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?", (digest,)
            ).fetchone()
            if stored is None or original is None:
                raise RuntimeError("materialized source bytes unavailable")
            identity = json.loads(stored[0])
            if identity != source_identity or identity["envelope"] != json.loads(original[0]):
                raise ValueError("materialized source metadata identity mismatch")
            envelope = IngestEnvelope(
                **{**identity["envelope"], "rights": tuple(identity["envelope"]["rights"])}
            )
            source = MaterializedTrainingSource(
                envelope=envelope,
                payload=bytes(stored[1]),
                format=identity["format"],
                rights_refs=tuple(identity["rights_refs"]),
                lineage_refs=tuple(identity["lineage_refs"]),
                evidence=identity["evidence"],
            )
            if source.as_dict() != identity or envelope.content_digest != digest:
                raise ValueError("materialized source content identity mismatch")
            sources[digest] = source.documents()
        corpora: dict[str, tuple[str, ...]] = {}
        if set(materialization["splits"]) != {split.name for split in manifest.splits}:
            raise ValueError("materialized split identity mismatch")
        actual_names = {
            item[0]
            for item in self._db.execute(
                "SELECT DISTINCT split_name FROM materialized_document WHERE dataset_digest=?",
                (manifest.digest,),
            ).fetchall()
        }
        if actual_names != set(materialization["splits"]):
            raise ValueError("materialized document split coverage mismatch")
        for name, expected_rows in materialization["splits"].items():
            dimensions = self._db.execute(
                "SELECT COUNT(*),MAX(length(document_bytes)),SUM(length(document_bytes)) FROM materialized_document WHERE dataset_digest=? AND split_name=?",
                (manifest.digest, name),
            ).fetchone()
            if (
                dimensions[0] > 4096
                or (dimensions[1] or 0) > 1024 * 1024
                or (dimensions[2] or 0) > _MAX_SOURCE_BYTES
            ):
                raise ValueError("stored corpus exceeds materialization bounds")
            rows = self._db.execute(
                "SELECT ordinal,source_content_digest,source_ordinal,document_digest,document_bytes FROM materialized_document WHERE dataset_digest=? AND split_name=? ORDER BY ordinal",
                (manifest.digest, name),
            ).fetchall()
            if len(rows) != len(expected_rows):
                raise ValueError("materialized document count mismatch")
            documents: list[str] = []
            for index, (stored, expected) in enumerate(zip(rows, expected_rows, strict=True)):
                ordinal, source_digest, source_ordinal, text_digest, payload = stored
                identity = {
                    "ordinal": ordinal,
                    "source_content_digest": source_digest,
                    "source_ordinal": source_ordinal,
                    "document_digest": text_digest,
                }
                if (
                    identity != expected
                    or ordinal != index
                    or hashlib.sha256(bytes(payload)).hexdigest() != text_digest
                ):
                    raise ValueError("materialized document identity mismatch")
                try:
                    text = bytes(payload).decode("utf-8")
                    original_text = sources[source_digest][source_ordinal]
                except (UnicodeDecodeError, KeyError, IndexError, TypeError) as exc:
                    raise ValueError("materialized document provenance unavailable") from exc
                if text != original_text:
                    raise ValueError("materialized document/source correspondence mismatch")
                documents.append(text)
            corpora[name] = _documents(documents)
        observed = _observations(corpora)
        observation_digest = _sha256(observed)
        if (
            observed != json.loads(row[2])
            or observation_digest != row[1]
            or observation_digest != materialization["observation_digest"]
        ):
            raise ValueError("materialized observations integrity mismatch")
        for split in manifest.splits:
            actual = observed["splits"][split.name]
            if split.digest != actual["legacy_split_digest"] or split.record_count != actual["record_count"]:
                raise ValueError("materialized manifest split observation mismatch")
        if report is not None:
            expected_sequences = {
                name: value["document_sequence_digest"] for name, value in observed["splits"].items()
            }
            if (
                report.dataset_digest != manifest.digest
                or report.observation_digest != observation_digest
                or dict(report.metrics) != observed["metrics"]
                or dict(report.split_sequence_digests) != expected_sequences
            ):
                raise ValueError("quality report does not bind materialized observations/splits")
            supplied = {rule.rule_id: rule.as_dict() for rule in report.rules}
            if any(
                supplied.get(rule.rule_id) != rule.as_dict()
                for rule in _baseline_rules(manifest.permitted_uses)
            ):
                raise ValueError("quality report may not bypass observed baseline gates")
        return corpora

    def materialized_ingestion(self, ingestion_id: str) -> MaterializedDatasetReceipt | None:
        iid = _text(ingestion_id, field="ingestion_id")
        row = self._db.execute(
            "SELECT request_digest,dataset_digest,receipt_digest,receipt_json FROM materialized_ingestion WHERE ingestion_id=?",
            (iid,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[3])
        manifest = self.dataset(row[1])
        receipt = MaterializedDatasetReceipt(
            manifest,
            payload["ingestion_id"],
            payload["request_digest"],
            payload["observation_digest"],
            payload["quality_report_digest"],
        )
        if (
            receipt.digest != row[2]
            or receipt.request_digest != row[0]
            or receipt.ingestion_id != iid
            or receipt.as_dict() != payload
        ):
            raise ValueError("materialized ingestion receipt integrity mismatch")
        self._authority_epoch(
            manifest,
            purpose="training" if "training" in manifest.permitted_uses else manifest.permitted_uses[0],
        )
        report = self.latest_quality(manifest.digest)
        if report is None or not report.passed:
            raise RuntimeError("materialized ingestion is no longer quality-admitted")
        self._materialized_documents(manifest, report=report)
        return receipt

    def ingest_materialized(
        self,
        *,
        ingestion_id: str,
        dataset_id: str,
        expected_version: int,
        sources: Mapping[str, Sequence[MaterializedTrainingSource]],
        classification: str,
        permitted_uses: Sequence[str],
        retention_class: str,
        quality_rules: Sequence[DataQualityRule] | None = None,
    ) -> MaterializedDatasetReceipt:
        iid = _text(ingestion_id, field="ingestion_id")
        did = _text(dataset_id, field="dataset_id")
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 0
        ):
            raise ValueError("expected_version must be a non-negative integer")
        uses = _references(
            tuple(use.lower() for use in _references(permitted_uses, field="permitted_use")),
            field="permitted_use",
        )
        if (
            not uses
            or classification not in _CLASSIFICATION_RANK
            or set(uses) - {"training", "evaluation", "simulation_training", "simulation_evaluation"}
        ):
            raise ValueError("permitted uses and classification must be explicit")
        if not isinstance(sources, Mapping) or not 1 <= len(sources) <= 64:
            raise ValueError("materialized sources require a bounded split mapping")
        retention = _text(retention_class, field="retention_class")
        checked: dict[str, tuple[MaterializedTrainingSource, ...]] = {}
        identities: dict[str, dict[str, object]] = {}
        source_objects: dict[str, MaterializedTrainingSource] = {}
        corpora: dict[str, tuple[str, ...]] = {}
        split_rows: dict[str, list[dict[str, object]]] = {}
        total_documents = 0
        total_bytes = 0
        for raw_name, split_sources in sources.items():
            name = _text(raw_name, field="split_name")
            if name in checked:
                raise ValueError("split names must be unique after normalization")
            if isinstance(split_sources, (str, bytes)) or not isinstance(split_sources, Sequence):
                raise TypeError("split sources must be an ordered source sequence")
            if not 1 <= len(split_sources) <= 4096:
                raise ValueError("split source count exceeds bound")
            values = tuple(split_sources[index] for index in range(len(split_sources)))
            if not values or any(not isinstance(source, MaterializedTrainingSource) for source in values):
                raise ValueError("every split requires materialized source objects")
            checked[name] = values
            documents: list[str] = []
            rows: list[dict[str, object]] = []
            for source in values:
                identity = source.as_dict()
                if not source.envelope.trusted or source.envelope.quarantine_reason:
                    raise PermissionError("materialized source remains quarantined")
                if not set(uses).issubset({right.lower() for right in source.envelope.rights}):
                    raise PermissionError("dataset may not escalate source ingest rights")
                if (
                    _CLASSIFICATION_RANK[classification]
                    < _CLASSIFICATION_RANK[source.envelope.classification]
                ):
                    raise PermissionError("dataset may not downgrade source classification")
                digest = source.envelope.content_digest
                if digest in identities and identities[digest] != identity:
                    raise ValueError("source content cannot bind conflicting provenance")
                identities[digest] = identity
                source_objects[digest] = source
                for source_ordinal, document in enumerate(source.documents()):
                    total_documents += 1
                    total_bytes += len(document.encode("utf-8"))
                    if total_documents > 4096 or total_bytes > _MAX_SOURCE_BYTES:
                        raise ValueError("materialized dataset exceeds document/byte bounds")
                    rows.append(
                        {
                            "ordinal": len(documents),
                            "source_content_digest": digest,
                            "source_ordinal": source_ordinal,
                            "document_digest": hashlib.sha256(document.encode("utf-8")).hexdigest(),
                        }
                    )
                    documents.append(document)
            corpora[name] = _documents(documents)
            split_rows[name] = rows
        if not checked:
            raise ValueError("materialized ingestion requires splits")
        observations = _observations(corpora)
        observation_digest = _sha256(observations)
        if quality_rules is not None and (
            not isinstance(quality_rules, Sequence) or len(quality_rules) > 256
        ):
            raise ValueError("quality policy must be a bounded rule sequence")
        additional = tuple(quality_rules or ())
        if any(not isinstance(rule, DataQualityRule) for rule in additional):
            raise TypeError("quality_rules must contain DataQualityRule")
        rules = (*_baseline_rules(uses), *additional)
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ValueError("quality rule IDs may not override baseline rules")
        request = {
            "ingestion_id": iid,
            "dataset_id": did,
            "expected_version": expected_version,
            "sources": {
                name: [source.as_dict() for source in split_sources]
                for name, split_sources in checked.items()
            },
            "classification": classification,
            "permitted_uses": list(uses),
            "retention_class": retention,
            "quality_rules": [rule.as_dict() for rule in rules],
        }
        request_digest = _sha256(request)
        if len(_canonical(request).encode("utf-8")) > _MAX_IDENTITY_BYTES:
            raise ValueError("materialized ingestion identity exceeds byte bounds")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                previous = self.materialized_ingestion(iid)
                if previous is not None:
                    if previous.request_digest != request_digest:
                        raise ValueError("ingestion identity is bound to a different request")
                    self._db.rollback()
                    return previous
                versions = self._db.execute(
                    "SELECT m.version,d.dataset_digest FROM dataset_manifest m LEFT JOIN materialized_dataset d ON d.dataset_digest=m.dataset_digest WHERE m.dataset_id=?",
                    (did,),
                ).fetchall()
                if any(row[1] is None for row in versions):
                    raise ValueError("materialized versioning cannot reuse a legacy dataset namespace")
                actual_version = max((int(row[0]) for row in versions), default=0)
                if actual_version != expected_version:
                    raise ValueError("materialized dataset version conflict")
                for (prior_digest,) in self._db.execute(
                    "SELECT dataset_digest FROM dataset_manifest WHERE dataset_id=?", (did,)
                ).fetchall():
                    if self._authority_state("dataset", prior_digest)[1] != "active":
                        raise PermissionError("deleted dataset namespace cannot be reused")
                materialization = {
                    "schema_version": "training_materialization.v1",
                    "dataset_id": did,
                    "version": actual_version + 1,
                    "sources": identities,
                    "splits": split_rows,
                    "observation_digest": observation_digest,
                }
                manifest = DatasetManifest(
                    dataset_id=did,
                    version=str(actual_version + 1),
                    splits=tuple(
                        DatasetSplit(
                            name, observations["splits"][name]["legacy_split_digest"], len(documents)
                        )
                        for name, documents in corpora.items()
                    ),
                    source_ingest_digests=tuple(identities),
                    classification=classification,
                    permitted_uses=uses,
                    retention_class=retention,
                    parser_versions=tuple(
                        dict.fromkeys(source.envelope.parser_version for source in source_objects.values())
                    ),
                    materialization_digest=_sha256(materialization),
                )
                sequences = {
                    name: value["document_sequence_digest"] for name, value in observations["splits"].items()
                }
                report = DataQualityReport.evaluate(
                    manifest.digest,
                    rules,
                    observations["metrics"],
                    observation_digest=observation_digest,
                    split_sequence_digests=sequences,
                )
                if not report.passed:
                    raise RuntimeError("materialized dataset failed critical observed quality gates")
                for digest, source in source_objects.items():
                    encoded = _canonical(source.envelope.as_dict())
                    prior = self._db.execute(
                        "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?", (digest,)
                    ).fetchone()
                    if prior is not None:
                        _, status, revoked = self._authority_state("source", digest)
                        if status != "active" or set(uses) & set(revoked):
                            raise PermissionError("source rights revoked or source deleted")
                        if prior[0] != encoded:
                            raise ValueError("content digest already bound to different source metadata")
                    self._db.execute("INSERT OR IGNORE INTO ingest_envelope VALUES (?, ?)", (digest, encoded))
                    self._db.execute(
                        "INSERT OR IGNORE INTO source_authority VALUES (?, ?, 0, 'active', '[]')",
                        (digest, _sha256(source.envelope.as_dict())),
                    )
                    prior_content = self._source_blob(digest)
                    if prior_content is not None and (
                        prior_content[0] != _canonical(identities[digest])
                        or bytes(prior_content[1]) != source.payload
                    ):
                        raise ValueError("materialized source identity is immutable")
                    self._db.execute(
                        "INSERT OR IGNORE INTO materialized_source VALUES (?, ?, ?)",
                        (digest, _canonical(identities[digest]), source.payload),
                    )
                self._db.execute(
                    "INSERT INTO dataset_manifest VALUES (?, ?, ?, ?)",
                    (manifest.digest, manifest.dataset_id, manifest.version, _canonical(manifest.as_dict())),
                )
                self._db.execute("INSERT INTO dataset_authority VALUES (?, 0, 'active')", (manifest.digest,))
                self._db.execute(
                    "INSERT INTO materialized_dataset VALUES (?, ?, ?, ?)",
                    (
                        manifest.digest,
                        _canonical(materialization),
                        observation_digest,
                        _canonical(observations),
                    ),
                )
                for name, rows in split_rows.items():
                    for row, document in zip(rows, corpora[name], strict=True):
                        self._db.execute(
                            "INSERT INTO materialized_document VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                manifest.digest,
                                name,
                                row["ordinal"],
                                row["source_content_digest"],
                                row["source_ordinal"],
                                row["document_digest"],
                                document.encode("utf-8"),
                            ),
                        )
                self._db.execute(
                    "INSERT INTO quality_report VALUES (?, ?, ?, ?)",
                    (report.digest, manifest.digest, _canonical(report.as_dict()), 1),
                )
                receipt = MaterializedDatasetReceipt(
                    manifest, iid, request_digest, observation_digest, report.digest
                )
                self._db.execute(
                    "INSERT INTO materialized_ingestion VALUES (?, ?, ?, ?, ?)",
                    (iid, request_digest, manifest.digest, receipt.digest, _canonical(receipt.as_dict())),
                )
                self._materialized_documents(manifest, report=report)
                self._db.commit()
                return receipt
            except BaseException:
                self._db.rollback()
                raise

    def ingest_export(
        self,
        export_manifest,
        documents: Sequence[str],
        *,
        dataset_id: str,
        expected_version: int = 0,
        ingestion_id: str | None = None,
        classification: str = "internal",
        retention_class: str = "model-development",
        acquired_at: datetime | None = None,
    ) -> MaterializedDatasetReceipt:
        from skeleton.ai.runtime.learning_foundation.multimodal import (
            MultimodalFoundationError,
            MultimodalTrainingManifest,
        )

        if not isinstance(export_manifest, MultimodalTrainingManifest):
            raise TypeError("export_manifest must be MultimodalTrainingManifest")
        try:
            export_manifest.validate_documents(documents)
        except MultimodalFoundationError as exc:
            raise ValueError("multimodal export document/evidence validation failed") from exc
        checked = _documents(documents)
        payload = _canonical({"manifest": export_manifest.as_dict(), "documents": list(checked)}).encode(
            "utf-8"
        )
        digest = hashlib.sha256(payload).hexdigest()
        source_id = "multimodal-export:" + export_manifest.digest
        existing = self._db.execute(
            "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?", (digest,)
        ).fetchone()
        if existing is not None and acquired_at is None:
            identity = json.loads(existing[0])
            envelope = IngestEnvelope(**{**identity, "rights": tuple(identity["rights"])})
            if (
                envelope.source_id != source_id
                or envelope.classification != classification
                or envelope.rights != (export_manifest.purpose,)
            ):
                raise ValueError("multimodal export source metadata identity conflict")
        else:
            envelope = IngestEnvelope.from_bytes(
                source_id=source_id,
                payload=payload,
                parser_version="multimodal-text-projection@1",
                classification=classification,
                rights=(export_manifest.purpose,),
                trusted=True,
                acquired_at=acquired_at,
            )
        rights = tuple(dict.fromkeys(ref for sample in export_manifest.samples for ref in sample.rights_refs))
        lineage = tuple(
            dict.fromkeys(
                (
                    export_manifest.digest,
                    *(
                        ref
                        for sample in export_manifest.samples
                        for ref in (
                            *sample.lineage_refs,
                            sample.record_digest,
                            sample.asset_digest,
                            sample.projection_digest,
                        )
                    ),
                )
            )
        )
        source = MaterializedTrainingSource(
            envelope=envelope,
            payload=payload,
            format="multimodal_projection",
            rights_refs=rights,
            lineage_refs=lineage,
            evidence={
                "multimodal_manifest": export_manifest.as_dict(),
                "multimodal_manifest_digest": export_manifest.digest,
            },
        )
        return self.ingest_materialized(
            ingestion_id=ingestion_id or "multimodal:" + export_manifest.export_id,
            dataset_id=dataset_id,
            expected_version=expected_version,
            sources={"train" if export_manifest.purpose.endswith("training") else "evaluation": (source,)},
            classification=classification,
            permitted_uses=(export_manifest.purpose,),
            retention_class=retention_class,
        )

    def materialized_sources(self, dataset_digest: str) -> tuple[MaterializedTrainingSource, ...]:
        manifest = self.dataset(dataset_digest)
        self._authority_epoch(
            manifest,
            purpose="training" if "training" in manifest.permitted_uses else manifest.permitted_uses[0],
        )
        self._materialized_documents(manifest)
        sources: list[MaterializedTrainingSource] = []
        for digest in manifest.source_ingest_digests:
            identity_json, payload = self._source_blob(digest)
            identity = json.loads(identity_json)
            sources.append(
                MaterializedTrainingSource(
                    envelope=IngestEnvelope(
                        **{**identity["envelope"], "rights": tuple(identity["envelope"]["rights"])}
                    ),
                    payload=bytes(payload),
                    format=identity["format"],
                    rights_refs=tuple(identity["rights_refs"]),
                    lineage_refs=tuple(identity["lineage_refs"]),
                    evidence=identity["evidence"],
                )
            )
        return tuple(sources)

    @contextmanager
    def training_authority(self, dataset_digest: str, expected_epoch: int):
        """Keep source admission ordered against concurrent revocation commits."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self.assert_dataset_authority(dataset_digest, expected_epoch)
                yield
                self.assert_dataset_authority(dataset_digest, expected_epoch)
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise

    def _write_authority_event(
        self, kind: str, digest: str, operation: str, uses: Sequence[str], reason: str, command_id: str
    ) -> str:
        request = {
            "command_id": _text(command_id, field="command_id"),
            "resource_kind": kind,
            "resource_digest": digest,
            "operation": operation,
            "uses": list(uses),
            "reason": _text(reason, field="reason"),
        }
        encoded = _canonical(request)
        existing = self._db.execute(
            "SELECT request_json,event_json,event_digest FROM dataset_authority_event WHERE command_id=?",
            (request["command_id"],),
        ).fetchone()
        if existing is not None:
            if existing[0] != encoded or _sha256(json.loads(existing[1])) != existing[2]:
                raise ValueError("authority command identity conflict/integrity failure")
            self._authority_state(kind, digest)
            return existing[2]
        epoch, status, revoked = self._authority_state(kind, digest)
        if status == "deleted":
            raise PermissionError("deleted authority cannot be mutated or restored")
        new_status = "deleted" if operation == "delete" else status
        new_revoked = tuple(sorted(set(revoked) | set(uses))) if kind == "source" else ()
        payload = {
            **request,
            "previous_epoch": epoch,
            "new_epoch": epoch + 1,
            "status": new_status,
            "revoked_uses": list(new_revoked),
        }
        event_digest = _sha256(payload)
        self._db.execute(
            "INSERT INTO dataset_authority_event VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request["command_id"], kind, digest, epoch + 1, encoded, _canonical(payload), event_digest),
        )
        if kind == "source":
            self._db.execute(
                "UPDATE source_authority SET epoch=?,status=?,revoked_uses_json=? WHERE content_digest=?",
                (epoch + 1, new_status, _canonical(list(new_revoked)), digest),
            )
        else:
            self._db.execute(
                "UPDATE dataset_authority SET epoch=?,status=? WHERE dataset_digest=?",
                (epoch + 1, new_status, digest),
            )
        return event_digest

    def revoke_source_rights(
        self, content_digest: str, *, uses: Sequence[str] = ("training",), reason: str, command_id: str
    ) -> str:
        digest = _require_digest(content_digest, field="content_digest")
        revoked = _references(
            tuple(use.lower() for use in _references(uses, field="revoked_use")), field="revoked_use"
        )
        if not revoked:
            raise ValueError("rights revocation requires explicit uses")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                original = self._db.execute(
                    "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?", (digest,)
                ).fetchone()
                if original is None:
                    raise KeyError(digest)
                if set(revoked) - {right.lower() for right in json.loads(original[0])["rights"]}:
                    raise ValueError("cannot revoke an undeclared source use")
                result = self._write_authority_event(
                    "source", digest, "revoke_rights", revoked, reason, command_id
                )
                self._db.commit()
                return result
            except BaseException:
                self._db.rollback()
                raise

    def delete_source(self, content_digest: str, *, reason: str, command_id: str) -> str:
        digest = _require_digest(content_digest, field="content_digest")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                result = self._write_authority_event("source", digest, "delete", (), reason, command_id)
                self._db.execute("DELETE FROM materialized_document WHERE source_content_digest=?", (digest,))
                self._db.execute("DELETE FROM materialized_source WHERE content_digest=?", (digest,))
                self._db.commit()
                return result
            except BaseException:
                self._db.rollback()
                raise

    def delete_dataset(self, dataset_digest: str, *, reason: str, command_id: str) -> str:
        manifest = self.dataset(dataset_digest)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                result = self._write_authority_event(
                    "dataset", manifest.digest, "delete", (), reason, command_id
                )
                self._db.execute(
                    "DELETE FROM materialized_document WHERE dataset_digest=?", (manifest.digest,)
                )
                others = self._db.execute(
                    "SELECT m.manifest_json FROM dataset_manifest m JOIN dataset_authority a ON a.dataset_digest=m.dataset_digest WHERE a.status='active'"
                ).fetchall()
                referenced = {
                    digest for row in others for digest in json.loads(row[0])["source_ingest_digests"]
                }
                for digest in manifest.source_ingest_digests:
                    if digest not in referenced:
                        self._db.execute("DELETE FROM materialized_source WHERE content_digest=?", (digest,))
                self._db.commit()
                return result
            except BaseException:
                self._db.rollback()
                raise

    def close(self) -> None:
        self._db.close()
