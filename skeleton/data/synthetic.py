"""Synthetic data with immutable provenance and bounded quality gates."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math


class SyntheticDataError(ValueError):
    pass


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise SyntheticDataError("synthetic value is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _tokens(values, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SyntheticDataError(f"{label} must be a collection")
    try:
        rows = tuple(values)
    except TypeError as exc:
        raise SyntheticDataError(f"{label} must be iterable") from exc
    if any(not isinstance(value, str) or not value for value in rows):
        raise SyntheticDataError(f"invalid {label}")
    unique = tuple(sorted(set(rows)))
    if not unique and not allow_empty:
        raise SyntheticDataError(f"{label} required")
    return unique


def _ratio(value: object, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise SyntheticDataError(f"invalid {label}")
    return float(value)


@dataclass(frozen=True, slots=True)
class SyntheticJob:
    job_id: str
    generator_id: str
    generator_version: str
    config_digest: str
    reference_dataset_ref: str


@dataclass(frozen=True, slots=True)
class SyntheticRecord:
    record_id: str
    job_id: str
    content_digest: str
    group_label: str
    parent_refs: tuple[str, ...]
    origin: str = "synthetic"


@dataclass(frozen=True, slots=True)
class SyntheticQuality:
    record_count: int
    diversity_ratio: float
    validity_ratio: float
    memorization_ratio: float
    max_group_share: float
    promotion_allowed: bool


class SyntheticDataFactory:
    def __init__(self, job: SyntheticJob) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (
                job.job_id,
                job.generator_id,
                job.generator_version,
                job.reference_dataset_ref,
            )
        ) or not _is_digest(job.config_digest):
            raise SyntheticDataError("invalid job")
        self.job = job
        self._records: dict[str, SyntheticRecord] = {}

    def record(
        self,
        *,
        record_id: str,
        value: object,
        group_label: str,
        parent_refs,
    ) -> SyntheticRecord:
        parents = _tokens(parent_refs, "parent refs")
        if (
            not isinstance(record_id, str)
            or not record_id
            or not isinstance(group_label, str)
            or not group_label
        ):
            raise SyntheticDataError("provenance required")

        candidate = SyntheticRecord(
            record_id,
            self.job.job_id,
            _digest(value),
            group_label,
            parents,
            "synthetic",
        )
        old = self._records.get(record_id)
        if old is not None and old != candidate:
            raise SyntheticDataError("identity cannot rebind")
        self._records[record_id] = candidate
        return candidate

    def evaluate(
        self,
        *,
        reference_content_digests,
        valid_record_ids,
        min_diversity: float = 0.8,
        min_validity: float = 0.95,
        max_memorization: float = 0.05,
        max_group_share: float = 0.8,
    ) -> SyntheticQuality:
        thresholds = (
            _ratio(min_diversity, "minimum diversity"),
            _ratio(min_validity, "minimum validity"),
            _ratio(max_memorization, "maximum memorization"),
            _ratio(max_group_share, "maximum group share"),
        )
        rows = tuple(self._records.values())
        if not rows:
            raise SyntheticDataError("empty set")

        refs = _tokens(
            reference_content_digests,
            "reference content digests",
            allow_empty=True,
        )
        if any(not _is_digest(value) for value in refs):
            raise SyntheticDataError("invalid reference content digest")
        valid = set(_tokens(valid_record_ids, "valid record ids", allow_empty=True))

        digests = [record.content_digest for record in rows]
        groups: dict[str, int] = {}
        for record in rows:
            groups[record.group_label] = groups.get(record.group_label, 0) + 1

        diversity = len(set(digests)) / len(rows)
        validity = sum(record.record_id in valid for record in rows) / len(rows)
        memorization = sum(digest in set(refs) for digest in digests) / len(rows)
        group_share = max(groups.values()) / len(rows)
        min_diversity_value, min_validity_value, max_memorization_value, max_group_value = thresholds
        allowed = (
            diversity >= min_diversity_value
            and validity >= min_validity_value
            and memorization <= max_memorization_value
            and group_share <= max_group_value
        )
        return SyntheticQuality(
            len(rows),
            diversity,
            validity,
            memorization,
            group_share,
            allowed,
        )
