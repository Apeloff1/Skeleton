"""Transactional persistence for durable AI-chat turn operations.

The conversation repository remains authoritative for transcript state. This
module stores only turn-operation metadata and immutable transition events,
bound to a canonical conversation thread and causal user message.

SQLite is the portable conformance implementation. Production adapters must
preserve the same invariants:
- conversation binding is immutable;
- operation creation is idempotent only for an identical binding;
- event sequence is exact-next and digest chained;
- event append and snapshot advancement are atomic;
- restart reconstruction replays immutable events and verifies the materialized
  snapshot rather than trusting cached state;
- terminal snapshots cannot accept more events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable
from uuid import UUID

from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.turn_runtime import (
    CHAT_TURN_SCHEMA_VERSION,
    BudgetUsage,
    ExecutionBudget,
    FailureClass,
    RecoveryDecision,
    RecoveryPlanner,
    TurnEvent,
    TurnJournal,
    TurnRuntimeError,
    TurnSnapshot,
    TurnState,
    operation_digest,
    start_turn,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
)


class ChatTurnRepositoryError(RuntimeError):
    """Base durable turn repository failure."""


class ChatTurnNotFound(ChatTurnRepositoryError):
    """Requested turn operation does not exist."""


class ChatTurnAuthorizationError(ChatTurnRepositoryError):
    """Caller is not authorized for the requested turn operation."""


class ChatTurnConflict(ChatTurnRepositoryError):
    """Optimistic sequence, identity, or replay state conflicted."""


class ChatTurnCorruption(ChatTurnRepositoryError):
    """Persisted turn data violates the canonical runtime contract."""


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if (
        not isinstance(instant, datetime)
        or instant.tzinfo is None
        or instant.utcoffset() is None
    ):
        raise ChatTurnRepositoryError("timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _uuid(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChatTurnRepositoryError(f"{field_name} must be a canonical UUID")
    text = value.strip()
    try:
        parsed = UUID(text)
    except (ValueError, AttributeError) as exc:
        raise ChatTurnRepositoryError(
            f"{field_name} must be a canonical UUID"
        ) from exc
    if str(parsed) != text:
        raise ChatTurnRepositoryError(
            f"{field_name} must be a canonical UUID"
        )
    return text


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ChatTurnRepositoryError(f"{field_name} must be lowercase sha256")
    text = value.strip()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ChatTurnRepositoryError(f"{field_name} must be lowercase sha256")
    return text


def _text(value: object, field_name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChatTurnRepositoryError(f"{field_name} must be non-empty text")
    text = value.strip()
    if len(text) > maximum:
        raise ChatTurnRepositoryError(f"{field_name} exceeds maximum length")
    return text


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ChatTurnRepositoryError(
            "turn persistence value is not deterministic JSON"
        ) from exc


def _parse_json(raw: object, field_name: str) -> object:
    if not isinstance(raw, str):
        raise ChatTurnCorruption(f"{field_name} must be JSON text")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChatTurnCorruption(f"{field_name} contains invalid JSON") from exc


def _parse_time(raw: object, field_name: str) -> datetime:
    if not isinstance(raw, str):
        raise ChatTurnCorruption(f"{field_name} must be ISO-8601 text")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ChatTurnCorruption(f"{field_name} is invalid") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ChatTurnCorruption(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _budget_from_dict(raw: object) -> ExecutionBudget:
    if not isinstance(raw, dict):
        raise ChatTurnCorruption("budget must be an object")
    try:
        return ExecutionBudget(
            max_wall_seconds=raw["max_wall_seconds"],
            max_input_tokens=raw["max_input_tokens"],
            max_output_tokens=raw["max_output_tokens"],
            max_model_calls=raw["max_model_calls"],
            max_tool_calls=raw["max_tool_calls"],
            max_agent_depth=raw["max_agent_depth"],
            max_parallel_workers=raw["max_parallel_workers"],
            max_retrieval_queries=raw["max_retrieval_queries"],
            max_external_writes=raw["max_external_writes"],
            max_cost_usd=raw["max_cost_usd"],
        )
    except (KeyError, TypeError, ValueError, TurnRuntimeError) as exc:
        raise ChatTurnCorruption("persisted budget is invalid") from exc


def _usage_from_dict(raw: object) -> BudgetUsage:
    if not isinstance(raw, dict):
        raise ChatTurnCorruption("usage must be an object")
    try:
        return BudgetUsage(
            wall_seconds=raw["wall_seconds"],
            input_tokens=raw["input_tokens"],
            output_tokens=raw["output_tokens"],
            model_calls=raw["model_calls"],
            tool_calls=raw["tool_calls"],
            agent_depth=raw["agent_depth"],
            parallel_workers=raw["parallel_workers"],
            retrieval_queries=raw["retrieval_queries"],
            external_writes=raw["external_writes"],
            cost_usd=raw["cost_usd"],
        )
    except (KeyError, TypeError, ValueError, TurnRuntimeError) as exc:
        raise ChatTurnCorruption("persisted usage is invalid") from exc


def _event_from_dict(raw: object) -> TurnEvent:
    if not isinstance(raw, dict):
        raise ChatTurnCorruption("turn event must be an object")
    try:
        usage_raw = raw.get("usage")
        return TurnEvent(
            operation_id=raw["operation_id"],
            request_digest=raw["request_digest"],
            sequence=raw["sequence"],
            from_state=TurnState(raw["from_state"]),
            to_state=TurnState(raw["to_state"]),
            observed_at=_parse_time(raw["observed_at"], "event observed_at"),
            previous_event_digest=raw.get("previous_event_digest"),
            reason_code=raw["reason_code"],
            failure_class=(
                None
                if raw.get("failure_class") is None
                else FailureClass(raw["failure_class"])
            ),
            tool_call_id=raw.get("tool_call_id"),
            tool_side_effect=(
                None
                if raw.get("tool_side_effect") is None
                else SideEffectClass(raw["tool_side_effect"])
            ),
            tool_receipt_ref=raw.get("tool_receipt_ref"),
            external_effect_started=bool(raw.get("external_effect_started")),
            provider_receipt_ref=raw.get("provider_receipt_ref"),
            usage=(
                None
                if usage_raw is None
                else _usage_from_dict(usage_raw)
            ),
            payload=raw.get("payload") or {},
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        TurnRuntimeError,
        ChatTurnCorruption,
    ) as exc:
        if isinstance(exc, ChatTurnCorruption):
            raise
        raise ChatTurnCorruption("persisted turn event is invalid") from exc


@dataclass(frozen=True, slots=True)
class ChatTurnBinding:
    """Immutable conversation authority binding for one turn operation."""

    tenant_id: str
    owner_id: str
    thread_id: str
    causal_user_message_id: str
    admitted_thread_version: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tenant_id",
            _text(self.tenant_id, "tenant_id"),
        )
        object.__setattr__(
            self,
            "owner_id",
            _text(self.owner_id, "owner_id"),
        )
        object.__setattr__(
            self,
            "thread_id",
            _uuid(self.thread_id, "thread_id"),
        )
        object.__setattr__(
            self,
            "causal_user_message_id",
            _uuid(
                self.causal_user_message_id,
                "causal_user_message_id",
            ),
        )
        if (
            isinstance(self.admitted_thread_version, bool)
            or not isinstance(self.admitted_thread_version, int)
            or self.admitted_thread_version < 1
        ):
            raise ChatTurnRepositoryError(
                "admitted_thread_version must be a positive integer"
            )

    @classmethod
    def from_conversation(
        cls,
        thread: ConversationThread,
        user_message: ConversationMessage,
    ) -> "ChatTurnBinding":
        if not isinstance(thread, ConversationThread):
            raise TypeError("thread must be ConversationThread")
        if not isinstance(user_message, ConversationMessage):
            raise TypeError("user_message must be ConversationMessage")
        if user_message.thread_id != thread.thread_id:
            raise ChatTurnConflict(
                "causal user message belongs to a different thread"
            )
        if user_message.author_type is not ConversationAuthorType.USER:
            raise ChatTurnConflict(
                "turn causal message must be a canonical user message"
            )
        if user_message.sequence > thread.message_sequence:
            raise ChatTurnConflict(
                "causal user message is not committed in the thread"
            )
        if not thread.writable:
            raise ChatTurnConflict("conversation thread is not writable")
        return cls(
            tenant_id=thread.tenant_id,
            owner_id=thread.owner_id,
            thread_id=thread.thread_id,
            causal_user_message_id=user_message.message_id,
            admitted_thread_version=thread.version,
        )


@dataclass(frozen=True, slots=True)
class PersistedChatTurn:
    snapshot: TurnSnapshot
    binding: ChatTurnBinding
    created_at: datetime
    updated_at: datetime
    snapshot_digest: str

    def __post_init__(self) -> None:
        if self.snapshot.thread_id != self.binding.thread_id:
            raise ChatTurnCorruption(
                "snapshot thread differs from persisted conversation binding"
            )
        if (
            self.snapshot.causal_user_message_id
            != self.binding.causal_user_message_id
        ):
            raise ChatTurnCorruption(
                "snapshot causal user differs from persisted binding"
            )
        object.__setattr__(self, "created_at", _utc(self.created_at))
        object.__setattr__(self, "updated_at", _utc(self.updated_at))
        if self.updated_at < self.created_at:
            raise ChatTurnCorruption(
                "turn updated_at precedes created_at"
            )
        expected = operation_digest(self.snapshot)
        if self.snapshot_digest != expected:
            raise ChatTurnCorruption(
                "persisted turn snapshot digest does not match materialized state"
            )


class SQLiteChatTurnRepository:
    """Transactional conformance repository for durable AI-chat turns."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "ai-chat-turn",
    ) -> None:
        self.namespace = _text(namespace, "namespace", maximum=128)
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

                CREATE TABLE IF NOT EXISTS ai_chat_turn_operation (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    causal_user_message_id TEXT NOT NULL,
                    admitted_thread_version INTEGER NOT NULL,
                    initial_budget_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    usage_json TEXT NOT NULL,
                    next_sequence INTEGER NOT NULL,
                    last_event_digest TEXT,
                    pending_tool_call_id TEXT,
                    pending_tool_side_effect TEXT,
                    pending_tool_receipt_ref TEXT,
                    external_effect_started INTEGER NOT NULL,
                    provider_receipt_ref TEXT,
                    failure_class TEXT,
                    snapshot_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    PRIMARY KEY(namespace, operation_id)
                );

                CREATE INDEX IF NOT EXISTS idx_ai_chat_turn_owner
                ON ai_chat_turn_operation(
                    namespace, tenant_id, owner_id, updated_at
                );

                CREATE INDEX IF NOT EXISTS idx_ai_chat_turn_thread
                ON ai_chat_turn_operation(
                    namespace, thread_id, created_at
                );

                CREATE TABLE IF NOT EXISTS ai_chat_turn_event (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_digest TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, operation_id, sequence),
                    UNIQUE(namespace, operation_id, event_digest),
                    FOREIGN KEY(namespace, operation_id)
                        REFERENCES ai_chat_turn_operation(
                            namespace, operation_id
                        )
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_ai_chat_turn_event_order
                ON ai_chat_turn_event(
                    namespace, operation_id, sequence
                );
                """
            )

    @staticmethod
    def _binding_from_row(row: sqlite3.Row) -> ChatTurnBinding:
        try:
            return ChatTurnBinding(
                tenant_id=row["tenant_id"],
                owner_id=row["owner_id"],
                thread_id=row["thread_id"],
                causal_user_message_id=row["causal_user_message_id"],
                admitted_thread_version=int(row["admitted_thread_version"]),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            ChatTurnRepositoryError,
        ) as exc:
            if isinstance(exc, ChatTurnCorruption):
                raise
            raise ChatTurnCorruption(
                "persisted conversation binding is invalid"
            ) from exc

    @staticmethod
    def _snapshot_from_row(row: sqlite3.Row) -> TurnSnapshot:
        try:
            budget = _budget_from_dict(
                _parse_json(row["initial_budget_json"], "initial_budget_json")
            )
            usage = _usage_from_dict(
                _parse_json(row["usage_json"], "usage_json")
            )
            return TurnSnapshot(
                operation_id=row["operation_id"],
                request_digest=row["request_digest"],
                thread_id=row["thread_id"],
                causal_user_message_id=row["causal_user_message_id"],
                state=TurnState(row["state"]),
                budget=budget,
                usage=usage,
                next_sequence=int(row["next_sequence"]),
                last_event_digest=row["last_event_digest"],
                pending_tool_call_id=row["pending_tool_call_id"],
                pending_tool_side_effect=(
                    None
                    if row["pending_tool_side_effect"] is None
                    else SideEffectClass(row["pending_tool_side_effect"])
                ),
                pending_tool_receipt_ref=row["pending_tool_receipt_ref"],
                external_effect_started=bool(row["external_effect_started"]),
                provider_receipt_ref=row["provider_receipt_ref"],
                failure_class=(
                    None
                    if row["failure_class"] is None
                    else FailureClass(row["failure_class"])
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            TurnRuntimeError,
            ChatTurnCorruption,
        ) as exc:
            if isinstance(exc, ChatTurnCorruption):
                raise
            raise ChatTurnCorruption(
                "persisted turn snapshot is invalid"
            ) from exc

    @classmethod
    def _turn_from_row(cls, row: sqlite3.Row) -> PersistedChatTurn:
        snapshot = cls._snapshot_from_row(row)
        binding = cls._binding_from_row(row)
        try:
            return PersistedChatTurn(
                snapshot=snapshot,
                binding=binding,
                created_at=_parse_time(row["created_at"], "created_at"),
                updated_at=_parse_time(row["updated_at"], "updated_at"),
                snapshot_digest=row["snapshot_digest"],
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            ChatTurnRepositoryError,
        ) as exc:
            if isinstance(exc, ChatTurnCorruption):
                raise
            raise ChatTurnCorruption(
                "persisted turn record is invalid"
            ) from exc

    def _operation_row(self, operation_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM ai_chat_turn_operation
            WHERE namespace = ? AND operation_id = ?
            """,
            (self.namespace, operation_id),
        ).fetchone()

    @staticmethod
    def _authorize(
        turn: PersistedChatTurn,
        tenant_id: str,
        owner_id: str,
    ) -> None:
        if (
            turn.binding.tenant_id != tenant_id
            or turn.binding.owner_id != owner_id
        ):
            raise ChatTurnAuthorizationError("AI chat turn access denied")

    @staticmethod
    def _same_creation(
        existing: PersistedChatTurn,
        *,
        request_digest: str,
        binding: ChatTurnBinding,
        budget: ExecutionBudget,
    ) -> bool:
        return (
            existing.snapshot.request_digest == request_digest
            and existing.binding == binding
            and existing.snapshot.budget == budget
            and existing.snapshot.state is TurnState.RECEIVED
            and existing.snapshot.next_sequence == 1
            and existing.snapshot.last_event_digest is None
        )

    def create_operation(
        self,
        *,
        operation_id: str,
        request_digest: str,
        binding: ChatTurnBinding,
        budget: ExecutionBudget | None = None,
        created_at: datetime | None = None,
    ) -> PersistedChatTurn:
        operation = _uuid(operation_id, "operation_id")
        digest = _sha256(request_digest, "request_digest")
        if not isinstance(binding, ChatTurnBinding):
            raise TypeError("binding must be ChatTurnBinding")
        effective_budget = budget or ExecutionBudget()
        if not isinstance(effective_budget, ExecutionBudget):
            raise TypeError("budget must be ExecutionBudget")
        now = _utc(created_at)
        snapshot = start_turn(
            operation_id=operation,
            request_digest=digest,
            thread_id=binding.thread_id,
            causal_user_message_id=binding.causal_user_message_id,
            budget=effective_budget,
        )
        turn = PersistedChatTurn(
            snapshot=snapshot,
            binding=binding,
            created_at=now,
            updated_at=now,
            snapshot_digest=operation_digest(snapshot),
        )

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing_row = self._operation_row(operation)
                if existing_row is not None:
                    existing = self._turn_from_row(existing_row)
                    self._authorize(
                        existing,
                        binding.tenant_id,
                        binding.owner_id,
                    )
                    if self._same_creation(
                        existing,
                        request_digest=digest,
                        binding=binding,
                        budget=effective_budget,
                    ):
                        self._connection.execute("COMMIT")
                        return existing
                    raise ChatTurnConflict(
                        "operation_id was reused with different turn identity"
                    )

                self._connection.execute(
                    """
                    INSERT INTO ai_chat_turn_operation(
                        namespace, operation_id, request_digest,
                        tenant_id, owner_id, thread_id,
                        causal_user_message_id, admitted_thread_version,
                        initial_budget_json, state, usage_json,
                        next_sequence, last_event_digest,
                        pending_tool_call_id, pending_tool_side_effect,
                        pending_tool_receipt_ref, external_effect_started,
                        provider_receipt_ref, failure_class,
                        snapshot_digest, created_at, updated_at,
                        schema_version
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        self.namespace,
                        snapshot.operation_id,
                        snapshot.request_digest,
                        binding.tenant_id,
                        binding.owner_id,
                        binding.thread_id,
                        binding.causal_user_message_id,
                        binding.admitted_thread_version,
                        _json(snapshot.budget.as_dict()),
                        snapshot.state.value,
                        _json(snapshot.usage.as_dict()),
                        snapshot.next_sequence,
                        snapshot.last_event_digest,
                        snapshot.pending_tool_call_id,
                        None,
                        snapshot.pending_tool_receipt_ref,
                        int(snapshot.external_effect_started),
                        snapshot.provider_receipt_ref,
                        None,
                        turn.snapshot_digest,
                        turn.created_at.isoformat(),
                        turn.updated_at.isoformat(),
                        CHAT_TURN_SCHEMA_VERSION,
                    ),
                )
                self._connection.execute("COMMIT")
                return turn
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ChatTurnConflict(
                    "turn operation identity already exists"
                ) from exc
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def get_operation(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        operation = _uuid(operation_id, "operation_id")
        with self._lock:
            row = self._operation_row(operation)
        if row is None:
            raise ChatTurnNotFound(operation)
        turn = self._turn_from_row(row)
        self._authorize(turn, tenant_id, owner_id)
        return turn

    def list_events(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> tuple[TurnEvent, ...]:
        operation = _uuid(operation_id, "operation_id")
        if (
            isinstance(after_sequence, bool)
            or not isinstance(after_sequence, int)
            or after_sequence < 0
        ):
            raise ValueError(
                "after_sequence must be a non-negative integer"
            )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 2000
        ):
            raise ValueError("limit must be between 1 and 2000")

        turn = self.get_operation(
            operation,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        del turn
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT event_json FROM ai_chat_turn_event
                WHERE namespace = ? AND operation_id = ?
                  AND sequence > ?
                ORDER BY sequence ASC
                LIMIT ?
                """,
                (
                    self.namespace,
                    operation,
                    after_sequence,
                    limit,
                ),
            ).fetchall()
        events: list[TurnEvent] = []
        for row in rows:
            event = _event_from_dict(
                _parse_json(row["event_json"], "event_json")
            )
            events.append(event)
        return tuple(events)

    def append_event(
        self,
        event: TurnEvent,
        *,
        tenant_id: str,
        owner_id: str,
        updated_at: datetime | None = None,
    ) -> PersistedChatTurn:
        if not isinstance(event, TurnEvent):
            raise TypeError("event must be TurnEvent")
        operation = _uuid(event.operation_id, "operation_id")
        now = _utc(updated_at or event.observed_at)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._operation_row(operation)
                if row is None:
                    raise ChatTurnNotFound(operation)
                current = self._turn_from_row(row)
                self._authorize(current, tenant_id, owner_id)

                duplicate = self._connection.execute(
                    """
                    SELECT event_digest, event_json
                    FROM ai_chat_turn_event
                    WHERE namespace = ? AND operation_id = ?
                      AND sequence = ?
                    """,
                    (
                        self.namespace,
                        operation,
                        event.sequence,
                    ),
                ).fetchone()
                if duplicate is not None:
                    if duplicate["event_digest"] != event.digest:
                        raise ChatTurnConflict(
                            "turn event sequence was reused with different content"
                        )
                    persisted_event = _event_from_dict(
                        _parse_json(
                            duplicate["event_json"],
                            "event_json",
                        )
                    )
                    if persisted_event.digest != event.digest:
                        raise ChatTurnCorruption(
                            "persisted event digest does not match event payload"
                        )
                    self._connection.execute("COMMIT")
                    return current

                try:
                    next_snapshot = current.snapshot.apply(event)
                except TurnRuntimeError as exc:
                    raise ChatTurnConflict(str(exc)) from exc

                next_digest = operation_digest(next_snapshot)
                cursor = self._connection.execute(
                    """
                    UPDATE ai_chat_turn_operation
                    SET state = ?, usage_json = ?, next_sequence = ?,
                        last_event_digest = ?,
                        pending_tool_call_id = ?,
                        pending_tool_side_effect = ?,
                        pending_tool_receipt_ref = ?,
                        external_effect_started = ?,
                        provider_receipt_ref = ?,
                        failure_class = ?,
                        snapshot_digest = ?, updated_at = ?
                    WHERE namespace = ? AND operation_id = ?
                      AND next_sequence = ?
                      AND (
                        (last_event_digest IS NULL AND ? IS NULL)
                        OR last_event_digest = ?
                      )
                    """,
                    (
                        next_snapshot.state.value,
                        _json(next_snapshot.usage.as_dict()),
                        next_snapshot.next_sequence,
                        next_snapshot.last_event_digest,
                        next_snapshot.pending_tool_call_id,
                        (
                            None
                            if next_snapshot.pending_tool_side_effect is None
                            else next_snapshot.pending_tool_side_effect.value
                        ),
                        next_snapshot.pending_tool_receipt_ref,
                        int(next_snapshot.external_effect_started),
                        next_snapshot.provider_receipt_ref,
                        (
                            None
                            if next_snapshot.failure_class is None
                            else next_snapshot.failure_class.value
                        ),
                        next_digest,
                        now.isoformat(),
                        self.namespace,
                        operation,
                        current.snapshot.next_sequence,
                        current.snapshot.last_event_digest,
                        current.snapshot.last_event_digest,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ChatTurnConflict(
                        "turn snapshot changed during event append"
                    )

                self._connection.execute(
                    """
                    INSERT INTO ai_chat_turn_event(
                        namespace, operation_id, sequence,
                        event_digest, event_json, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        operation,
                        event.sequence,
                        event.digest,
                        _json(event.as_dict()),
                        event.observed_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ChatTurnConflict(
                    "turn event identity conflict"
                ) from exc
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

        return self.get_operation(
            operation,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    def reconstruct(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        persisted = self.get_operation(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        events = self.list_events(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            after_sequence=0,
            limit=max(1, persisted.snapshot.next_sequence),
        )
        if len(events) != persisted.snapshot.next_sequence - 1:
            raise ChatTurnCorruption(
                "turn event journal has a sequence gap"
            )
        initial = start_turn(
            operation_id=persisted.snapshot.operation_id,
            request_digest=persisted.snapshot.request_digest,
            thread_id=persisted.binding.thread_id,
            causal_user_message_id=persisted.binding.causal_user_message_id,
            budget=persisted.snapshot.budget,
        )
        replayed, errors = TurnJournal.verify(initial, events)
        if errors:
            raise ChatTurnCorruption(
                "turn event replay failed: " + "; ".join(errors)
            )
        if replayed != persisted.snapshot:
            raise ChatTurnCorruption(
                "materialized turn snapshot differs from journal replay"
            )
        if operation_digest(replayed) != persisted.snapshot_digest:
            raise ChatTurnCorruption(
                "materialized turn snapshot digest differs from replay"
            )
        return persisted

    def recovery_decision(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> tuple[PersistedChatTurn, RecoveryDecision]:
        turn = self.reconstruct(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        return turn, RecoveryPlanner.plan(turn.snapshot)

    def assert_assistant_message_binding(
        self,
        message: ConversationMessage,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        if not isinstance(message, ConversationMessage):
            raise TypeError("message must be ConversationMessage")
        if message.author_type is not ConversationAuthorType.ASSISTANT:
            raise ChatTurnConflict(
                "only canonical assistant messages can finalize a turn"
            )
        if message.operation_id is None:
            raise ChatTurnConflict(
                "assistant message is missing operation identity"
            )
        turn = self.reconstruct(
            message.operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if message.thread_id != turn.binding.thread_id:
            raise ChatTurnConflict(
                "assistant message thread differs from turn binding"
            )
        if (
            message.causal_user_message_id
            != turn.binding.causal_user_message_id
        ):
            raise ChatTurnConflict(
                "assistant causal user differs from turn binding"
            )
        if turn.snapshot.state not in {
            TurnState.FINALIZING,
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            TurnState.MEMORY_PROPOSAL,
            TurnState.COMPLETE,
            TurnState.DEGRADED,
        }:
            raise ChatTurnConflict(
                "assistant message cannot bind before finalization"
            )
        return turn

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "ChatTurnAuthorizationError",
    "ChatTurnBinding",
    "ChatTurnConflict",
    "ChatTurnCorruption",
    "ChatTurnNotFound",
    "ChatTurnRepositoryError",
    "PersistedChatTurn",
    "SQLiteChatTurnRepository",
]
