"""Durable reference repository for canonical conversation authority.

Production conversation state is expected to live in backend core Mongo. This
SQLite adapter is the portable conformance implementation for ownership,
idempotency, exact-next sequencing, optimistic thread versions, immutable
branch lineage, and transcript reconstruction.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable
from uuid import UUID, uuid4

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationContractError,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


class ConversationRepositoryError(RuntimeError):
    """Base conversation repository failure."""


class ConversationNotFound(ConversationRepositoryError):
    """Requested thread or message does not exist."""


class ConversationAuthorizationError(ConversationRepositoryError):
    """Caller is not authorized for the requested conversation."""


class ConversationConflict(ConversationRepositoryError):
    """Version, idempotency, sequence, or lineage conflict."""


class ConversationRepositoryCorruption(ConversationRepositoryError):
    """Persisted conversation state violates the canonical contract."""


def conversation_search_text(value: str) -> str:
    """Normalize a bounded literal title query; never interpret query syntax."""
    if not isinstance(value, str) or len(value) > 200 or "\x00" in value:
        raise ValueError("conversation search must contain at most 200 characters")
    return value.strip()


def conversation_data_class_rank(value: str) -> int:
    return ("public", "internal", "confidential", "restricted").index(value)


def encode_thread_cursor(updated_at: datetime, thread_id: str) -> str:
    instant = _utc(updated_at)
    if str(UUID(thread_id)) != thread_id:
        raise ValueError("conversation cursor thread identity is invalid")
    raw = json.dumps(
        {"version": 1, "updated_at": instant.isoformat(), "thread_id": thread_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_thread_cursor(value: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not 1 <= len(value) <= 1024:
        raise ValueError("conversation cursor is invalid")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if set(payload) != {"version", "updated_at", "thread_id"} or type(payload["version"]) is not int:
            raise ValueError("conversation cursor fields are invalid")
        if payload["version"] != 1:
            raise ValueError("conversation cursor version is invalid")
        instant = _utc(datetime.fromisoformat(payload["updated_at"]))
        thread_id = payload["thread_id"]
        if encode_thread_cursor(instant, thread_id) != value:
            raise ValueError("conversation cursor is not canonical")
        return instant, thread_id
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("conversation cursor is invalid") from exc


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ConversationRepositoryError("timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _json_refs(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _json_context_snapshot(values: Iterable[tuple[str, str]]) -> str:
    return json.dumps(
        [list(item) for item in values],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _parse_context_snapshot(
    raw: object,
    field: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, str):
        raise ConversationRepositoryCorruption(f"{field} must be JSON text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConversationRepositoryCorruption(f"{field} contains invalid JSON") from exc
    if not isinstance(value, list):
        raise ConversationRepositoryCorruption(f"{field} must contain a pair list")
    result: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ConversationRepositoryCorruption(f"{field} entries must be pairs")
        if any(not isinstance(part, str) for part in item):
            raise ConversationRepositoryCorruption(f"{field} entries must contain strings")
        result.append((item[0], item[1]))
    return tuple(result)


def _parse_refs(raw: object, field: str) -> tuple[str, ...]:
    if not isinstance(raw, str):
        raise ConversationRepositoryCorruption(f"{field} must be JSON text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConversationRepositoryCorruption(f"{field} contains invalid JSON") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConversationRepositoryCorruption(f"{field} must contain a string list")
    return tuple(value)


def _parse_time(raw: object, field: str) -> datetime:
    if not isinstance(raw, str):
        raise ConversationRepositoryCorruption(f"{field} must be ISO-8601 text")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ConversationRepositoryCorruption(f"{field} is invalid") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ConversationRepositoryCorruption(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


class SQLiteConversationRepository:
    """Transactional conversation authority reference implementation."""

    def __init__(self, path: str | Path = ":memory:", *, namespace: str = "conversation") -> None:
        namespace = str(namespace).strip()
        if not namespace:
            raise ValueError("namespace must not be empty")
        self.namespace = namespace
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            timeout=5.0,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS conversation_thread (
                    namespace TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    message_sequence INTEGER NOT NULL,
                    active_branch_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    title TEXT NOT NULL,
                    data_class TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    PRIMARY KEY(namespace, thread_id)
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_thread_owner
                ON conversation_thread(namespace, tenant_id, owner_id, updated_at);

                CREATE TABLE IF NOT EXISTS conversation_message (
                    namespace TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    author_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    content TEXT,
                    content_ref TEXT,
                    parent_message_id TEXT,
                    supersedes_message_id TEXT,
                    causal_user_message_id TEXT,
                    operation_id TEXT,
                    ai_result_id TEXT,
                    context_id TEXT,
                    context_digest TEXT,
                    context_source_snapshot_json TEXT NOT NULL DEFAULT '[]',
                    context_compiler_version TEXT,
                    attachment_refs_json TEXT NOT NULL,
                    tool_receipt_refs_json TEXT NOT NULL,
                    provider_receipt_refs_json TEXT NOT NULL DEFAULT '[]',
                    memory_refs_json TEXT NOT NULL DEFAULT '[]',
                    citation_refs_json TEXT NOT NULL,
                    artifact_refs_json TEXT NOT NULL,
                    data_class TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    PRIMARY KEY(namespace, message_id),
                    UNIQUE(namespace, thread_id, sequence),
                    UNIQUE(namespace, thread_id, idempotency_key),
                    FOREIGN KEY(namespace, thread_id)
                        REFERENCES conversation_thread(namespace, thread_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_message_thread
                ON conversation_message(namespace, thread_id, sequence);

                CREATE TABLE IF NOT EXISTS conversation_chat_execution (
                    namespace TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY(namespace, message_id),
                    FOREIGN KEY(namespace, thread_id)
                        REFERENCES conversation_thread(namespace, thread_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY(namespace, message_id)
                        REFERENCES conversation_message(namespace, message_id)
                        ON DELETE CASCADE
                );
                """
            )
            columns = {
                row["name"]
                for row in self._connection.execute(
                    "PRAGMA table_info(conversation_message)"
                ).fetchall()
            }
            migrations = {
                "context_id": "context_id TEXT",
                "context_digest": "context_digest TEXT",
                "context_source_snapshot_json": (
                    "context_source_snapshot_json TEXT NOT NULL DEFAULT '[]'"
                ),
                "context_compiler_version": "context_compiler_version TEXT",
                "provider_receipt_refs_json": (
                    "provider_receipt_refs_json TEXT NOT NULL DEFAULT '[]'"
                ),
                "memory_refs_json": (
                    "memory_refs_json TEXT NOT NULL DEFAULT '[]'"
                ),
            }
            for column, declaration in migrations.items():
                if column not in columns:
                    self._connection.execute(
                        f"ALTER TABLE conversation_message ADD COLUMN {declaration}"
                    )

    @staticmethod
    def _thread_from_row(row: sqlite3.Row) -> ConversationThread:
        try:
            return ConversationThread(
                thread_id=row["thread_id"],
                tenant_id=row["tenant_id"],
                owner_id=row["owner_id"],
                created_at=_parse_time(row["created_at"], "created_at"),
                updated_at=_parse_time(row["updated_at"], "updated_at"),
                version=int(row["version"]),
                message_sequence=int(row["message_sequence"]),
                active_branch_id=row["active_branch_id"],
                state=ConversationThreadState(row["state"]),
                title=row["title"],
                data_class=row["data_class"],
                schema_version=int(row["schema_version"]),
            )
        except (KeyError, TypeError, ValueError, ConversationContractError) as exc:
            if isinstance(exc, ConversationRepositoryCorruption):
                raise
            raise ConversationRepositoryCorruption(
                "persisted thread violates canonical conversation contract"
            ) from exc

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> ConversationMessage:
        try:
            return ConversationMessage(
                message_id=row["message_id"],
                thread_id=row["thread_id"],
                branch_id=row["branch_id"],
                sequence=int(row["sequence"]),
                author_type=ConversationAuthorType(row["author_type"]),
                created_at=_parse_time(row["created_at"], "created_at"),
                idempotency_key=row["idempotency_key"],
                content=row["content"],
                content_ref=row["content_ref"],
                parent_message_id=row["parent_message_id"],
                supersedes_message_id=row["supersedes_message_id"],
                causal_user_message_id=row["causal_user_message_id"],
                operation_id=row["operation_id"],
                ai_result_id=row["ai_result_id"],
                context_id=row["context_id"],
                context_digest=row["context_digest"],
                context_source_snapshot=_parse_context_snapshot(
                    row["context_source_snapshot_json"],
                    "context_source_snapshot_json",
                ),
                context_compiler_version=row["context_compiler_version"],
                attachment_refs=_parse_refs(row["attachment_refs_json"], "attachment_refs_json"),
                tool_receipt_refs=_parse_refs(row["tool_receipt_refs_json"], "tool_receipt_refs_json"),
                provider_receipt_refs=_parse_refs(
                    row["provider_receipt_refs_json"],
                    "provider_receipt_refs_json",
                ),
                memory_refs=_parse_refs(row["memory_refs_json"], "memory_refs_json"),
                citation_refs=_parse_refs(row["citation_refs_json"], "citation_refs_json"),
                artifact_refs=_parse_refs(row["artifact_refs_json"], "artifact_refs_json"),
                data_class=row["data_class"],
                schema_version=int(row["schema_version"]),
            )
        except (KeyError, TypeError, ValueError, ConversationContractError) as exc:
            if isinstance(exc, ConversationRepositoryCorruption):
                raise
            raise ConversationRepositoryCorruption(
                "persisted message violates canonical conversation contract"
            ) from exc

    def _thread_row(self, thread_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM conversation_thread WHERE namespace = ? AND thread_id = ?",
            (self.namespace, thread_id),
        ).fetchone()

    def _message_row(self, message_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM conversation_message WHERE namespace = ? AND message_id = ?",
            (self.namespace, message_id),
        ).fetchone()

    @staticmethod
    def _authorize(thread: ConversationThread, tenant_id: str, owner_id: str) -> None:
        if thread.tenant_id != tenant_id or thread.owner_id != owner_id:
            raise ConversationAuthorizationError("conversation access denied")

    def create_thread(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        title: str = "New conversation",
        data_class: str = "confidential",
        thread_id: str | None = None,
        branch_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ConversationThread:
        now = _utc(created_at)
        thread = ConversationThread(
            thread_id=thread_id or str(uuid4()),
            tenant_id=tenant_id,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
            version=1,
            message_sequence=0,
            active_branch_id=branch_id or str(uuid4()),
            state=ConversationThreadState.ACTIVE,
            title=title,
            data_class=data_class,
        )
        with self._lock:
            try:
                self._connection.execute(
                    """
                    INSERT INTO conversation_thread(
                        namespace, thread_id, tenant_id, owner_id, created_at, updated_at,
                        version, message_sequence, active_branch_id, state, title,
                        data_class, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        thread.thread_id,
                        thread.tenant_id,
                        thread.owner_id,
                        thread.created_at.isoformat(),
                        thread.updated_at.isoformat(),
                        thread.version,
                        thread.message_sequence,
                        thread.active_branch_id,
                        thread.state.value,
                        thread.title,
                        thread.data_class,
                        thread.schema_version,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConversationConflict("thread identity already exists") from exc
        return thread

    def get_thread(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> ConversationThread:
        with self._lock:
            row = self._thread_row(thread_id)
        if row is None:
            raise ConversationNotFound(thread_id)
        thread = self._thread_from_row(row)
        self._authorize(thread, tenant_id, owner_id)
        return thread

    def list_threads(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        include_archived: bool = False,
        limit: int = 50,
        search: str = "",
        cursor: str | None = None,
    ) -> tuple[ConversationThread, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        states = ("active", "archived") if include_archived else ("active",)
        placeholders = ",".join("?" for _ in states)
        query = conversation_search_text(search)
        conditions = ["namespace = ?", "tenant_id = ?", "owner_id = ?", f"state IN ({placeholders})"]
        parameters: list[object] = [self.namespace, tenant_id, owner_id, *states]
        if query:
            conditions.append("instr(lower(title), lower(?)) > 0")
            parameters.append(query)
        if cursor is not None:
            instant, thread_id = decode_thread_cursor(cursor)
            conditions.append("(updated_at < ? OR (updated_at = ? AND thread_id > ?))")
            parameters.extend([instant.isoformat(), instant.isoformat(), thread_id])
        parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT * FROM conversation_thread
                WHERE {' AND '.join(conditions)}
                ORDER BY updated_at DESC, thread_id ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return tuple(self._thread_from_row(row) for row in rows)
    def rename_thread(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        expected_version: int,
        title: str,
    ) -> ConversationThread:
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expected_version must be a positive integer")
        if not isinstance(title, str):
            raise TypeError("conversation title must be text")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._thread_row(thread_id)
                if row is None:
                    raise ConversationNotFound(thread_id)
                thread = self._thread_from_row(row)
                self._authorize(thread, tenant_id, owner_id)
                if thread.version != expected_version:
                    raise ConversationConflict("thread version conflict")
                if thread.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
                    raise ConversationConflict("thread metadata is not writable")
                candidate = replace(
                    thread, title=title.strip(), updated_at=_utc(), version=thread.version + 1
                )
                updated = self._connection.execute(
                    """UPDATE conversation_thread SET title=?,updated_at=?,version=?
                    WHERE namespace=? AND thread_id=? AND tenant_id=? AND owner_id=? AND version=?""",
                    (
                        candidate.title,
                        candidate.updated_at.isoformat(),
                        candidate.version,
                        self.namespace,
                        thread_id,
                        tenant_id,
                        owner_id,
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise ConversationConflict("thread version changed during rename")
                self._connection.execute("COMMIT")
                return candidate
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise


    def _same_message_identity(
        self,
        existing: ConversationMessage,
        candidate: ConversationMessage,
    ) -> bool:
        return (
            existing.thread_id == candidate.thread_id
            and existing.author_type == candidate.author_type
            and existing.content == candidate.content
            and existing.content_ref == candidate.content_ref
            and existing.parent_message_id == candidate.parent_message_id
            and existing.supersedes_message_id == candidate.supersedes_message_id
            and existing.causal_user_message_id == candidate.causal_user_message_id
            and existing.operation_id == candidate.operation_id
            and existing.ai_result_id == candidate.ai_result_id
            and existing.context_id == candidate.context_id
            and existing.context_digest == candidate.context_digest
            and existing.context_source_snapshot == candidate.context_source_snapshot
            and existing.context_compiler_version == candidate.context_compiler_version
            and existing.attachment_refs == candidate.attachment_refs
            and existing.tool_receipt_refs == candidate.tool_receipt_refs
            and existing.provider_receipt_refs == candidate.provider_receipt_refs
            and existing.memory_refs == candidate.memory_refs
            and existing.citation_refs == candidate.citation_refs
            and existing.artifact_refs == candidate.artifact_refs
            and existing.data_class == candidate.data_class
        )

    def append_message(
        self,
        message: ConversationMessage,
        *,
        tenant_id: str,
        owner_id: str,
        expected_thread_version: int,
        activate_branch: bool = True,
        execution_metadata: dict[str, object] | None = None,
    ) -> tuple[ConversationThread, ConversationMessage]:
        if not isinstance(message, ConversationMessage):
            raise TypeError("message must be a ConversationMessage")
        encoded_execution = None
        if execution_metadata is not None:
            if (
                message.author_type is not ConversationAuthorType.USER
                or "chat-prepared-execution:v1" not in message.attachment_refs
                or not isinstance(execution_metadata, dict)
            ):
                raise ConversationConflict("prepared execution must be bound to a canonical USER")
            try:
                encoded_execution = json.dumps(
                    execution_metadata, ensure_ascii=False, allow_nan=False,
                    sort_keys=True, separators=(",", ":"),
                )
            except (TypeError, ValueError, RecursionError, OverflowError) as exc:
                raise ConversationConflict("prepared execution metadata is not canonical JSON") from exc
            if len(encoded_execution.encode("utf-8")) > 2 * 1024 * 1024:
                raise ConversationConflict("prepared execution metadata exceeds its byte bound")
            # The portable owner shares the same canonical, digest-sealed
            # envelope as Mongo. Full engine-command semantic checks happen
            # at preparation/read; malformed envelopes cannot be published.
            mandatory = {
                "schema_version", "request_digest", "command",
                "dependencies", "command_digest", "record_digest",
            }
            if (
                set(execution_metadata) != mandatory
                or execution_metadata["schema_version"] != "backend.ai.chat-execution.v1"
                or not isinstance(execution_metadata["command"], dict)
                or not isinstance(execution_metadata["dependencies"], dict)
            ):
                raise ConversationConflict("prepared execution envelope is invalid")
            request_digest = execution_metadata["request_digest"]
            if (
                not isinstance(request_digest, str)
                or len(request_digest) != 64
                or any(digit not in "0123456789abcdef" for digit in request_digest)
                or "chat-request-sha256:" + request_digest not in message.attachment_refs
            ):
                raise ConversationConflict("prepared execution request identity differs")
            def canonical_digest(value: object) -> str:
                data = json.dumps(
                    value, ensure_ascii=False, allow_nan=False,
                    sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")
                return hashlib.sha256(data).hexdigest()
            if (
                execution_metadata["command_digest"]
                != canonical_digest(execution_metadata["command"])
                or execution_metadata["record_digest"]
                != canonical_digest({
                    key: value for key, value in execution_metadata.items()
                    if key != "record_digest"
                })
            ):
                raise ConversationConflict("prepared execution digest differs")
        elif "chat-prepared-execution:v1" in message.attachment_refs:
            raise ConversationConflict("prepared USER requires its original execution metadata")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._thread_row(message.thread_id)
                if row is None:
                    raise ConversationNotFound(message.thread_id)
                thread = self._thread_from_row(row)
                self._authorize(thread, tenant_id, owner_id)
                if not thread.writable:
                    raise ConversationConflict("thread is not writable")

                # A replay may not replace or drop the frozen engine command
                # under the same immutable USER/idempotency identity.
                def matching_execution(existing_id: str) -> bool:
                    stored = self._connection.execute(
                        """
                        SELECT metadata_json FROM conversation_chat_execution
                        WHERE namespace = ? AND thread_id = ? AND message_id = ?
                        """,
                        (self.namespace, message.thread_id, existing_id),
                    ).fetchone()
                    if encoded_execution is None:
                        return stored is None
                    return stored is not None and stored["metadata_json"] == encoded_execution

                by_id = self._message_row(message.message_id)
                if by_id is not None:
                    existing = self._message_from_row(by_id)
                    if self._same_message_identity(existing, message):
                        if not matching_execution(existing.message_id):
                            raise ConversationConflict("replayed execution metadata differs")
                        self._connection.execute("COMMIT")
                        return thread, existing
                    raise ConversationConflict("message_id was reused with different content")

                idem = self._connection.execute(
                    """
                    SELECT * FROM conversation_message
                    WHERE namespace = ? AND thread_id = ? AND idempotency_key = ?
                    """,
                    (self.namespace, message.thread_id, message.idempotency_key),
                ).fetchone()
                if idem is not None:
                    existing = self._message_from_row(idem)
                    if self._same_message_identity(existing, message):
                        if not matching_execution(existing.message_id):
                            raise ConversationConflict("replayed execution metadata differs")
                        self._connection.execute("COMMIT")
                        return thread, existing
                    raise ConversationConflict("idempotency_key was reused with different content")

                if thread.version != expected_thread_version:
                    raise ConversationConflict("thread version conflict")
                expected_sequence = thread.message_sequence + 1
                if message.sequence != expected_sequence:
                    raise ConversationConflict(
                        f"message sequence must be exact-next ({expected_sequence})"
                    )

                if message.parent_message_id is not None:
                    parent_row = self._message_row(message.parent_message_id)
                    if parent_row is None:
                        raise ConversationConflict("parent message does not exist")
                    parent = self._message_from_row(parent_row)
                    if parent.thread_id != message.thread_id:
                        raise ConversationConflict("parent message belongs to another thread")
                    if parent.sequence >= message.sequence:
                        raise ConversationConflict("parent message must precede child")

                if message.supersedes_message_id is not None:
                    prior_row = self._message_row(message.supersedes_message_id)
                    if prior_row is None:
                        raise ConversationConflict("superseded message does not exist")
                    prior = self._message_from_row(prior_row)
                    if prior.thread_id != message.thread_id:
                        raise ConversationConflict("superseded message belongs to another thread")
                    if prior.author_type != message.author_type:
                        raise ConversationConflict("superseding message must preserve author type")

                self._connection.execute(
                    """
                    INSERT INTO conversation_message(
                        namespace, message_id, thread_id, branch_id, sequence, author_type,
                        created_at, idempotency_key, content, content_ref, parent_message_id,
                        supersedes_message_id, causal_user_message_id, operation_id,
                        ai_result_id, context_id, context_digest,
                        context_source_snapshot_json, context_compiler_version,
                        attachment_refs_json, tool_receipt_refs_json,
                        provider_receipt_refs_json, memory_refs_json,
                        citation_refs_json, artifact_refs_json,
                        data_class, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        message.message_id,
                        message.thread_id,
                        message.branch_id,
                        message.sequence,
                        message.author_type.value,
                        message.created_at.isoformat(),
                        message.idempotency_key,
                        message.content,
                        message.content_ref,
                        message.parent_message_id,
                        message.supersedes_message_id,
                        message.causal_user_message_id,
                        message.operation_id,
                        message.ai_result_id,
                        message.context_id,
                        message.context_digest,
                        _json_context_snapshot(message.context_source_snapshot),
                        message.context_compiler_version,
                        _json_refs(message.attachment_refs),
                        _json_refs(message.tool_receipt_refs),
                        _json_refs(message.provider_receipt_refs),
                        _json_refs(message.memory_refs),
                        _json_refs(message.citation_refs),
                        _json_refs(message.artifact_refs),
                        message.data_class,
                        message.schema_version,
                    ),
                )
                if encoded_execution is not None:
                    self._connection.execute(
                        """
                        INSERT INTO conversation_chat_execution(
                            namespace, thread_id, message_id, metadata_json
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (self.namespace, message.thread_id, message.message_id, encoded_execution),
                    )
                now = _utc()
                next_thread = replace(
                    thread,
                    updated_at=now,
                    version=thread.version + 1,
                    message_sequence=message.sequence,
                    active_branch_id=(
                        message.branch_id if activate_branch else thread.active_branch_id
                    ),
                )
                updated = self._connection.execute(
                    """
                    UPDATE conversation_thread
                    SET updated_at = ?, version = ?, message_sequence = ?, active_branch_id = ?
                    WHERE namespace = ? AND thread_id = ? AND version = ?
                    """,
                    (
                        next_thread.updated_at.isoformat(),
                        next_thread.version,
                        next_thread.message_sequence,
                        next_thread.active_branch_id,
                        self.namespace,
                        thread.thread_id,
                        thread.version,
                    ),
                )
                if updated.rowcount != 1:
                    raise ConversationConflict("thread version changed during append")
                self._connection.execute("COMMIT")
                return next_thread, message
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def chat_execution(
        self,
        thread_id: str,
        message_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> dict[str, object] | None:
        """Read only the frozen command belonging to an authorized USER."""
        with self._lock:
            row = self._thread_row(thread_id)
            if row is None:
                raise ConversationNotFound(thread_id)
            self._authorize(self._thread_from_row(row), tenant_id, owner_id)
            message_row = self._message_row(message_id)
            if message_row is None or message_row["thread_id"] != thread_id:
                raise ConversationNotFound(message_id)
            stored = self._connection.execute(
                """
                SELECT metadata_json FROM conversation_chat_execution
                WHERE namespace = ? AND thread_id = ? AND message_id = ?
                """,
                (self.namespace, thread_id, message_id),
            ).fetchone()
            if stored is None:
                return None
            try:
                value = json.loads(stored["metadata_json"])
            except (TypeError, ValueError, UnicodeError) as exc:
                raise ConversationRepositoryCorruption("prepared chat metadata is unreadable") from exc
            if not isinstance(value, dict):
                raise ConversationRepositoryCorruption("prepared chat metadata has invalid shape")
            return value

    def list_messages(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[ConversationMessage, ...]:
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < 0:
            raise ValueError("after_sequence must be a non-negative integer")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        thread = self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
            raise ConversationConflict("conversation content is unavailable")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM conversation_message
                WHERE namespace = ? AND thread_id = ? AND sequence > ? AND sequence <= ?
                ORDER BY sequence ASC
                LIMIT ?
                """,
                (self.namespace, thread_id, after_sequence, thread.message_sequence, limit),
            ).fetchall()
        return tuple(self._message_from_row(row) for row in rows)

    def active_transcript(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> tuple[ConversationMessage, ...]:
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                thread = self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
                messages, cursor, _tip = self._active_lineage_page(thread, limit=10_000)
                if cursor is not None:
                    raise ConversationRepositoryCorruption(
                        "conversation active lineage exceeds the message bound"
                    )
                self._connection.execute("COMMIT")
                return messages
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
    def _active_lineage_page(
        self, thread: ConversationThread, *, limit: int, before_message_id: str | None = None
    ) -> tuple[tuple[ConversationMessage, ...], str | None, ConversationMessage | None]:
        if thread.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
            raise ConversationConflict("conversation content is unavailable")
        if thread.message_sequence == 0:
            if before_message_id is not None:
                raise ConversationNotFound(before_message_id)
            return (), None, None
        row = self._connection.execute(
            """SELECT * FROM conversation_message
            WHERE namespace=? AND thread_id=? AND branch_id=? AND sequence<=?
            ORDER BY sequence DESC LIMIT 1""",
            (self.namespace, thread.thread_id, thread.active_branch_id, thread.message_sequence),
        ).fetchone()
        if row is None:
            raise ConversationRepositoryCorruption("conversation active branch tip is missing")
        tip = self._message_from_row(row)
        current = tip
        seen: set[str] = set()
        page: list[ConversationMessage] = []
        started = before_message_id is None
        previous_sequence = thread.message_sequence + 1
        content_bytes = 0
        for _depth in range(10_000):
            if (
                current.thread_id != thread.thread_id
                or current.message_id in seen
                or not 0 < current.sequence < previous_sequence
            ):
                raise ConversationRepositoryCorruption("conversation parent lineage is invalid")
            seen.add(current.message_id)
            previous_sequence = current.sequence
            started = started or current.message_id == before_message_id
            if started:
                content_bytes += len(
                    json.dumps(current.as_dict(), ensure_ascii=False, allow_nan=False).encode("utf-8")
                )
                if content_bytes > 8 * 1024 * 1024:
                    raise ConversationRepositoryCorruption(
                        "conversation projection exceeds its content bound"
                    )
                page.append(current)
            if current.parent_message_id is None:
                if not started:
                    raise ConversationNotFound(str(before_message_id))
                return tuple(reversed(page)), None, tip
            parent_row = self._message_row(current.parent_message_id)
            if parent_row is None:
                raise ConversationRepositoryCorruption("conversation parent lineage is incomplete")
            parent = self._message_from_row(parent_row)
            if parent.thread_id != thread.thread_id or parent.sequence >= current.sequence:
                raise ConversationRepositoryCorruption("conversation parent lineage is invalid")
            if started and len(page) == limit:
                return tuple(reversed(page)), parent.message_id, tip
            current = parent
        raise ConversationRepositoryCorruption("conversation lineage exceeds the recovery bound")

    def conversation_snapshot(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        limit: int = 100,
        before_message_id: str | None = None,
        expected_thread_version: int | None = None,
    ) -> dict[str, object]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("snapshot limit must be between 1 and 500")
        if expected_thread_version is not None and (
            type(expected_thread_version) is not int or expected_thread_version < 1
        ):
            raise ValueError("expected_thread_version must be a positive integer")
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                thread = self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
                if expected_thread_version is not None and thread.version != expected_thread_version:
                    raise ConversationConflict(
                        "thread version conflict; reconstruct the current conversation"
                    )
                messages, cursor, tip = self._active_lineage_page(
                    thread, limit=limit, before_message_id=before_message_id
                )
                pending = None
                if tip is not None and tip.author_type is ConversationAuthorType.USER:
                    pending = {
                        "message_id": tip.message_id,
                        "idempotency_key": tip.idempotency_key,
                        "sequence": tip.sequence,
                        "attachment_refs": list(tip.attachment_refs),
                        "can_retry": thread.writable,
                    }
                result = {
                    "thread": thread.as_dict(),
                    "messages": [message.as_dict() for message in messages],
                    "last_sequence": 0 if tip is None else tip.sequence,
                    "next_before_message_id": cursor,
                    "pending_turn": pending,
                    "projection": "active",
                    "snapshot_version": thread.version,
                }
                self._connection.execute("COMMIT")
                return result
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise


    def set_state(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        expected_version: int,
        state: ConversationThreadState,
    ) -> ConversationThread:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._thread_row(thread_id)
                if row is None:
                    raise ConversationNotFound(thread_id)
                thread = self._thread_from_row(row)
                self._authorize(thread, tenant_id, owner_id)
                if thread.version != expected_version:
                    raise ConversationConflict("thread version conflict")
                next_state = ConversationThreadState(state)
                if thread.state is ConversationThreadState.DELETED:
                    raise ConversationConflict("deleted thread is terminal")
                now = _utc()
                updated_thread = replace(
                    thread,
                    state=next_state,
                    updated_at=now,
                    version=thread.version + 1,
                )
                updated = self._connection.execute(
                    """
                    UPDATE conversation_thread
                    SET state = ?, updated_at = ?, version = ?
                    WHERE namespace = ? AND thread_id = ? AND version = ?
                    """,
                    (
                        next_state.value,
                        updated_thread.updated_at.isoformat(),
                        updated_thread.version,
                        self.namespace,
                        thread_id,
                        thread.version,
                    ),
                )
                if updated.rowcount != 1:
                    raise ConversationConflict("thread version changed during state update")
                self._connection.execute("COMMIT")
                return updated_thread
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "ConversationAuthorizationError",
    "ConversationConflict",
    "ConversationNotFound",
    "ConversationRepositoryCorruption",
    "ConversationRepositoryError",
    "SQLiteConversationRepository",
]
