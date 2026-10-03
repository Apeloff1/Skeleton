"""Deterministic, content-addressed data foundation for P3-T2.

The implementation is intentionally provider-independent.  It gives training
and multimodal code one strict identity/provenance seam instead of growing
parallel dataset, cache and lineage authorities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Iterable, Mapping, Sequence

from skeleton.learning.model_program import TrainingDataset, corpus_digest


class DataPlaneError(RuntimeError):
    """Data identity, provenance or quality invariants cannot be proven."""


class DataConflictError(DataPlaneError):
    """An optimistic multi-record transaction observed stale state."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DataPlaneError("value is not deterministic JSON") from exc


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(value: object) -> str:
    return _digest_bytes(_json(value).encode("utf-8"))


def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataPlaneError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise DataPlaneError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise DataPlaneError(f"{name} must be lowercase sha256")
    return result


def _unique(name: str, values: Iterable[str], *, minimum: int = 0) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        item = _text(name, raw)
        if item in result:
            raise DataPlaneError(f"{name} contains duplicate {item}")
        result.append(item)
    if len(result) < minimum:
        raise DataPlaneError(f"{name} requires at least {minimum} entries")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ContentObject:
    digest: str
    size_bytes: int
    media_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "digest", _sha("digest", self.digest))
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise DataPlaneError("size_bytes must be a non-negative integer")
        object.__setattr__(self, "media_type", _text("media_type", self.media_type, maximum=255))

    @property
    def uri(self) -> str:
        return f"sha256:{self.digest}"


class ContentAddressedStore:
    """Immutable in-memory witness for content-addressing/cache semantics."""

    def __init__(self, *, max_object_bytes: int = 64 * 1024 * 1024) -> None:
        if isinstance(max_object_bytes, bool) or not isinstance(max_object_bytes, int) or max_object_bytes <= 0:
            raise ValueError("max_object_bytes must be positive")
        self.max_object_bytes = max_object_bytes
        self._objects: dict[str, bytes] = {}
        self._types: dict[str, str] = {}

    def put(self, payload: bytes, *, media_type: str = "application/octet-stream") -> ContentObject:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be immutable bytes")
        if len(payload) > self.max_object_bytes:
            raise DataPlaneError("content object exceeds configured limit")
        digest = _digest_bytes(payload)
        prior = self._objects.get(digest)
        if prior is not None and prior != payload:
            raise DataPlaneError("sha256 identity collision")
        normalized_type = _text("media_type", media_type, maximum=255).lower()
        prior_type = self._types.get(digest)
        if prior_type is not None and prior_type != normalized_type:
            raise DataPlaneError("content identity cannot change media type")
        self._objects[digest] = payload
        self._types[digest] = normalized_type
        return ContentObject(digest=digest, size_bytes=len(payload), media_type=normalized_type)

    def get(self, digest: str) -> bytes:
        key = _sha("digest", digest)
        try:
            payload = self._objects[key]
        except KeyError as exc:
            raise KeyError(key) from exc
        if _digest_bytes(payload) != key:
            raise DataPlaneError("stored object failed content verification")
        return payload

    def contains(self, digest: str) -> bool:
        return _sha("digest", digest) in self._objects


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    sample_count: int
    unique_sample_count: int
    empty_sample_count: int
    duplicate_sample_count: int
    quality_score: float
    report_digest: str

    def __post_init__(self) -> None:
        for name in (
            "sample_count",
            "unique_sample_count",
            "empty_sample_count",
            "duplicate_sample_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DataPlaneError(f"{name} must be a non-negative integer")
        if not 0.0 <= self.quality_score <= 1.0:
            raise DataPlaneError("quality_score must be in [0, 1]")
        object.__setattr__(self, "report_digest", _sha("report_digest", self.report_digest))


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    dataset_id: str
    version: int
    manifest_digest: str
    sample_digests: tuple[str, ...]
    source_refs: tuple[str, ...]
    rights_refs: tuple[str, ...]
    lineage_refs: tuple[str, ...] = ()
    training_content_digest: str | None = None
    synthetic: bool = False
    generator_ref: str | None = None
    quality: DataQualityReport | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version <= 0:
            raise DataPlaneError("dataset version must be positive")
        object.__setattr__(self, "manifest_digest", _sha("manifest_digest", self.manifest_digest))
        object.__setattr__(self, "sample_digests", tuple(_sha("sample_digest", item) for item in self.sample_digests))
        if not self.sample_digests:
            raise DataPlaneError("dataset requires at least one sample")
        object.__setattr__(self, "source_refs", _unique("source_ref", self.source_refs, minimum=1))
        object.__setattr__(self, "rights_refs", _unique("rights_ref", self.rights_refs, minimum=1))
        object.__setattr__(self, "lineage_refs", _unique("lineage_ref", self.lineage_refs))
        if self.training_content_digest is not None:
            object.__setattr__(self, "training_content_digest", _sha("training_content_digest", self.training_content_digest))
        if self.synthetic:
            object.__setattr__(self, "generator_ref", _text("generator_ref", self.generator_ref))
        elif self.generator_ref is not None:
            raise DataPlaneError("non-synthetic dataset may not claim generator_ref")
        frozen = dict(self.metadata)
        _json(frozen)
        object.__setattr__(self, "metadata", frozen)

    @property
    def identity(self) -> str:
        return f"{self.dataset_id}@{self.version}:{self.manifest_digest}"

    def as_training_dataset(self) -> TrainingDataset:
        if self.training_content_digest is None:
            raise DataPlaneError("dataset is not text-decodable training content")
        return TrainingDataset(
            dataset_id=self.identity,
            content_digest=self.training_content_digest,
            sample_count=len(self.sample_digests),
            source_refs=self.source_refs,
            rights_refs=self.rights_refs,
            lineage_refs=self.lineage_refs,
            metadata={
                **dict(self.metadata),
                "synthetic": self.synthetic,
                "generator_ref": self.generator_ref,
                "sample_digests": list(self.sample_digests),
                "quality_report_digest": None if self.quality is None else self.quality.report_digest,
            },
        )


@dataclass(frozen=True, slots=True)
class IngestionRecord:
    ingestion_id: str
    dataset_id: str
    expected_version: int
    committed_version: int
    input_digest: str
    manifest_digest: str
    lineage_refs: tuple[str, ...]
    synthetic: bool

    @property
    def digest(self) -> str:
        return _digest(
            {
                "ingestion_id": self.ingestion_id,
                "dataset_id": self.dataset_id,
                "expected_version": self.expected_version,
                "committed_version": self.committed_version,
                "input_digest": self.input_digest,
                "manifest_digest": self.manifest_digest,
                "lineage_refs": list(self.lineage_refs),
                "synthetic": self.synthetic,
            }
        )


@dataclass(frozen=True, slots=True)
class DatasetTransactionReceipt:
    transaction_id: str
    before_versions: Mapping[str, int]
    after_versions: Mapping[str, int]
    record_digests: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "transaction_id", _text("transaction_id", self.transaction_id))
        before = {str(key): int(value) for key, value in self.before_versions.items()}
        after = {str(key): int(value) for key, value in self.after_versions.items()}
        digests = {str(key): _sha("record_digest", value) for key, value in self.record_digests.items()}
        if set(before) != set(after) or set(after) != set(digests):
            raise DataPlaneError("transaction receipt key coverage drift")
        object.__setattr__(self, "before_versions", before)
        object.__setattr__(self, "after_versions", after)
        object.__setattr__(self, "record_digests", digests)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "transaction_id": self.transaction_id,
                "before_versions": dict(self.before_versions),
                "after_versions": dict(self.after_versions),
                "record_digests": dict(self.record_digests),
            }
        )


def _quality(samples: Sequence[bytes]) -> DataQualityReport:
    texts = [sample.decode("utf-8", errors="ignore").strip() for sample in samples]
    digests = [_digest_bytes(sample) for sample in samples]
    unique = len(set(digests))
    empty = sum(not text for text in texts)
    duplicate = len(samples) - unique
    if not samples:
        score = 0.0
    else:
        penalty = (empty + duplicate) / len(samples)
        score = max(0.0, 1.0 - penalty)
    payload = {
        "sample_count": len(samples),
        "unique_sample_count": unique,
        "empty_sample_count": empty,
        "duplicate_sample_count": duplicate,
        "quality_score": score,
    }
    return DataQualityReport(**payload, report_digest=_digest(payload))


class DatasetRegistry:
    """Versioned dataset registry with optimistic multi-dataset transactions."""

    def __init__(self, store: ContentAddressedStore | None = None) -> None:
        self.store = store or ContentAddressedStore()
        self._records: dict[str, DatasetRecord] = {}
        self._history: dict[str, list[DatasetRecord]] = {}
        self._ingestions: dict[str, IngestionRecord] = {}

    def current(self, dataset_id: str) -> DatasetRecord:
        key = _text("dataset_id", dataset_id)
        try:
            return self._records[key]
        except KeyError as exc:
            raise KeyError(key) from exc

    def history(self, dataset_id: str) -> tuple[DatasetRecord, ...]:
        return tuple(self._history.get(_text("dataset_id", dataset_id), ()))

    def ingest(
        self,
        *,
        ingestion_id: str,
        dataset_id: str,
        samples: Sequence[bytes],
        source_refs: Sequence[str],
        rights_refs: Sequence[str],
        expected_version: int = 0,
        lineage_refs: Sequence[str] = (),
        synthetic: bool = False,
        generator_ref: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> tuple[DatasetRecord, IngestionRecord]:
        iid = _text("ingestion_id", ingestion_id)
        did = _text("dataset_id", dataset_id)
        if iid in self._ingestions:
            prior = self._ingestions[iid]
            return self.current(prior.dataset_id), prior
        if not samples:
            raise DataPlaneError("ingestion requires at least one sample")
        if any(not isinstance(sample, bytes) for sample in samples):
            raise TypeError("all dataset samples must be immutable bytes")
        current = self._records.get(did)
        actual_version = 0 if current is None else current.version
        if expected_version != actual_version:
            raise DataConflictError(
                f"dataset version conflict: {did} expected={expected_version} actual={actual_version}"
            )

        objects = tuple(self.store.put(sample, media_type="application/octet-stream") for sample in samples)
        sample_digests = tuple(item.digest for item in objects)
        quality = _quality(samples)
        normalized_lineage = _unique("lineage_ref", lineage_refs)
        try:
            training_text = tuple(sample.decode("utf-8") for sample in samples)
        except UnicodeDecodeError:
            training_digest = None
        else:
            training_digest = corpus_digest(training_text)
        manifest = {
            "schema_version": 1,
            "dataset_id": did,
            "version": actual_version + 1,
            "sample_digests": list(sample_digests),
            "source_refs": list(_unique("source_ref", source_refs, minimum=1)),
            "rights_refs": list(_unique("rights_ref", rights_refs, minimum=1)),
            "lineage_refs": list(normalized_lineage),
            "training_content_digest": training_digest,
            "synthetic": bool(synthetic),
            "generator_ref": generator_ref,
            "quality_report_digest": quality.report_digest,
            "metadata": {} if metadata is None else dict(metadata),
        }
        manifest_digest = _digest(manifest)
        record = DatasetRecord(
            dataset_id=did,
            version=actual_version + 1,
            manifest_digest=manifest_digest,
            sample_digests=sample_digests,
            source_refs=tuple(source_refs),
            rights_refs=tuple(rights_refs),
            lineage_refs=normalized_lineage,
            training_content_digest=training_digest,
            synthetic=bool(synthetic),
            generator_ref=generator_ref,
            quality=quality,
            metadata={} if metadata is None else dict(metadata),
        )
        input_digest = _digest({"sample_digests": list(sample_digests), "manifest": manifest})
        ingestion = IngestionRecord(
            ingestion_id=iid,
            dataset_id=did,
            expected_version=expected_version,
            committed_version=record.version,
            input_digest=input_digest,
            manifest_digest=record.manifest_digest,
            lineage_refs=record.lineage_refs,
            synthetic=record.synthetic,
        )
        self._records[did] = record
        self._history.setdefault(did, []).append(record)
        self._ingestions[iid] = ingestion
        return record, ingestion

    def transact(
        self,
        *,
        transaction_id: str,
        expected_versions: Mapping[str, int],
        replacements: Mapping[str, DatasetRecord],
    ) -> DatasetTransactionReceipt:
        tx = _text("transaction_id", transaction_id)
        if not replacements:
            raise DataPlaneError("transaction requires replacements")
        if set(expected_versions) != set(replacements):
            raise DataPlaneError("transaction expected/replacement key coverage drift")
        before: dict[str, int] = {}
        for raw_id, expected in expected_versions.items():
            did = _text("dataset_id", raw_id)
            current = self._records.get(did)
            actual = 0 if current is None else current.version
            if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
                raise DataPlaneError("expected version must be a non-negative integer")
            before[did] = actual
            if actual != expected:
                raise DataConflictError(
                    f"transaction stale dataset: {did} expected={expected} actual={actual}"
                )

        checked: dict[str, DatasetRecord] = {}
        for raw_id, record in replacements.items():
            did = _text("dataset_id", raw_id)
            if not isinstance(record, DatasetRecord) or record.dataset_id != did:
                raise DataPlaneError(f"replacement identity drift: {did}")
            if record.version != before[did] + 1:
                raise DataPlaneError(f"replacement version drift: {did}")
            checked[did] = record

        for did, record in checked.items():
            self._records[did] = record
            self._history.setdefault(did, []).append(record)

        digests = {
            did: _digest(
                {
                    "dataset_id": record.dataset_id,
                    "version": record.version,
                    "manifest_digest": record.manifest_digest,
                    "sample_digests": list(record.sample_digests),
                }
            )
            for did, record in checked.items()
        }
        return DatasetTransactionReceipt(
            transaction_id=tx,
            before_versions=before,
            after_versions={did: record.version for did, record in checked.items()},
            record_digests=digests,
        )


__all__ = [
    "ContentAddressedStore",
    "ContentObject",
    "DataConflictError",
    "DataPlaneError",
    "DataQualityReport",
    "DatasetRecord",
    "DatasetRegistry",
    "DatasetTransactionReceipt",
    "IngestionRecord",
]
