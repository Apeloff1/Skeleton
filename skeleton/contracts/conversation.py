"""Canonical server-owned conversation contracts.

Conversation state is product state, not provider history and not a browser cache.
These envelopes deliberately separate:
- thread ownership/version/active branch;
- immutable ordered messages;
- edit/regenerate lineage;
- model execution identity from message identity;
- large/sensitive content references from inline text.

Storage implementations may change, but they must preserve these invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import UUID


CONVERSATION_SCHEMA_VERSION = 1
MAX_CONVERSATION_MESSAGE_CHARS = 100_000
MAX_REFERENCE_COUNT = 256


class ConversationContractError(ValueError):
    """A conversation envelope violates the canonical contract."""


class ConversationThreadState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETING = "deleting"
    DELETED = "deleted"


class ConversationAuthorType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM_DERIVED = "system-derived"


def _text(
    value: object,
    field_name: str,
    *,
    max_length: int = 512,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConversationContractError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise ConversationContractError(f"{field_name} must be normalized")
    if len(normalized) > max_length:
        raise ConversationContractError(f"{field_name} exceeds maximum length")
    return normalized


def _uuid(value: object, field_name: str) -> str:
    text = _text(value, field_name, max_length=64)
    try:
        parsed = UUID(text)
    except (ValueError, AttributeError) as exc:
        raise ConversationContractError(
            f"{field_name} must be a canonical UUID"
        ) from exc
    if str(parsed) != text:
        raise ConversationContractError(
            f"{field_name} must be a canonical UUID"
        )
    return text


def _optional_uuid(value: object | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _uuid(value, field_name)


def _aware_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ConversationContractError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ConversationContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConversationContractError(f"{field_name} must be a positive integer")
    return value


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConversationContractError(
            f"{field_name} must be a non-negative integer"
        )
    return value


def _refs(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ConversationContractError(f"{field_name} must be an iterable")
    result: list[str] = []
    for raw in values:
        value = _text(raw, field_name, max_length=512)
        if value not in result:
            result.append(value)
        if len(result) > MAX_REFERENCE_COUNT:
            raise ConversationContractError(
                f"{field_name} exceeds reference count limit"
            )
    return tuple(result)


def _data_class(value: object) -> str:
    normalized = _text(value, "data_class", max_length=32).lower()
    if normalized not in {"public", "internal", "confidential", "restricted"}:
        raise ConversationContractError("data_class is invalid")
    return normalized


def _context_snapshot(
    values: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    if isinstance(values, (str, bytes)):
        raise ConversationContractError("context_source_snapshot must be an iterable")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    previous: str | None = None
    for raw in values:
        if not isinstance(raw, (tuple, list)) or len(raw) != 2:
            raise ConversationContractError(
                "context_source_snapshot entries must be pairs"
            )
        segment_id = _uuid(raw[0], "context_source_snapshot segment_id")
        digest = _text(
            raw[1],
            "context_source_snapshot digest",
            max_length=64,
        )
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ConversationContractError(
                "context_source_snapshot digest must be lowercase sha256"
            )
        if segment_id in seen:
            raise ConversationContractError(
                "context_source_snapshot contains duplicate segment ids"
            )
        if previous is not None and segment_id <= previous:
            raise ConversationContractError(
                "context_source_snapshot must be strictly ordered by segment id"
            )
        seen.add(segment_id)
        previous = segment_id
        result.append((segment_id, digest))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ConversationThread:
    thread_id: str
    tenant_id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime
    version: int
    message_sequence: int
    active_branch_id: str
    state: ConversationThreadState = ConversationThreadState.ACTIVE
    title: str = "New conversation"
    data_class: str = "confidential"
    schema_version: int = CONVERSATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.thread_id, "thread_id")
        _text(self.tenant_id, "tenant_id")
        _text(self.owner_id, "owner_id")
        created = _aware_utc(self.created_at, "created_at")
        updated = _aware_utc(self.updated_at, "updated_at")
        if updated < created:
            raise ConversationContractError("updated_at must not precede created_at")
        _positive_int(self.version, "version")
        _nonnegative_int(self.message_sequence, "message_sequence")
        _uuid(self.active_branch_id, "active_branch_id")
        try:
            state = ConversationThreadState(self.state)
        except ValueError as exc:
            raise ConversationContractError("thread state is invalid") from exc
        object.__setattr__(self, "state", state)
        _text(self.title, "title", max_length=200)
        object.__setattr__(self, "data_class", _data_class(self.data_class))
        if self.schema_version != CONVERSATION_SCHEMA_VERSION:
            raise ConversationContractError("unsupported conversation schema version")

    @property
    def writable(self) -> bool:
        return ConversationThreadState(self.state) is ConversationThreadState.ACTIVE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thread_id": self.thread_id,
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "created_at": _aware_utc(self.created_at, "created_at").isoformat(),
            "updated_at": _aware_utc(self.updated_at, "updated_at").isoformat(),
            "version": self.version,
            "message_sequence": self.message_sequence,
            "active_branch_id": self.active_branch_id,
            "state": ConversationThreadState(self.state).value,
            "title": self.title,
            "data_class": self.data_class,
        }


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    message_id: str
    thread_id: str
    branch_id: str
    sequence: int
    author_type: ConversationAuthorType
    created_at: datetime
    idempotency_key: str
    content: str | None = None
    content_ref: str | None = None
    parent_message_id: str | None = None
    supersedes_message_id: str | None = None
    causal_user_message_id: str | None = None
    operation_id: str | None = None
    ai_result_id: str | None = None
    context_id: str | None = None
    context_digest: str | None = None
    context_source_snapshot: tuple[tuple[str, str], ...] = ()
    context_compiler_version: str | None = None
    attachment_refs: tuple[str, ...] = ()
    tool_receipt_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    citation_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    data_class: str = "confidential"
    schema_version: int = CONVERSATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.message_id, "message_id")
        _uuid(self.thread_id, "thread_id")
        _uuid(self.branch_id, "branch_id")
        _positive_int(self.sequence, "sequence")
        try:
            author = ConversationAuthorType(self.author_type)
        except ValueError as exc:
            raise ConversationContractError("author_type is invalid") from exc
        object.__setattr__(self, "author_type", author)
        _aware_utc(self.created_at, "created_at")
        _text(self.idempotency_key, "idempotency_key", max_length=1024)

        content = self.content
        if content is not None:
            if not isinstance(content, str) or not content.strip():
                raise ConversationContractError(
                    "content must be non-empty when provided"
                )
            if len(content) > MAX_CONVERSATION_MESSAGE_CHARS:
                raise ConversationContractError("content exceeds maximum length")
        content_ref = self.content_ref
        if content_ref is not None:
            _text(content_ref, "content_ref", max_length=1024)
        if content is None and content_ref is None:
            raise ConversationContractError(
                "message requires content or content_ref"
            )

        for field_name in (
            "parent_message_id",
            "supersedes_message_id",
            "causal_user_message_id",
            "operation_id",
        ):
            normalized = _optional_uuid(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, normalized)

        if self.ai_result_id is not None:
            _text(self.ai_result_id, "ai_result_id", max_length=512)

        if (self.context_id is None) != (self.context_digest is None):
            raise ConversationContractError(
                "context_id and context_digest must be supplied together"
            )
        if self.context_id is not None:
            object.__setattr__(self, "context_id", _uuid(self.context_id, "context_id"))
            digest = _text(self.context_digest, "context_digest", max_length=64)
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ConversationContractError(
                    "context_digest must be lowercase sha256"
                )
            snapshot = _context_snapshot(self.context_source_snapshot)
            if not snapshot:
                raise ConversationContractError(
                    "context-bound message requires source snapshot"
                )
            object.__setattr__(self, "context_source_snapshot", snapshot)
            version = _text(
                self.context_compiler_version,
                "context_compiler_version",
                max_length=128,
            )
            object.__setattr__(self, "context_compiler_version", version)
        else:
            if self.context_source_snapshot or self.context_compiler_version is not None:
                raise ConversationContractError(
                    "context snapshot/compiler version require context identity"
                )
            object.__setattr__(self, "context_source_snapshot", ())

        if self.parent_message_id == self.message_id:
            raise ConversationContractError("message cannot parent itself")
        if self.supersedes_message_id == self.message_id:
            raise ConversationContractError("message cannot supersede itself")

        object.__setattr__(
            self,
            "attachment_refs",
            _refs(self.attachment_refs, "attachment_refs"),
        )
        object.__setattr__(
            self,
            "tool_receipt_refs",
            _refs(self.tool_receipt_refs, "tool_receipt_refs"),
        )
        object.__setattr__(
            self,
            "memory_refs",
            _refs(self.memory_refs, "memory_refs"),
        )
        object.__setattr__(
            self,
            "citation_refs",
            _refs(self.citation_refs, "citation_refs"),
        )
        object.__setattr__(
            self,
            "artifact_refs",
            _refs(self.artifact_refs, "artifact_refs"),
        )
        object.__setattr__(self, "data_class", _data_class(self.data_class))
        if self.schema_version != CONVERSATION_SCHEMA_VERSION:
            raise ConversationContractError("unsupported conversation schema version")

        if author is ConversationAuthorType.ASSISTANT:
            if self.causal_user_message_id is None:
                raise ConversationContractError(
                    "assistant message requires causal_user_message_id"
                )
            if self.operation_id is None or self.ai_result_id is None:
                raise ConversationContractError(
                    "assistant message requires operation_id and ai_result_id"
                )
        if author is ConversationAuthorType.TOOL and not self.tool_receipt_refs:
            raise ConversationContractError(
                "tool message requires at least one tool receipt reference"
            )
        if author is ConversationAuthorType.USER and self.ai_result_id is not None:
            raise ConversationContractError(
                "user message cannot bind an AI execution result"
            )
        if author is ConversationAuthorType.USER and self.context_id is not None:
            raise ConversationContractError(
                "user message cannot bind provider context identity"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "branch_id": self.branch_id,
            "sequence": self.sequence,
            "author_type": ConversationAuthorType(self.author_type).value,
            "created_at": _aware_utc(self.created_at, "created_at").isoformat(),
            "idempotency_key": self.idempotency_key,
            "content": self.content,
            "content_ref": self.content_ref,
            "parent_message_id": self.parent_message_id,
            "supersedes_message_id": self.supersedes_message_id,
            "causal_user_message_id": self.causal_user_message_id,
            "operation_id": self.operation_id,
            "ai_result_id": self.ai_result_id,
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "context_source_snapshot": [
                list(item) for item in self.context_source_snapshot
            ],
            "context_compiler_version": self.context_compiler_version,
            "attachment_refs": list(self.attachment_refs),
            "tool_receipt_refs": list(self.tool_receipt_refs),
            "memory_refs": list(self.memory_refs),
            "citation_refs": list(self.citation_refs),
            "artifact_refs": list(self.artifact_refs),
            "data_class": self.data_class,
        }


__all__ = [
    "CONVERSATION_SCHEMA_VERSION",
    "MAX_CONVERSATION_MESSAGE_CHARS",
    "ConversationAuthorType",
    "ConversationContractError",
    "ConversationMessage",
    "ConversationThread",
    "ConversationThreadState",
]
