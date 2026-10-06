"""Mongo-backed durable AI-chat turn authority.

Conversation content remains authoritative in core.conversations. This adapter
persists only turn-operation snapshots and immutable transition events.

The append protocol mirrors the conversation authority's recoverable write
pattern without requiring Mongo transactions:

1. persist an immutable event with _commit_state=prepared;
2. atomically advance the operation snapshot using exact sequence/digest
   preconditions;
3. mark the event committed.

A later reader completes or discards an interrupted prepared event
predictably. This prevents a process crash from silently losing a transition
or replaying an ambiguous external side effect.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.databases import core_db
from skeleton.ai.assistant.turn_runtime import (
    CHAT_TURN_SCHEMA_VERSION,
    ExecutionBudget,
    RecoveryDecision,
    RecoveryPlanner,
    TurnEvent,
    TurnJournal,
    TurnRuntimeError,
    TurnSnapshot,
    operation_digest,
    start_turn,
    turn_event_from_dict,
    turn_snapshot_dict,
    turn_snapshot_from_dict,
)
from skeleton.persistence.chat_turn_repository import (
    ChatTurnAuthorizationError,
    ChatTurnBinding,
    ChatTurnConflict,
    ChatTurnCorruption,
    ChatTurnNotFound,
    ChatTurnRepositoryError,
    PersistedChatTurn,
)


class ChatTurnStorageUnavailable(ChatTurnRepositoryError):
    """Mongo turn state cannot currently be used safely."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ChatTurnRepositoryError(
            f"{field_name} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _operation_doc(turn: PersistedChatTurn) -> dict[str, Any]:
    snapshot = turn.snapshot
    return {
        "_id": snapshot.operation_id,
        "operation_id": snapshot.operation_id,
        "request_digest": snapshot.request_digest,
        "tenant_id": turn.binding.tenant_id,
        "owner_id": turn.binding.owner_id,
        "thread_id": turn.binding.thread_id,
        "causal_user_message_id": turn.binding.causal_user_message_id,
        "admitted_thread_version": turn.binding.admitted_thread_version,
        "snapshot": turn_snapshot_dict(snapshot),
        "snapshot_digest": turn.snapshot_digest,
        "state": snapshot.state.value,
        "next_sequence": snapshot.next_sequence,
        "last_event_digest": snapshot.last_event_digest,
        "created_at": turn.created_at,
        "updated_at": turn.updated_at,
        "schema_version": CHAT_TURN_SCHEMA_VERSION,
    }


def _turn_from_doc(doc: Mapping[str, Any]) -> PersistedChatTurn:
    try:
        snapshot_raw = doc["snapshot"]
        if not isinstance(snapshot_raw, Mapping):
            raise ChatTurnCorruption("Mongo turn snapshot must be an object")
        snapshot = turn_snapshot_from_dict(snapshot_raw)
        binding = ChatTurnBinding(
            tenant_id=str(doc["tenant_id"]),
            owner_id=str(doc["owner_id"]),
            thread_id=str(doc["thread_id"]),
            causal_user_message_id=str(doc["causal_user_message_id"]),
            admitted_thread_version=int(doc["admitted_thread_version"]),
        )
        turn = PersistedChatTurn(
            snapshot=snapshot,
            binding=binding,
            created_at=_aware_utc(doc["created_at"], "created_at"),
            updated_at=_aware_utc(doc["updated_at"], "updated_at"),
            snapshot_digest=str(doc["snapshot_digest"]),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        TurnRuntimeError,
        ChatTurnRepositoryError,
    ) as exc:
        if isinstance(exc, ChatTurnCorruption):
            raise
        raise ChatTurnCorruption(
            "persisted Mongo AI-chat operation is invalid"
        ) from exc

    if doc.get("operation_id") != snapshot.operation_id:
        raise ChatTurnCorruption("Mongo operation identity drifted")
    if doc.get("request_digest") != snapshot.request_digest:
        raise ChatTurnCorruption("Mongo request digest drifted")
    if doc.get("state") != snapshot.state.value:
        raise ChatTurnCorruption("Mongo materialized state drifted")
    if int(doc.get("next_sequence", -1)) != snapshot.next_sequence:
        raise ChatTurnCorruption("Mongo materialized sequence drifted")
    if doc.get("last_event_digest") != snapshot.last_event_digest:
        raise ChatTurnCorruption("Mongo materialized digest chain drifted")
    return turn


def _event_doc(event: TurnEvent) -> dict[str, Any]:
    return {
        "_id": f"{event.operation_id}:{event.sequence}",
        "operation_id": event.operation_id,
        "sequence": event.sequence,
        "event_digest": event.digest,
        "event": event.as_dict(),
        "observed_at": event.observed_at,
        "_commit_state": "prepared",
        "_expected_sequence": event.sequence,
        "_expected_previous_event_digest": event.previous_event_digest,
    }


def _event_from_doc(doc: Mapping[str, Any]) -> TurnEvent:
    try:
        raw = doc["event"]
        if not isinstance(raw, Mapping):
            raise ChatTurnCorruption("Mongo turn event must be an object")
        event = turn_event_from_dict(raw)
    except (
        KeyError,
        TypeError,
        ValueError,
        TurnRuntimeError,
    ) as exc:
        if isinstance(exc, ChatTurnCorruption):
            raise
        raise ChatTurnCorruption(
            "persisted Mongo turn event is invalid"
        ) from exc
    if doc.get("operation_id") != event.operation_id:
        raise ChatTurnCorruption("Mongo event operation identity drifted")
    if int(doc.get("sequence", -1)) != event.sequence:
        raise ChatTurnCorruption("Mongo event sequence drifted")
    if doc.get("event_digest") != event.digest:
        raise ChatTurnCorruption("Mongo event digest drifted")
    return event


class MongoChatTurnAuthority:
    """Production durable turn state with recoverable event commits."""

    def __init__(self, database=core_db) -> None:
        self.database = database
        self.operations = database["ai_chat_turn_operations"]
        self.events = database["ai_chat_turn_events"]

    @staticmethod
    def _authorized_filter(
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> dict[str, str]:
        return {
            "_id": str(operation_id),
            "tenant_id": str(tenant_id),
            "owner_id": str(owner_id),
        }

    async def create_operation(
        self,
        *,
        operation_id: str,
        request_digest: str,
        binding: ChatTurnBinding,
        budget: ExecutionBudget | None = None,
        created_at: datetime | None = None,
    ) -> PersistedChatTurn:
        if not isinstance(binding, ChatTurnBinding):
            raise TypeError("binding must be ChatTurnBinding")
        effective_budget = budget or ExecutionBudget()
        now = (
            _utcnow()
            if created_at is None
            else _aware_utc(created_at, "created_at")
        )
        snapshot = start_turn(
            operation_id=operation_id,
            request_digest=request_digest,
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
        try:
            await self.operations.insert_one(_operation_doc(turn))
        except DuplicateKeyError:
            existing = await self.get_operation(
                operation_id,
                tenant_id=binding.tenant_id,
                owner_id=binding.owner_id,
            )
            if (
                existing.snapshot.request_digest == request_digest
                and existing.binding == binding
                and existing.snapshot.budget == effective_budget
                and existing.snapshot.next_sequence == 1
                and existing.snapshot.last_event_digest is None
            ):
                return existing
            raise ChatTurnConflict(
                "operation_id was reused with different turn identity"
            )
        except PyMongoError as exc:
            raise ChatTurnStorageUnavailable(
                "AI chat turn operation could not be created"
            ) from exc
        return turn

    async def _raw_operation(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> Mapping[str, Any]:
        try:
            doc = await self.operations.find_one(
                self._authorized_filter(
                    operation_id,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                )
            )
        except PyMongoError as exc:
            raise ChatTurnStorageUnavailable(
                "AI chat turn storage is unavailable"
            ) from exc
        if doc is None:
            try:
                exists = await self.operations.find_one(
                    {"_id": str(operation_id)},
                    {"_id": 1},
                )
            except PyMongoError as exc:
                raise ChatTurnStorageUnavailable(
                    "AI chat turn storage is unavailable"
                ) from exc
            if exists is not None:
                raise ChatTurnAuthorizationError(
                    "AI chat turn access denied"
                )
            raise ChatTurnNotFound(str(operation_id))
        return doc

    async def _recover_prepared(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        raw = await self._raw_operation(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        current = _turn_from_doc(raw)
        try:
            prepared = await self.events.find_one(
                {
                    "operation_id": operation_id,
                    "_commit_state": "prepared",
                },
                sort=[("sequence", ASCENDING)],
            )
        except PyMongoError as exc:
            raise ChatTurnStorageUnavailable(
                "AI chat turn recovery state is unavailable"
            ) from exc
        if prepared is None:
            return current

        event = _event_from_doc(prepared)
        if event.sequence < current.snapshot.next_sequence:
            try:
                await self.events.update_one(
                    {
                        "_id": prepared["_id"],
                        "_commit_state": "prepared",
                    },
                    {"$set": {"_commit_state": "committed"}},
                )
            except PyMongoError:
                pass
            return current

        if (
            event.sequence != current.snapshot.next_sequence
            or event.previous_event_digest
            != current.snapshot.last_event_digest
        ):
            try:
                await self.events.delete_one(
                    {
                        "_id": prepared["_id"],
                        "_commit_state": "prepared",
                    }
                )
            except PyMongoError as exc:
                raise ChatTurnStorageUnavailable(
                    "stale AI chat turn event could not be discarded"
                ) from exc
            return current

        try:
            next_snapshot = current.snapshot.apply(event)
        except TurnRuntimeError as exc:
            raise ChatTurnCorruption(
                "prepared AI chat turn event cannot be replayed"
            ) from exc
        now = _utcnow()
        query: dict[str, Any] = {
            **self._authorized_filter(
                operation_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            ),
            "next_sequence": current.snapshot.next_sequence,
            "last_event_digest": current.snapshot.last_event_digest,
        }

        try:
            advanced = await self.operations.find_one_and_update(
                query,
                {"$set": self._snapshot_update(next_snapshot, now)},
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise ChatTurnStorageUnavailable(
                "prepared AI chat turn event could not advance operation"
            ) from exc
        if advanced is None:
            refreshed_raw = await self._raw_operation(
                operation_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
            refreshed = _turn_from_doc(refreshed_raw)
            if refreshed.snapshot.next_sequence > event.sequence:
                try:
                    await self.events.update_one(
                        {
                            "_id": prepared["_id"],
                            "_commit_state": "prepared",
                        },
                        {"$set": {"_commit_state": "committed"}},
                    )
                except PyMongoError:
                    pass
                return refreshed
            raise ChatTurnConflict(
                "prepared AI chat turn event could not reach commit point"
            )

        try:
            await self.events.update_one(
                {
                    "_id": prepared["_id"],
                    "_commit_state": "prepared",
                },
                {"$set": {"_commit_state": "committed"}},
            )
        except PyMongoError:
            pass
        return _turn_from_doc(advanced)

    @staticmethod
    def _snapshot_update(
        snapshot: TurnSnapshot,
        updated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "snapshot": turn_snapshot_dict(snapshot),
            "snapshot_digest": operation_digest(snapshot),
            "state": snapshot.state.value,
            "next_sequence": snapshot.next_sequence,
            "last_event_digest": snapshot.last_event_digest,
            "updated_at": updated_at,
        }

    async def get_operation(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        return await self._recover_prepared(
            str(operation_id),
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    async def append_event(
        self,
        event: TurnEvent,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        if not isinstance(event, TurnEvent):
            raise TypeError("event must be TurnEvent")
        current = await self._recover_prepared(
            event.operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

        try:
            next_snapshot = current.snapshot.apply(event)
        except TurnRuntimeError as exc:
            raise ChatTurnConflict(str(exc)) from exc

        prepared = _event_doc(event)
        try:
            await self.events.insert_one(prepared)
        except DuplicateKeyError:
            try:
                existing_doc = await self.events.find_one(
                    {"_id": prepared["_id"]}
                )
            except PyMongoError as exc:
                raise ChatTurnStorageUnavailable(
                    "AI chat turn idempotency state is unavailable"
                ) from exc
            if existing_doc is None:
                raise ChatTurnConflict(
                    "AI chat turn event identity conflict"
                )
            existing = _event_from_doc(existing_doc)
            if existing.digest != event.digest:
                raise ChatTurnConflict(
                    "turn event sequence was reused with different content"
                )
            return await self._recover_prepared(
                event.operation_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
        except PyMongoError as exc:
            raise ChatTurnStorageUnavailable(
                "AI chat turn event could not be prepared"
            ) from exc

        query: dict[str, Any] = {
            **self._authorized_filter(
                event.operation_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            ),
            "next_sequence": current.snapshot.next_sequence,
            "last_event_digest": current.snapshot.last_event_digest,
        }

        try:
            advanced = await self.operations.find_one_and_update(
                query,
                {
                    "$set": self._snapshot_update(
                        next_snapshot,
                        event.observed_at,
                    )
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise ChatTurnStorageUnavailable(
                "AI chat turn snapshot could not be advanced"
            ) from exc
        if advanced is None:
            return await self._recover_prepared(
                event.operation_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )

        try:
            await self.events.update_one(
                {
                    "_id": prepared["_id"],
                    "_commit_state": "prepared",
                },
                {"$set": {"_commit_state": "committed"}},
            )
        except PyMongoError:
            pass
        return _turn_from_doc(advanced)

    async def list_events(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> tuple[TurnEvent, ...]:
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

        await self._recover_prepared(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        try:
            docs = await (
                self.events.find(
                    {
                        "operation_id": operation_id,
                        "_commit_state": "committed",
                        "sequence": {"$gt": after_sequence},
                    }
                )
                .sort("sequence", ASCENDING)
                .limit(limit)
                .to_list(length=limit)
            )
        except PyMongoError as exc:
            raise ChatTurnStorageUnavailable(
                "AI chat turn event storage is unavailable"
            ) from exc
        return tuple(_event_from_doc(doc) for doc in docs)

    async def reconstruct(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        persisted = await self.get_operation(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        expected = persisted.snapshot.next_sequence - 1
        events: list[TurnEvent] = []
        after = 0
        while len(events) < expected:
            page = await self.list_events(
                operation_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                after_sequence=after,
                limit=min(2000, expected - len(events)),
            )
            if not page:
                break
            events.extend(page)
            after = page[-1].sequence
        if len(events) != expected:
            raise ChatTurnCorruption(
                "AI chat turn event journal has a sequence gap"
            )

        initial = start_turn(
            operation_id=persisted.snapshot.operation_id,
            request_digest=persisted.snapshot.request_digest,
            thread_id=persisted.binding.thread_id,
            causal_user_message_id=persisted.binding.causal_user_message_id,
            budget=persisted.snapshot.budget,
        )
        replayed, errors = TurnJournal.verify(initial, tuple(events))
        if errors:
            raise ChatTurnCorruption(
                "AI chat turn replay failed: " + "; ".join(errors)
            )
        if replayed != persisted.snapshot:
            raise ChatTurnCorruption(
                "Mongo AI chat snapshot differs from journal replay"
            )
        if operation_digest(replayed) != persisted.snapshot_digest:
            raise ChatTurnCorruption(
                "Mongo AI chat snapshot digest differs from replay"
            )
        return persisted

    async def recovery_decision(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> tuple[PersistedChatTurn, RecoveryDecision]:
        turn = await self.reconstruct(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        return turn, RecoveryPlanner.plan(turn.snapshot)


chat_turn_authority = MongoChatTurnAuthority()


__all__ = [
    "ChatTurnStorageUnavailable",
    "MongoChatTurnAuthority",
    "chat_turn_authority",
]
