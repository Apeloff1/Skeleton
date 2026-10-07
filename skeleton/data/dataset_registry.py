"""Immutable dataset/split registry with explicit governance validation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


class DatasetRegistryError(ValueError):
    pass


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _tokens(values, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DatasetRegistryError(f"{label} must be a collection")
    try:
        rows = tuple(values)
    except TypeError as exc:
        raise DatasetRegistryError(f"{label} must be iterable") from exc
    if any(not isinstance(value, str) or not value for value in rows):
        raise DatasetRegistryError(f"invalid {label}")
    unique = tuple(sorted(set(rows)))
    if not unique and not allow_empty:
        raise DatasetRegistryError(f"{label} required")
    return unique


@dataclass(frozen=True, slots=True)
class Dataset:
    dataset_id: str
    owner: str


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    dataset_id: str
    version: int
    manifest_digest: str
    allowed_uses: tuple[str, ...]
    pii: bool
    retention_until_epoch: int | None
    contamination_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    dataset_id: str
    version: int
    name: str
    record_fingerprint: str
    record_ids: tuple[str, ...]


class DatasetRegistry:
    def __init__(self) -> None:
        self._datasets: dict[str, Dataset] = {}
        self._versions: dict[tuple[str, int], DatasetVersion] = {}
        self._splits: dict[tuple[str, int, str], DatasetSplit] = {}

    def register_dataset(self, dataset: Dataset) -> None:
        if (
            not isinstance(dataset.dataset_id, str)
            or not dataset.dataset_id
            or not isinstance(dataset.owner, str)
            or not dataset.owner
        ):
            raise DatasetRegistryError("invalid dataset")
        old = self._datasets.get(dataset.dataset_id)
        if old is not None and old != dataset:
            raise DatasetRegistryError("dataset identity cannot be rebound")
        self._datasets[dataset.dataset_id] = dataset

    def register_version(
        self,
        *,
        dataset_id: str,
        version: int,
        source_refs,
        allowed_uses,
        pii: bool,
        retention_until_epoch: int | None,
        contamination_tags=(),
    ) -> DatasetVersion:
        if dataset_id not in self._datasets:
            raise DatasetRegistryError("unknown dataset")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise DatasetRegistryError("invalid version")
        if not isinstance(pii, bool):
            raise DatasetRegistryError("pii must be boolean")
        if retention_until_epoch is not None and (
            isinstance(retention_until_epoch, bool)
            or not isinstance(retention_until_epoch, int)
            or retention_until_epoch < 0
        ):
            raise DatasetRegistryError("invalid retention epoch")

        refs = _tokens(source_refs, "source refs")
        uses = _tokens(allowed_uses, "allowed uses")
        tags = _tokens(contamination_tags, "contamination tags", allow_empty=True)
        manifest_digest = _fingerprint(
            [
                dataset_id,
                version,
                refs,
                uses,
                pii,
                retention_until_epoch,
                tags,
            ]
        )
        candidate = DatasetVersion(
            dataset_id,
            version,
            manifest_digest,
            uses,
            pii,
            retention_until_epoch,
            tags,
        )
        key = (dataset_id, version)
        old = self._versions.get(key)
        if old is not None and old != candidate:
            raise DatasetRegistryError("dataset version is immutable")
        self._versions[key] = candidate
        return candidate

    def register_split(
        self,
        *,
        dataset_id: str,
        version: int,
        name: str,
        record_ids,
    ) -> DatasetSplit:
        if (dataset_id, version) not in self._versions:
            raise DatasetRegistryError("unknown dataset version")
        if not isinstance(name, str) or not name:
            raise DatasetRegistryError("invalid split name")
        ids = _tokens(record_ids, "record ids")

        for (other_dataset, other_version, other_name), split in self._splits.items():
            if (
                other_dataset == dataset_id
                and other_version == version
                and other_name != name
                and set(ids) & set(split.record_ids)
            ):
                raise DatasetRegistryError("split leakage detected")

        candidate = DatasetSplit(
            dataset_id,
            version,
            name,
            _fingerprint(ids),
            ids,
        )
        key = (dataset_id, version, name)
        old = self._splits.get(key)
        if old is not None and old != candidate:
            raise DatasetRegistryError("split immutable")
        self._splits[key] = candidate
        return candidate

    def authorize_use(
        self,
        *,
        dataset_id: str,
        version: int,
        use: str,
        current_epoch: int,
    ) -> DatasetVersion:
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
            or isinstance(current_epoch, bool)
            or not isinstance(current_epoch, int)
            or current_epoch < 0
        ):
            raise DatasetRegistryError("invalid authorization epoch/version")
        if not isinstance(use, str) or not use:
            raise DatasetRegistryError("invalid use")

        version_record = self._versions.get((dataset_id, version))
        if version_record is None:
            raise KeyError("dataset version")
        if use not in version_record.allowed_uses:
            raise DatasetRegistryError("use not permitted")
        if (
            version_record.retention_until_epoch is not None
            and current_epoch > version_record.retention_until_epoch
        ):
            raise DatasetRegistryError("retention expired")
        if version_record.pii and use == "public_export":
            raise DatasetRegistryError("PII export forbidden")
        if use == "train" and "benchmark" in version_record.contamination_tags:
            raise DatasetRegistryError("benchmark contamination")
        return version_record
