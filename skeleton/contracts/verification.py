"""Canonical verification, claim, evidence, and postcondition contracts.

Verification is evidence-derived product state. Model output, confidence text, or
citation count alone never upgrades a claim. These contracts preserve scope,
source lineage, contradiction, and postcondition evidence so runtimes can make
deterministic publication decisions without inferring authority from prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, IntEnum
import hashlib
import json
import math
from typing import Any, Iterable, Mapping
from uuid import UUID


VERIFICATION_SCHEMA_VERSION = 1
MAX_VERIFICATION_REFS = 256
MAX_CLAIM_CHARS = 100_000


class VerificationContractError(ValueError):
    """A canonical verification envelope is malformed."""


class VerificationRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClaimKind(str, Enum):
    FACT = "fact"
    INTERPRETATION = "interpretation"
    HYPOTHESIS = "hypothesis"
    STRUCTURED_OUTPUT = "structured_output"
    TOOL_RESULT = "tool_result"
    ACTION_OUTCOME = "action_outcome"


class EvidenceRelation(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT_ONLY = "context_only"


class EvidenceProducer(str, Enum):
    SOURCE = "source"
    MODEL = "model"
    TOOL = "tool"
    TEST = "test"
    HUMAN = "human"
    SYSTEM = "system"


class VerificationLevel(IntEnum):
    STRUCTURAL = 0
    EVIDENCE = 1
    INDEPENDENT = 2
    POSTCONDITION = 3


class VerificationOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    CONTESTED = "contested"
    UNKNOWN = "unknown"
    ABSTAINED = "abstained"


def _text(value: object, field: str, *, max_length: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationContractError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise VerificationContractError(f"{field} must be normalized")
    if len(normalized) > max_length:
        raise VerificationContractError(f"{field} exceeds maximum length")
    return normalized


def _optional_text(value: object | None, field: str, *, max_length: int = 1024) -> str | None:
    if value is None:
        return None
    return _text(value, field, max_length=max_length)


def _uuid(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    try:
        parsed = UUID(raw)
    except (ValueError, AttributeError, TypeError) as exc:
        raise VerificationContractError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != raw:
        raise VerificationContractError(f"{field} must be a canonical UUID")
    return raw


def _optional_uuid(value: object | None, field: str) -> str | None:
    return None if value is None else _uuid(value, field)


def _sha256(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    if len(raw) != 64 or any(ch not in "0123456789abcdef" for ch in raw):
        raise VerificationContractError(f"{field} must be lowercase sha256")
    return raw


def _optional_sha256(value: object | None, field: str) -> str | None:
    return None if value is None else _sha256(value, field)


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise VerificationContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _refs(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise VerificationContractError(f"{field} must be an iterable")
    result: list[str] = []
    for raw in values:
        item = _text(raw, field, max_length=2048)
        if item not in result:
            result.append(item)
        if len(result) > MAX_VERIFICATION_REFS:
            raise VerificationContractError(f"{field} exceeds reference count limit")
    return tuple(result)


def _uuid_refs(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise VerificationContractError(f"{field} must be an iterable")
    result: list[str] = []
    for raw in values:
        item = _uuid(raw, field)
        if item not in result:
            result.append(item)
        if len(result) > MAX_VERIFICATION_REFS:
            raise VerificationContractError(f"{field} exceeds reference count limit")
    return tuple(result)


def _finite_unit_interval(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VerificationContractError(f"{field} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise VerificationContractError(f"{field} must be within [0, 1]")
    return normalized


def _canonical_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ClaimScope:
    """First-class scope used to prevent temporal/population/environment collapse."""

    valid_from: datetime | None = None
    valid_to: datetime | None = None
    population: str | None = None
    environment: str | None = None
    jurisdiction: str | None = None

    def __post_init__(self) -> None:
        start = None if self.valid_from is None else _utc(self.valid_from, "valid_from")
        end = None if self.valid_to is None else _utc(self.valid_to, "valid_to")
        if start is not None:
            object.__setattr__(self, "valid_from", start)
        if end is not None:
            object.__setattr__(self, "valid_to", end)
        if start is not None and end is not None and end < start:
            raise VerificationContractError("valid_to must not precede valid_from")
        for field in ("population", "environment", "jurisdiction"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(
                    self,
                    field,
                    _text(value, field, max_length=512),
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "population": self.population,
            "environment": self.environment,
            "jurisdiction": self.jurisdiction,
        }


@dataclass(frozen=True, slots=True)
class VerificationClaim:
    claim_id: str
    tenant_id: str
    text: str
    kind: ClaimKind
    risk: VerificationRisk
    created_at: datetime
    scope: ClaimScope = ClaimScope()
    operation_id: str | None = None
    turn_id: str | None = None
    context_id: str | None = None
    context_digest: str | None = None
    provenance_refs: tuple[str, ...] = ()
    generated_by_model: bool = False
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _uuid(self.claim_id, "claim_id"))
        _text(self.tenant_id, "tenant_id")
        if not isinstance(self.text, str) or not self.text.strip():
            raise VerificationContractError("text must be non-empty")
        if len(self.text) > MAX_CLAIM_CHARS:
            raise VerificationContractError("text exceeds maximum length")
        try:
            object.__setattr__(self, "kind", ClaimKind(self.kind))
            object.__setattr__(self, "risk", VerificationRisk(self.risk))
        except ValueError as exc:
            raise VerificationContractError("claim enum value is invalid") from exc
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))
        if not isinstance(self.scope, ClaimScope):
            raise VerificationContractError("scope must be ClaimScope")
        object.__setattr__(
            self,
            "operation_id",
            _optional_uuid(self.operation_id, "operation_id"),
        )
        object.__setattr__(self, "turn_id", _optional_uuid(self.turn_id, "turn_id"))
        if (self.context_id is None) != (self.context_digest is None):
            raise VerificationContractError(
                "context_id and context_digest must be supplied together"
            )
        object.__setattr__(
            self,
            "context_id",
            _optional_uuid(self.context_id, "context_id"),
        )
        object.__setattr__(
            self,
            "context_digest",
            _optional_sha256(self.context_digest, "context_digest"),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs(self.provenance_refs, "provenance_refs"),
        )
        if not isinstance(self.generated_by_model, bool):
            raise VerificationContractError("generated_by_model must be boolean")
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "tenant_id": self.tenant_id,
            "text": self.text,
            "kind": self.kind.value,
            "risk": self.risk.value,
            "created_at": self.created_at.isoformat(),
            "scope": self.scope.as_dict(),
            "operation_id": self.operation_id,
            "turn_id": self.turn_id,
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "provenance_refs": list(self.provenance_refs),
            "generated_by_model": self.generated_by_model,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    claim_id: str
    tenant_id: str
    source_id: str
    origin_id: str
    content_digest: str
    locator: str
    relation: EvidenceRelation
    producer: EvidenceProducer
    observed_at: datetime
    scope: ClaimScope = ClaimScope()
    provenance_refs: tuple[str, ...] = ()
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _uuid(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "claim_id", _uuid(self.claim_id, "claim_id"))
        _text(self.tenant_id, "tenant_id")
        _text(self.source_id, "source_id", max_length=2048)
        _text(self.origin_id, "origin_id", max_length=2048)
        object.__setattr__(
            self,
            "content_digest",
            _sha256(self.content_digest, "content_digest"),
        )
        _text(self.locator, "locator", max_length=4096)
        try:
            object.__setattr__(self, "relation", EvidenceRelation(self.relation))
            object.__setattr__(self, "producer", EvidenceProducer(self.producer))
        except ValueError as exc:
            raise VerificationContractError("evidence enum value is invalid") from exc
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if not isinstance(self.scope, ClaimScope):
            raise VerificationContractError("scope must be ClaimScope")
        object.__setattr__(
            self,
            "provenance_refs",
            _refs(self.provenance_refs, "provenance_refs"),
        )
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "claim_id": self.claim_id,
            "tenant_id": self.tenant_id,
            "source_id": self.source_id,
            "origin_id": self.origin_id,
            "content_digest": self.content_digest,
            "locator": self.locator,
            "relation": self.relation.value,
            "producer": self.producer.value,
            "observed_at": self.observed_at.isoformat(),
            "scope": self.scope.as_dict(),
            "provenance_refs": list(self.provenance_refs),
        }


@dataclass(frozen=True, slots=True)
class PostconditionSpec:
    postcondition_id: str
    operation_id: str
    tenant_id: str
    description: str
    verification_method: str
    required: bool = True
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "postcondition_id",
            _uuid(self.postcondition_id, "postcondition_id"),
        )
        object.__setattr__(
            self,
            "operation_id",
            _uuid(self.operation_id, "operation_id"),
        )
        _text(self.tenant_id, "tenant_id")
        _text(self.description, "description", max_length=4096)
        _text(self.verification_method, "verification_method", max_length=256)
        if not isinstance(self.required, bool):
            raise VerificationContractError("required must be boolean")
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")


@dataclass(frozen=True, slots=True)
class PostconditionObservation:
    observation_id: str
    postcondition_id: str
    operation_id: str
    tenant_id: str
    observed_at: datetime
    passed: bool
    evidence_ids: tuple[str, ...] = ()
    result_ref: str | None = None
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_id",
            _uuid(self.observation_id, "observation_id"),
        )
        object.__setattr__(
            self,
            "postcondition_id",
            _uuid(self.postcondition_id, "postcondition_id"),
        )
        object.__setattr__(
            self,
            "operation_id",
            _uuid(self.operation_id, "operation_id"),
        )
        _text(self.tenant_id, "tenant_id")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if not isinstance(self.passed, bool):
            raise VerificationContractError("passed must be boolean")
        object.__setattr__(
            self,
            "evidence_ids",
            _uuid_refs(self.evidence_ids, "evidence_ids"),
        )
        object.__setattr__(
            self,
            "result_ref",
            _optional_text(self.result_ref, "result_ref", max_length=2048),
        )
        if not self.evidence_ids and self.result_ref is None:
            raise VerificationContractError(
                "postcondition observation requires evidence_ids or result_ref"
            )
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    check_id: str
    claim_id: str
    tenant_id: str
    level: VerificationLevel
    outcome: VerificationOutcome
    verifier_id: str
    verified_at: datetime
    evidence_ids: tuple[str, ...] = ()
    postcondition_observation_ids: tuple[str, ...] = ()
    independent: bool = False
    issues: tuple[str, ...] = ()
    confidence: float | None = None
    schema_version: int = VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", _uuid(self.check_id, "check_id"))
        object.__setattr__(self, "claim_id", _uuid(self.claim_id, "claim_id"))
        _text(self.tenant_id, "tenant_id")
        try:
            object.__setattr__(self, "level", VerificationLevel(self.level))
            object.__setattr__(self, "outcome", VerificationOutcome(self.outcome))
        except ValueError as exc:
            raise VerificationContractError("verification enum value is invalid") from exc
        _text(self.verifier_id, "verifier_id", max_length=512)
        object.__setattr__(self, "verified_at", _utc(self.verified_at, "verified_at"))
        object.__setattr__(
            self,
            "evidence_ids",
            _uuid_refs(self.evidence_ids, "evidence_ids"),
        )
        object.__setattr__(
            self,
            "postcondition_observation_ids",
            _uuid_refs(
                self.postcondition_observation_ids,
                "postcondition_observation_ids",
            ),
        )
        if not isinstance(self.independent, bool):
            raise VerificationContractError("independent must be boolean")
        object.__setattr__(self, "issues", _refs(self.issues, "issues"))
        if self.confidence is not None:
            object.__setattr__(
                self,
                "confidence",
                _finite_unit_interval(self.confidence, "confidence"),
            )
        if self.level >= VerificationLevel.EVIDENCE and not self.evidence_ids:
            raise VerificationContractError(
                "evidence-level verification requires evidence_ids"
            )
        if self.level >= VerificationLevel.INDEPENDENT and not self.independent:
            raise VerificationContractError(
                "independent-level verification requires independent verifier"
            )
        if (
            self.level >= VerificationLevel.POSTCONDITION
            and not self.postcondition_observation_ids
        ):
            raise VerificationContractError(
                "postcondition-level verification requires observations"
            )
        if self.schema_version != VERIFICATION_SCHEMA_VERSION:
            raise VerificationContractError("unsupported verification schema version")


__all__ = [
    "VERIFICATION_SCHEMA_VERSION",
    "ClaimKind",
    "ClaimScope",
    "EvidenceProducer",
    "EvidenceReference",
    "EvidenceRelation",
    "PostconditionObservation",
    "PostconditionSpec",
    "VerificationCheck",
    "VerificationContractError",
    "VerificationLevel",
    "VerificationOutcome",
    "VerificationRisk",
    "VerificationClaim",
]
