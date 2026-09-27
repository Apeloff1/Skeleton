"""Deterministic reproducibility bundles for P1 qualifying evidence.

A reproducibility bundle captures the immutable inputs needed to replay a
promotion-evidence claim without embedding an arbitrary command.  Independent
runs are expected to have different run identities and timestamps; they must
reproduce the same subject/evidence identity under the same governed runner,
budget, configuration, environment, verifier, and test manifest.

This contract is evidence-only.  It never executes a runner and never grants
maturity or promotion authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .canonical import EvidenceRef, evidence_ref_identity
from .promotion_evidence import PromotionEvidenceReceipt


REPRODUCIBILITY_SCHEMA_ID = "skeleton.p1.reproducibility_bundle"
REPRODUCIBILITY_SCHEMA_VERSION = 1
MAX_REPRODUCIBILITY_INPUTS = 256
MAX_REPRODUCIBILITY_BYTES = 96_000

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class ReproducibilityError(ValueError):
    """A reproducibility bundle or replay observation is malformed."""


class ReplayDisposition(str, Enum):
    REPRODUCED = "reproduced"
    INCOMPATIBLE = "incompatible"
    FAILED = "failed"


def _text(value: object, field: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value:
        raise ReproducibilityError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise ReproducibilityError(f"{field} must be normalized")
    if len(value) > max_length:
        raise ReproducibilityError(f"{field} exceeds maximum length")
    return value


def _token(value: object, field: str, *, max_length: int = 256) -> str:
    text = _text(value, field, max_length=max_length)
    if not _TOKEN_RE.fullmatch(text):
        raise ReproducibilityError(f"{field} must be a canonical token")
    return text


def _sha(value: object, field: str) -> str:
    text = _text(value, field, max_length=40)
    if not _SHA_RE.fullmatch(text):
        raise ReproducibilityError(
            f"{field} must be a lowercase 40-character git SHA"
        )
    return text


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, max_length=64)
    if not _SHA256_RE.fullmatch(text):
        raise ReproducibilityError(f"{field} must be lowercase sha256")
    return text


def _positive_epoch(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReproducibilityError(
            f"{field} must be a positive SOURCE_DATE_EPOCH integer"
        )
    return value


def _canonical_bytes(value: object) -> bytes:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(raw) > MAX_REPRODUCIBILITY_BYTES:
        raise ReproducibilityError("reproducibility payload exceeds byte budget")
    return raw


def canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _normalize_inputs(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise ReproducibilityError("inputs must contain EvidenceRef values")
    by_identity: dict[str, EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise ReproducibilityError("inputs must contain EvidenceRef values")
        source = _text(item.source, "input.source")
        if source.startswith("planned:"):
            raise ReproducibilityError(
                "reproducibility inputs must be materialized, not planned"
            )
        _sha256(item.digest, "input.digest")
        _token(item.category, "input.category", max_length=128)
        by_identity[evidence_ref_identity(item)] = item
        if len(by_identity) > MAX_REPRODUCIBILITY_INPUTS:
            raise ReproducibilityError("reproducibility input budget exceeded")
    if not by_identity:
        raise ReproducibilityError("reproducibility bundle requires inputs")
    return tuple(by_identity[key] for key in sorted(by_identity))


@dataclass(frozen=True, slots=True)
class ReproducibilityBundle:
    repository: str
    commit_sha: str
    task_id: str
    accountability_id: str
    configuration_digest: str
    environment_digest: str
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    runner_id: str
    runner_digest: str
    budget_digest: str
    source_date_epoch: int
    expected_subject_digest: str
    expected_evidence_digest: str
    inputs: tuple[EvidenceRef, ...]
    schema_version: int = REPRODUCIBILITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        repository = _text(self.repository, "repository", max_length=200)
        if repository.count("/") != 1:
            raise ReproducibilityError("repository must be owner/name")
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "commit_sha", _sha(self.commit_sha, "commit_sha"))
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
            "runner_digest",
            "budget_digest",
            "expected_subject_digest",
            "expected_evidence_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(
            self,
            "verifier_id",
            _text(self.verifier_id, "verifier_id", max_length=512),
        )
        object.__setattr__(self, "runner_id", _token(self.runner_id, "runner_id"))
        object.__setattr__(
            self,
            "source_date_epoch",
            _positive_epoch(self.source_date_epoch, "source_date_epoch"),
        )
        object.__setattr__(self, "inputs", _normalize_inputs(self.inputs))
        if self.schema_version != REPRODUCIBILITY_SCHEMA_VERSION:
            raise ReproducibilityError("unsupported reproducibility schema")
        _canonical_bytes(self.as_dict())

    @property
    def bundle_digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_id": REPRODUCIBILITY_SCHEMA_ID,
            "schema_version": self.schema_version,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "configuration_digest": self.configuration_digest,
            "environment_digest": self.environment_digest,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "test_manifest_digest": self.test_manifest_digest,
            "runner_id": self.runner_id,
            "runner_digest": self.runner_digest,
            "budget_digest": self.budget_digest,
            "source_date_epoch": self.source_date_epoch,
            "expected_subject_digest": self.expected_subject_digest,
            "expected_evidence_digest": self.expected_evidence_digest,
            "inputs": [
                {
                    "identity": evidence_ref_identity(item),
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.inputs
            ],
        }


@dataclass(frozen=True, slots=True)
class ReplayObservation:
    runner_id: str
    runner_digest: str
    budget_digest: str
    source_date_epoch: int
    receipt: PromotionEvidenceReceipt | None = None
    failure_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "runner_id", _token(self.runner_id, "runner_id"))
        for field in ("runner_digest", "budget_digest"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(
            self,
            "source_date_epoch",
            _positive_epoch(self.source_date_epoch, "source_date_epoch"),
        )
        if self.receipt is not None and not isinstance(
            self.receipt, PromotionEvidenceReceipt
        ):
            raise ReproducibilityError("receipt must be PromotionEvidenceReceipt")
        if self.receipt is None:
            if self.failure_digest is None:
                raise ReproducibilityError(
                    "failed replay requires failure_digest"
                )
            object.__setattr__(
                self,
                "failure_digest",
                _sha256(self.failure_digest, "failure_digest"),
            )
        elif self.failure_digest is not None:
            raise ReproducibilityError(
                "successful replay receipt cannot include failure_digest"
            )


@dataclass(frozen=True, slots=True)
class ReproducibilityEvaluation:
    bundle_digest: str
    disposition: ReplayDisposition
    compatible: bool
    reproduced: bool
    incompatibilities: tuple[str, ...]
    replay_subject_digest: str | None = None
    replay_evidence_digest: str | None = None
    failure_digest: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_digest": self.bundle_digest,
            "disposition": self.disposition.value,
            "compatible": self.compatible,
            "reproduced": self.reproduced,
            "incompatibilities": list(self.incompatibilities),
            "replay_subject_digest": self.replay_subject_digest,
            "replay_evidence_digest": self.replay_evidence_digest,
            "failure_digest": self.failure_digest,
        }

    @property
    def evaluation_digest(self) -> str:
        return canonical_digest(self.as_dict())


def bundle_from_receipt(
    receipt: PromotionEvidenceReceipt,
    *,
    runner_id: str,
    runner_digest: str,
    budget_digest: str,
    source_date_epoch: int,
    inputs: Iterable[EvidenceRef],
) -> ReproducibilityBundle:
    if not isinstance(receipt, PromotionEvidenceReceipt):
        raise ReproducibilityError("receipt must be PromotionEvidenceReceipt")
    return ReproducibilityBundle(
        repository=receipt.repository,
        commit_sha=receipt.commit_sha,
        task_id=receipt.task_id,
        accountability_id=receipt.accountability_id,
        configuration_digest=receipt.configuration_digest,
        environment_digest=receipt.environment_digest,
        verifier_id=receipt.verifier_id,
        verifier_digest=receipt.verifier_digest,
        test_manifest_digest=receipt.test_manifest_digest,
        runner_id=runner_id,
        runner_digest=runner_digest,
        budget_digest=budget_digest,
        source_date_epoch=source_date_epoch,
        expected_subject_digest=receipt.subject_digest,
        expected_evidence_digest=receipt.evidence_digest,
        inputs=tuple(inputs),
    )


def evaluate_replay(
    bundle: ReproducibilityBundle,
    replay: ReplayObservation,
) -> ReproducibilityEvaluation:
    if not isinstance(bundle, ReproducibilityBundle):
        raise ReproducibilityError("bundle must be ReproducibilityBundle")
    if not isinstance(replay, ReplayObservation):
        raise ReproducibilityError("replay must be ReplayObservation")

    if replay.receipt is None:
        return ReproducibilityEvaluation(
            bundle_digest=bundle.bundle_digest,
            disposition=ReplayDisposition.FAILED,
            compatible=True,
            reproduced=False,
            incompatibilities=("replay execution failed",),
            failure_digest=replay.failure_digest,
        )

    receipt = replay.receipt
    mismatches: list[str] = []
    pairs = (
        ("runner_id", replay.runner_id, bundle.runner_id),
        ("runner_digest", replay.runner_digest, bundle.runner_digest),
        ("budget_digest", replay.budget_digest, bundle.budget_digest),
        (
            "source_date_epoch",
            str(replay.source_date_epoch),
            str(bundle.source_date_epoch),
        ),
        ("repository", receipt.repository, bundle.repository),
        ("commit_sha", receipt.commit_sha, bundle.commit_sha),
        ("task_id", receipt.task_id, bundle.task_id),
        ("accountability_id", receipt.accountability_id, bundle.accountability_id),
        (
            "configuration_digest",
            receipt.configuration_digest,
            bundle.configuration_digest,
        ),
        ("environment_digest", receipt.environment_digest, bundle.environment_digest),
        ("verifier_id", receipt.verifier_id, bundle.verifier_id),
        ("verifier_digest", receipt.verifier_digest, bundle.verifier_digest),
        (
            "test_manifest_digest",
            receipt.test_manifest_digest,
            bundle.test_manifest_digest,
        ),
        (
            "subject_digest",
            receipt.subject_digest,
            bundle.expected_subject_digest,
        ),
        (
            "evidence_digest",
            receipt.evidence_digest,
            bundle.expected_evidence_digest,
        ),
    )
    for field, actual, expected in pairs:
        if actual != expected:
            mismatches.append(
                f"{field} mismatch: expected={expected} actual={actual}"
            )

    if mismatches:
        return ReproducibilityEvaluation(
            bundle_digest=bundle.bundle_digest,
            disposition=ReplayDisposition.INCOMPATIBLE,
            compatible=False,
            reproduced=False,
            incompatibilities=tuple(mismatches),
            replay_subject_digest=receipt.subject_digest,
            replay_evidence_digest=receipt.evidence_digest,
        )

    return ReproducibilityEvaluation(
        bundle_digest=bundle.bundle_digest,
        disposition=ReplayDisposition.REPRODUCED,
        compatible=True,
        reproduced=True,
        incompatibilities=(),
        replay_subject_digest=receipt.subject_digest,
        replay_evidence_digest=receipt.evidence_digest,
    )
