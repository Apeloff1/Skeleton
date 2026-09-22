"""Canonical durable memory record and write-proposal contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import copy
import json
import re
from typing import Any, Mapping


MEMORY_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MemoryContractError(ValueError):
    """A durable memory envelope violates the canonical contract."""


class MemoryKind(str, Enum):
    PREFERENCE = "preference"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    CONVERSATION_SUMMARY = "conversation_summary"
    TASK_OUTCOME = "task_outcome"
    TOOL_FACT = "tool_fact"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETING = "deleting"
    DELETED = "deleted"
    EXPIRED = "expired"


class MemoryAuthorityClass(str, Enum):
    USER_EXPLICIT = "user_explicit"
    TOOL_AUTHORITATIVE = "tool_authoritative"
    VERIFIED_OUTCOME = "verified_outcome"
    DERIVED_SUMMARY = "derived_summary"
    IMPORTED = "imported"


class ConfidenceBand(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


def _text(value: object, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryContractError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise MemoryContractError(f"{field} must be normalized")
    if len(normalized) > max_length:
        raise MemoryContractError(f"{field} exceeds maximum length")
    return normalized


def _optional_text(
    value: object | None,
    field: str,
    *,
    max_length: int = 512,
) -> str | None:
    if value is None:
        return None
    return _text(value, field, max_length=max_length)


def _digest(value: object) -> str:
    digest = _text(value, "content_digest", max_length=64).lower()
    if not _SHA256.fullmatch(digest):
        raise MemoryContractError("content_digest must be lowercase sha256 hex")
    return digest


def _utc(value: object, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MemoryContractError(f"{field} must be RFC3339") from exc
    if not isinstance(value, datetime):
        raise MemoryContractError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise MemoryContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _optional_utc(value: object | None, field: str) -> datetime | None:
    if value is None:
        return None
    return _utc(value, field)


def _json_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MemoryContractError(f"{field} must be an object")
    cloned = copy.deepcopy(dict(value))
    try:
        encoded = json.dumps(
            cloned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        normalized = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise MemoryContractError(f"{field} must be strict JSON") from exc
    if not isinstance(normalized, dict):
        raise MemoryContractError(f"{field} must normalize to an object")
    return normalized


def _data_class(value: object) -> str:
    normalized = _text(value, "data_class", max_length=32).lower()
    if normalized not in {"public", "internal", "confidential", "restricted"}:
        raise MemoryContractError("data_class is invalid")
    return normalized


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MemoryContractError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class MemoryWriteProposal:
    proposal_id: str
    operation_id: str
    execution_id: str
    tenant_id: str
    user_id: str | None
    namespace: str
    kind: MemoryKind
    content_ref: str
    content_digest: str
    provenance: Mapping[str, Any]
    authority_class: MemoryAuthorityClass
    data_class: str
    purpose: str
    retention_class: str
    dedupe_key: str
    confidence_band: ConfidenceBand = ConfidenceBand.UNKNOWN
    expires_at: datetime | None = None
    schema_version: int = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in ("proposal_id", "operation_id", "execution_id", "tenant_id"):
            _text(getattr(self, field), field)
        object.__setattr__(self, "user_id", _optional_text(self.user_id, "user_id"))
        _text(self.namespace, "namespace", max_length=256)
        try:
            object.__setattr__(self, "kind", MemoryKind(self.kind))
        except ValueError as exc:
            raise MemoryContractError("kind is invalid") from exc
        _text(self.content_ref, "content_ref", max_length=2048)
        object.__setattr__(self, "content_digest", _digest(self.content_digest))
        object.__setattr__(self, "provenance", _json_object(self.provenance, "provenance"))
        try:
            object.__setattr__(
                self,
                "authority_class",
                MemoryAuthorityClass(self.authority_class),
            )
        except ValueError as exc:
            raise MemoryContractError("authority_class is invalid") from exc
        object.__setattr__(self, "data_class", _data_class(self.data_class))
        _text(self.purpose, "purpose", max_length=256)
        _text(self.retention_class, "retention_class", max_length=128)
        _text(self.dedupe_key, "dedupe_key", max_length=512)
        try:
            object.__setattr__(
                self,
                "confidence_band",
                ConfidenceBand(self.confidence_band),
            )
        except ValueError as exc:
            raise MemoryContractError("confidence_band is invalid") from exc
        object.__setattr__(
            self,
            "expires_at",
            _optional_utc(self.expires_at, "expires_at"),
        )
        if self.schema_version != MEMORY_SCHEMA_VERSION:
            raise MemoryContractError("unsupported memory schema version")

    def scope_key(self) -> tuple[str, str | None, str, str]:
        return (self.tenant_id, self.user_id, self.namespace, self.dedupe_key)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    tenant_id: str
    user_id: str | None
    namespace: str
    kind: MemoryKind
    content_ref: str
    content_digest: str
    data_class: str
    purpose: str
    provenance: Mapping[str, Any]
    authority_class: MemoryAuthorityClass
    confidence_band: ConfidenceBand
    retention_class: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    dedupe_key: str
    version: int
    status: MemoryStatus = MemoryStatus.ACTIVE
    schema_version: int = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.memory_id, "memory_id")
        _text(self.tenant_id, "tenant_id")
        object.__setattr__(self, "user_id", _optional_text(self.user_id, "user_id"))
        _text(self.namespace, "namespace", max_length=256)
        try:
            object.__setattr__(self, "kind", MemoryKind(self.kind))
        except ValueError as exc:
            raise MemoryContractError("kind is invalid") from exc
        _text(self.content_ref, "content_ref", max_length=2048)
        object.__setattr__(self, "content_digest", _digest(self.content_digest))
        object.__setattr__(self, "data_class", _data_class(self.data_class))
        _text(self.purpose, "purpose", max_length=256)
        object.__setattr__(self, "provenance", _json_object(self.provenance, "provenance"))
        try:
            object.__setattr__(
                self,
                "authority_class",
                MemoryAuthorityClass(self.authority_class),
            )
        except ValueError as exc:
            raise MemoryContractError("authority_class is invalid") from exc
        try:
            object.__setattr__(
                self,
                "confidence_band",
                ConfidenceBand(self.confidence_band),
            )
        except ValueError as exc:
            raise MemoryContractError("confidence_band is invalid") from exc
        _text(self.retention_class, "retention_class", max_length=128)
        created = _utc(self.created_at, "created_at")
        updated = _utc(self.updated_at, "updated_at")
        expires = _optional_utc(self.expires_at, "expires_at")
        if updated < created:
            raise MemoryContractError("updated_at must not precede created_at")
        if expires is not None and expires <= created:
            raise MemoryContractError("expires_at must follow created_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "expires_at", expires)
        _text(self.dedupe_key, "dedupe_key", max_length=512)
        _positive_int(self.version, "version")
        try:
            object.__setattr__(self, "status", MemoryStatus(self.status))
        except ValueError as exc:
            raise MemoryContractError("status is invalid") from exc
        if self.schema_version != MEMORY_SCHEMA_VERSION:
            raise MemoryContractError("unsupported memory schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "memory_id": self.memory_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "namespace": self.namespace,
            "kind": self.kind.value,
            "content_ref": self.content_ref,
            "content_digest": self.content_digest,
            "data_class": self.data_class,
            "purpose": self.purpose,
            "provenance": copy.deepcopy(dict(self.provenance)),
            "authority_class": self.authority_class.value,
            "confidence_band": self.confidence_band.value,
            "retention_class": self.retention_class,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "dedupe_key": self.dedupe_key,
            "version": self.version,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MemoryRecord":
        if not isinstance(raw, Mapping):
            raise MemoryContractError("memory record must be an object")
        payload = dict(raw)
        payload.pop("_id", None)
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class MemoryWriteReceipt:
    proposal_id: str
    memory_id: str
    version: int
    content_digest: str
    committed_at: datetime
    deduplicated: bool

    def __post_init__(self) -> None:
        _text(self.proposal_id, "proposal_id")
        _text(self.memory_id, "memory_id")
        _positive_int(self.version, "version")
        object.__setattr__(self, "content_digest", _digest(self.content_digest))
        object.__setattr__(self, "committed_at", _utc(self.committed_at, "committed_at"))


__all__ = [
    "MEMORY_SCHEMA_VERSION",
    "ConfidenceBand",
    "MemoryAuthorityClass",
    "MemoryContractError",
    "MemoryKind",
    "MemoryRecord",
    "MemoryStatus",
    "MemoryWriteProposal",
    "MemoryWriteReceipt",
]
