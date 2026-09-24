"""Canonical verification, claim, evidence, and postcondition contracts.

Verification state is evidence-derived product state. Model confidence, repeated
sampling, or generated prose never authorizes a VERIFIED disposition by itself.
The contracts in this module deliberately preserve evidence provenance,
correlation identity, temporal/population/environment scope, and action
postconditions so later verification runtimes can make deterministic decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Iterable
from uuid import UUID


VERIFICATION_SCHEMA_VERSION = 1
MAX_VERIFICATION_REFS = 256
MAX_CLAIM_CHARS = 100_000


class VerificationContractError(ValueError):
    """Canonical verification data violates a fail-closed invariant."""


class ClaimKind(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    ACTION_OUTCOME = "action_outcome"


class ProvenanceOrigin(str, Enum):
    PRIMARY_SOURCE = "primary_source"
    SECONDARY_SOURCE = "secondary_source"
    TOOL = "tool"
    USER = "user"
    MODEL = "model"
    SYSTEM = "system"


class EvidenceKind(str, Enum):
    SOURCE = "source"
    CITATION = "citation"
    TOOL_RECEIPT = "tool_receipt"
    ARTIFACT = "artifact"
    OBSERVATION = "observation"
    POSTCONDITION = "postcondition"


class EvidenceRelation(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"
    POSTCONDITION = "postcondition"


class PostconditionState(str, Enum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    UNKNOWN = "unknown"
    COMPENSATED = "compensated"


class VerificationLevel(str, Enum):
    STRUCTURAL = "structural"
    GROUNDED = "grounded"
    INDEPENDENT = "independent"
    HIGH_ASSURANCE = "high_assurance"


class VerificationDisposition(str, Enum):
    VERIFIED = "verified"
    QUALIFIED = "qualified"
    ABSTAIN = "abstain"
    REPAIR = "repair"
    BLOCK = "block"


def _text(value: object, field: str, *, max_length: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationContractError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise VerificationContractError(f"{field} must be normalized")
    if len(normalized) > max_length:
        raise VerificationContractError(f"{field} exceeds maximum length")
    return normalized


def _uuid(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    try:
        parsed = UUID(raw)
    except (ValueError, TypeError, AttributeError) as exc:
        raise VerificationContractError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != raw:
        raise VerificationContractError(f"{field} must be a canonical UUID")
    return raw


def _optional_uuid(value: object | None, field: str) -> str | None:
    return None if value is None else _uuid(value, field)


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise VerificationContractError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise VerificationContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _optional_aware(value: object | None, field: str) -> datetime | None:
    return None if value is None else _aware(value, field)


def _sha256(value: object, field: str) -> str:
    digest = _text(value, field, max_length=64)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise VerificationContractError(f"{field} must be lowercase sha256 hex")
    return digest


def _refs(
    values: Iterable[str],
    field: str,
    *,
    max_length: int = 2048,
    sort_values: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise VerificationContractError(f"{field} must be an iterable")
    result: list[str] = []
    for raw in values:
        value = _text(raw, field, max_length=max_length)
        if value not in result:
            result.append(value)
        if len(result) > MAX_VERIFICATION_REFS:
            raise VerificationContractError(f"{field} exceeds reference count limit")
    return tuple(sorted(result) if sort_values else result)


def _uuid_refs(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise VerificationContractError(f"{field} must be an iterable")
    result: list[str] = []
    for raw in values:
        value = _uuid(raw, field)
        if value not in result:
            result.append(value)
        if len(result) > MAX_VERIFICATION_REFS:
            raise VerificationContractError(f"{field} exceeds reference count limit")
    return tuple(sorted(result))


def _scope_window(
    valid_from: datetime | None,
    valid_until: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    start = _optional_aware(valid_from, "valid_from")
    end = _optional_aware(valid_until, "valid_until")
    if start is not None and end is not None and end < start:
        raise VerificationContractError("valid_until must not precede valid_from")
    return start, end


def _canonical_digest(payload: MappingLike) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


MappingLike = dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerificationClaim:
    claim_id: str
    tenant_id: str
    text: str
    kind: ClaimKind
    origin_type: ProvenanceOrigin
    origin_ref: str
    asserted_at: datetime
    operation_id: str | None = None
    context_digest: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    population_scope: tuple[str, ...] = ()
    environment_scope: tuple[str, ...] = ()
    parent_claim_ids: tuple[str, ...] = ()
    data_class: str = "internal"
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _uuid(self.claim_id, "claim_id"))
        _text(self.tenant_id, "tenant_id")
        _text(self.text, "text", max_length=MAX_CLAIM_CHARS)
        try:
            kind = ClaimKind(self.kind)
        except ValueError as exc:
            raise VerificationContractError("kind is invalid") from exc
        try:
            origin = ProvenanceOrigin(self.origin_type)
        except ValueError as exc:
            raise VerificationContractError("origin_type is invalid") from exc
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "origin_type", origin)
        _text(self.origin_ref, "origin_ref", max_length=2048)
        object.__setattr__(self, "asserted_at", _aware(self.asserted_at, "asserted_at"))
        object.__setattr__(
            self,
            "operation_id",
            _optional_uuid(self.operation_id, "operation_id"),
        )
        if self.context_digest is not None:
            object.__setattr__(
                self,
                "context_digest",
                _sha256(self.context_digest, "context_digest"),
            )
        start, end = _scope_window(self.valid_from, self.valid_until)
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_until", end)
        object.__setattr__(
            self,
            "population_scope",
            _refs(self.population_scope, "population_scope", sort_values=True),
        )
        object.__setattr__(
            self,
            "environment_scope",
            _refs(self.environment_scope, "environment_scope", sort_values=True),
        )
        object.__setattr__(
            self,
            "parent_claim_ids",
            _uuid_refs(self.parent_claim_ids, "parent_claim_ids"),
        )
        normalized_class = _text(self.data_class, "data_class", max_length=32).lower()
        if normalized_class not in {"public", "internal", "confidential", "restricted"}:
            raise VerificationContractError("data_class is invalid")
        object.__setattr__(self, "data_class", normalized_class)
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")

    @property
    def claim_digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": self.schema_version,
                "claim_id": self.claim_id,
                "tenant_id": self.tenant_id,
                "text": self.text,
                "kind": self.kind.value,
                "origin_type": self.origin_type.value,
                "origin_ref": self.origin_ref,
                "asserted_at": self.asserted_at.isoformat(),
                "operation_id": self.operation_id,
                "context_digest": self.context_digest,
                "valid_from": self.valid_from.isoformat() if self.valid_from else None,
                "valid_until": self.valid_until.isoformat() if self.valid_until else None,
                "population_scope": self.population_scope,
                "environment_scope": self.environment_scope,
                "parent_claim_ids": self.parent_claim_ids,
                "data_class": self.data_class,
            }
        )

    def as_dict(self) -> MappingLike:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "tenant_id": self.tenant_id,
            "text": self.text,
            "kind": self.kind.value,
            "origin_type": self.origin_type.value,
            "origin_ref": self.origin_ref,
            "asserted_at": self.asserted_at.isoformat(),
            "operation_id": self.operation_id,
            "context_digest": self.context_digest,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "population_scope": list(self.population_scope),
            "environment_scope": list(self.environment_scope),
            "parent_claim_ids": list(self.parent_claim_ids),
            "data_class": self.data_class,
            "claim_digest": self.claim_digest,
        }


@dataclass(frozen=True, slots=True)
class VerificationEvidence:
    evidence_id: str
    tenant_id: str
    kind: EvidenceKind
    origin_type: ProvenanceOrigin
    source_id: str
    origin_id: str
    content_digest: str
    observed_at: datetime
    locator: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    population_scope: tuple[str, ...] = ()
    environment_scope: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    bound_claim_ids: tuple[str, ...] = ()
    relation: EvidenceRelation = EvidenceRelation.CONTEXT
    derived_from_claim_ids: tuple[str, ...] = ()
    data_class: str = "internal"
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _uuid(self.evidence_id, "evidence_id"))
        _text(self.tenant_id, "tenant_id")
        try:
            kind = EvidenceKind(self.kind)
        except ValueError as exc:
            raise VerificationContractError("kind is invalid") from exc
        try:
            origin = ProvenanceOrigin(self.origin_type)
        except ValueError as exc:
            raise VerificationContractError("origin_type is invalid") from exc
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "origin_type", origin)
        _text(self.source_id, "source_id", max_length=2048)
        _text(self.origin_id, "origin_id", max_length=2048)
        object.__setattr__(
            self,
            "content_digest",
            _sha256(self.content_digest, "content_digest"),
        )
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.locator is not None:
            _text(self.locator, "locator", max_length=4096)
        start, end = _scope_window(self.valid_from, self.valid_until)
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_until", end)
        object.__setattr__(
            self,
            "population_scope",
            _refs(self.population_scope, "population_scope", sort_values=True),
        )
        object.__setattr__(
            self,
            "environment_scope",
            _refs(self.environment_scope, "environment_scope", sort_values=True),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs(self.provenance_refs, "provenance_refs"),
        )
        object.__setattr__(
            self,
            "bound_claim_ids",
            _uuid_refs(self.bound_claim_ids, "bound_claim_ids"),
        )
        try:
            relation = EvidenceRelation(self.relation)
        except ValueError as exc:
            raise VerificationContractError("relation is invalid") from exc
        object.__setattr__(self, "relation", relation)
        if relation in {EvidenceRelation.SUPPORTS, EvidenceRelation.CONTRADICTS} and not self.bound_claim_ids:
            raise VerificationContractError(
                "supporting/contradicting evidence requires bound_claim_ids"
            )
        object.__setattr__(
            self,
            "derived_from_claim_ids",
            _uuid_refs(self.derived_from_claim_ids, "derived_from_claim_ids"),
        )
        normalized_class = _text(self.data_class, "data_class", max_length=32).lower()
        if normalized_class not in {"public", "internal", "confidential", "restricted"}:
            raise VerificationContractError("data_class is invalid")
        object.__setattr__(self, "data_class", normalized_class)
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")

    @property
    def evidence_digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": self.schema_version,
                "evidence_id": self.evidence_id,
                "tenant_id": self.tenant_id,
                "kind": self.kind.value,
                "origin_type": self.origin_type.value,
                "source_id": self.source_id,
                "origin_id": self.origin_id,
                "content_digest": self.content_digest,
                "observed_at": self.observed_at.isoformat(),
                "locator": self.locator,
                "valid_from": self.valid_from.isoformat() if self.valid_from else None,
                "valid_until": self.valid_until.isoformat() if self.valid_until else None,
                "population_scope": self.population_scope,
                "environment_scope": self.environment_scope,
                "provenance_refs": self.provenance_refs,
                "bound_claim_ids": self.bound_claim_ids,
                "relation": self.relation.value,
                "derived_from_claim_ids": self.derived_from_claim_ids,
                "data_class": self.data_class,
            }
        )

    def independent_for(self, claim: VerificationClaim) -> bool:
        """Whether this evidence can count toward process/source independence."""

        if self.tenant_id != claim.tenant_id:
            return False
        if self.origin_type is ProvenanceOrigin.MODEL:
            return False
        if claim.claim_id in self.derived_from_claim_ids:
            return False
        return True

    def as_dict(self) -> MappingLike:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "tenant_id": self.tenant_id,
            "kind": self.kind.value,
            "origin_type": self.origin_type.value,
            "source_id": self.source_id,
            "origin_id": self.origin_id,
            "content_digest": self.content_digest,
            "observed_at": self.observed_at.isoformat(),
            "locator": self.locator,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "population_scope": list(self.population_scope),
            "environment_scope": list(self.environment_scope),
            "provenance_refs": list(self.provenance_refs),
            "bound_claim_ids": list(self.bound_claim_ids),
            "relation": self.relation.value,
            "derived_from_claim_ids": list(self.derived_from_claim_ids),
            "data_class": self.data_class,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class VerificationPostcondition:
    postcondition_id: str
    tenant_id: str
    operation_id: str
    subject_ref: str
    state: PostconditionState
    observed_at: datetime
    evidence_ids: tuple[str, ...] = ()
    tool_receipt_ref: str | None = None
    expected_digest: str | None = None
    actual_digest: str | None = None
    detail_code: str | None = None
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "postcondition_id",
            _uuid(self.postcondition_id, "postcondition_id"),
        )
        _text(self.tenant_id, "tenant_id")
        object.__setattr__(
            self,
            "operation_id",
            _uuid(self.operation_id, "operation_id"),
        )
        _text(self.subject_ref, "subject_ref", max_length=2048)
        try:
            state = PostconditionState(self.state)
        except ValueError as exc:
            raise VerificationContractError("state is invalid") from exc
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(
            self,
            "evidence_ids",
            _uuid_refs(self.evidence_ids, "evidence_ids"),
        )
        if self.tool_receipt_ref is not None:
            _text(self.tool_receipt_ref, "tool_receipt_ref", max_length=2048)
        if self.expected_digest is not None:
            object.__setattr__(
                self,
                "expected_digest",
                _sha256(self.expected_digest, "expected_digest"),
            )
        if self.actual_digest is not None:
            object.__setattr__(
                self,
                "actual_digest",
                _sha256(self.actual_digest, "actual_digest"),
            )
        if self.detail_code is not None:
            _text(self.detail_code, "detail_code", max_length=256)
        if (
            state is PostconditionState.SATISFIED
            and self.expected_digest is not None
            and self.actual_digest is not None
            and self.expected_digest != self.actual_digest
        ):
            raise VerificationContractError(
                "satisfied postcondition cannot carry mismatched expected/actual digests"
            )
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")

    @property
    def postcondition_digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": self.schema_version,
                "postcondition_id": self.postcondition_id,
                "tenant_id": self.tenant_id,
                "operation_id": self.operation_id,
                "subject_ref": self.subject_ref,
                "state": self.state.value,
                "observed_at": self.observed_at.isoformat(),
                "evidence_ids": self.evidence_ids,
                "tool_receipt_ref": self.tool_receipt_ref,
                "expected_digest": self.expected_digest,
                "actual_digest": self.actual_digest,
                "detail_code": self.detail_code,
            }
        )


@dataclass(frozen=True, slots=True)
class VerificationBundle:
    bundle_id: str
    claim: VerificationClaim
    evidence: tuple[VerificationEvidence, ...]
    postconditions: tuple[VerificationPostcondition, ...]
    requested_level: VerificationLevel
    created_at: datetime
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id", _uuid(self.bundle_id, "bundle_id"))
        if not isinstance(self.claim, VerificationClaim):
            raise VerificationContractError("claim must be VerificationClaim")
        if any(not isinstance(item, VerificationEvidence) for item in self.evidence):
            raise VerificationContractError(
                "evidence must contain VerificationEvidence values"
            )
        if any(
            not isinstance(item, VerificationPostcondition)
            for item in self.postconditions
        ):
            raise VerificationContractError(
                "postconditions must contain VerificationPostcondition values"
            )
        try:
            level = VerificationLevel(self.requested_level)
        except ValueError as exc:
            raise VerificationContractError("requested_level is invalid") from exc
        object.__setattr__(self, "requested_level", level)
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise VerificationContractError("evidence ids must be unique")
        postcondition_ids = [item.postcondition_id for item in self.postconditions]
        if len(postcondition_ids) != len(set(postcondition_ids)):
            raise VerificationContractError("postcondition ids must be unique")
        if any(item.tenant_id != self.claim.tenant_id for item in self.evidence):
            raise VerificationContractError("evidence tenant mismatch")
        if any(
            item.tenant_id != self.claim.tenant_id for item in self.postconditions
        ):
            raise VerificationContractError("postcondition tenant mismatch")
        if any(
            bound_id != self.claim.claim_id
            for item in self.evidence
            for bound_id in item.bound_claim_ids
        ):
            raise VerificationContractError(
                "evidence binds a claim outside verification bundle"
            )
        known_evidence = set(evidence_ids)
        if any(
            evidence_id not in known_evidence
            for postcondition in self.postconditions
            for evidence_id in postcondition.evidence_ids
        ):
            raise VerificationContractError(
                "postcondition references evidence outside verification bundle"
            )
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")

    @property
    def independent_origin_ids(self) -> tuple[str, ...]:
        """Distinct non-model origins that are not derived from the claim itself."""

        return tuple(
            sorted(
                {
                    item.origin_id
                    for item in self.evidence
                    if item.independent_for(self.claim)
                }
            )
        )

    @property
    def bundle_digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": self.schema_version,
                "bundle_id": self.bundle_id,
                "claim_digest": self.claim.claim_digest,
                "evidence_digests": sorted(
                    item.evidence_digest for item in self.evidence
                ),
                "postcondition_digests": sorted(
                    item.postcondition_digest for item in self.postconditions
                ),
                "requested_level": self.requested_level.value,
                "created_at": self.created_at.isoformat(),
            }
        )


__all__ = [
    "VERIFICATION_SCHEMA_VERSION",
    "MAX_VERIFICATION_REFS",
    "ClaimKind",
    "EvidenceKind",
    "EvidenceRelation",
    "PostconditionState",
    "ProvenanceOrigin",
    "VerificationBundle",
    "VerificationClaim",
    "VerificationContractError",
    "VerificationDisposition",
    "VerificationEvidence",
    "VerificationLevel",
    "VerificationPostcondition",
]
