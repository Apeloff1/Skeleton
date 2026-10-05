"""Bounded SOTA-candidate claim, evidence, and independent replay contracts.

VOL-107 deliberately separates a scoped candidate claim from universal "SOTA"
language. A claim is admissible only when it is tied to exact benchmark,
dataset, source-revision, contamination, robustness, security, efficiency, and
per-metric evidence. Qualification requires an independent verifier-family
replay of the exact candidate metrics on the exact bound identities.

This module is evaluation-only: it cannot promote, deploy, route traffic, or
mark masterplan completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Mapping, Sequence


SOTA_CANDIDATE_SCHEMA = "skeleton.sota_candidate.v1"
SOTA_CANDIDATE_CLAIM = "bounded_sota_candidate"

PROHIBITED_SHORTCUTS = (
    "aggregate_only_scoring",
    "benchmark_digest_substitution",
    "contamination_unknown_or_dirty",
    "dataset_digest_substitution",
    "evidence_omission",
    "metric_omission",
    "metric_regression_compensation",
    "replay_metric_drift",
    "replay_without_exact_revision",
    "same_family_verification",
    "self_verification",
    "unbounded_sota_claim",
)

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_METRICS = 128
_MAX_EVIDENCE_REFS = 512


class SOTACandidateError(ValueError):
    """A SOTA-candidate claim or qualification violates the bounded contract."""


class SOTAMetricDirection(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SOTACandidateError("payload must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise SOTACandidateError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SOTACandidateError(f"{field} must be non-empty text")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise SOTACandidateError(f"{field} must be normalized text")
    return normalized


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SOTACandidateError(f"{field} must be lowercase sha256")
    return value


def _git_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise SOTACandidateError(f"{field} must be a lowercase 40-character git SHA")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SOTACandidateError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SOTACandidateError(f"{field} must be finite")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0:
        raise SOTACandidateError(f"{field} must be non-negative")
    return result


def _refs(values: Sequence[str], field: str, *, minimum: int = 1) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SOTACandidateError(f"{field} must be a sequence of references")
    result: list[str] = []
    for value in values:
        ref = _text(value, field, maximum=1024)
        if ref not in result:
            result.append(ref)
    if len(result) < minimum:
        raise SOTACandidateError(f"{field} requires at least {minimum} unique refs")
    if len(result) > _MAX_EVIDENCE_REFS:
        raise SOTACandidateError(f"{field} exceeds reference limit")
    return tuple(result)


def _metrics(
    values: Mapping[str, float],
    field: str,
) -> Mapping[str, float]:
    if not isinstance(values, Mapping) or not values:
        raise SOTACandidateError(f"{field} must be a non-empty mapping")
    if len(values) > _MAX_METRICS:
        raise SOTACandidateError(f"{field} exceeds metric limit")
    normalized: dict[str, float] = {}
    for key, value in values.items():
        metric_id = _token(key, f"{field}.metric_id")
        if metric_id in normalized:
            raise SOTACandidateError(f"{field} contains duplicate metric")
        normalized[metric_id] = _finite(value, f"{field}.{metric_id}")
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class SOTAMetricRequirement:
    metric_id: str
    direction: SOTAMetricDirection
    baseline_value: float
    minimum_delta: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _token(self.metric_id, "metric_id"))
        try:
            direction = SOTAMetricDirection(self.direction)
        except ValueError as exc:
            raise SOTACandidateError("metric direction is invalid") from exc
        object.__setattr__(self, "direction", direction)
        object.__setattr__(
            self,
            "baseline_value",
            _finite(self.baseline_value, "baseline_value"),
        )
        object.__setattr__(
            self,
            "minimum_delta",
            _nonnegative(self.minimum_delta, "minimum_delta"),
        )

    def satisfied_by(self, candidate_value: float) -> bool:
        candidate = _finite(candidate_value, f"candidate_metrics.{self.metric_id}")
        if self.direction is SOTAMetricDirection.MAXIMIZE:
            return candidate >= self.baseline_value + self.minimum_delta
        return candidate <= self.baseline_value - self.minimum_delta

    def strictly_improved_by(self, candidate_value: float) -> bool:
        candidate = _finite(candidate_value, f"candidate_metrics.{self.metric_id}")
        if self.direction is SOTAMetricDirection.MAXIMIZE:
            return candidate > self.baseline_value
        return candidate < self.baseline_value

    def as_dict(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "direction": self.direction.value,
            "baseline_value": self.baseline_value,
            "minimum_delta": self.minimum_delta,
        }


@dataclass(frozen=True, slots=True)
class SOTACandidateClaim:
    claim_id: str
    candidate_id: str
    benchmark_id: str
    benchmark_digest: str
    dataset_digest: str
    source_revision: str
    task_scope: str
    population: str
    generator_id: str
    generator_family_id: str
    metric_requirements: tuple[SOTAMetricRequirement, ...]
    candidate_metrics: Mapping[str, float]
    contamination_status: str
    contamination_audit_digest: str
    robustness_evidence_digest: str
    security_evidence_digest: str
    efficiency_evidence_digest: str
    evidence_refs: tuple[str, ...]
    claim_scope: str = SOTA_CANDIDATE_CLAIM

    def __post_init__(self) -> None:
        for field in (
            "claim_id",
            "candidate_id",
            "benchmark_id",
            "generator_id",
            "generator_family_id",
        ):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        for field in ("task_scope", "population"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "benchmark_digest",
            _sha256(self.benchmark_digest, "benchmark_digest"),
        )
        object.__setattr__(
            self,
            "dataset_digest",
            _sha256(self.dataset_digest, "dataset_digest"),
        )
        object.__setattr__(
            self,
            "source_revision",
            _git_sha(self.source_revision, "source_revision"),
        )
        if self.claim_scope != SOTA_CANDIDATE_CLAIM:
            raise SOTACandidateError("unbounded SOTA claims are prohibited")
        if self.contamination_status != "clean":
            raise SOTACandidateError("candidate requires clean contamination status")
        for field in (
            "contamination_audit_digest",
            "robustness_evidence_digest",
            "security_evidence_digest",
            "efficiency_evidence_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))

        if not isinstance(self.metric_requirements, tuple) or not self.metric_requirements:
            raise SOTACandidateError("metric_requirements must be a non-empty tuple")
        if len(self.metric_requirements) > _MAX_METRICS:
            raise SOTACandidateError("metric_requirements exceeds metric limit")
        ordered = tuple(sorted(self.metric_requirements, key=lambda item: item.metric_id))
        if any(not isinstance(item, SOTAMetricRequirement) for item in ordered):
            raise SOTACandidateError("metric_requirements contains invalid entries")
        ids = [item.metric_id for item in ordered]
        if len(ids) != len(set(ids)):
            raise SOTACandidateError("metric requirements must have unique ids")
        object.__setattr__(self, "metric_requirements", ordered)

        metrics = _metrics(self.candidate_metrics, "candidate_metrics")
        if set(metrics) != set(ids):
            raise SOTACandidateError(
                "candidate metrics must exactly match required metric ids"
            )
        object.__setattr__(self, "candidate_metrics", metrics)
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "evidence_refs", minimum=5),
        )

        failed = [
            requirement.metric_id
            for requirement in ordered
            if not requirement.satisfied_by(metrics[requirement.metric_id])
        ]
        if failed:
            raise SOTACandidateError(
                "candidate fails non-compensable metrics: " + ",".join(failed)
            )
        if not any(
            requirement.strictly_improved_by(metrics[requirement.metric_id])
            for requirement in ordered
        ):
            raise SOTACandidateError(
                "candidate must strictly improve at least one required metric"
            )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": SOTA_CANDIDATE_SCHEMA,
            "claim_scope": self.claim_scope,
            "claim_id": self.claim_id,
            "candidate_id": self.candidate_id,
            "benchmark_id": self.benchmark_id,
            "benchmark_digest": self.benchmark_digest,
            "dataset_digest": self.dataset_digest,
            "source_revision": self.source_revision,
            "task_scope": self.task_scope,
            "population": self.population,
            "generator_id": self.generator_id,
            "generator_family_id": self.generator_family_id,
            "metric_requirements": [
                requirement.as_dict() for requirement in self.metric_requirements
            ],
            "candidate_metrics": dict(self.candidate_metrics),
            "contamination_status": self.contamination_status,
            "contamination_audit_digest": self.contamination_audit_digest,
            "robustness_evidence_digest": self.robustness_evidence_digest,
            "security_evidence_digest": self.security_evidence_digest,
            "efficiency_evidence_digest": self.efficiency_evidence_digest,
            "evidence_refs": list(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class SOTAReplayRecord:
    replay_id: str
    claim_digest: str
    source_revision: str
    benchmark_digest: str
    dataset_digest: str
    verifier_id: str
    verifier_family_id: str
    observed_metrics: Mapping[str, float]
    evidence_refs: tuple[str, ...]
    passed: bool

    def __post_init__(self) -> None:
        for field in ("replay_id", "verifier_id", "verifier_family_id"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        for field in ("claim_digest", "benchmark_digest", "dataset_digest"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(
            self,
            "source_revision",
            _git_sha(self.source_revision, "source_revision"),
        )
        object.__setattr__(
            self,
            "observed_metrics",
            _metrics(self.observed_metrics, "observed_metrics"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "replay_evidence_refs", minimum=1),
        )
        if not isinstance(self.passed, bool):
            raise SOTACandidateError("passed must be boolean")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.sota_candidate.replay.v1",
            "replay_id": self.replay_id,
            "claim_digest": self.claim_digest,
            "source_revision": self.source_revision,
            "benchmark_digest": self.benchmark_digest,
            "dataset_digest": self.dataset_digest,
            "verifier_id": self.verifier_id,
            "verifier_family_id": self.verifier_family_id,
            "observed_metrics": dict(self.observed_metrics),
            "evidence_refs": list(self.evidence_refs),
            "passed": self.passed,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class SOTAQualificationReceipt:
    claim_digest: str
    replay_digest: str
    source_revision: str
    verifier_id: str
    verifier_family_id: str
    metric_ids: tuple[str, ...]
    status: str
    qualification_digest: str

    def __post_init__(self) -> None:
        for field in ("claim_digest", "replay_digest", "qualification_digest"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(
            self,
            "source_revision",
            _git_sha(self.source_revision, "source_revision"),
        )
        for field in ("verifier_id", "verifier_family_id"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        ids = tuple(_token(item, "metric_id") for item in self.metric_ids)
        if not ids or tuple(sorted(set(ids))) != ids:
            raise SOTACandidateError("metric_ids must be sorted, unique, and non-empty")
        object.__setattr__(self, "metric_ids", ids)
        if self.status != "qualified_bounded_candidate":
            raise SOTACandidateError("qualification status is invalid")

    def payload_without_digest(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.sota_candidate.qualification.v1",
            "claim_digest": self.claim_digest,
            "replay_digest": self.replay_digest,
            "source_revision": self.source_revision,
            "verifier_id": self.verifier_id,
            "verifier_family_id": self.verifier_family_id,
            "metric_ids": list(self.metric_ids),
            "status": self.status,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.payload_without_digest(),
            "qualification_digest": self.qualification_digest,
        }


class SOTACandidateGate:
    """Fail-closed qualification from claim plus exact independent replay."""

    def qualify(
        self,
        claim: SOTACandidateClaim,
        replay: SOTAReplayRecord,
    ) -> SOTAQualificationReceipt:
        if not isinstance(claim, SOTACandidateClaim):
            raise TypeError("claim must be SOTACandidateClaim")
        if not isinstance(replay, SOTAReplayRecord):
            raise TypeError("replay must be SOTAReplayRecord")
        if not replay.passed:
            raise SOTACandidateError("independent replay did not pass")
        if replay.claim_digest != claim.digest:
            raise SOTACandidateError("replay claim identity mismatch")
        if replay.source_revision != claim.source_revision:
            raise SOTACandidateError("replay source revision mismatch")
        if replay.benchmark_digest != claim.benchmark_digest:
            raise SOTACandidateError("replay benchmark digest mismatch")
        if replay.dataset_digest != claim.dataset_digest:
            raise SOTACandidateError("replay dataset digest mismatch")
        if replay.verifier_id == claim.generator_id:
            raise SOTACandidateError("candidate cannot self-verify")
        if replay.verifier_family_id == claim.generator_family_id:
            raise SOTACandidateError("verification family must be independent")
        if set(replay.observed_metrics) != set(claim.candidate_metrics):
            raise SOTACandidateError("replay metric coverage mismatch")
        if dict(replay.observed_metrics) != dict(claim.candidate_metrics):
            raise SOTACandidateError("replay metrics drift from claimed observations")

        payload = {
            "schema_version": "skeleton.sota_candidate.qualification.v1",
            "claim_digest": claim.digest,
            "replay_digest": replay.digest,
            "source_revision": claim.source_revision,
            "verifier_id": replay.verifier_id,
            "verifier_family_id": replay.verifier_family_id,
            "metric_ids": sorted(claim.candidate_metrics),
            "status": "qualified_bounded_candidate",
        }
        return SOTAQualificationReceipt(
            claim_digest=claim.digest,
            replay_digest=replay.digest,
            source_revision=claim.source_revision,
            verifier_id=replay.verifier_id,
            verifier_family_id=replay.verifier_family_id,
            metric_ids=tuple(sorted(claim.candidate_metrics)),
            status="qualified_bounded_candidate",
            qualification_digest=_digest(payload),
        )

    def verify(
        self,
        claim: SOTACandidateClaim,
        replay: SOTAReplayRecord,
        receipt: SOTAQualificationReceipt,
    ) -> None:
        if not isinstance(receipt, SOTAQualificationReceipt):
            raise TypeError("receipt must be SOTAQualificationReceipt")
        expected = self.qualify(claim, replay)
        if receipt != expected:
            raise SOTACandidateError("qualification receipt drift or tampering detected")
        if _digest(receipt.payload_without_digest()) != receipt.qualification_digest:
            raise SOTACandidateError("qualification digest mismatch")


__all__ = [
    "PROHIBITED_SHORTCUTS",
    "SOTA_CANDIDATE_CLAIM",
    "SOTA_CANDIDATE_SCHEMA",
    "SOTACandidateClaim",
    "SOTACandidateError",
    "SOTACandidateGate",
    "SOTAMetricDirection",
    "SOTAMetricRequirement",
    "SOTAQualificationReceipt",
    "SOTAReplayRecord",
]
