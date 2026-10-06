"""Exact-head promotion evidence identity for P1 maturity decisions.

The contract deliberately separates a stable *subject* identity from an
individual verifier receipt. Independent gates can therefore join evidence for
the same repository/head/config/environment/task without scraping filenames or
logs, while every receipt still binds the exact verifier, test manifest, run,
timestamp and evidence set that produced it.

This module carries evidence only. It never grants execution or promotion
authority.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .canonical import (
    CanonicalContractError,
    EvidenceRef,
    canonical_json_bytes,
    evidence_ref_identity,
)


PROMOTION_EVIDENCE_SCHEMA_ID = "skeleton.p1.promotion_evidence"
PROMOTION_EVIDENCE_SCHEMA_VERSION = 1
MAX_PROMOTION_EVIDENCE_REFS = 128
MAX_PROMOTION_EVIDENCE_BYTES = 64_000

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class PromotionEvidenceError(ValueError):
    """Raised when a promotion evidence receipt violates its contract."""


def _text(value: object, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value:
        raise PromotionEvidenceError(f"{field} must be a non-empty string")
    if value.strip() != value:
        raise PromotionEvidenceError(f"{field} must be normalized")
    if len(value) > max_length:
        raise PromotionEvidenceError(f"{field} exceeds maximum length")
    return value


def _token(value: object, field: str, *, max_length: int = 256) -> str:
    text = _text(value, field, max_length=max_length)
    if not _TOKEN_RE.fullmatch(text):
        raise PromotionEvidenceError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, max_length=64)
    if not _SHA256_RE.fullmatch(text):
        raise PromotionEvidenceError(f"{field} must be lowercase sha256")
    return text


def _utc(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise PromotionEvidenceError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    try:
        raw = canonical_json_bytes(payload)
    except CanonicalContractError as exc:
        raise PromotionEvidenceError(
            "promotion evidence is not strict canonical JSON"
        ) from exc
    if len(raw) > MAX_PROMOTION_EVIDENCE_BYTES:
        raise PromotionEvidenceError("promotion evidence exceeds byte budget")
    return raw


def _validate_evidence_ref(item: EvidenceRef) -> EvidenceRef:
    if not isinstance(item, EvidenceRef):
        raise PromotionEvidenceError("evidence entries must be EvidenceRef")
    _text(item.source, "evidence.source", max_length=2048)
    _sha256(item.digest, "evidence.digest")
    _token(item.category, "evidence.category", max_length=128)
    return item


def _normalize_evidence(
    evidence: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if isinstance(evidence, (str, bytes)):
        raise PromotionEvidenceError("evidence must be an iterable of EvidenceRef")
    by_identity: dict[str, EvidenceRef] = {}
    for item in evidence:
        validated = _validate_evidence_ref(item)
        by_identity[evidence_ref_identity(validated)] = validated
        if len(by_identity) > MAX_PROMOTION_EVIDENCE_REFS:
            raise PromotionEvidenceError("evidence reference budget exceeded")
    if not by_identity:
        raise PromotionEvidenceError("promotion evidence requires references")
    return tuple(
        by_identity[key]
        for key in sorted(by_identity)
    )


@dataclass(frozen=True, slots=True)
class PromotionEvidenceReceipt:
    """Immutable evidence receipt for one exact P1 promotion subject."""

    repository: str
    commit_sha: str
    task_id: str
    accountability_id: str
    configuration_digest: str
    environment_digest: str
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    run_id: str
    run_attempt: int
    observed_at: datetime
    evidence: tuple[EvidenceRef, ...]
    schema_version: int = PROMOTION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        repository = _text(self.repository, "repository", max_length=200)
        if repository.count("/") != 1:
            raise PromotionEvidenceError("repository must be owner/name")
        if not isinstance(self.commit_sha, str) or not _SHA_RE.fullmatch(
            self.commit_sha
        ):
            raise PromotionEvidenceError(
                "commit_sha must be a lowercase 40-character git SHA"
            )
        object.__setattr__(self, "task_id", _token(self.task_id, "task_id"))
        object.__setattr__(
            self,
            "accountability_id",
            _token(self.accountability_id, "accountability_id"),
        )
        for field in (
            "configuration_digest",
            "environment_digest",
            "verifier_digest",
            "test_manifest_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(
            self,
            "verifier_id",
            _text(self.verifier_id, "verifier_id", max_length=512),
        )
        object.__setattr__(
            self,
            "run_id",
            _token(self.run_id, "run_id", max_length=128),
        )
        if (
            isinstance(self.run_attempt, bool)
            or not isinstance(self.run_attempt, int)
            or self.run_attempt < 1
        ):
            raise PromotionEvidenceError("run_attempt must be a positive integer")
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "evidence",
            _normalize_evidence(self.evidence),
        )
        if self.schema_version != PROMOTION_EVIDENCE_SCHEMA_VERSION:
            raise PromotionEvidenceError("unsupported promotion evidence schema")
        # Enforce the serialized-size budget during construction.
        _canonical_bytes(self.to_payload())

    def subject_payload(self) -> dict[str, Any]:
        """Fields shared by independent gates for deterministic correlation."""

        return {
            "schema_id": PROMOTION_EVIDENCE_SCHEMA_ID,
            "schema_version": self.schema_version,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "configuration_digest": self.configuration_digest,
            "environment_digest": self.environment_digest,
        }

    @property
    def subject_digest(self) -> str:
        return hashlib.sha256(
            _canonical_bytes(self.subject_payload())
        ).hexdigest()

    @property
    def evidence_digest(self) -> str:
        payload = [
            {
                "identity": evidence_ref_identity(item),
                "source": item.source,
                "digest": item.digest,
                "category": item.category,
            }
            for item in self.evidence
        ]
        return hashlib.sha256(
            _canonical_bytes({"evidence": payload})
        ).hexdigest()

    def to_payload(self) -> dict[str, Any]:
        return {
            **self.subject_payload(),
            "subject_digest": self.subject_digest,
            "verifier": {
                "id": self.verifier_id,
                "digest": self.verifier_digest,
                "test_manifest_digest": self.test_manifest_digest,
            },
            "run": {
                "id": self.run_id,
                "attempt": self.run_attempt,
            },
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "evidence_digest": self.evidence_digest,
            "evidence": [
                {
                    "identity": evidence_ref_identity(item),
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence
            ],
        }

    @property
    def receipt_digest(self) -> str:
        return hashlib.sha256(
            _canonical_bytes(self.to_payload())
        ).hexdigest()

    def matches_head(self, expected_sha: str) -> bool:
        return bool(_SHA_RE.fullmatch(expected_sha or "")) and (
            self.commit_sha == expected_sha
        )

    def same_subject(self, other: object) -> bool:
        return isinstance(other, PromotionEvidenceReceipt) and (
            self.subject_digest == other.subject_digest
        )
