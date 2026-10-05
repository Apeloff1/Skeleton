"""Deterministic compliance-control registry for VOL-088.

This module models technical compliance obligations without pretending to make
legal determinations. Ambiguous legal interpretation remains review-required;
only explicitly technical, applicable requirements may be mechanically
evaluated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Iterable, Mapping

_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ComplianceError(ValueError):
    """Raised when compliance state is ambiguous, stale, or structurally unsafe."""


class Applicability(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    REVIEW_REQUIRED = "review_required"


class Interpretation(str, Enum):
    TECHNICAL = "technical"
    LEGAL_REVIEW = "legal_review"


class ControlKind(str, Enum):
    ACCESS = "access"
    DATA = "data"
    RETENTION = "retention"
    SECURITY = "security"
    EVIDENCE = "evidence"


class EvidenceStatus(str, Enum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    UNKNOWN = "unknown"


def _text(value: str, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise ComplianceError(f"{field} must be text")
    value = value.strip()
    if not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ComplianceError(f"{field} is invalid")
    return value


def _identifier(value: str, field: str) -> str:
    value = _text(value, field, maximum=128)
    if not _ID.fullmatch(value):
        raise ComplianceError(f"{field} must be a stable identifier")
    return value


def _utc(value: str, field: str) -> str:
    value = _text(value, field, maximum=64)
    if not value.endswith("Z"):
        raise ComplianceError(f"{field} must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ComplianceError(f"{field} must be RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ComplianceError(f"{field} must be UTC")
    return value


def _digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ComplianceRequirement:
    requirement_id: str
    title: str
    jurisdiction: str
    applicability: Applicability
    owner: str
    review_date: str
    interpretation: Interpretation
    source_ref: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _identifier(self.requirement_id, "requirement_id"))
        for field in ("title", "jurisdiction", "owner", "source_ref", "rationale"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        try:
            date.fromisoformat(self.review_date)
        except (TypeError, ValueError) as exc:
            raise ComplianceError("review_date must be ISO date") from exc
        if self.applicability is Applicability.APPLICABLE and self.interpretation is Interpretation.LEGAL_REVIEW:
            raise ComplianceError("legal-review requirement cannot be auto-declared applicable")

    @property
    def digest(self) -> str:
        return _digest({
            "requirement_id": self.requirement_id,
            "title": self.title,
            "jurisdiction": self.jurisdiction,
            "applicability": self.applicability.value,
            "owner": self.owner,
            "review_date": self.review_date,
            "interpretation": self.interpretation.value,
            "source_ref": self.source_ref,
            "rationale": self.rationale,
        })

    def is_stale(self, on_date: date) -> bool:
        return date.fromisoformat(self.review_date) < on_date


@dataclass(frozen=True, slots=True)
class ComplianceControl:
    control_id: str
    requirement_id: str
    kind: ControlKind
    owner: str
    implementation_ref: str
    verifier_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "control_id", _identifier(self.control_id, "control_id"))
        object.__setattr__(self, "requirement_id", _identifier(self.requirement_id, "requirement_id"))
        object.__setattr__(self, "owner", _text(self.owner, "owner"))
        object.__setattr__(self, "implementation_ref", _text(self.implementation_ref, "implementation_ref"))
        object.__setattr__(self, "verifier_id", _identifier(self.verifier_id, "verifier_id"))

    @property
    def digest(self) -> str:
        return _digest({
            "control_id": self.control_id,
            "requirement_id": self.requirement_id,
            "kind": self.kind.value,
            "owner": self.owner,
            "implementation_ref": self.implementation_ref,
            "verifier_id": self.verifier_id,
        })


@dataclass(frozen=True, slots=True)
class ComplianceEvidence:
    evidence_id: str
    requirement_id: str
    control_id: str
    verifier_id: str
    observed_at: str
    artifact_digest: str
    status: EvidenceStatus

    def __post_init__(self) -> None:
        for field in ("evidence_id", "requirement_id", "control_id", "verifier_id"):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if not isinstance(self.artifact_digest, str) or not _SHA256.fullmatch(self.artifact_digest):
            raise ComplianceError("artifact_digest must be lowercase sha256")

    @property
    def digest(self) -> str:
        return _digest({
            "evidence_id": self.evidence_id,
            "requirement_id": self.requirement_id,
            "control_id": self.control_id,
            "verifier_id": self.verifier_id,
            "observed_at": self.observed_at,
            "artifact_digest": self.artifact_digest,
            "status": self.status.value,
        })


@dataclass(frozen=True, slots=True)
class ComplianceAssessment:
    requirement_id: str
    requirement_digest: str
    control_digests: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    decision: EvidenceStatus
    reasons: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest({
            "requirement_id": self.requirement_id,
            "requirement_digest": self.requirement_digest,
            "control_digests": self.control_digests,
            "evidence_digests": self.evidence_digests,
            "decision": self.decision.value,
            "reasons": self.reasons,
        })


class ComplianceRegistry:
    """Immutable-by-identity registry with fail-closed assessment semantics."""

    def __init__(self) -> None:
        self._requirements: dict[str, ComplianceRequirement] = {}
        self._controls: dict[str, ComplianceControl] = {}
        self._evidence: dict[str, ComplianceEvidence] = {}

    def add_requirement(self, item: ComplianceRequirement) -> None:
        prior = self._requirements.get(item.requirement_id)
        if prior is not None and prior != item:
            raise ComplianceError("requirement identity is immutable")
        self._requirements[item.requirement_id] = item

    def add_control(self, item: ComplianceControl) -> None:
        requirement = self._requirements.get(item.requirement_id)
        if requirement is None:
            raise ComplianceError("control references unknown requirement")
        prior = self._controls.get(item.control_id)
        if prior is not None and prior != item:
            raise ComplianceError("control identity is immutable")
        self._controls[item.control_id] = item

    def add_evidence(self, item: ComplianceEvidence) -> None:
        requirement = self._requirements.get(item.requirement_id)
        control = self._controls.get(item.control_id)
        if requirement is None or control is None:
            raise ComplianceError("evidence references unknown requirement/control")
        if control.requirement_id != item.requirement_id:
            raise ComplianceError("evidence crosses requirement boundary")
        if control.verifier_id != item.verifier_id:
            raise ComplianceError("evidence verifier does not own control verification")
        prior = self._evidence.get(item.evidence_id)
        if prior is not None and prior != item:
            raise ComplianceError("evidence identity is immutable")
        self._evidence[item.evidence_id] = item

    def assess(self, requirement_id: str, *, on_date: date) -> ComplianceAssessment:
        requirement = self._requirements.get(requirement_id)
        if requirement is None:
            raise ComplianceError("unknown requirement")
        reasons: list[str] = []
        if requirement.applicability is Applicability.NOT_APPLICABLE:
            return ComplianceAssessment(requirement_id, requirement.digest, (), (), EvidenceStatus.SATISFIED, ("explicitly_not_applicable",))
        if requirement.applicability is Applicability.REVIEW_REQUIRED or requirement.interpretation is Interpretation.LEGAL_REVIEW:
            reasons.append("legal_or_applicability_review_required")
        if requirement.is_stale(on_date):
            reasons.append("requirement_review_expired")

        controls = sorted((c for c in self._controls.values() if c.requirement_id == requirement_id), key=lambda c: c.control_id)
        if not controls:
            reasons.append("no_controls")

        selected: list[ComplianceEvidence] = []
        for control in controls:
            matches = sorted(
                (e for e in self._evidence.values() if e.control_id == control.control_id),
                key=lambda e: (e.observed_at, e.evidence_id),
            )
            if not matches:
                reasons.append(f"missing_evidence:{control.control_id}")
                continue
            latest = matches[-1]
            selected.append(latest)
            if latest.status is not EvidenceStatus.SATISFIED:
                reasons.append(f"evidence_{latest.status.value}:{control.control_id}")

        decision = EvidenceStatus.SATISFIED if not reasons else (
            EvidenceStatus.FAILED if any(r.startswith("evidence_failed:") for r in reasons) else EvidenceStatus.UNKNOWN
        )
        return ComplianceAssessment(
            requirement_id=requirement_id,
            requirement_digest=requirement.digest,
            control_digests=tuple(c.digest for c in controls),
            evidence_digests=tuple(e.digest for e in selected),
            decision=decision,
            reasons=tuple(sorted(reasons)),
        )

    def inventory_digest(self) -> str:
        return _digest({
            "requirements": [r.digest for r in sorted(self._requirements.values(), key=lambda x: x.requirement_id)],
            "controls": [c.digest for c in sorted(self._controls.values(), key=lambda x: x.control_id)],
            "evidence": [e.digest for e in sorted(self._evidence.values(), key=lambda x: x.evidence_id)],
        })
