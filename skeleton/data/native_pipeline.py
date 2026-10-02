"""Provider-independent data foundation for native model learning.

The P3-T2 data plane is intentionally small and strict:

* canonical row serialization gives deterministic dataset identity;
* a filesystem CAS stores immutable payloads under their SHA-256 digest;
* SQLite owns tenant-scoped dataset versions and provenance manifests;
* quality policy is evaluated before a version can commit;
* derived datasets preserve parent identities and transformation receipts;
* reads re-hash payloads and fail closed on corruption.

The module performs no network I/O and contains no provider integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import threading
from typing import Any, Iterable, Mapping, Sequence


class NativeDataError(RuntimeError):
    """Base failure for the native data plane."""


class DataQualityError(NativeDataError):
    """Dataset content failed its declared quality contract."""


class DatasetConflict(NativeDataError):
    """Dataset version or identity conflicted with committed state."""


class DatasetCorruption(NativeDataError):
    """Persisted bytes no longer match their content address."""


def _canonical_text(value: object, field: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NativeDataError(f"{field} must be non-empty text")
    if value != value.strip():
        raise NativeDataError(f"{field} must be canonical text")
    if len(value) > limit:
        raise NativeDataError(f"{field} exceeds maximum length")
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeDataError("value is not canonical JSON") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _aware(value: datetime | None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise NativeDataError("timestamp must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _rows_payload(rows: Sequence[Mapping[str, Any]]) -> bytes:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise NativeDataError(f"row {index} must be an object")
        normalized.append(dict(row))
    return _canonical_json(normalized)


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    required_fields: tuple[str, ...] = ()
    unique_fields: tuple[str, ...] = ()
    allow_empty: bool = False
    max_rows: int = 1_000_000

    def __post_init__(self) -> None:
        required = tuple(dict.fromkeys(_canonical_text(x, "required_field") for x in self.required_fields))
        unique = tuple(dict.fromkeys(_canonical_text(x, "unique_field") for x in self.unique_fields))
        if isinstance(self.max_rows, bool) or not isinstance(self.max_rows, int) or self.max_rows < 1:
            raise NativeDataError("max_rows must be a positive integer")
        object.__setattr__(self, "required_fields", required)
        object.__setattr__(self, "unique_fields", unique)

    @property
    def digest(self) -> str:
        return _sha256_bytes(
            _canonical_json(
                {
                    "required_fields": self.required_fields,
                    "unique_fields": self.unique_fields,
                    "allow_empty": self.allow_empty,
                    "max_rows": self.max_rows,
                }
            )
        )


@dataclass(frozen=True, slots=True)
class QualityReport:
    row_count: int
    duplicate_row_count: int
    missing_required_count: int
    duplicate_key_count: int
    policy_digest: str
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "duplicate_row_count": self.duplicate_row_count,
            "missing_required_count": self.missing_required_count,
            "duplicate_key_count": self.duplicate_key_count,
            "policy_digest": self.policy_digest,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    tenant_id: str
    dataset_id: str
    version: int
    payload_digest: str
    schema_digest: str
    manifest_digest: str
    quality_digest: str
    parent_manifest_digests: tuple[str, ...]
    transform: str
    source_id: str
    row_count: int
    committed_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "payload_digest": self.payload_digest,
            "schema_digest": self.schema_digest,
            "manifest_digest": self.manifest_digest,
            "quality_digest": self.quality_digest,
            "parent_manifest_digests": list(self.parent_manifest_digests),
            "transform": self.transform,
            "source_id": self.source_id,
            "row_count": self.row_count,
            "committed_at": self.committed_at.isoformat(),
        }


class ContentAddressedStore:
    """Immutable SHA-256 object store with read-time corruption detection."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise NativeDataError("digest must be lowercase sha256")
        return self.root / digest[:2] / digest[2:]

    def put(self, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        digest = _sha256_bytes(payload)
        path = self._path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            current = path.read_bytes()
            if _sha256_bytes(current) != digest:
                raise DatasetCorruption("existing CAS object is corrupt")
            if current != payload:
                raise DatasetCorruption("digest collision or corrupt CAS object")
            return digest
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
        return digest

    def get(self, digest: str) -> bytes:
        path = self._path(digest)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise DatasetCorruption("CAS object is missing") from exc
        if _sha256_bytes(payload) != digest:
            raise DatasetCorruption("CAS object digest mismatch")
        return payload


def evaluate_quality(
    rows: Sequence[Mapping[str, Any]],
    policy: QualityPolicy,
) -> QualityReport:
    if not isinstance(policy, QualityPolicy):
        raise TypeError("policy must be QualityPolicy")
    if len(rows) > policy.max_rows:
        raise DataQualityError("dataset exceeds max_rows")
    if not rows and not policy.allow_empty:
        raise DataQualityError("empty dataset rejected")

    row_digests: set[str] = set()
    duplicate_rows = 0
    missing = 0
    unique_seen: dict[tuple[str, ...], set[tuple[str, ...]]] = {
        (field,): set() for field in policy.unique_fields
    }
    duplicate_keys = 0

    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise DataQualityError(f"row {index} is not an object")
        row = dict(raw)
        for field in policy.required_fields:
            if field not in row or row[field] is None or row[field] == "":
                missing += 1
        digest = _sha256_bytes(_canonical_json(row))
        if digest in row_digests:
            duplicate_rows += 1
        row_digests.add(digest)
        for field in policy.unique_fields:
            key = (_sha256_bytes(_canonical_json(row.get(field))),)
            bucket = unique_seen[(field,)]
            if key in bucket:
                duplicate_keys += 1
            bucket.add(key)

    report = QualityReport(
        row_count=len(rows),
        duplicate_row_count=duplicate_rows,
        missing_required_count=missing,
        duplicate_key_count=duplicate_keys,
        policy_digest=policy.digest,
        passed=missing == 0 and duplicate_keys == 0,
    )
    if not report.passed:
        raise DataQualityError(
            "quality policy failed: "
            f"missing_required={missing}, duplicate_keys={duplicate_keys}"
        )
    return report


class NativeDatasetRepository:
    """Tenant-scoped durable dataset registry backed by CAS + SQLite."""

    def __init__(
        self,
        database: str | Path,
        *,
        cas_root: str | Path,
    ) -> None:
        self.cas = ContentAddressedStore(cas_root)
        self._connection = sqlite3.connect(
            str(database),
            check_same_thread=False,
            timeout=5.0,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS native_dataset_version (
                    tenant_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload_digest TEXT NOT NULL,
                    schema_digest TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    quality_digest TEXT NOT NULL,
                    parents_json TEXT NOT NULL,
                    transform TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    committed_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, dataset_id, version),
                    UNIQUE(tenant_id, manifest_digest)
                );

                CREATE INDEX IF NOT EXISTS native_dataset_manifest_idx
                ON native_dataset_version(tenant_id, manifest_digest);
                """
            )

    def _latest_version(self, tenant_id: str, dataset_id: str) -> int:
        row = self._connection.execute(
            """
            SELECT MAX(version) AS version
            FROM native_dataset_version
            WHERE tenant_id = ? AND dataset_id = ?
            """,
            (tenant_id, dataset_id),
        ).fetchone()
        value = row["version"]
        return 0 if value is None else int(value)

    def commit(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        rows: Sequence[Mapping[str, Any]],
        schema: Mapping[str, Any],
        source_id: str,
        quality_policy: QualityPolicy,
        expected_version: int,
        parent_manifest_digests: Sequence[str] = (),
        transform: str = "ingest",
        now: datetime | None = None,
    ) -> DatasetVersion:
        tenant = _canonical_text(tenant_id, "tenant_id")
        dataset = _canonical_text(dataset_id, "dataset_id")
        source = _canonical_text(source_id, "source_id")
        transform_name = _canonical_text(transform, "transform")
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 0
        ):
            raise NativeDataError("expected_version must be an integer >= 0")
        if not isinstance(schema, Mapping):
            raise NativeDataError("schema must be an object")
        parents = tuple(dict.fromkeys(parent_manifest_digests))
        for digest in parents:
            ContentAddressedStore._path(self.cas, digest)

        report = evaluate_quality(rows, quality_policy)
        payload = _rows_payload(rows)
        payload_digest = self.cas.put(payload)
        schema_digest = _sha256_bytes(_canonical_json(dict(schema)))
        quality_digest = _sha256_bytes(_canonical_json(report.as_dict()))
        instant = _aware(now)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._latest_version(tenant, dataset)
                if current != expected_version:
                    raise DatasetConflict(
                        f"stale dataset version: expected={expected_version} current={current}"
                    )
                version = current + 1
                manifest_material = {
                    "tenant_id": tenant,
                    "dataset_id": dataset,
                    "version": version,
                    "payload_digest": payload_digest,
                    "schema_digest": schema_digest,
                    "quality_digest": quality_digest,
                    "parent_manifest_digests": parents,
                    "transform": transform_name,
                    "source_id": source,
                    "row_count": report.row_count,
                }
                manifest_digest = _sha256_bytes(_canonical_json(manifest_material))
                self._connection.execute(
                    """
                    INSERT INTO native_dataset_version(
                        tenant_id, dataset_id, version, payload_digest,
                        schema_digest, manifest_digest, quality_digest,
                        parents_json, transform, source_id, row_count, committed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant,
                        dataset,
                        version,
                        payload_digest,
                        schema_digest,
                        manifest_digest,
                        quality_digest,
                        json.dumps(list(parents), separators=(",", ":")),
                        transform_name,
                        source,
                        report.row_count,
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

        return DatasetVersion(
            tenant_id=tenant,
            dataset_id=dataset,
            version=version,
            payload_digest=payload_digest,
            schema_digest=schema_digest,
            manifest_digest=manifest_digest,
            quality_digest=quality_digest,
            parent_manifest_digests=parents,
            transform=transform_name,
            source_id=source,
            row_count=report.row_count,
            committed_at=instant,
        )

    def get(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        version: int | None = None,
    ) -> tuple[DatasetVersion, list[dict[str, Any]]]:
        tenant = _canonical_text(tenant_id, "tenant_id")
        dataset = _canonical_text(dataset_id, "dataset_id")
        with self._lock:
            if version is None:
                row = self._connection.execute(
                    """
                    SELECT * FROM native_dataset_version
                    WHERE tenant_id = ? AND dataset_id = ?
                    ORDER BY version DESC LIMIT 1
                    """,
                    (tenant, dataset),
                ).fetchone()
            else:
                if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                    raise NativeDataError("version must be an integer >= 1")
                row = self._connection.execute(
                    """
                    SELECT * FROM native_dataset_version
                    WHERE tenant_id = ? AND dataset_id = ? AND version = ?
                    """,
                    (tenant, dataset, version),
                ).fetchone()
        if row is None:
            raise NativeDataError("dataset version not found")
        payload = self.cas.get(row["payload_digest"])
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, list) or any(not isinstance(x, dict) for x in decoded):
            raise DatasetCorruption("dataset payload shape is invalid")
        record = DatasetVersion(
            tenant_id=tenant,
            dataset_id=dataset,
            version=int(row["version"]),
            payload_digest=row["payload_digest"],
            schema_digest=row["schema_digest"],
            manifest_digest=row["manifest_digest"],
            quality_digest=row["quality_digest"],
            parent_manifest_digests=tuple(json.loads(row["parents_json"])),
            transform=row["transform"],
            source_id=row["source_id"],
            row_count=int(row["row_count"]),
            committed_at=datetime.fromisoformat(row["committed_at"]).astimezone(timezone.utc),
        )
        if record.row_count != len(decoded):
            raise DatasetCorruption("dataset row count diverged from manifest")
        return record, decoded

    def derive_sample(
        self,
        *,
        tenant_id: str,
        parent_dataset_id: str,
        output_dataset_id: str,
        count: int,
        seed: int,
        quality_policy: QualityPolicy,
        source_id: str = "native-synthetic-sampler",
        now: datetime | None = None,
    ) -> DatasetVersion:
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise NativeDataError("count must be a positive integer")
        parent, rows = self.get(
            tenant_id=tenant_id,
            dataset_id=parent_dataset_id,
        )
        if not rows:
            raise DataQualityError("cannot derive from an empty dataset")
        rng = random.Random(seed ^ int(parent.manifest_digest[:16], 16))
        derived = [dict(rows[rng.randrange(len(rows))]) for _ in range(count)]
        fields = sorted({key for row in rows for key in row})
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {field: {} for field in fields},
            },
        }
        return self.commit(
            tenant_id=tenant_id,
            dataset_id=output_dataset_id,
            rows=derived,
            schema=schema,
            source_id=source_id,
            quality_policy=quality_policy,
            expected_version=0,
            parent_manifest_digests=(parent.manifest_digest,),
            transform=f"deterministic-sample:seed={seed}",
            now=now,
        )

    def lineage(
        self,
        *,
        tenant_id: str,
        manifest_digest: str,
    ) -> tuple[str, ...]:
        tenant = _canonical_text(tenant_id, "tenant_id")
        target = _canonical_text(manifest_digest, "manifest_digest")
        seen: set[str] = set()
        stack = [target]
        while stack:
            current = stack.pop()
            row = self._connection.execute(
                """
                SELECT parents_json FROM native_dataset_version
                WHERE tenant_id = ? AND manifest_digest = ?
                """,
                (tenant, current),
            ).fetchone()
            if row is None:
                raise NativeDataError("unknown manifest in lineage")
            parents = tuple(json.loads(row["parents_json"]))
            for parent in parents:
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return tuple(sorted(seen))

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "NativeDatasetRepository":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = [
    "ContentAddressedStore",
    "DataQualityError",
    "DatasetConflict",
    "DatasetCorruption",
    "DatasetVersion",
    "NativeDataError",
    "NativeDatasetRepository",
    "QualityPolicy",
    "QualityReport",
    "evaluate_quality",
]
