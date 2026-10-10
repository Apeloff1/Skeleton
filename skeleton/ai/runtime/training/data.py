"""Governed, content-addressed data plane for native model training.

The training plane must not accept anonymous bytes.  Every dataset version is
immutable, content-addressed, rights/classification-aware, quality-gated and
lineage-linked before it can become a training input.

This module deliberately has no network dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterable, Mapping, Sequence


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
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    name: str
    digest: str
    record_count: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("dataset split name must be non-empty")
        object.__setattr__(self, "digest", _require_digest(self.digest, field="split digest"))
        if isinstance(self.record_count, bool) or not isinstance(self.record_count, int) or self.record_count < 0:
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
        object.__setattr__(self, "content_digest", _require_digest(self.content_digest, field="content_digest"))
        if self.classification not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("unsupported classification")
        rights = tuple(dict.fromkeys(item.strip() for item in self.rights if item.strip()))
        if not rights:
            raise ValueError("ingest rights must be explicit")
        object.__setattr__(self, "rights", rights)
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
    ) -> "IngestEnvelope":
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
            tuple(_require_digest(item, field="source_dataset_digest") for item in self.source_dataset_digests),
        )
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
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

    def __post_init__(self) -> None:
        if not self.dataset_id.strip() or not self.version.strip():
            raise ValueError("dataset_id and version must be non-empty")
        if self.classification not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("unsupported dataset classification")
        if not self.retention_class.strip():
            raise ValueError("retention_class must be explicit")
        if not self.splits:
            raise ValueError("dataset requires at least one split")
        names=[item.name for item in self.splits]
        if len(names)!=len(set(names)):
            raise ValueError("dataset split names must be unique")
        ingest=tuple(_require_digest(item, field="source_ingest_digest") for item in self.source_ingest_digests)
        if not ingest:
            raise ValueError("dataset requires source ingest identity")
        object.__setattr__(self, "source_ingest_digests", ingest)
        uses=tuple(dict.fromkeys(item.strip().lower() for item in self.permitted_uses if item.strip()))
        if not uses:
            raise ValueError("dataset permitted_uses must be explicit")
        object.__setattr__(self, "permitted_uses", uses)
        parsers=tuple(dict.fromkeys(item.strip() for item in self.parser_versions if item.strip()))
        if not parsers:
            raise ValueError("dataset parser_versions must be explicit")
        object.__setattr__(self, "parser_versions", parsers)
        labels=tuple(dict.fromkeys(item.strip().lower() for item in self.contamination_labels if item.strip()))
        object.__setattr__(self, "contamination_labels", labels)

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
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DatasetManifest":
        synthetic=payload.get("synthetic_receipt")
        receipt=None
        if isinstance(synthetic, Mapping):
            receipt=SyntheticDataReceipt(
                generator_id=str(synthetic["generator_id"]),
                generator_config_digest=str(synthetic["generator_config_digest"]),
                source_dataset_digests=tuple(map(str, synthetic.get("source_dataset_digests", []))),
                seed=int(synthetic["seed"]),
                generated_record_count=int(synthetic["generated_record_count"]),
            )
        manifest=cls(
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
        )
        claimed=payload.get("dataset_digest")
        if claimed is not None and str(claimed)!=manifest.digest:
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
        object.__setattr__(self, "input_digests", tuple(_require_digest(x, field="input_digest") for x in self.input_digests))
        if not self.input_digests:
            raise ValueError("lineage requires at least one input")
        object.__setattr__(self, "output_digest", _require_digest(self.output_digest, field="output_digest"))
        object.__setattr__(self, "environment_digest", _require_digest(self.environment_digest, field="environment_digest"))
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
        if not math.isfinite(float(self.threshold)):
            raise ValueError("quality threshold must be finite")
        if not isinstance(self.critical, bool):
            raise ValueError("quality rule critical flag must be boolean")

    def evaluate(self, metrics: Mapping[str, float]) -> bool:
        if self.metric not in metrics:
            return False
        value=float(metrics[self.metric])
        target=float(self.threshold)
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_digest", _require_digest(self.dataset_digest, field="dataset_digest"))
        rules=tuple(self.rules)
        if not rules:
            raise ValueError("quality report requires at least one rule")
        rule_ids=[rule.rule_id for rule in rules]
        if len(rule_ids)!=len(set(rule_ids)):
            raise ValueError("quality rule ids must be unique")
        values={str(k): float(v) for k,v in self.metrics.items()}
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("quality metrics must be finite")

        expected_passed=[]
        expected_failed=[]
        for rule in rules:
            (expected_passed if rule.evaluate(values) else expected_failed).append(rule.rule_id)

        passed=tuple(self.passed_rule_ids)
        failed=tuple(self.failed_rule_ids)
        if passed!=tuple(expected_passed) or failed!=tuple(expected_failed):
            raise ValueError("quality report outcome does not match rules and metrics")

        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "metrics", values)
        object.__setattr__(self, "passed_rule_ids", passed)
        object.__setattr__(self, "failed_rule_ids", failed)

    @classmethod
    def evaluate(
        cls,
        dataset_digest: str,
        rules: Sequence[DataQualityRule],
        metrics: Mapping[str, float],
    ) -> "DataQualityReport":
        passed=[]; failed=[]
        for rule in rules:
            (passed if rule.evaluate(metrics) else failed).append(rule.rule_id)
        return cls(
            dataset_digest=dataset_digest,
            rules=tuple(rules),
            metrics=metrics,
            passed_rule_ids=tuple(passed),
            failed_rule_ids=tuple(failed),
        )

    @property
    def critical_failures(self) -> tuple[str, ...]:
        critical={rule.rule_id for rule in self.rules if rule.critical}
        return tuple(item for item in self.failed_rule_ids if item in critical)

    @property
    def passed(self) -> bool:
        return not self.critical_failures

    @property
    def digest(self) -> str:
        return _sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_digest": self.dataset_digest,
            "rules": [item.as_dict() for item in self.rules],
            "metrics": dict(sorted(self.metrics.items())),
            "passed_rule_ids": list(self.passed_rule_ids),
            "failed_rule_ids": list(self.failed_rule_ids),
            "critical_failures": list(self.critical_failures),
            "passed": self.passed,
        }

_CLASSIFICATION_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


class DatasetRegistry:
    """SQLite-backed immutable dataset/lineage/quality authority."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path=str(path)
        self._lock=threading.RLock()
        self._db=sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(
            """
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
            """
        )
        self._db.commit()

    def register_ingest(self, envelope: IngestEnvelope) -> None:
        if not isinstance(envelope, IngestEnvelope):
            raise TypeError("envelope must be IngestEnvelope")
        encoded=_canonical(envelope.as_dict())
        with self._lock:
            row=self._db.execute(
                "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?",
                (envelope.content_digest,),
            ).fetchone()
            if row is not None and row[0]!=encoded:
                raise ValueError("content digest already registered with different ingest metadata")
            self._db.execute(
                "INSERT OR IGNORE INTO ingest_envelope(content_digest,envelope_json) VALUES (?,?)",
                (envelope.content_digest,encoded),
            )
            self._db.commit()

    def register_dataset(self, manifest: DatasetManifest) -> str:
        if not isinstance(manifest, DatasetManifest):
            raise TypeError("manifest must be DatasetManifest")
        with self._lock:
            for digest in manifest.source_ingest_digests:
                row=self._db.execute(
                    "SELECT envelope_json FROM ingest_envelope WHERE content_digest=?",
                    (digest,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"dataset source ingest not registered: {digest}")
                ingest=json.loads(row[0])
                if not ingest.get("trusted"):
                    raise ValueError(f"dataset source remains quarantined: {digest}")

                source_rights = {
                    str(item).strip().lower()
                    for item in ingest.get("rights", [])
                    if str(item).strip()
                }
                undelegated = set(manifest.permitted_uses) - source_rights
                if undelegated:
                    raise PermissionError(
                        "dataset may not escalate source ingest rights: "
                        + ",".join(sorted(undelegated))
                    )

                source_classification = str(ingest.get("classification", ""))
                if (
                    source_classification not in _CLASSIFICATION_RANK
                    or _CLASSIFICATION_RANK[manifest.classification]
                    < _CLASSIFICATION_RANK[source_classification]
                ):
                    raise PermissionError(
                        "dataset classification may not downgrade "
                        "source ingest classification"
                    )

                parser_version = str(ingest.get("parser_version", ""))
                if parser_version not in manifest.parser_versions:
                    raise ValueError(
                        f"dataset parser_versions omit source parser: {parser_version}"
                    )
            encoded=_canonical(manifest.as_dict())
            row=self._db.execute(
                "SELECT dataset_digest,manifest_json FROM dataset_manifest WHERE dataset_id=? AND version=?",
                (manifest.dataset_id,manifest.version),
            ).fetchone()
            if row is not None:
                if row[0]!=manifest.digest or row[1]!=encoded:
                    raise ValueError("dataset id/version is immutable and already bound to different content")
                return manifest.digest
            self._db.execute(
                "INSERT INTO dataset_manifest(dataset_digest,dataset_id,version,manifest_json) VALUES (?,?,?,?)",
                (manifest.digest,manifest.dataset_id,manifest.version,encoded),
            )
            self._db.commit()
        return manifest.digest

    def dataset(self, digest: str) -> DatasetManifest:
        digest=_require_digest(digest, field="dataset_digest")
        row=self._db.execute(
            "SELECT manifest_json FROM dataset_manifest WHERE dataset_digest=?",
            (digest,),
        ).fetchone()
        if row is None:
            raise KeyError(digest)
        manifest=DatasetManifest.from_dict(json.loads(row[0]))
        if manifest.digest!=digest:
            raise ValueError("stored dataset manifest digest does not match registry key")
        return manifest

    def record_lineage(self, receipt: LineageReceipt) -> str:
        if not isinstance(receipt, LineageReceipt):
            raise TypeError("receipt must be LineageReceipt")
        with self._lock:
            for digest in receipt.input_digests:
                known=self._db.execute(
                    "SELECT 1 FROM dataset_manifest WHERE dataset_digest=?",
                    (digest,),
                ).fetchone()
                if known is None:
                    raise ValueError(f"lineage input is not a registered dataset: {digest}")
            encoded=_canonical(receipt.as_dict())
            self._db.execute(
                "INSERT OR IGNORE INTO lineage_receipt(receipt_digest,output_digest,receipt_json) VALUES (?,?,?)",
                (receipt.digest,receipt.output_digest,encoded),
            )
            self._db.commit()
        return receipt.digest

    def record_quality(self, report: DataQualityReport) -> str:
        if not isinstance(report, DataQualityReport):
            raise TypeError("report must be DataQualityReport")
        self.dataset(report.dataset_digest)
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO quality_report(report_digest,dataset_digest,report_json,passed) VALUES (?,?,?,?)",
                (report.digest,report.dataset_digest,_canonical(report.as_dict()),1 if report.passed else 0),
            )
            self._db.commit()
        return report.digest

    def latest_quality(self, dataset_digest: str) -> DataQualityReport | None:
        digest=_require_digest(dataset_digest, field="dataset_digest")
        row=self._db.execute(
            "SELECT report_digest,report_json,passed FROM quality_report "
            "WHERE dataset_digest=? ORDER BY rowid DESC LIMIT 1",
            (digest,),
        ).fetchone()
        if row is None:
            return None
        payload=json.loads(row[1])
        rules=tuple(
            DataQualityRule(
                rule_id=str(item["rule_id"]),
                metric=str(item["metric"]),
                operator=str(item["operator"]),
                threshold=item["threshold"],
                critical=item["critical"],
            )
            for item in payload["rules"]
        )
        report=DataQualityReport(
            dataset_digest=str(payload["dataset_digest"]),
            rules=rules,
            metrics=payload["metrics"],
            passed_rule_ids=tuple(map(str,payload["passed_rule_ids"])),
            failed_rule_ids=tuple(map(str,payload["failed_rule_ids"])),
        )
        if report.dataset_digest!=digest:
            raise ValueError("stored quality report dataset identity drift")
        if report.digest!=str(row[0]):
            raise ValueError("stored quality report digest mismatch")
        if (1 if report.passed else 0)!=int(row[2]):
            raise ValueError("stored quality report pass flag mismatch")
        return report

    def require_training_ready(self, dataset_digest: str) -> DatasetManifest:
        manifest=self.dataset(dataset_digest)
        if "training" not in manifest.permitted_uses:
            raise PermissionError("dataset is not permitted for training")
        if manifest.contamination_labels:
            raise PermissionError("dataset has unresolved contamination labels")
        report=self.latest_quality(dataset_digest)
        if report is None:
            raise RuntimeError("dataset has no quality report")
        if not report.passed:
            raise RuntimeError("dataset failed critical quality gates")
        return manifest

    def close(self) -> None:
        self._db.close()
