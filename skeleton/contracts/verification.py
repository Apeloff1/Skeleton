"""Observable verification contracts for candidate AI results.

These records capture claims, evidence, postconditions, policy levels, and
receipts. They deliberately exclude hidden chain-of-thought or private model
reasoning; verification evidence must be externally observable and replayable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


VERIFICATION_SCHEMA_VERSION = 1
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class VerificationContractError(ValueError):
    """A verification contract is malformed."""


class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationLevel(str, Enum):
    NONE = "none"
    STRUCTURAL = "structural"
    EVIDENCE = "evidence"
    ACTION = "action"
    HIGH_IMPACT = "high_impact"


class VerificationOutcome(str, Enum):
    VERIFIED = "verified"
    QUALIFIED = "qualified"
    ABSTAIN = "abstain"
    REPAIR = "repair"
    BLOCK = "block"


class ConfidenceBand(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ClaimKind(str, Enum):
    FACTUAL = "factual"
    COMPUTATION = "computation"
    ACTION = "action"
    INTERPRETATION = "interpretation"


def _text(
    value: object,
    field_name: str,
    *,
    max_length: int = 4096,
    optional: bool = False,
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise VerificationContractError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        if optional:
            return None
        raise VerificationContractError(f"{field_name} must be non-empty")
    if normalized != value:
        raise VerificationContractError(f"{field_name} must be normalized")
    if len(normalized) > max_length:
        raise VerificationContractError(f"{field_name} exceeds maximum length")
    return normalized


def _aware(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise VerificationContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _json_object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise VerificationContractError(f"{field_name} must be an object")
    normalized = dict(value)
    try:
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise VerificationContractError(
            f"{field_name} must be deterministic JSON"
        ) from exc
    if len(encoded.encode("utf-8")) > 512 * 1024:
        raise VerificationContractError(f"{field_name} exceeds maximum size")
    return normalized


def _refs(values: Iterable[str], field_name: str, *, maximum: int) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise VerificationContractError(f"{field_name} must be an iterable")
    result: list[str] = []
    for raw in values:
        item = _text(raw, field_name, max_length=2048)
        assert item is not None
        if item not in result:
            result.append(item)
        if len(result) > maximum:
            raise VerificationContractError(f"{field_name} exceeds maximum count")
    return tuple(result)


def content_digest(content: str) -> str:
    if not isinstance(content, str):
        raise VerificationContractError("content must be text")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    source_type: str
    source_id: str
    content_digest: str
    provenance: Mapping[str, Any]
    observed_at: datetime
    authority_class: str
    citation_metadata: Mapping[str, Any] = field(default_factory=dict)
    tenant_id: str | None = None
    data_class: str = "internal"
    source_version: str | None = None
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.evidence_id, "evidence_id", max_length=192)
        _text(self.source_type, "source_type", max_length=128)
        _text(self.source_id, "source_id", max_length=2048)
        digest = _text(self.content_digest, "content_digest", max_length=64)
        assert digest is not None
        if _DIGEST.fullmatch(digest) is None:
            raise VerificationContractError(
                "content_digest must be lowercase sha256"
            )
        object.__setattr__(
            self, "provenance", _json_object(self.provenance, "provenance")
        )
        object.__setattr__(
            self,
            "citation_metadata",
            _json_object(self.citation_metadata, "citation_metadata"),
        )
        object.__setattr__(
            self, "observed_at", _aware(self.observed_at, "observed_at")
        )
        _text(self.authority_class, "authority_class", max_length=128)
        if self.tenant_id is not None:
            _text(self.tenant_id, "tenant_id", max_length=192)
        if self.source_version is not None:
            _text(self.source_version, "source_version", max_length=256)
        normalized_class = str(self.data_class).strip().lower()
        if normalized_class not in {
            "public",
            "internal",
            "confidential",
            "restricted",
        }:
            raise VerificationContractError("data_class is invalid")
        object.__setattr__(self, "data_class", normalized_class)
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError(
                "unsupported verification schema version"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "content_digest": self.content_digest,
            "provenance": dict(self.provenance),
            "tenant_id": self.tenant_id,
            "data_class": self.data_class,
            "source_version": self.source_version,
            "observed_at": self.observed_at.isoformat(),
            "authority_class": self.authority_class,
            "citation_metadata": dict(self.citation_metadata),
        }


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    text: str
    kind: ClaimKind = ClaimKind.FACTUAL
    evidence_refs: tuple[str, ...] = ()
    citation_refs: tuple[str, ...] = ()
    required: bool = True
    claim_digest: str | None = None
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.claim_id, "claim_id", max_length=192)
        _text(self.text, "claim text", max_length=100_000)
        try:
            object.__setattr__(self, "kind", ClaimKind(self.kind))
        except ValueError as exc:
            raise VerificationContractError("claim kind is invalid") from exc
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "evidence_refs", maximum=4096),
        )
        object.__setattr__(
            self,
            "citation_refs",
            _refs(self.citation_refs, "citation_refs", maximum=4096),
        )
        if not isinstance(self.required, bool):
            raise VerificationContractError("required must be boolean")
        digest = content_digest(self.text)
        if self.claim_digest is not None and self.claim_digest != digest:
            raise VerificationContractError(
                "claim_digest does not match claim text"
            )
        object.__setattr__(self, "claim_digest", digest)
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError(
                "unsupported verification schema version"
            )


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    claim_id: str
    grounded: bool
    citation_valid: bool
    evidence_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.claim_id, "claim_id", max_length=192)
        if not isinstance(self.grounded, bool) or not isinstance(
            self.citation_valid, bool
        ):
            raise VerificationContractError(
                "claim check booleans are invalid"
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "evidence_refs", maximum=4096),
        )
        object.__setattr__(
            self,
            "reason_codes",
            _refs(self.reason_codes, "reason_codes", maximum=256),
        )

    @property
    def passed(self) -> bool:
        return self.grounded and self.citation_valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "grounded": self.grounded,
            "citation_valid": self.citation_valid,
            "evidence_refs": list(self.evidence_refs),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class PostconditionCheck:
    check_id: str
    subject_ref: str
    passed: bool
    reason_code: str
    evidence_refs: tuple[str, ...] = ()
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.check_id, "check_id", max_length=192)
        _text(self.subject_ref, "subject_ref", max_length=2048)
        if not isinstance(self.passed, bool):
            raise VerificationContractError("passed must be boolean")
        _text(self.reason_code, "reason_code", max_length=256)
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "evidence_refs", maximum=1024),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "subject_ref": self.subject_ref,
            "passed": self.passed,
            "reason_code": self.reason_code,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    verification_id: str
    operation_id: str
    execution_id: str
    turn_id: str
    capability: str
    risk_class: RiskClass
    required_level: VerificationLevel
    candidate_ref: str
    context_snapshot_id: str
    evidence_refs: tuple[str, ...] = ()
    tool_receipt_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    budget: Mapping[str, Any] = field(default_factory=dict)
    deadline: datetime | None = None
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "verification_id",
            "operation_id",
            "execution_id",
            "turn_id",
            "capability",
            "candidate_ref",
            "context_snapshot_id",
        ):
            _text(getattr(self, name), name, max_length=2048)
        try:
            object.__setattr__(self, "risk_class", RiskClass(self.risk_class))
            object.__setattr__(
                self,
                "required_level",
                VerificationLevel(self.required_level),
            )
        except ValueError as exc:
            raise VerificationContractError(
                "verification request enum is invalid"
            ) from exc
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "evidence_refs", maximum=4096),
        )
        object.__setattr__(
            self,
            "tool_receipt_refs",
            _refs(
                self.tool_receipt_refs,
                "tool_receipt_refs",
                maximum=2048,
            ),
        )
        object.__setattr__(
            self,
            "artifact_refs",
            _refs(self.artifact_refs, "artifact_refs", maximum=1024),
        )
        object.__setattr__(self, "budget", _json_object(self.budget, "budget"))
        if self.deadline is not None:
            object.__setattr__(
                self, "deadline", _aware(self.deadline, "deadline")
            )
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError(
                "unsupported verification schema version"
            )


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    verification_id: str
    operation_id: str
    execution_id: str
    turn_id: str
    candidate_ref: str
    level: VerificationLevel
    outcome: VerificationOutcome
    reason_codes: tuple[str, ...]
    claim_checks: tuple[ClaimCheck, ...]
    postcondition_checks: tuple[PostconditionCheck, ...]
    evidence_refs: tuple[str, ...]
    verifier_route_refs: tuple[str, ...] = ()
    repair_directive: Mapping[str, Any] | None = None
    confidence_band: ConfidenceBand = ConfidenceBand.UNKNOWN
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "verification_id",
            "operation_id",
            "execution_id",
            "turn_id",
            "candidate_ref",
        ):
            _text(getattr(self, name), name, max_length=2048)
        try:
            object.__setattr__(self, "level", VerificationLevel(self.level))
            object.__setattr__(self, "outcome", VerificationOutcome(self.outcome))
            object.__setattr__(
                self,
                "confidence_band",
                ConfidenceBand(self.confidence_band),
            )
        except ValueError as exc:
            raise VerificationContractError(
                "verification receipt enum is invalid"
            ) from exc
        object.__setattr__(
            self,
            "reason_codes",
            _refs(self.reason_codes, "reason_codes", maximum=256),
        )
        if any(not isinstance(item, ClaimCheck) for item in self.claim_checks):
            raise VerificationContractError(
                "claim_checks must contain ClaimCheck values"
            )
        if any(
            not isinstance(item, PostconditionCheck)
            for item in self.postcondition_checks
        ):
            raise VerificationContractError(
                "postcondition_checks must contain PostconditionCheck values"
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "evidence_refs", maximum=4096),
        )
        object.__setattr__(
            self,
            "verifier_route_refs",
            _refs(
                self.verifier_route_refs,
                "verifier_route_refs",
                maximum=128,
            ),
        )
        if self.repair_directive is not None:
            object.__setattr__(
                self,
                "repair_directive",
                _json_object(
                    self.repair_directive,
                    "repair_directive",
                ),
            )
        created = _aware(self.created_at, "created_at")
        completed = _aware(self.completed_at, "completed_at")
        if completed < created:
            raise VerificationContractError(
                "completed_at must not precede created_at"
            )
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "completed_at", completed)
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError(
                "unsupported verification schema version"
            )

    @property
    def passed(self) -> bool:
        return self.outcome is VerificationOutcome.VERIFIED

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "verification_id": self.verification_id,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "candidate_ref": self.candidate_ref,
            "level": self.level.value,
            "outcome": self.outcome.value,
            "reason_codes": list(self.reason_codes),
            "claim_checks": [item.as_dict() for item in self.claim_checks],
            "postcondition_checks": [
                item.as_dict() for item in self.postcondition_checks
            ],
            "evidence_refs": list(self.evidence_refs),
            "verifier_route_refs": list(self.verifier_route_refs),
            "repair_directive": (
                None
                if self.repair_directive is None
                else dict(self.repair_directive)
            ),
            "confidence_band": self.confidence_band.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
        }


__all__ = [
    "Claim",
    "ClaimCheck",
    "ClaimKind",
    "ConfidenceBand",
    "EvidenceReference",
    "PostconditionCheck",
    "RiskClass",
    "VERIFICATION_SCHEMA_VERSION",
    "VerificationContractError",
    "VerificationLevel",
    "VerificationOutcome",
    "VerificationReceipt",
    "VerificationRequest",
    "content_digest",
]
