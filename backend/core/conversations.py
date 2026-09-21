"""Mongo-backed authoritative conversation state.

This is the production adapter for the canonical conversation envelopes in
skeleton.contracts.conversation. The adapter fails closed when a multi-document
transaction cannot be established: authoritative message append and thread
version advancement must commit together.

The browser is a cache/projection. Provider history is never authoritative.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.databases import core_db
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationNotFound,
    ConversationRepositoryError,
)


class ConversationStorageUnavailable(ConversationRepositoryError):
    """Authoritative Mongo state cannot currently be used safely."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _thread_doc(thread: ConversationThread) -> dict[str, Any]:
    payload = thread.as_dict()
    payload["_id"] = thread.thread_id
    payload["created_at"] = thread.created_at
    payload["updated_at"] = thread.updated_at
    return payload


def _message_doc(message: ConversationMessage) -> dict[str, Any]:
    payload = message.as_dict()
    payload["_id"] = message.message_id
    payload["created_at"] = message.created_at
    return payload


def _thread_from_doc(doc: dict[str, Any]) -> ConversationThread:
    return ConversationThread(
        thread_id=str(doc["thread_id"]),
        tenant_id=str(doc["tenant_id"]),
        owner_id=str(doc["owner_id"]),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        version=int(doc["version"]),
        message_sequence=int(doc["message_sequence"]),
        active_branch_id=str(doc["active_branch_id"]),
        state=ConversationThreadState(str(doc["state"])),
        title=str(doc["title"]),
        data_class=str(doc["data_class"]),
        schema_version=int(doc.get("schema_version", 1)),
    )


def _message_from_doc(doc: dict[str, Any]) -> ConversationMessage:
    return ConversationMessage(
        message_id=str(doc["message_id"]),
        thread_id=str(doc["thread_id"]),
        branch_id=str(doc["branch_id"]),
        sequence=int(doc["sequence"]),
        author_type=ConversationAuthorType(str(doc["author_type"])),
        created_at=doc["created_at"],
        idempotency_key=str(doc["idempotency_key"]),
        content=doc.get("content"),
        content_ref=doc.get("content_ref"),
        parent_message_id=doc.get("parent_message_id"),
        supersedes_message_id=doc.get("supersedes_message_id"),
        causal_user_message_id=doc.get("causal_user_message_id"),
        operation_id=doc.get("operation_id"),
        ai_result_id=doc.get("ai_result_id"),
        attachment_refs=tuple(doc.get("attachment_refs") or ()),
        tool_receipt_refs=tuple(doc.get("tool_receipt_refs") or ()),
        citation_refs=tuple(doc.get("citation_refs") or ()),
        artifact_refs=tuple(doc.get("artifact_refs") or ()),
        data_class=str(doc.get("data_class") or "confidential"),
        schema_version=int(doc.get("schema_version", 1)),
    )


class MongoConversationAuthority:
    """Server-authoritative conversation repository for product runtime."""

    def __init__(self, database=core_db) -> None:
        self.database = database
        self.threads = database["conversation_threads"]
        self.messages = database["conversation_messages"]

    async def ensure_indexes(self) -> None:
        try:
            await self.threads.create_index(
                [("tenant_id", ASCENDING), ("owner_id", ASCENDING), ("updated_at", DESCENDING)],
                name="conversation_owner_updated",
            )
            await self.messages.create_index(
                [("thread_id", ASCENDING), ("sequence", ASCENDING)],
                unique=True,
                name="conversation_thread_sequence_unique",
            )
            await self.messages.create_index(
                [("thread_id", ASCENDING), ("idempotency_key", ASCENDING)],
                unique=True,
                name="conversation_thread_idempotency_unique",
            )
            await self.messages.create_index(
                [("thread_id", ASCENDING), ("branch_id", ASCENDING), ("sequence", ASCENDING)],
                name="conversation_branch_sequence",
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation indexes are unavailable"
            ) from exc

    @staticmethod
    def _authorized_filter(
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> dict[str, Any]:
        return {
            "_id": thread_id,
            "tenant_id": tenant_id,
            "owner_id": owner_id,
        }

    async def create_thread(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        title: str = "New conversation",
        data_class: str = "confidential",
        thread_id: str | None = None,
        branch_id: str | None = None,
    ) -> ConversationThread:
        now = _utcnow()
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
        try:
            await self.threads.insert_one(_thread_doc(thread))
        except DuplicateKeyError as exc:
            raise ConversationConflict("thread identity already exists") from exc
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation storage is unavailable"
            ) from exc
        return thread

    async def get_thread(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> ConversationThread:
        try:
            doc = await self.threads.find_one(
                self._authorized_filter(
                    thread_id,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                )
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation storage is unavailable"
            ) from exc
        if doc is None:
            raise ConversationNotFound(thread_id)
        return _thread_from_doc(doc)

    async def list_threads(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        include_archived: bool = False,
        limit: int = 50,
    ) -> tuple[ConversationThread, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        states = ["active", "archived"] if include_archived else ["active"]
        try:
            docs = await (
                self.threads.find(
                    {
                        "tenant_id": tenant_id,
                        "owner_id": owner_id,
                        "state": {"$in": states},
                    }
                )
                .sort([("updated_at", DESCENDING), ("_id", ASCENDING)])
                .limit(limit)
                .to_list(length=limit)
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation storage is unavailable"
            ) from exc
        return tuple(_thread_from_doc(doc) for doc in docs)

    async def _message_by_idempotency(
        self,
        thread_id: str,
        idempotency_key: str,
        *,
        session=None,
    ) -> ConversationMessage | None:
        doc = await self.messages.find_one(
            {
                "thread_id": thread_id,
                "idempotency_key": idempotency_key,
            },
            session=session,
        )
        return _message_from_doc(doc) if doc is not None else None

    @staticmethod
    def _same_identity(
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

    async def append_message(
        self,
        message: ConversationMessage,
        *,
        tenant_id: str,
        owner_id: str,
        expected_thread_version: int,
        activate_branch: bool = True,
    ) -> tuple[ConversationThread, ConversationMessage]:
        """Atomically append immutable message and advance thread sequence/version."""

        try:
            async with await self.database.client.start_session() as session:
                async with session.start_transaction():
                    existing = await self._message_by_idempotency(
                        message.thread_id,
                        message.idempotency_key,
                        session=session,
                    )
                    if existing is not None:
                        if not self._same_identity(existing, message):
                            raise ConversationConflict(
                                "idempotency_key was reused with different content"
                            )
                        thread_doc = await self.threads.find_one(
                            self._authorized_filter(
                                message.thread_id,
                                tenant_id=tenant_id,
                                owner_id=owner_id,
                            ),
                            session=session,
                        )
                        if thread_doc is None:
                            raise ConversationNotFound(message.thread_id)
                        return _thread_from_doc(thread_doc), existing

                    thread_doc = await self.threads.find_one(
                        self._authorized_filter(
                            message.thread_id,
                            tenant_id=tenant_id,
                            owner_id=owner_id,
                        ),
                        session=session,
                    )
                    if thread_doc is None:
                        raise ConversationNotFound(message.thread_id)
                    thread = _thread_from_doc(thread_doc)
                    if not thread.writable:
                        raise ConversationConflict("thread is not writable")
                    if thread.version != expected_thread_version:
                        raise ConversationConflict("thread version conflict")
                    if message.sequence != thread.message_sequence + 1:
                        raise ConversationConflict(
                            f"message sequence must be exact-next ({thread.message_sequence + 1})"
                        )

                    if message.parent_message_id is not None:
                        parent = await self.messages.find_one(
                            {
                                "_id": message.parent_message_id,
                                "thread_id": message.thread_id,
                            },
                            session=session,
                        )
                        if parent is None or int(parent["sequence"]) >= message.sequence:
                            raise ConversationConflict(
                                "parent message is missing or invalid"
                            )

                    if message.supersedes_message_id is not None:
                        prior_doc = await self.messages.find_one(
                            {
                                "_id": message.supersedes_message_id,
                                "thread_id": message.thread_id,
                            },
                            session=session,
                        )
                        if prior_doc is None:
                            raise ConversationConflict(
                                "superseded message does not exist"
                            )
                        prior = _message_from_doc(prior_doc)
                        if prior.author_type != message.author_type:
                            raise ConversationConflict(
                                "superseding message must preserve author type"
                            )

                    await self.messages.insert_one(
                        _message_doc(message),
                        session=session,
                    )
                    now = _utcnow()
                    branch_id = (
                        message.branch_id
                        if activate_branch
                        else thread.active_branch_id
                    )
                    updated = await self.threads.find_one_and_update(
                        {
                            **self._authorized_filter(
                                message.thread_id,
                                tenant_id=tenant_id,
                                owner_id=owner_id,
                            ),
                            "version": expected_thread_version,
                            "message_sequence": message.sequence - 1,
                            "state": ConversationThreadState.ACTIVE.value,
                        },
                        {
                            "$set": {
                                "updated_at": now,
                                "active_branch_id": branch_id,
                                "message_sequence": message.sequence,
                            },
                            "$inc": {"version": 1},
                        },
                        return_document=ReturnDocument.AFTER,
                        session=session,
                    )
                    if updated is None:
                        raise ConversationConflict(
                            "thread changed during message append"
                        )
                    return _thread_from_doc(updated), message
        except (ConversationConflict, ConversationNotFound):
            raise
        except DuplicateKeyError as exc:
            raise ConversationConflict(
                "conversation message identity or ordering conflict"
            ) from exc
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "transactional conversation append is unavailable"
            ) from exc

    async def append_user_message(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
        parent_message_id: str | None = None,
        branch_id: str | None = None,
        supersedes_message_id: str | None = None,
        attachment_refs: tuple[str, ...] = (),
        data_class: str = "confidential",
    ) -> tuple[ConversationThread, ConversationMessage]:
        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=branch_id or thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.USER,
            created_at=_utcnow(),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=parent_message_id,
            supersedes_message_id=supersedes_message_id,
            attachment_refs=attachment_refs,
            data_class=data_class,
        )
        return await self.append_message(
            message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )

    async def commit_assistant_message(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
        causal_user_message_id: str,
        operation_id: str,
        ai_result_id: str,
        branch_id: str | None = None,
        supersedes_message_id: str | None = None,
        tool_receipt_refs: tuple[str, ...] = (),
        citation_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        data_class: str = "confidential",
    ) -> tuple[ConversationThread, ConversationMessage]:
        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=branch_id or thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=_utcnow(),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=causal_user_message_id,
            supersedes_message_id=supersedes_message_id,
            causal_user_message_id=causal_user_message_id,
            operation_id=operation_id,
            ai_result_id=ai_result_id,
            tool_receipt_refs=tool_receipt_refs,
            citation_refs=citation_refs,
            artifact_refs=artifact_refs,
            data_class=data_class,
        )
        return await self.append_message(
            message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )

    async def list_messages(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[ConversationMessage, ...]:
        await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < 0:
            raise ValueError("after_sequence must be a non-negative integer")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        try:
            docs = await (
                self.messages.find(
                    {
                        "thread_id": thread_id,
                        "sequence": {"$gt": after_sequence},
                    }
                )
                .sort("sequence", ASCENDING)
                .limit(limit)
                .to_list(length=limit)
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation storage is unavailable"
            ) from exc
        return tuple(_message_from_doc(doc) for doc in docs)

    async def active_transcript(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> tuple[ConversationMessage, ...]:
        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        messages = await self.list_messages(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            limit=500,
        )
        if not messages:
            return ()
        by_id = {message.message_id: message for message in messages}
        candidates = [
            message
            for message in messages
            if message.branch_id == thread.active_branch_id
        ]
        tip = candidates[-1] if candidates else messages[-1]
        lineage: list[ConversationMessage] = []
        seen: set[str] = set()
        current: ConversationMessage | None = tip
        while current is not None:
            if current.message_id in seen:
                raise ConversationStorageUnavailable(
                    "conversation lineage contains a cycle"
                )
            seen.add(current.message_id)
            lineage.append(current)
            current = (
                by_id.get(current.parent_message_id)
                if current.parent_message_id is not None
                else None
            )
        lineage.reverse()
        return tuple(lineage)

    async def edit_user_message(
        self,
        thread_id: str,
        message_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
    ) -> tuple[ConversationThread, ConversationMessage]:
        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        try:
            doc = await self.messages.find_one(
                {"_id": message_id, "thread_id": thread_id}
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation storage is unavailable"
            ) from exc
        if doc is None:
            raise ConversationNotFound(message_id)
        prior = _message_from_doc(doc)
        if prior.author_type is not ConversationAuthorType.USER:
            raise ConversationConflict("only user messages can be edited")
        edited = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=str(uuid4()),
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.USER,
            created_at=_utcnow(),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=prior.parent_message_id,
            supersedes_message_id=prior.message_id,
            attachment_refs=prior.attachment_refs,
            data_class=prior.data_class,
        )
        return await self.append_message(
            edited,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )

    async def set_state(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        expected_version: int,
        state: ConversationThreadState,
    ) -> ConversationThread:
        state = ConversationThreadState(state)
        if state is ConversationThreadState.ACTIVE:
            allowed_current = [ConversationThreadState.ARCHIVED.value]
        elif state is ConversationThreadState.ARCHIVED:
            allowed_current = [ConversationThreadState.ACTIVE.value]
        elif state is ConversationThreadState.DELETING:
            allowed_current = [
                ConversationThreadState.ACTIVE.value,
                ConversationThreadState.ARCHIVED.value,
            ]
        elif state is ConversationThreadState.DELETED:
            allowed_current = [ConversationThreadState.DELETING.value]
        else:
            allowed_current = []
        try:
            updated = await self.threads.find_one_and_update(
                {
                    **self._authorized_filter(
                        thread_id,
                        tenant_id=tenant_id,
                        owner_id=owner_id,
                    ),
                    "version": expected_version,
                    "state": {"$in": allowed_current},
                },
                {
                    "$set": {
                        "state": state.value,
                        "updated_at": _utcnow(),
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation storage is unavailable"
            ) from exc
        if updated is None:
            exists = await self.threads.find_one(
                self._authorized_filter(
                    thread_id,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                ),
                {"_id": 1},
            )
            if exists is None:
                raise ConversationNotFound(thread_id)
            raise ConversationConflict("thread state/version conflict")
        return _thread_from_doc(updated)


conversation_authority = MongoConversationAuthority()


__all__ = [
    "ConversationStorageUnavailable",
    "MongoConversationAuthority",
    "conversation_authority",
]
