"""Canonical durable memory contracts.

Memory is governed product state. Vector indexes, caches, and provider context
are derived projections; they are never the authority represented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Iterable
from uuid import UUID


MEMORY_SCHEMA_VERSION = 1
MAX_MEMORY_CONTENT_CHARS = 100_000
MAX_MEMORY_REFS = 128


class MemoryContractError(ValueError):
    """A canonical memory envelope is malformed."""


class MemoryKind(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"


class MemoryState(str, Enum):
    ACTIVE = "active"
    TOMBSTONED = "tombstoned"


def _text(value: object, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryContractError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise MemoryContractError(f"{field} must be normalized")
    if len(normalized) > max_length:
        raise MemoryContractError(f"{field} exceeds maximum length")
    return normalized


def _uuid(value: object, field: str) -> str:
    raw = _text(value, field, max_length=64)
    try:
        parsed = UUID(raw)
    except (TypeError, ValueError, AttributeError) as exc:
        raise MemoryContractError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != raw:
        raise MemoryContractError(f"{field} must be a canonical UUID")
    return raw


def _optional_uuid(value: object | None, field: str) -> str | None:
    return None if value is None else _uuid(value, field)


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MemoryContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _refs(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise MemoryContractError(f"{field} must be an iterable")
    result: list[str] = []
    for raw in values:
        item = _text(raw, field, max_length=1024)
        if item not in result:
            result.append(item)
        if len(result) > MAX_MEMORY_REFS:
            raise MemoryContractError(f"{field} exceeds reference count limit")
    return tuple(result)


def _content(content: str | None, content_ref: str | None) -> tuple[str | None, str | None]:
    if content is None and content_ref is None:
        raise MemoryContractError("memory requires content or content_ref")
    if content is not None:
        if not isinstance(content, str) or not content.strip():
            raise MemoryContractError("content must be non-empty when provided")
        if len(content) > MAX_MEMORY_CONTENT_CHARS:
            raise MemoryContractError("content exceeds maximum length")
    if content_ref is not None:
        _text(content_ref, "content_ref", max_length=1024)
    return content, content_ref


def memory_payload_digest(
    *,
    kind: MemoryKind | str,
    content: str | None,
    content_ref: str | None,
    provenance_refs: Iterable[str],
) -> str:
    normalized_kind = MemoryKind(kind).value
    refs = tuple(provenance_refs)
    material = "\x1f".join(
        (normalized_kind, content or "", content_ref or "", *refs)
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class MemoryWriteProposal:
    proposal_id: str
    tenant_id: str
    namespace: str
    subject_id: str
    kind: MemoryKind
    idempotency_key: str
    proposed_at: datetime
    content: str | None = None
    content_ref: str | None = None
    provenance_refs: tuple[str, ...] = ()
    source_operation_id: str | None = None
    target_memory_id: str | None = None
    expected_version: int | None = None
    expires_at: datetime | None = None
    data_class: str = "confidential"
    schema_version: int = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.proposal_id, "proposal_id")
        _text(self.tenant_id, "tenant_id")
        _text(self.namespace, "namespace")
        _text(self.subject_id, "subject_id")
        try:
            kind = MemoryKind(self.kind)
        except ValueError as exc:
            raise MemoryContractError("kind is invalid") from exc
        object.__setattr__(self, "kind", kind)
        _text(self.idempotency_key, "idempotency_key", max_length=1024)
        proposed = _utc(self.proposed_at, "proposed_at")
        _content(self.content, self.content_ref)
        object.__setattr__(
            self, "provenance_refs", _refs(self.provenance_refs, "provenance_refs")
        )
        object.__setattr__(
            self,
            "source_operation_id",
            _optional_uuid(self.source_operation_id, "source_operation_id"),
        )
        object.__setattr__(
            self,
            "target_memory_id",
            _optional_uuid(self.target_memory_id, "target_memory_id"),
        )
        if self.expected_version is not None:
            if (
                isinstance(self.expected_version, bool)
                or not isinstance(self.expected_version, int)
                or self.expected_version < 1
            ):
                raise MemoryContractError("expected_version must be a positive integer")
            if self.target_memory_id is None:
                raise MemoryContractError(
                    "expected_version requires target_memory_id"
                )
        if self.expires_at is not None:
            expiry = _utc(self.expires_at, "expires_at")
            if expiry <= proposed:
                raise MemoryContractError("expires_at must follow proposed_at")
        normalized_class = _text(self.data_class, "data_class", max_length=32).lower()
        if normalized_class not in {"public", "internal", "confidential", "restricted"}:
            raise MemoryContractError("data_class is invalid")
        object.__setattr__(self, "data_class", normalized_class)
        if self.schema_version != MEMORY_SCHEMA_VERSION:
            raise MemoryContractError("unsupported memory schema version")

    @property
    def payload_digest(self) -> str:
        return memory_payload_digest(
            kind=self.kind,
            content=self.content,
            content_ref=self.content_ref,
            provenance_refs=self.provenance_refs,
        )


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    tenant_id: str
    namespace: str
    subject_id: str
    kind: MemoryKind
    version: int
    created_at: datetime
    updated_at: datetime
    idempotency_key: str
    payload_digest: str
    content: str | None = None
    content_ref: str | None = None
    provenance_refs: tuple[str, ...] = ()
    source_operation_id: str | None = None
    expires_at: datetime | None = None
    state: MemoryState = MemoryState.ACTIVE
    data_class: str = "confidential"
    schema_version: int = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.memory_id, "memory_id")
        _text(self.tenant_id, "tenant_id")
        _text(self.namespace, "namespace")
        _text(self.subject_id, "subject_id")
        try:
            kind = MemoryKind(self.kind)
        except ValueError as exc:
            raise MemoryContractError("kind is invalid") from exc
        object.__setattr__(self, "kind", kind)
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise MemoryContractError("version must be a positive integer")
        created = _utc(self.created_at, "created_at")
        updated = _utc(self.updated_at, "updated_at")
        if updated < created:
            raise MemoryContractError("updated_at must not precede created_at")
        _text(self.idempotency_key, "idempotency_key", max_length=1024)
        digest = _text(self.payload_digest, "payload_digest", max_length=64)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise MemoryContractError("payload_digest must be lowercase sha256")
        _content(self.content, self.content_ref)
        object.__setattr__(
            self, "provenance_refs", _refs(self.provenance_refs, "provenance_refs")
        )
        object.__setattr__(
            self,
            "source_operation_id",
            _optional_uuid(self.source_operation_id, "source_operation_id"),
        )
        if self.expires_at is not None:
            _utc(self.expires_at, "expires_at")
        try:
            state = MemoryState(self.state)
        except ValueError as exc:
            raise MemoryContractError("state is invalid") from exc
        object.__setattr__(self, "state", state)
        normalized_class = _text(self.data_class, "data_class", max_length=32).lower()
        if normalized_class not in {"public", "internal", "confidential", "restricted"}:
            raise MemoryContractError("data_class is invalid")
        object.__setattr__(self, "data_class", normalized_class)
        if self.schema_version != MEMORY_SCHEMA_VERSION:
            raise MemoryContractError("unsupported memory schema version")
        expected = memory_payload_digest(
            kind=self.kind,
            content=self.content,
            content_ref=self.content_ref,
            provenance_refs=self.provenance_refs,
        )
        if expected != self.payload_digest:
            raise MemoryContractError("payload_digest does not match memory payload")

    @property
    def active(self) -> bool:
        return self.state is MemoryState.ACTIVE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "memory_id": self.memory_id,
            "tenant_id": self.tenant_id,
            "namespace": self.namespace,
            "subject_id": self.subject_id,
            "kind": self.kind.value,
            "version": self.version,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "idempotency_key": self.idempotency_key,
            "payload_digest": self.payload_digest,
            "content": self.content,
            "content_ref": self.content_ref,
            "provenance_refs": list(self.provenance_refs),
            "source_operation_id": self.source_operation_id,
            "expires_at": (
                None
                if self.expires_at is None
                else self.expires_at.astimezone(timezone.utc).isoformat()
            ),
            "state": self.state.value,
            "data_class": self.data_class,
        }


__all__ = [
    "MEMORY_SCHEMA_VERSION",
    "MAX_MEMORY_CONTENT_CHARS",
    "MemoryContractError",
    "MemoryKind",
    "MemoryRecord",
    "MemoryState",
    "MemoryWriteProposal",
    "memory_payload_digest",
]
