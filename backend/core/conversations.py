"""Mongo-backed authoritative conversation state.

This is the production adapter for the canonical conversation envelopes in
skeleton.contracts.conversation. It uses a recoverable write-ahead append
protocol so it works on standalone Mongo as well as replica sets:

1. prepare the immutable message document;
2. atomically advance the thread version/sequence as the commit point;
3. mark the prepared message committed.

Prepared rows beyond the thread sequence are not visible transcript state and
can be completed or discarded deterministically after interruption.

The browser is a cache/projection. Provider history is never authoritative.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Awaitable, Callable, Mapping
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.databases import core_db
from core.engine_client import EngineClient
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


def _storage_bytes(payload: object) -> int:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=(
                lambda value: (
                    value.astimezone(timezone.utc).isoformat()
                    if isinstance(value, datetime)
                    else str(value)
                )
            ),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConversationStorageUnavailable(
            "conversation storage payload is not deterministic JSON"
        ) from exc
    return len(encoded)


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
        context_id=doc.get("context_id"),
        context_digest=doc.get("context_digest"),
        context_source_snapshot=tuple(
            tuple(item) for item in (doc.get("context_source_snapshot") or ())
        ),
        context_compiler_version=doc.get("context_compiler_version"),
        attachment_refs=tuple(doc.get("attachment_refs") or ()),
        tool_receipt_refs=tuple(doc.get("tool_receipt_refs") or ()),
        citation_refs=tuple(doc.get("citation_refs") or ()),
        artifact_refs=tuple(doc.get("artifact_refs") or ()),
        data_class=str(doc.get("data_class") or "confidential"),
        schema_version=int(doc.get("schema_version", 1)),
    )


class MongoConversationAuthority:
    """Server-authoritative conversation repository for product runtime."""

    def __init__(
        self,
        database=core_db,
        *,
        storage_admitter: Callable[..., Awaitable[Mapping[str, Any]]] | None = None,
        governance_registrar: Callable[..., Awaitable[Mapping[str, Any]]] | None = None,
        governance_deletion_planner: Callable[..., Awaitable[Mapping[str, Any]]] | None = None,
        governance_deletion_acker: Callable[..., Awaitable[Mapping[str, Any]]] | None = None,
        governance_inventory_reader: Callable[..., Awaitable[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.database = database
        self.threads = database["conversation_threads"]
        self.messages = database["conversation_messages"]
        self.storage_admitter = storage_admitter
        self.governance_registrar = governance_registrar
        self.governance_deletion_planner = governance_deletion_planner
        self.governance_deletion_acker = governance_deletion_acker
        self.governance_inventory_reader = governance_inventory_reader

    @staticmethod
    def _governed_conversation_location(
        record_id: str,
        source_ref: str,
    ) -> tuple[Any, dict[str, str], int]:
        record_key = str(record_id).strip()
        source = str(source_ref).strip()
        thread_prefix = "conversation-thread://"
        message_prefix = "conversation-message://"
        if source.startswith(thread_prefix):
            thread_id = source[len(thread_prefix):]
            if not thread_id or thread_id != record_key or "/" in thread_id:
                raise ConversationStorageUnavailable(
                    "conversation thread governance source_ref is invalid"
                )
            return "thread", {"_id": record_key}, 1
        if source.startswith(message_prefix):
            tail = source[len(message_prefix):]
            thread_id, separator, message_id = tail.partition("/")
            if (
                not separator
                or not thread_id
                or not message_id
                or "/" in message_id
                or message_id != record_key
            ):
                raise ConversationStorageUnavailable(
                    "conversation message governance source_ref is invalid"
                )
            return (
                "message",
                {"_id": record_key, "thread_id": thread_id},
                0,
            )
        raise ConversationStorageUnavailable(
            "unsupported conversation governance source_ref"
        )

    async def execute_governed_deletion(
        self,
        *,
        tenant_id: str,
        record_ids: tuple[str, ...] | None = None,
        reason: str = "tenant-request",
    ) -> Mapping[str, Any]:
        planner = self.governance_deletion_planner
        acker = self.governance_deletion_acker
        if planner is None or acker is None:
            raise ConversationStorageUnavailable(
                "conversation governance deletion protocol is unavailable"
            )
        try:
            plan = await planner(
                tenant_id=str(tenant_id),
                record_ids=record_ids,
                reason=str(reason),
            )
        except Exception as exc:
            raise ConversationStorageUnavailable(
                "conversation governance deletion plan is unavailable"
            ) from exc
        if not isinstance(plan, Mapping):
            raise ConversationStorageUnavailable(
                "conversation governance deletion plan is malformed"
            )
        plan_id = str(plan.get("plan_id") or "").strip()
        if (
            not plan_id
            or plan.get("tenant_id") != str(tenant_id)
            or not isinstance(plan.get("actions"), list)
        ):
            raise ConversationStorageUnavailable(
                "conversation governance deletion plan identity mismatch"
            )

        actions = []
        for raw in plan["actions"]:
            if not isinstance(raw, Mapping):
                raise ConversationStorageUnavailable(
                    "conversation governance deletion action is malformed"
                )
            if str(raw.get("target") or "").lower() != "conversation":
                continue
            if raw.get("tenant_id") != str(tenant_id):
                raise ConversationStorageUnavailable(
                    "conversation governance deletion tenant mismatch"
                )
            record_id = str(raw.get("record_id") or "").strip()
            source_ref = str(raw.get("source_ref") or "").strip()
            kind, query, order = self._governed_conversation_location(
                record_id,
                source_ref,
            )
            if kind == "thread":
                query["tenant_id"] = str(tenant_id)
            actions.append((order, kind, query, dict(raw)))

        actions.sort(key=lambda item: (item[0], item[3]["record_id"]))
        deleted: list[str] = []
        acknowledgements: list[dict[str, Any]] = []
        for _order, kind, query, raw in actions:
            collection = self.messages if kind == "message" else self.threads
            try:
                await collection.delete_one(query)
            except Exception as exc:
                raise ConversationStorageUnavailable(
                    "conversation physical deletion failed"
                ) from exc
            try:
                receipt = await acker(
                    tenant_id=str(tenant_id),
                    plan_id=plan_id,
                    record_id=str(raw["record_id"]),
                    target="conversation",
                )
            except Exception as exc:
                raise ConversationStorageUnavailable(
                    "conversation deletion acknowledgement failed"
                ) from exc
            if (
                not isinstance(receipt, Mapping)
                or receipt.get("plan_id") != plan_id
                or receipt.get("record_id") != str(raw["record_id"])
                or receipt.get("target") != "conversation"
                or receipt.get("state") != "deleted"
            ):
                raise ConversationStorageUnavailable(
                    "conversation deletion acknowledgement is malformed"
                )
            deleted.append(str(raw["record_id"]))
            acknowledgements.append(dict(receipt))

        return {
            "plan_id": plan_id,
            "tenant_id": str(tenant_id),
            "deleted_record_ids": deleted,
            "acknowledgements": acknowledgements,
        }

    async def export_governed_records(
        self,
        *,
        tenant_id: str,
    ) -> Mapping[str, Any]:
        reader = self.governance_inventory_reader
        if reader is None:
            raise ConversationStorageUnavailable(
                "conversation governance inventory is unavailable"
            )
        try:
            inventory = await reader(tenant_id=str(tenant_id))
        except Exception as exc:
            raise ConversationStorageUnavailable(
                "conversation governance inventory is unavailable"
            ) from exc
        if (
            not isinstance(inventory, Mapping)
            or inventory.get("tenant_id") != str(tenant_id)
            or not isinstance(inventory.get("records"), list)
        ):
            raise ConversationStorageUnavailable(
                "conversation governance inventory is malformed"
            )

        exported = []
        for raw in inventory["records"]:
            if (
                not isinstance(raw, Mapping)
                or raw.get("owner_plane") != "conversation"
                or raw.get("tenant_id") != str(tenant_id)
            ):
                continue
            record_id = str(raw.get("record_id") or "").strip()
            source_ref = str(raw.get("source_ref") or "").strip()
            kind, query, _order = self._governed_conversation_location(
                record_id,
                source_ref,
            )
            if kind == "thread":
                query["tenant_id"] = str(tenant_id)
            collection = self.messages if kind == "message" else self.threads
            try:
                payload = await collection.find_one(query)
            except Exception as exc:
                raise ConversationStorageUnavailable(
                    "conversation governed export read failed"
                ) from exc
            if payload is not None:
                payload = dict(payload)
                payload.pop("_id", None)
            exported.append(
                {
                    "governance": dict(raw),
                    "payload": payload,
                }
            )

        return {
            "tenant_id": str(tenant_id),
            "records": exported,
            "count": len(exported),
        }

    async def _register_governance(
        self,
        *,
        record_id: str,
        tenant_id: str,
        source_ref: str,
        data_class: str,
        created_at: datetime,
    ) -> Mapping[str, Any] | None:
        registrar = self.governance_registrar
        if registrar is None:
            return None
        try:
            receipt = await registrar(
                mode="register",
                plane="conversation",
                record_id=str(record_id),
                tenant_id=str(tenant_id),
                source_ref=str(source_ref),
                data_class=str(data_class),
                purposes=("model-inference", "retrieval-synthesis"),
                deletion_targets=("conversation",),
                created_at=created_at.astimezone(timezone.utc).timestamp(),
                exportable=True,
            )
        except Exception as exc:
            raise ConversationStorageUnavailable(
                "conversation governance registration is unavailable"
            ) from exc
        if not isinstance(receipt, Mapping):
            raise ConversationStorageUnavailable(
                "conversation governance registration returned invalid receipt"
            )
        record = receipt.get("record")
        if not isinstance(record, Mapping):
            raise ConversationStorageUnavailable(
                "conversation governance registration receipt is malformed"
            )
        if (
            record.get("record_id") != str(record_id)
            or record.get("tenant_id") != str(tenant_id)
            or record.get("owner_plane") != "conversation"
            or record.get("state") != "active"
        ):
            raise ConversationStorageUnavailable(
                "conversation governance registration identity mismatch"
            )
        return receipt

    async def _admit_storage(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        write_id: str,
        payload: object,
    ) -> Mapping[str, Any] | None:
        admitter = self.storage_admitter
        if admitter is None:
            return None
        try:
            receipt = await admitter(
                tenant_id=str(tenant_id),
                capability="conversation-persistence",
                resource_id=str(resource_id),
                write_id=str(write_id),
                storage_bytes=max(1, _storage_bytes(payload)),
            )
        except Exception as exc:
            raise ConversationStorageUnavailable(
                "conversation storage admission is unavailable"
            ) from exc
        if not isinstance(receipt, Mapping):
            raise ConversationStorageUnavailable(
                "conversation storage admission returned invalid receipt"
            )
        admitted = int(receipt.get("storage_bytes") or 0)
        if admitted < _storage_bytes(payload):
            raise ConversationStorageUnavailable(
                "conversation storage admission under-accounted payload"
            )
        return receipt

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
            await self.messages.create_index(
                [
                    ("operation_id", ASCENDING),
                    ("author_type", ASCENDING),
                    ("_commit_state", ASCENDING),
                ],
                name="conversation_operation_result",
                sparse=True,
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
        await self._admit_storage(
            tenant_id=thread.tenant_id,
            resource_id="conversation-thread",
            write_id="thread:" + thread.thread_id,
            payload=thread.as_dict(),
        )
        await self._register_governance(
            record_id=thread.thread_id,
            tenant_id=thread.tenant_id,
            source_ref="conversation-thread://" + thread.thread_id,
            data_class=thread.data_class,
            created_at=thread.created_at,
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
            and existing.context_id == candidate.context_id
            and existing.context_digest == candidate.context_digest
            and existing.context_source_snapshot == candidate.context_source_snapshot
            and existing.context_compiler_version == candidate.context_compiler_version
            and existing.attachment_refs == candidate.attachment_refs
            and existing.tool_receipt_refs == candidate.tool_receipt_refs
            and existing.citation_refs == candidate.citation_refs
            and existing.artifact_refs == candidate.artifact_refs
            and existing.data_class == candidate.data_class
        )

    async def _recover_prepared(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> ConversationThread:
        """Complete or discard the single exact-next prepared append, if any."""

        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        try:
            prepared = await self.messages.find_one(
                {
                    "thread_id": thread_id,
                    "_commit_state": "prepared",
                },
                sort=[("sequence", ASCENDING)],
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation recovery state is unavailable"
            ) from exc
        if prepared is None:
            return thread

        sequence = int(prepared.get("sequence", -1))
        expected = int(prepared.get("_expected_thread_version", -1))
        if sequence <= thread.message_sequence:
            try:
                await self.messages.update_one(
                    {"_id": prepared["_id"], "_commit_state": "prepared"},
                    {"$set": {"_commit_state": "committed"}},
                )
            except PyMongoError:
                pass
            return thread

        if sequence != thread.message_sequence + 1 or expected != thread.version:
            try:
                await self.messages.delete_one(
                    {"_id": prepared["_id"], "_commit_state": "prepared"}
                )
            except PyMongoError as exc:
                raise ConversationStorageUnavailable(
                    "stale conversation append could not be recovered"
                ) from exc
            return thread

        branch_id = (
            str(prepared["branch_id"])
            if prepared.get("_activate_branch", True)
            else thread.active_branch_id
        )
        try:
            updated = await self.threads.find_one_and_update(
                {
                    **self._authorized_filter(
                        thread_id,
                        tenant_id=tenant_id,
                        owner_id=owner_id,
                    ),
                    "version": expected,
                    "message_sequence": sequence - 1,
                    "state": ConversationThreadState.ACTIVE.value,
                },
                {
                    "$set": {
                        "updated_at": _utcnow(),
                        "active_branch_id": branch_id,
                        "message_sequence": sequence,
                        "last_message_id": prepared["_id"],
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "prepared conversation append could not be committed"
            ) from exc
        if updated is None:
            refreshed = await self.get_thread(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
            if refreshed.message_sequence >= sequence:
                try:
                    await self.messages.update_one(
                        {"_id": prepared["_id"]},
                        {"$set": {"_commit_state": "committed"}},
                    )
                except PyMongoError:
                    pass
                return refreshed
            raise ConversationConflict("prepared conversation append could not advance thread")

        try:
            await self.messages.update_one(
                {"_id": prepared["_id"], "_commit_state": "prepared"},
                {"$set": {"_commit_state": "committed"}},
            )
        except PyMongoError:
            # The thread sequence is the commit point. A later recovery pass
            # will normalize this operational marker without losing the turn.
            pass
        return _thread_from_doc(updated)

    async def append_message(
        self,
        message: ConversationMessage,
        *,
        tenant_id: str,
        owner_id: str,
        expected_thread_version: int,
        activate_branch: bool = True,
    ) -> tuple[ConversationThread, ConversationMessage]:
        """Append with a recoverable write-ahead intent and atomic thread commit."""

        thread = await self._recover_prepared(
            message.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        try:
            existing = await self._message_by_idempotency(
                message.thread_id,
                message.idempotency_key,
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation idempotency state is unavailable"
            ) from exc
        if existing is not None:
            if not self._same_identity(existing, message):
                raise ConversationConflict(
                    "idempotency_key was reused with different content"
                )
            if existing.sequence <= thread.message_sequence:
                return thread, existing

        if not thread.writable:
            raise ConversationConflict("thread is not writable")
        if thread.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        if message.sequence != thread.message_sequence + 1:
            raise ConversationConflict(
                f"message sequence must be exact-next ({thread.message_sequence + 1})"
            )

        try:
            if message.parent_message_id is not None:
                parent = await self.messages.find_one(
                    {
                        "_id": message.parent_message_id,
                        "thread_id": message.thread_id,
                        "sequence": {"$lte": thread.message_sequence},
                    }
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
                        "sequence": {"$lte": thread.message_sequence},
                    }
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
                if (
                    prior.author_type is ConversationAuthorType.ASSISTANT
                    and prior.causal_user_message_id
                    != message.causal_user_message_id
                ):
                    raise ConversationConflict(
                        "assistant regeneration must preserve causal user lineage"
                    )

            prepared = _message_doc(message)
            prepared["_commit_state"] = "prepared"
            prepared["_expected_thread_version"] = expected_thread_version
            prepared["_activate_branch"] = bool(activate_branch)
            await self._admit_storage(
                tenant_id=tenant_id,
                resource_id="conversation-message",
                write_id=(
                    "message:"
                    + message.thread_id
                    + ":"
                    + message.idempotency_key
                ),
                payload={
                    "message": message.as_dict(),
                    "thread_commit": {
                        "thread_id": message.thread_id,
                        "expected_version": expected_thread_version,
                        "sequence": message.sequence,
                        "activate_branch": bool(activate_branch),
                    },
                },
            )
            await self._register_governance(
                record_id=message.message_id,
                tenant_id=tenant_id,
                source_ref=(
                    "conversation-message://"
                    + message.thread_id
                    + "/"
                    + message.message_id
                ),
                data_class=message.data_class,
                created_at=message.created_at,
            )
            await self.messages.insert_one(prepared)
        except ConversationConflict:
            raise
        except DuplicateKeyError as exc:
            retry = await self.messages.find_one(
                {
                    "thread_id": message.thread_id,
                    "idempotency_key": message.idempotency_key,
                }
            )
            if retry is not None:
                existing = _message_from_doc(retry)
                if self._same_identity(existing, message):
                    recovered = await self._recover_prepared(
                        message.thread_id,
                        tenant_id=tenant_id,
                        owner_id=owner_id,
                    )
                    if existing.sequence <= recovered.message_sequence:
                        return recovered, existing
            raise ConversationConflict(
                "conversation message identity or ordering conflict"
            ) from exc
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation append intent could not be prepared"
            ) from exc

        committed = await self._recover_prepared(
            message.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if committed.message_sequence < message.sequence:
            raise ConversationConflict("conversation append did not reach commit point")
        return committed, message

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
        context_id: str | None = None,
        context_digest: str | None = None,
        context_source_snapshot: tuple[tuple[str, str], ...] = (),
        context_compiler_version: str | None = None,
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
            context_id=context_id,
            context_digest=context_digest,
            context_source_snapshot=context_source_snapshot,
            context_compiler_version=context_compiler_version,
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

    async def regenerate_assistant_message(
        self,
        thread_id: str,
        prior_assistant_message_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
        operation_id: str,
        ai_result_id: str,
        context_id: str | None = None,
        context_digest: str | None = None,
        context_source_snapshot: tuple[tuple[str, str], ...] = (),
        context_compiler_version: str | None = None,
        tool_receipt_refs: tuple[str, ...] = (),
        citation_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
    ) -> tuple[ConversationThread, ConversationMessage]:
        """Commit a regenerated assistant result as a new active branch.

        The prior assistant message remains immutable. Regeneration creates a
        fresh branch that preserves the original causal user message and binds
        the replacement to a new canonical operation/result identity.
        """

        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        try:
            doc = await self.messages.find_one(
                {
                    "_id": prior_assistant_message_id,
                    "thread_id": thread_id,
                    "sequence": {"$lte": thread.message_sequence},
                }
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation storage is unavailable"
            ) from exc
        if doc is None:
            raise ConversationNotFound(prior_assistant_message_id)
        prior = _message_from_doc(doc)
        if prior.author_type is not ConversationAuthorType.ASSISTANT:
            raise ConversationConflict("only assistant messages can be regenerated")
        if prior.causal_user_message_id is None:
            raise ConversationConflict(
                "assistant message is missing causal user lineage"
            )

        return await self.commit_assistant_message(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            content=content,
            idempotency_key=idempotency_key,
            expected_thread_version=expected_thread_version,
            causal_user_message_id=prior.causal_user_message_id,
            operation_id=operation_id,
            ai_result_id=ai_result_id,
            context_id=context_id,
            context_digest=context_digest,
            context_source_snapshot=context_source_snapshot,
            context_compiler_version=context_compiler_version,
            branch_id=str(uuid4()),
            supersedes_message_id=prior.message_id,
            tool_receipt_refs=tool_receipt_refs,
            citation_refs=citation_refs,
            artifact_refs=artifact_refs,
            data_class=prior.data_class,
        )

    async def assistant_message_for_operation(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> ConversationMessage | None:
        """Resolve committed canonical assistant output for one operation.

        The lookup is tenant/owner bound through the owning thread. Prepared
        messages are never exposed as canonical resync state.
        """

        operation = str(operation_id).strip()
        if not operation or len(operation) > 512:
            raise ValueError("operation_id must be non-empty bounded text")
        tenant = str(tenant_id).strip()
        owner = str(owner_id).strip()
        if not tenant or not owner:
            raise ValueError("tenant_id and owner_id are required")

        try:
            docs = await (
                self.messages.find(
                    {
                        "operation_id": operation,
                        "author_type": ConversationAuthorType.ASSISTANT.value,
                        "_commit_state": "committed",
                    }
                )
                .sort("sequence", DESCENDING)
                .limit(8)
                .to_list(length=8)
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation operation result is unavailable"
            ) from exc

        for doc in docs:
            thread_id = str(doc.get("thread_id") or "")
            if not thread_id:
                continue
            try:
                await self.get_thread(
                    thread_id,
                    tenant_id=tenant,
                    owner_id=owner,
                )
            except ConversationNotFound:
                continue
            return _message_from_doc(doc)
        return None

    async def list_messages(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[ConversationMessage, ...]:
        thread = await self._recover_prepared(
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
                        "sequence": {
                            "$gt": after_sequence,
                            "$lte": thread.message_sequence,
                        },
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
        await self._admit_storage(
            tenant_id=tenant_id,
            resource_id="conversation-thread-state",
            write_id=(
                "state:"
                + str(thread_id)
                + ":"
                + str(expected_version)
                + ":"
                + state.value
            ),
            payload={
                "thread_id": str(thread_id),
                "tenant_id": str(tenant_id),
                "owner_id": str(owner_id),
                "expected_version": expected_version,
                "state": state.value,
            },
        )
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


_conversation_engine_client = EngineClient.from_env()
conversation_authority = MongoConversationAuthority(
    storage_admitter=(
        None
        if _conversation_engine_client is None
        else _conversation_engine_client.admit_storage_write
    ),
    governance_registrar=(
        None
        if _conversation_engine_client is None
        else _conversation_engine_client.reconcile_governed_write
    ),
    governance_deletion_planner=(
        None
        if _conversation_engine_client is None
        else _conversation_engine_client.request_governance_deletion
    ),
    governance_deletion_acker=(
        None
        if _conversation_engine_client is None
        else _conversation_engine_client.acknowledge_governance_deletion
    ),
    governance_inventory_reader=(
        None
        if _conversation_engine_client is None
        else _conversation_engine_client.governance_inventory
    ),
)


__all__ = [
    "ConversationStorageUnavailable",
    "MongoConversationAuthority",
    "conversation_authority",
]
