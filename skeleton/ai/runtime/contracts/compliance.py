"""Deterministic, evidence-bound compliance contracts for VOL-088.

This module is a technical compliance control plane, not a legal decision
engine. Legal interpretation remains an explicit reviewed input. Automated
assessment may only evaluate controls whose applicability has been reviewed
and whose review is still current.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable

COMPLIANCE_SCHEMA = "skeleton.contracts.compliance.v1"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_REQUIREMENTS = 4096
_MAX_CONTROLS = 4096
_MAX_EVIDENCE_PER_CONTROL = 4096
_MAX_REVIEW_SECONDS = 31_536_000


class ComplianceError(ValueError):
    """Raised when compliance state is ambiguous, stale, or non-canonical."""


class RequirementDisposition(str, Enum):
    REQUIRED = "required"
    NOT_APPLICABLE = "not_applicable"


class InterpretationAuthority(str, Enum):
    HUMAN_LEGAL_REVIEW = "human_legal_review"
    POLICY_OWNER_REVIEW = "policy_owner_review"


class EnforcementMode(str, Enum):
    TECHNICAL = "technical"
    REVIEW_ONLY = "review_only"


class ControlKind(str, Enum):
    ACCESS = "access"
    DATA = "data"
    RETENTION = "retention"
    SECURITY = "security"
    EVIDENCE = "evidence"


class EvidenceResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class ControlStatus(str, Enum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_STALE = "evidence_stale"
    APPLICABILITY_STALE = "applicability_stale"
    REVIEW_REQUIRED = "review_required"
    NOT_APPLICABLE = "not_applicable"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ComplianceError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, max_length: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > max_length
    ):
        raise ComplianceError(f"{field} must be bounded canonical text")
    return value


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ComplianceError(f"{field} must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        raise ComplianceError(f"{field} must use whole-second precision")
    return normalized


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ComplianceError(f"{field} must be lowercase sha256")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ComplianceError("value must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ComplianceRequirement:
    requirement_id: str
    source: str
    jurisdiction: str
    statement: str
    owner: str
    legal_reviewer: str
    reviewed_at: datetime
    review_ttl_seconds: int
    disposition: RequirementDisposition = RequirementDisposition.REQUIRED
    applicability_reason: str = "in-scope"
    interpretation_authority: InterpretationAuthority = (
        InterpretationAuthority.HUMAN_LEGAL_REVIEW
    )

    def __post_init__(self) -> None:
        for field in (
            "requirement_id",
            "source",
            "jurisdiction",
            "owner",
            "legal_reviewer",
        ):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        object.__setattr__(
            self,
            "applicability_reason",
            _text(self.applicability_reason, "applicability_reason"),
        )
        object.__setattr__(self, "reviewed_at", _utc(self.reviewed_at, "reviewed_at"))
        if (
            isinstance(self.review_ttl_seconds, bool)
            or not isinstance(self.review_ttl_seconds, int)
            or not 1 <= self.review_ttl_seconds <= _MAX_REVIEW_SECONDS
        ):
            raise ComplianceError("review_ttl_seconds is outside policy bounds")
        if not isinstance(self.disposition, RequirementDisposition):
            raise ComplianceError("invalid requirement disposition")
        if not isinstance(self.interpretation_authority, InterpretationAuthority):
            raise ComplianceError("invalid interpretation authority")

    def review_is_current(self, at: datetime) -> bool:
        now = _utc(at, "assessment time")
        if self.reviewed_at > now:
            return False
        return (now - self.reviewed_at).total_seconds() <= self.review_ttl_seconds

    @property
    def digest(self) -> str:
        return _digest(
            [
                COMPLIANCE_SCHEMA,
                self.requirement_id,
                self.source,
                self.jurisdiction,
                self.statement,
                self.owner,
                self.legal_reviewer,
                self.reviewed_at.isoformat(),
                self.review_ttl_seconds,
                self.disposition.value,
                self.applicability_reason,
                self.interpretation_authority.value,
            ]
        )


@dataclass(frozen=True, slots=True)
class ComplianceControl:
    control_id: str
    owner: str
    requirement_ids: tuple[str, ...]
    evidence_ttl_seconds: int
    description: str
    kind: ControlKind
    implementation_ref: str
    verifier_id: str
    enforcement_mode: EnforcementMode = EnforcementMode.TECHNICAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "control_id", _token(self.control_id, "control_id"))
        object.__setattr__(self, "owner", _token(self.owner, "owner"))
        if (
            not isinstance(self.requirement_ids, tuple)
            or not self.requirement_ids
            or len(self.requirement_ids) > 256
        ):
            raise ComplianceError("bounded requirement tuple required")
        ids = tuple(sorted(_token(item, "requirement_id") for item in self.requirement_ids))
        if len(ids) != len(set(ids)):
            raise ComplianceError("duplicate requirement mapping")
        object.__setattr__(self, "requirement_ids", ids)
        if (
            isinstance(self.evidence_ttl_seconds, bool)
            or not isinstance(self.evidence_ttl_seconds, int)
            or not 1 <= self.evidence_ttl_seconds <= _MAX_REVIEW_SECONDS
        ):
            raise ComplianceError("evidence_ttl_seconds is outside policy bounds")
        object.__setattr__(
            self, "description", _text(self.description, "description")
        )
        if not isinstance(self.kind, ControlKind):
            raise ComplianceError("invalid control kind")
        object.__setattr__(
            self,
            "implementation_ref",
            _token(self.implementation_ref, "implementation_ref"),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _token(self.verifier_id, "verifier_id"),
        )
        if not isinstance(self.enforcement_mode, EnforcementMode):
            raise ComplianceError("invalid enforcement mode")

    @property
    def digest(self) -> str:
        return _digest(
            [
                COMPLIANCE_SCHEMA,
                self.control_id,
                self.owner,
                self.requirement_ids,
                self.evidence_ttl_seconds,
                self.description,
                self.kind.value,
                self.implementation_ref,
                self.verifier_id,
                self.enforcement_mode.value,
            ]
        )


@dataclass(frozen=True, slots=True)
class ComplianceEvidence:
    evidence_id: str
    control_id: str
    control_digest: str
    owner: str
    verifier_id: str
    artifact_digest: str
    observed_at: datetime
    result: EvidenceResult

    def __post_init__(self) -> None:
        for field in ("evidence_id", "control_id", "owner", "verifier_id"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        object.__setattr__(
            self, "control_digest", _sha(self.control_digest, "control_digest")
        )
        object.__setattr__(
            self, "artifact_digest", _sha(self.artifact_digest, "artifact_digest")
        )
        object.__setattr__(
            self, "observed_at", _utc(self.observed_at, "observed_at")
        )
        if not isinstance(self.result, EvidenceResult):
            raise ComplianceError("invalid evidence result")

    @property
    def digest(self) -> str:
        return _digest(
            [
                COMPLIANCE_SCHEMA,
                self.evidence_id,
                self.control_id,
                self.control_digest,
                self.owner,
                self.verifier_id,
                self.artifact_digest,
                self.observed_at.isoformat(),
                self.result.value,
            ]
        )


@dataclass(frozen=True, slots=True)
class ControlAssessment:
    control_id: str
    status: ControlStatus
    evidence_digest: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ComplianceAssessment:
    registry_digest: str
    assessed_at: datetime
    controls: tuple[ControlAssessment, ...]

    @property
    def compliant(self) -> bool:
        return bool(self.controls) and all(
            item.status in (ControlStatus.SATISFIED, ControlStatus.NOT_APPLICABLE)
            for item in self.controls
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                COMPLIANCE_SCHEMA,
                self.registry_digest,
                self.assessed_at.isoformat(),
                [
                    (
                        item.control_id,
                        item.status.value,
                        item.evidence_digest,
                        item.reason,
                    )
                    for item in self.controls
                ],
            ]
        )


class ComplianceRegistry:
    """Immutable requirement/control registry with fail-closed assessment."""

    def __init__(
        self,
        requirements: Iterable[ComplianceRequirement],
        controls: Iterable[ComplianceControl],
    ) -> None:
        self.requirements = tuple(
            sorted(requirements, key=lambda item: item.requirement_id)
        )
        self.controls = tuple(sorted(controls, key=lambda item: item.control_id))
        if (
            not self.requirements
            or not self.controls
            or len(self.requirements) > _MAX_REQUIREMENTS
            or len(self.controls) > _MAX_CONTROLS
        ):
            raise ComplianceError("registry size is outside policy bounds")
        if len({item.requirement_id for item in self.requirements}) != len(
            self.requirements
        ):
            raise ComplianceError("duplicate requirement id")
        if len({item.control_id for item in self.controls}) != len(self.controls):
            raise ComplianceError("duplicate control id")

        known = {item.requirement_id for item in self.requirements}
        covered: set[str] = set()
        for control in self.controls:
            unknown = set(control.requirement_ids) - known
            if unknown:
                raise ComplianceError("control references unknown requirement")
            covered.update(control.requirement_ids)

        required = {
            item.requirement_id
            for item in self.requirements
            if item.disposition is RequirementDisposition.REQUIRED
        }
        if required - covered:
            raise ComplianceError("required requirement lacks control")

    @property
    def digest(self) -> str:
        return _digest(
            [
                COMPLIANCE_SCHEMA,
                [item.digest for item in self.requirements],
                [item.digest for item in self.controls],
            ]
        )

    def assess(
        self,
        evidence: Iterable[ComplianceEvidence],
        *,
        at: datetime,
    ) -> ComplianceAssessment:
        now = _utc(at, "assessment time")
        by_control: dict[str, list[ComplianceEvidence]] = {}
        evidence_ids: set[str] = set()
        for item in evidence:
            if item.evidence_id in evidence_ids:
                raise ComplianceError("duplicate evidence id")
            evidence_ids.add(item.evidence_id)
            bucket = by_control.setdefault(item.control_id, [])
            bucket.append(item)
            if len(bucket) > _MAX_EVIDENCE_PER_CONTROL:
                raise ComplianceError("evidence set exceeds policy bound")

        known_controls = {item.control_id for item in self.controls}
        if set(by_control) - known_controls:
            raise ComplianceError("evidence references unknown control")

        requirements = {
            item.requirement_id: item for item in self.requirements
        }
        assessments: list[ControlAssessment] = []

        for control in self.controls:
            linked = [requirements[item] for item in control.requirement_ids]

            if any(not item.review_is_current(now) for item in linked):
                assessments.append(
                    ControlAssessment(
                        control.control_id,
                        ControlStatus.APPLICABILITY_STALE,
                        None,
                        "linked requirement applicability review is stale or future-dated",
                    )
                )
                continue

            applicable = [
                item
                for item in linked
                if item.disposition is RequirementDisposition.REQUIRED
            ]
            if not applicable:
                assessments.append(
                    ControlAssessment(
                        control.control_id,
                        ControlStatus.NOT_APPLICABLE,
                        None,
                        "all linked requirements are currently reviewed as not applicable",
                    )
                )
                continue

            if control.enforcement_mode is EnforcementMode.REVIEW_ONLY:
                assessments.append(
                    ControlAssessment(
                        control.control_id,
                        ControlStatus.REVIEW_REQUIRED,
                        None,
                        "legal/policy interpretation is review-only and cannot be auto-satisfied",
                    )
                )
                continue

            candidates = by_control.get(control.control_id, ())
            identity_bound = [
                item
                for item in candidates
                if item.control_digest == control.digest
                and item.owner == control.owner
                and item.verifier_id == control.verifier_id
                and item.observed_at <= now
            ]
            if not identity_bound:
                assessments.append(
                    ControlAssessment(
                        control.control_id,
                        ControlStatus.EVIDENCE_MISSING,
                        None,
                        "no current identity-bound evidence",
                    )
                )
                continue

            latest_at = max(item.observed_at for item in identity_bound)
            latest_cohort = tuple(
                item for item in identity_bound
                if item.observed_at == latest_at
            )
            latest = max(latest_cohort, key=lambda item: item.digest)
            age = (now - latest_at).total_seconds()
            if age > control.evidence_ttl_seconds:
                status = ControlStatus.EVIDENCE_STALE
                reason = "evidence exceeded freshness policy"
            elif any(item.result is EvidenceResult.FAIL for item in latest_cohort):
                status = ControlStatus.FAILED
                reason = "latest identity-bound evidence cohort contains failure"
            else:
                status = ControlStatus.SATISFIED
                reason = "fresh identity-bound evidence cohort passed"

            assessments.append(
                ControlAssessment(
                    control.control_id,
                    status,
                    latest.digest,
                    reason,
                )
            )

        return ComplianceAssessment(self.digest, now, tuple(assessments))
