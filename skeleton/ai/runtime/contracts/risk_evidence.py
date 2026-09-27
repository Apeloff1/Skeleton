"""Fail-closed P1 risk/gap evidence binding contracts.

This module evaluates evidence and accepted-risk dispositions for immutable risk
obligations. It never mutates source risk state and never grants maturity or
promotion authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable

from .canonical import EvidenceRef, evidence_ref_identity


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
MAX_RISK_EVIDENCE_REFS = 128
ACCEPTED_RISK_SIGNER_TYPES = frozenset({"human", "governance"})
ACCEPTED_RISK_SIGNATURE_METHODS = frozenset(
    {"github_identity", "contract_attestation"}
)


class RiskEvidenceError(ValueError):
    """Risk-evidence input is malformed."""


class RiskKind(str, Enum):
    RISK = "risk"
    GAP = "gap"
    ADVERSARIAL = "adversarial"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNCLASSIFIED = "unclassified"


class RiskDisposition(str, Enum):
    EVIDENCE = "evidence"
    ACCEPTED_RISK = "accepted_risk"
    NON_BLOCKING = "non_blocking"


def canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value:
        raise RiskEvidenceError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise RiskEvidenceError(f"{field} must be normalized")
    if len(value) > max_length:
        raise RiskEvidenceError(f"{field} exceeds maximum length")
    return value


def _token(value: object, field: str, *, max_length: int = 256) -> str:
    text = _text(value, field, max_length=max_length)
    if not _TOKEN_RE.fullmatch(text):
        raise RiskEvidenceError(f"{field} must be a canonical token")
    return text


def _sha(value: object, field: str) -> str:
    text = _text(value, field, max_length=40)
    if not _SHA_RE.fullmatch(text):
        raise RiskEvidenceError(
            f"{field} must be a lowercase 40-character git SHA"
        )
    return text


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, max_length=64)
    if not _SHA256_RE.fullmatch(text):
        raise RiskEvidenceError(f"{field} must be lowercase sha256")
    return text


def _utc(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise RiskEvidenceError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def make_obligation_id(
    kind: RiskKind | str,
    source_ref: str,
    statement: str,
) -> str:
    try:
        normalized_kind = RiskKind(kind)
    except ValueError as exc:
        raise RiskEvidenceError("invalid risk kind") from exc
    source = _token(source_ref, "source_ref", max_length=256)
    text = _text(statement, "statement", max_length=4096)
    suffix = canonical_digest(
        {
            "kind": normalized_kind.value,
            "source_ref": source,
            "statement": text,
        }
    )[:16]
    return f"P1-{normalized_kind.value.upper()}-{source}-{suffix}"


def _normalize_evidence(
    evidence: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if isinstance(evidence, (str, bytes)):
        raise RiskEvidenceError("evidence must contain EvidenceRef values")
    by_identity: dict[str, EvidenceRef] = {}
    for item in evidence:
        if not isinstance(item, EvidenceRef):
            raise RiskEvidenceError("evidence must contain EvidenceRef values")
        source = _text(item.source, "evidence.source")
        if source.startswith("planned:"):
            raise RiskEvidenceError(
                "risk evidence source must be materialized, not planned"
            )
        _sha256(item.digest, "evidence.digest")
        _token(item.category, "evidence.category", max_length=128)
        by_identity[evidence_ref_identity(item)] = item
        if len(by_identity) > MAX_RISK_EVIDENCE_REFS:
            raise RiskEvidenceError("risk evidence reference budget exceeded")
    return tuple(by_identity[key] for key in sorted(by_identity))


@dataclass(frozen=True, slots=True)
class RiskObligation:
    obligation_id: str
    kind: RiskKind
    source_ref: str
    statement: str
    source_digest: str
    default_severity: RiskSeverity
    blocking_by_default: bool
    required_evidence_modes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            _token(self.obligation_id, "obligation_id", max_length=320),
        )
        try:
            object.__setattr__(self, "kind", RiskKind(self.kind))
            object.__setattr__(
                self,
                "default_severity",
                RiskSeverity(self.default_severity),
            )
        except ValueError as exc:
            raise RiskEvidenceError("invalid obligation enum value") from exc
        object.__setattr__(
            self,
            "source_ref",
            _token(self.source_ref, "source_ref", max_length=256),
        )
        object.__setattr__(
            self,
            "statement",
            _text(self.statement, "statement", max_length=4096),
        )
        object.__setattr__(
            self,
            "source_digest",
            _sha256(self.source_digest, "source_digest"),
        )
        if not isinstance(self.blocking_by_default, bool):
            raise RiskEvidenceError("blocking_by_default must be boolean")
        modes = tuple(
            dict.fromkeys(
                _token(item, "required_evidence_modes", max_length=128)
                for item in self.required_evidence_modes
            )
        )
        object.__setattr__(self, "required_evidence_modes", modes)
        expected_id = make_obligation_id(
            self.kind,
            self.source_ref,
            self.statement,
        )
        if self.obligation_id != expected_id:
            raise RiskEvidenceError("obligation_id does not match source identity")

    @property
    def obligation_digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "kind": self.kind.value,
            "source_ref": self.source_ref,
            "statement": self.statement,
            "source_digest": self.source_digest,
            "default_severity": self.default_severity.value,
            "blocking_by_default": self.blocking_by_default,
            "required_evidence_modes": list(self.required_evidence_modes),
        }


@dataclass(frozen=True, slots=True)
class AcceptedRisk:
    obligation_id: str
    obligation_digest: str
    owner_id: str
    severity: RiskSeverity
    accepted_at: datetime
    review_at: datetime
    expires_at: datetime
    signer_id: str
    signer_type: str
    git_sha: str
    signature_method: str
    signature_ref: str
    statement: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            _token(self.obligation_id, "obligation_id", max_length=320),
        )
        object.__setattr__(
            self,
            "obligation_digest",
            _sha256(self.obligation_digest, "obligation_digest"),
        )
        object.__setattr__(
            self,
            "owner_id",
            _token(self.owner_id, "owner_id", max_length=256),
        )
        try:
            severity = RiskSeverity(self.severity)
        except ValueError as exc:
            raise RiskEvidenceError("invalid accepted-risk severity") from exc
        if severity not in {RiskSeverity.HIGH, RiskSeverity.CRITICAL}:
            raise RiskEvidenceError(
                "accepted risk is only valid for high/critical severity"
            )
        object.__setattr__(self, "severity", severity)
        accepted = _utc(self.accepted_at, "accepted_at")
        review = _utc(self.review_at, "review_at")
        expires = _utc(self.expires_at, "expires_at")
        if not accepted < review <= expires:
            raise RiskEvidenceError(
                "accepted risk requires accepted_at < review_at <= expires_at"
            )
        object.__setattr__(self, "accepted_at", accepted)
        object.__setattr__(self, "review_at", review)
        object.__setattr__(self, "expires_at", expires)
        for field in ("signer_id", "signer_type", "signature_method"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field, max_length=256),
            )
        if self.signer_type not in ACCEPTED_RISK_SIGNER_TYPES:
            raise RiskEvidenceError(
                "accepted risk requires a human/governance signer"
            )
        if self.signature_method not in ACCEPTED_RISK_SIGNATURE_METHODS:
            raise RiskEvidenceError(
                "accepted risk signature method is not approved"
            )
        object.__setattr__(self, "git_sha", _sha(self.git_sha, "git_sha"))
        object.__setattr__(
            self,
            "signature_ref",
            _text(self.signature_ref, "signature_ref", max_length=2048),
        )
        object.__setattr__(
            self,
            "statement",
            _text(self.statement, "statement", max_length=4096),
        )

    def valid_at(self, when: datetime) -> bool:
        now = _utc(when, "when")
        return (
            self.accepted_at <= now <= self.review_at
            and now < self.expires_at
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "obligation_digest": self.obligation_digest,
            "owner_id": self.owner_id,
            "severity": self.severity.value,
            "accepted_at": self.accepted_at.isoformat().replace("+00:00", "Z"),
            "review_at": self.review_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "signer_id": self.signer_id,
            "signer_type": self.signer_type,
            "git_sha": self.git_sha,
            "signature_method": self.signature_method,
            "signature_ref": self.signature_ref,
            "statement": self.statement,
        }


@dataclass(frozen=True, slots=True)
class RiskEvidenceBinding:
    obligation_id: str
    obligation_digest: str
    owner_id: str
    severity: RiskSeverity
    disposition: RiskDisposition
    bound_at: datetime
    review_at: datetime
    evidence: tuple[EvidenceRef, ...] = ()
    accepted_risk: AcceptedRisk | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            _token(self.obligation_id, "obligation_id", max_length=320),
        )
        object.__setattr__(
            self,
            "obligation_digest",
            _sha256(self.obligation_digest, "obligation_digest"),
        )
        object.__setattr__(
            self,
            "owner_id",
            _token(self.owner_id, "owner_id", max_length=256),
        )
        try:
            severity = RiskSeverity(self.severity)
            disposition = RiskDisposition(self.disposition)
        except ValueError as exc:
            raise RiskEvidenceError("invalid binding enum value") from exc
        if severity is RiskSeverity.UNCLASSIFIED:
            raise RiskEvidenceError("binding severity must be classified")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "disposition", disposition)
        bound = _utc(self.bound_at, "bound_at")
        review = _utc(self.review_at, "review_at")
        if review <= bound:
            raise RiskEvidenceError("review_at must be after bound_at")
        object.__setattr__(self, "bound_at", bound)
        object.__setattr__(self, "review_at", review)
        evidence = _normalize_evidence(self.evidence)
        object.__setattr__(self, "evidence", evidence)

        if disposition is RiskDisposition.EVIDENCE:
            if not evidence:
                raise RiskEvidenceError("evidence disposition requires evidence")
            if self.accepted_risk is not None:
                raise RiskEvidenceError(
                    "evidence disposition cannot contain accepted_risk"
                )
        elif disposition is RiskDisposition.ACCEPTED_RISK:
            if self.accepted_risk is None:
                raise RiskEvidenceError(
                    "accepted_risk disposition requires accepted_risk"
                )
            if evidence:
                raise RiskEvidenceError(
                    "accepted_risk disposition uses acceptance, not evidence"
                )
        elif disposition is RiskDisposition.NON_BLOCKING:
            if severity not in {RiskSeverity.LOW, RiskSeverity.MEDIUM}:
                raise RiskEvidenceError(
                    "non_blocking requires low/medium severity"
                )
            if evidence or self.accepted_risk is not None:
                raise RiskEvidenceError(
                    "non_blocking disposition cannot contain evidence/acceptance"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "obligation_digest": self.obligation_digest,
            "owner_id": self.owner_id,
            "severity": self.severity.value,
            "disposition": self.disposition.value,
            "bound_at": self.bound_at.isoformat().replace("+00:00", "Z"),
            "review_at": self.review_at.isoformat().replace("+00:00", "Z"),
            "evidence": [
                {
                    "identity": evidence_ref_identity(item),
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence
            ],
            "accepted_risk": (
                self.accepted_risk.as_dict()
                if self.accepted_risk is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class RiskBindingEvaluation:
    obligation_id: str
    obligation_digest: str
    resolved: bool
    blocking: bool
    severity: str
    disposition: str | None
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "obligation_digest": self.obligation_digest,
            "resolved": self.resolved,
            "blocking": self.blocking,
            "severity": self.severity,
            "disposition": self.disposition,
            "blockers": list(self.blockers),
        }


def evaluate_risk_binding(
    obligation: RiskObligation,
    binding: RiskEvidenceBinding | None,
    *,
    evaluated_at: datetime,
) -> RiskBindingEvaluation:
    now = _utc(evaluated_at, "evaluated_at")
    default_severity = obligation.default_severity
    default_blocking = obligation.blocking_by_default or (
        default_severity
        in {
            RiskSeverity.UNCLASSIFIED,
            RiskSeverity.HIGH,
            RiskSeverity.CRITICAL,
        }
    )
    if binding is None:
        reason = (
            "classification and binding required"
            if default_severity is RiskSeverity.UNCLASSIFIED
            else "binding required"
        )
        return RiskBindingEvaluation(
            obligation_id=obligation.obligation_id,
            obligation_digest=obligation.obligation_digest,
            resolved=False,
            blocking=default_blocking,
            severity=default_severity.value,
            disposition=None,
            blockers=(reason,),
        )

    blockers: list[str] = []
    if binding.obligation_id != obligation.obligation_id:
        blockers.append("binding obligation_id mismatch")
    if binding.obligation_digest != obligation.obligation_digest:
        blockers.append("binding obligation_digest mismatch")
    if now > binding.review_at:
        blockers.append("binding review is overdue")

    if (
        obligation.kind in {RiskKind.GAP, RiskKind.ADVERSARIAL}
        and binding.disposition is RiskDisposition.NON_BLOCKING
    ):
        blockers.append(
            "gap/adversarial obligations cannot be declared non-blocking"
        )

    if (
        binding.disposition is RiskDisposition.EVIDENCE
        and obligation.required_evidence_modes
    ):
        categories = {item.category for item in binding.evidence}
        missing_modes = sorted(
            set(obligation.required_evidence_modes) - categories
        )
        if missing_modes:
            blockers.append(
                "required evidence modes missing: " + ",".join(missing_modes)
            )

    if binding.disposition is RiskDisposition.ACCEPTED_RISK:
        accepted = binding.accepted_risk
        if accepted is None:
            blockers.append("accepted-risk record is missing")
        else:
            if accepted.obligation_id != obligation.obligation_id:
                blockers.append("accepted-risk obligation_id mismatch")
            if accepted.obligation_digest != obligation.obligation_digest:
                blockers.append("accepted-risk obligation_digest mismatch")
            if accepted.owner_id != binding.owner_id:
                blockers.append("accepted-risk owner mismatch")
            if accepted.severity != binding.severity:
                blockers.append("accepted-risk severity mismatch")
            if not accepted.valid_at(now):
                blockers.append("accepted-risk review/expiry is stale")

    blocking = (
        obligation.blocking_by_default
        or binding.severity in {RiskSeverity.HIGH, RiskSeverity.CRITICAL}
    )
    if (
        binding.disposition is RiskDisposition.NON_BLOCKING
        and obligation.kind is RiskKind.RISK
    ):
        blocking = False

    return RiskBindingEvaluation(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        resolved=not blockers,
        blocking=blocking,
        severity=binding.severity.value,
        disposition=binding.disposition.value,
        blockers=tuple(sorted(set(blockers))),
    )
