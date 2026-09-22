"""Durable reference repository for canonical conversation authority.

Production conversation state is expected to live in backend core Mongo. This
SQLite adapter is the portable conformance implementation for ownership,
idempotency, exact-next sequencing, optimistic thread versions, immutable
branch lineage, and transcript reconstruction.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable
from uuid import uuid4

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


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ConversationRepositoryError("timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _json_refs(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


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
                    attachment_refs_json TEXT NOT NULL,
                    tool_receipt_refs_json TEXT NOT NULL,
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
                """
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
                attachment_refs=_parse_refs(row["attachment_refs_json"], "attachment_refs_json"),
                tool_receipt_refs=_parse_refs(row["tool_receipt_refs_json"], "tool_receipt_refs_json"),
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
    ) -> tuple[ConversationThread, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        states = ("active", "archived") if include_archived else ("active",)
        placeholders = ",".join("?" for _ in states)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT * FROM conversation_thread
                WHERE namespace = ? AND tenant_id = ? AND owner_id = ?
                  AND state IN ({placeholders})
                ORDER BY updated_at DESC, thread_id ASC
                LIMIT ?
                """,
                (self.namespace, tenant_id, owner_id, *states, limit),
            ).fetchall()
        return tuple(self._thread_from_row(row) for row in rows)

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
            and existing.attachment_refs == candidate.attachment_refs
            and existing.tool_receipt_refs == candidate.tool_receipt_refs
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
    ) -> tuple[ConversationThread, ConversationMessage]:
        if not isinstance(message, ConversationMessage):
            raise TypeError("message must be a ConversationMessage")
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

                by_id = self._message_row(message.message_id)
                if by_id is not None:
                    existing = self._message_from_row(by_id)
                    if self._same_message_identity(existing, message):
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
                        ai_result_id, attachment_refs_json, tool_receipt_refs_json,
                        citation_refs_json, artifact_refs_json, data_class, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        _json_refs(message.attachment_refs),
                        _json_refs(message.tool_receipt_refs),
                        _json_refs(message.citation_refs),
                        _json_refs(message.artifact_refs),
                        message.data_class,
                        message.schema_version,
                    ),
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
        del thread
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM conversation_message
                WHERE namespace = ? AND thread_id = ? AND sequence > ?
                ORDER BY sequence ASC
                LIMIT ?
                """,
                (self.namespace, thread_id, after_sequence, limit),
            ).fetchall()
        return tuple(self._message_from_row(row) for row in rows)

    def active_transcript(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> tuple[ConversationMessage, ...]:
        thread = self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        messages = self.list_messages(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            after_sequence=0,
            limit=500,
        )
        by_id = {message.message_id: message for message in messages}
        branch_messages = [
            message for message in messages if message.branch_id == thread.active_branch_id
        ]
        if branch_messages:
            tip = branch_messages[-1]
        elif messages:
            tip = messages[-1]
        else:
            return ()

        lineage: list[ConversationMessage] = []
        seen: set[str] = set()
        current: ConversationMessage | None = tip
        while current is not None:
            if current.message_id in seen:
                raise ConversationRepositoryCorruption("conversation lineage contains a cycle")
            seen.add(current.message_id)
            lineage.append(current)
            current = (
                by_id.get(current.parent_message_id)
                if current.parent_message_id is not None
                else None
            )
        lineage.reverse()
        return tuple(lineage)

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
