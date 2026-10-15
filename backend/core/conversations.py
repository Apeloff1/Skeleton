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
from dataclasses import replace
import logging
import hashlib
import json
import math
import re
from typing import Any, Awaitable, Callable, Mapping
from uuid import uuid4

from bson.codec_options import CodecOptions
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
    decode_thread_cursor,
    conversation_search_text,
)


class ConversationStorageUnavailable(ConversationRepositoryError):
    """Authoritative Mongo state cannot currently be used safely."""


_EXECUTION_REF_PREFIXES = ("chat-request-sha256:", "ephemeral-context-sha256:", "chat-selection:")


def _request_refs(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > 256:
        raise ConversationStorageUnavailable("conversation request references are malformed")
    refs = tuple(values)
    if any(not isinstance(ref, str) or not ref or ref != ref.strip() or len(ref) > 512 for ref in refs):
        raise ConversationStorageUnavailable("conversation request references are malformed")
    if len(set(refs)) != len(refs):
        raise ConversationStorageUnavailable("conversation request references contain duplicates")
    for ref in refs:
        for prefix in _EXECUTION_REF_PREFIXES:
            if ref.startswith(prefix) and not re.fullmatch(r"[0-9a-f]{64}", ref[len(prefix) :]):
                raise ConversationStorageUnavailable("conversation request reference digest is malformed")
    if sum(ref.startswith("chat-request-sha256:") for ref in refs) != 1:
        raise ConversationStorageUnavailable("conversation request identity is missing or ambiguous")
    if sum(ref.startswith("ephemeral-context-sha256:") for ref in refs) > 1:
        raise ConversationStorageUnavailable("conversation context identity is ambiguous")
    return refs


def _request_refs_digest(thread_id: str, message_id: str, refs: tuple[str, ...]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"version": 1, "thread_id": thread_id, "message_id": message_id, "attachment_refs": list(refs)},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bson_datetime(value: object) -> datetime:
    """BSON datetimes are UTC, including the driver's default naïve decode.

    Normalize only the persistence boundary. API/domain timestamps still
    require an explicit timezone and the shared legacy client stays unchanged.
    """
    if not isinstance(value, datetime):
        raise ConversationStorageUnavailable("invalid persisted conversation timestamp")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
                    value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else str(value)
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
        created_at=_bson_datetime(doc["created_at"]),
        updated_at=_bson_datetime(doc["updated_at"]),
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
        created_at=_bson_datetime(doc["created_at"]),
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
        context_source_snapshot=tuple(tuple(item) for item in (doc.get("context_source_snapshot") or ())),
        context_compiler_version=doc.get("context_compiler_version"),
        attachment_refs=tuple(doc.get("attachment_refs") or ()),
        tool_receipt_refs=tuple(doc.get("tool_receipt_refs") or ()),
        provider_receipt_refs=tuple(doc.get("provider_receipt_refs") or ()),
        memory_refs=tuple(doc.get("memory_refs") or ()),
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
        governance_engine_target_executor: Callable[..., Awaitable[Mapping[str, Any]]] | None = None,
        governance_retention_planner: Callable[..., Awaitable[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.database = database
        if callable(getattr(database, "with_options", None)):
            database = database.with_options(codec_options=CodecOptions(tz_aware=True, tzinfo=timezone.utc))
        self.threads = database["conversation_threads"]
        self.messages = database["conversation_messages"]
        self.storage_admitter = storage_admitter
        self.governance_registrar = governance_registrar
        self.governance_deletion_planner = governance_deletion_planner
        self.governance_deletion_acker = governance_deletion_acker
        self.governance_inventory_reader = governance_inventory_reader
        self.governance_engine_target_executor = governance_engine_target_executor
        self.governance_retention_planner = governance_retention_planner
        # Installed only through the trusted application lifespan.
        self.dragon_projection = None

    async def dragon_context_segments(self, thread: ConversationThread, query: str) -> tuple:
        """Return only currently consented, untrusted Dragon context evidence."""
        projection = self.dragon_projection
        if projection is None:
            return ()
        try:
            return await projection.context_segments(thread, query)
        except Exception:
            # Advisory memory must never bypass or prevent canonical chat.
            logging.getLogger(__name__).exception(
                "Dragon projection retrieval unavailable thread=%s", thread.thread_id
            )
            return ()

    async def _delete_dragon_projection(self, *, tenant_id: str, owner_id: str, thread_id: str) -> None:
        """Erase the optional derived store before canonical deletion advances."""
        projection = self.dragon_projection
        if projection is None:
            return
        try:
            await projection.delete_thread(tenant_id, owner_id, thread_id)
        except Exception as exc:
            raise ConversationStorageUnavailable(
                "Dragon derived conversation deletion could not be confirmed"
            ) from exc

    async def _after_dragon_commit(self, thread: ConversationThread) -> None:
        """Checkpoint only exact ten-step committed windows, when configured."""
        projection = self.dragon_projection
        if projection is None or thread.message_sequence < 10 or thread.message_sequence % 10:
            return
        try:
            window = await self.list_messages(
                thread.thread_id,
                tenant_id=thread.tenant_id,
                owner_id=thread.owner_id,
                after_sequence=thread.message_sequence - 10,
                limit=10,
            )
            if len(window) == 10 and all(message.branch_id == thread.active_branch_id for message in window):
                await projection.after_commit(thread, window)
        except Exception:
            # This is derived, optional state. The canonical Mongo commit is final.
            # Log the failure for a scoped retention/recovery repair, never retry
            # the user message or change its committed identity.
            logging.getLogger(__name__).exception(
                "Dragon derived checkpoint unavailable thread=%s", thread.thread_id
            )

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
            thread_id = source[len(thread_prefix) :]
            if not thread_id or thread_id != record_key or "/" in thread_id:
                raise ConversationStorageUnavailable("conversation thread governance source_ref is invalid")
            return "thread", {"_id": record_key}, 1
        if source.startswith(message_prefix):
            tail = source[len(message_prefix) :]
            thread_id, separator, message_id = tail.partition("/")
            if (
                not separator
                or not thread_id
                or not message_id
                or "/" in message_id
                or message_id != record_key
            ):
                raise ConversationStorageUnavailable("conversation message governance source_ref is invalid")
            return (
                "message",
                {"_id": record_key, "thread_id": thread_id},
                0,
            )
        raise ConversationStorageUnavailable("unsupported conversation governance source_ref")

    @staticmethod
    def _governed_reference_tokens(
        message: ConversationMessage,
    ) -> set[str]:
        refs: set[str] = set()
        if message.content_ref:
            refs.add(str(message.content_ref))
        for values in (
            message.attachment_refs,
            message.tool_receipt_refs,
            message.provider_receipt_refs,
            message.memory_refs,
            message.citation_refs,
            message.artifact_refs,
        ):
            refs.update(str(value) for value in values if str(value).strip())
        return refs

    async def governed_record_ids_for_thread(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> tuple[str, ...]:
        """Resolve only lifecycle records owned or explicitly referenced by a thread."""

        reader = self.governance_inventory_reader
        if reader is None:
            raise ConversationStorageUnavailable("conversation governance inventory is unavailable")
        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if thread.message_sequence > 9_999:
            raise ConversationStorageUnavailable("conversation exceeds governed deletion record bound")

        messages: list[ConversationMessage] = []
        after = 0
        while after < thread.message_sequence:
            page = await self.list_messages(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                after_sequence=after,
                limit=500,
            )
            if not page:
                raise ConversationStorageUnavailable("conversation governance lineage is incomplete")
            messages.extend(page)
            after = page[-1].sequence

        conversation_ids = {thread.thread_id}
        conversation_ids.update(message.message_id for message in messages)
        expected_sources = {
            thread.thread_id: "conversation-thread://" + thread.thread_id,
        }
        expected_sources.update(
            {
                message.message_id: ("conversation-message://" + thread.thread_id + "/" + message.message_id)
                for message in messages
            }
        )
        refs: set[str] = set()
        for message in messages:
            refs.update(self._governed_reference_tokens(message))

        try:
            inventory = await reader(tenant_id=str(tenant_id))
        except Exception as exc:
            raise ConversationStorageUnavailable("conversation governance inventory is unavailable") from exc
        if (
            not isinstance(inventory, Mapping)
            or inventory.get("tenant_id") != str(tenant_id)
            or not isinstance(inventory.get("records"), list)
        ):
            raise ConversationStorageUnavailable("conversation governance inventory is malformed")

        selected: set[str] = set()
        found_conversation: set[str] = set()
        for raw in inventory["records"]:
            if not isinstance(raw, Mapping):
                raise ConversationStorageUnavailable("conversation governance inventory record is malformed")
            if raw.get("tenant_id") != str(tenant_id):
                continue
            record_id = str(raw.get("record_id") or "").strip()
            owner_plane = str(raw.get("owner_plane") or "").strip().lower()
            source_ref = str(raw.get("source_ref") or "").strip()
            if not record_id or not owner_plane or not source_ref:
                raise ConversationStorageUnavailable("conversation governance inventory record is malformed")

            if owner_plane == "conversation" and record_id in conversation_ids:
                if source_ref != expected_sources[record_id]:
                    raise ConversationStorageUnavailable("conversation governance record source mismatch")
                selected.add(record_id)
                found_conversation.add(record_id)
                continue

            aliases = {
                record_id,
                source_ref,
                owner_plane + ":" + record_id,
            }
            if refs.intersection(aliases):
                selected.add(record_id)

        missing = conversation_ids - found_conversation
        if missing:
            raise ConversationStorageUnavailable("conversation governance records are incomplete")
        if len(selected) > 10_000:
            raise ConversationStorageUnavailable("conversation governed deletion exceeds record bound")
        return tuple(sorted(selected))

    async def delete_thread_with_governance(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        expected_thread_version: int,
        reason: str = "conversation-delete",
    ) -> Mapping[str, Any]:
        """Delete one conversation plus its explicitly linked governed records."""

        initial = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if initial.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        await self._delete_dragon_projection(tenant_id=tenant_id, owner_id=owner_id, thread_id=thread_id)
        record_ids = await self.governed_record_ids_for_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

        if initial.state is not ConversationThreadState.DELETING:
            deleting = await self.set_state(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                expected_version=expected_thread_version,
                state=ConversationThreadState.DELETING,
            )
        else:
            deleting = initial

        planner = self.governance_deletion_planner
        if planner is None:
            raise ConversationStorageUnavailable("conversation governance deletion protocol is unavailable")
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
        if (
            not isinstance(plan, Mapping)
            or not str(plan.get("plan_id") or "").strip()
            or plan.get("tenant_id") != str(tenant_id)
            or not isinstance(plan.get("actions"), list)
        ):
            raise ConversationStorageUnavailable("conversation governance deletion plan is malformed")

        external_actions: list[Mapping[str, Any]] = []
        for raw in plan["actions"]:
            if not isinstance(raw, Mapping):
                raise ConversationStorageUnavailable("conversation governance deletion action is malformed")
            if raw.get("tenant_id") != str(tenant_id):
                raise ConversationStorageUnavailable("conversation governance deletion tenant mismatch")
            record_id = str(raw.get("record_id") or "").strip()
            target = str(raw.get("target") or "").strip().lower()
            source_ref = str(raw.get("source_ref") or "").strip()
            if not record_id or not target or not source_ref:
                raise ConversationStorageUnavailable("conversation governance deletion action is malformed")
            if record_id not in record_ids:
                raise ConversationStorageUnavailable(
                    "conversation governance plan contains unselected record"
                )
            if target == "conversation":
                self._governed_conversation_location(
                    record_id,
                    source_ref,
                )
            else:
                external_actions.append(raw)

        engine_result: Mapping[str, Any] | None = None
        if external_actions:
            executor = self.governance_engine_target_executor
            if executor is None:
                raise ConversationStorageUnavailable("conversation linked lifecycle executor is unavailable")
            try:
                engine_result = await executor(
                    tenant_id=str(tenant_id),
                    plan_id=str(plan["plan_id"]),
                )
            except Exception as exc:
                raise ConversationStorageUnavailable(
                    "conversation linked lifecycle propagation failed"
                ) from exc
            if (
                not isinstance(engine_result, Mapping)
                or engine_result.get("plan_id") != str(plan["plan_id"])
                or engine_result.get("tenant_id") != str(tenant_id)
            ):
                raise ConversationStorageUnavailable("conversation linked lifecycle receipt is malformed")

        conversation_result = await self.execute_governed_deletion(
            tenant_id=str(tenant_id),
            record_ids=record_ids,
            reason=str(reason),
        )
        return {
            "thread": deleting.as_dict(),
            "record_ids": list(record_ids),
            "plan_id": conversation_result["plan_id"],
            "linked_execution": (None if engine_result is None else dict(engine_result)),
            "conversation": dict(conversation_result),
            "complete": True,
        }

    async def execute_due_retention(
        self,
        *,
        tenant_id: str,
    ) -> Mapping[str, Any]:
        """Execute one tenant retention plan across engine and conversation owners."""

        # Expire Dragon's tenant-scoped derived summaries even when the
        # canonical governance plan has no parent records due in this sweep.
        projection = self.dragon_projection
        if projection is not None:
            try:
                await projection.expire_tenant(str(tenant_id))
            except Exception as exc:
                raise ConversationStorageUnavailable(
                    "Dragon derived retention sweep could not be confirmed"
                ) from exc
        planner = self.governance_retention_planner
        if planner is None:
            raise ConversationStorageUnavailable("conversation retention planning is unavailable")
        try:
            plan = await planner(tenant_id=str(tenant_id))
        except Exception as exc:
            raise ConversationStorageUnavailable("conversation retention plan is unavailable") from exc
        if (
            not isinstance(plan, Mapping)
            or plan.get("tenant_id") != str(tenant_id)
            or not isinstance(plan.get("actions"), list)
        ):
            raise ConversationStorageUnavailable("conversation retention plan is malformed")

        plan_id = str(plan.get("plan_id") or "").strip()
        if not plan_id:
            if plan["actions"]:
                raise ConversationStorageUnavailable("conversation retention plan is malformed")
            return {
                "tenant_id": str(tenant_id),
                "plan_id": None,
                "record_ids": [],
                "linked_execution": None,
                "conversation": None,
                "complete": True,
            }

        external_actions: list[Mapping[str, Any]] = []
        conversation_ids: list[str] = []
        seen_records: set[str] = set()
        for raw in plan["actions"]:
            if not isinstance(raw, Mapping):
                raise ConversationStorageUnavailable("conversation retention action is malformed")
            if raw.get("tenant_id") != str(tenant_id):
                raise ConversationStorageUnavailable("conversation retention tenant mismatch")
            record_id = str(raw.get("record_id") or "").strip()
            target = str(raw.get("target") or "").strip().lower()
            source_ref = str(raw.get("source_ref") or "").strip()
            if not record_id or not target or not source_ref:
                raise ConversationStorageUnavailable("conversation retention action is malformed")
            seen_records.add(record_id)
            if target == "conversation":
                self._governed_conversation_location(
                    record_id,
                    source_ref,
                )
                if record_id not in conversation_ids:
                    conversation_ids.append(record_id)
            else:
                external_actions.append(raw)

        engine_result: Mapping[str, Any] | None = None
        if external_actions:
            executor = self.governance_engine_target_executor
            if executor is None:
                raise ConversationStorageUnavailable("conversation retention engine executor is unavailable")
            try:
                engine_result = await executor(
                    tenant_id=str(tenant_id),
                    plan_id=plan_id,
                )
            except Exception as exc:
                raise ConversationStorageUnavailable(
                    "conversation retention linked propagation failed"
                ) from exc
            if (
                not isinstance(engine_result, Mapping)
                or engine_result.get("plan_id") != plan_id
                or engine_result.get("tenant_id") != str(tenant_id)
            ):
                raise ConversationStorageUnavailable("conversation retention linked receipt is malformed")

        conversation_result: Mapping[str, Any] | None = None
        if conversation_ids:
            conversation_result = await self.execute_governed_deletion(
                tenant_id=str(tenant_id),
                record_ids=tuple(conversation_ids),
                reason="retention-expired",
            )
            if conversation_result.get("plan_id") != plan_id:
                raise ConversationStorageUnavailable("conversation retention plan identity changed")

        return {
            "tenant_id": str(tenant_id),
            "plan_id": plan_id,
            "record_ids": sorted(seen_records),
            "linked_execution": (None if engine_result is None else dict(engine_result)),
            "conversation": (None if conversation_result is None else dict(conversation_result)),
            "complete": True,
        }

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
            raise ConversationStorageUnavailable("conversation governance deletion protocol is unavailable")
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
            raise ConversationStorageUnavailable("conversation governance deletion plan is malformed")
        plan_id = str(plan.get("plan_id") or "").strip()
        if (
            not plan_id
            or plan.get("tenant_id") != str(tenant_id)
            or not isinstance(plan.get("actions"), list)
        ):
            raise ConversationStorageUnavailable("conversation governance deletion plan identity mismatch")

        actions = []
        for raw in plan["actions"]:
            if not isinstance(raw, Mapping):
                raise ConversationStorageUnavailable("conversation governance deletion action is malformed")
            if str(raw.get("target") or "").lower() != "conversation":
                continue
            if raw.get("tenant_id") != str(tenant_id):
                raise ConversationStorageUnavailable("conversation governance deletion tenant mismatch")
            record_id = str(raw.get("record_id") or "").strip()
            source_ref = str(raw.get("source_ref") or "").strip()
            kind, query, order = self._governed_conversation_location(
                record_id,
                source_ref,
            )
            if kind == "thread":
                query["tenant_id"] = str(tenant_id)
            actions.append((order, kind, query, dict(raw)))

        # Any governed deletion of a conversation message invalidates the
        # derived ten-step checkpoint too. Fence the entire affected thread
        # before the first physical delete, not after a partial retry.
        if self.dragon_projection is not None and actions:
            affected_threads = {
                str(query["_id"] if kind == "thread" else query["thread_id"])
                for _order, kind, query, _raw in actions
            }
            for affected_thread_id in sorted(affected_threads):
                try:
                    owner_doc = await self.threads.find_one(
                        {"_id": affected_thread_id, "tenant_id": str(tenant_id)},
                        {"owner_id": 1},
                    )
                except PyMongoError as exc:
                    raise ConversationStorageUnavailable("Dragon deletion owner lookup unavailable") from exc
                if owner_doc is not None:
                    affected_owner = str(owner_doc.get("owner_id") or "")
                    if not affected_owner:
                        raise ConversationStorageUnavailable("Dragon deletion owner identity unavailable")
                    await self._delete_dragon_projection(
                        tenant_id=str(tenant_id),
                        owner_id=affected_owner,
                        thread_id=affected_thread_id,
                    )

        actions.sort(key=lambda item: (item[0], item[3]["record_id"]))
        deleted: list[str] = []
        acknowledgements: list[dict[str, Any]] = []
        for _order, kind, query, raw in actions:
            collection = self.messages if kind == "message" else self.threads
            try:
                await collection.delete_one(query)
            except Exception as exc:
                raise ConversationStorageUnavailable("conversation physical deletion failed") from exc
            try:
                receipt = await acker(
                    tenant_id=str(tenant_id),
                    plan_id=plan_id,
                    record_id=str(raw["record_id"]),
                    target="conversation",
                )
            except Exception as exc:
                raise ConversationStorageUnavailable("conversation deletion acknowledgement failed") from exc
            if (
                not isinstance(receipt, Mapping)
                or receipt.get("plan_id") != plan_id
                or receipt.get("record_id") != str(raw["record_id"])
                or receipt.get("target") != "conversation"
                or receipt.get("state") != "deleted"
            ):
                raise ConversationStorageUnavailable("conversation deletion acknowledgement is malformed")
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
            raise ConversationStorageUnavailable("conversation governance inventory is unavailable")
        try:
            inventory = await reader(tenant_id=str(tenant_id))
        except Exception as exc:
            raise ConversationStorageUnavailable("conversation governance inventory is unavailable") from exc
        if (
            not isinstance(inventory, Mapping)
            or inventory.get("tenant_id") != str(tenant_id)
            or not isinstance(inventory.get("records"), list)
        ):
            raise ConversationStorageUnavailable("conversation governance inventory is malformed")

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
                raise ConversationStorageUnavailable("conversation governed export read failed") from exc
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
            raise ConversationStorageUnavailable("conversation governance registration receipt is malformed")
        if (
            record.get("record_id") != str(record_id)
            or record.get("tenant_id") != str(tenant_id)
            or record.get("owner_plane") != "conversation"
            or record.get("state") != "active"
        ):
            raise ConversationStorageUnavailable("conversation governance registration identity mismatch")
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
            raise ConversationStorageUnavailable("conversation storage admission is unavailable") from exc
        if not isinstance(receipt, Mapping):
            raise ConversationStorageUnavailable("conversation storage admission returned invalid receipt")
        admitted = int(receipt.get("storage_bytes") or 0)
        if admitted < _storage_bytes(payload):
            raise ConversationStorageUnavailable("conversation storage admission under-accounted payload")
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
            raise ConversationStorageUnavailable("conversation indexes are unavailable") from exc

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
            raise ConversationStorageUnavailable("conversation storage is unavailable") from exc
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
            raise ConversationStorageUnavailable("conversation storage is unavailable") from exc
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
        search: str = "",
        cursor: str | None = None,
    ) -> tuple[ConversationThread, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        states = ["active", "archived"] if include_archived else ["active"]
        query: dict[str, Any] = {
            "tenant_id": tenant_id,
            "owner_id": owner_id,
            "state": {"$in": states},
        }
        literal = conversation_search_text(search)
        if literal:
            query["title"] = {"$regex": re.escape(literal), "$options": "i"}
        if cursor is not None:
            instant, thread_id = decode_thread_cursor(cursor)
            query["$or"] = [
                {"updated_at": {"$lt": instant}},
                {"updated_at": instant, "_id": {"$gt": thread_id}},
            ]
        try:
            docs = await (
                self.threads.find(query)
                .sort([("updated_at", DESCENDING), ("_id", ASCENDING)])
                .limit(limit)
                .to_list(length=limit)
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation storage is unavailable") from exc
        return tuple(_thread_from_doc(doc) for doc in docs)

    async def rename_thread(
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
            raise ValueError("conversation title must be text")
        initial = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if initial.version != expected_version:
            raise ConversationConflict("thread version conflict")
        if initial.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
            raise ConversationConflict("thread metadata is not writable")
        candidate = replace(initial, title=title.strip(), updated_at=_utcnow(), version=initial.version + 1)
        await self._admit_storage(
            tenant_id=tenant_id,
            resource_id="conversation-thread-metadata",
            write_id=f"rename:{thread_id}:{expected_version}:"
            + hashlib.sha256(candidate.title.encode()).hexdigest(),
            payload={"thread_id": thread_id, "expected_version": expected_version, "title": candidate.title},
        )
        try:
            updated = await self.threads.find_one_and_update(
                {
                    **self._authorized_filter(thread_id, tenant_id=tenant_id, owner_id=owner_id),
                    "version": expected_version,
                    "state": {"$in": ["active", "archived"]},
                },
                {
                    "$set": {"title": candidate.title, "updated_at": candidate.updated_at},
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation metadata is unavailable") from exc
        if updated is None:
            await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
            raise ConversationConflict("thread version changed during rename")
        return _thread_from_doc(updated)

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
            and existing.provider_receipt_refs == candidate.provider_receipt_refs
            and existing.memory_refs == candidate.memory_refs
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
            raise ConversationStorageUnavailable("conversation recovery state is unavailable") from exc
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
                await self.messages.delete_one({"_id": prepared["_id"], "_commit_state": "prepared"})
            except PyMongoError as exc:
                raise ConversationStorageUnavailable(
                    "stale conversation append could not be recovered"
                ) from exc
            return thread

        branch_id = (
            str(prepared["branch_id"]) if prepared.get("_activate_branch", True) else thread.active_branch_id
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
        execution_metadata: Mapping[str, Any] | None = None,
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
            raise ConversationStorageUnavailable("conversation idempotency state is unavailable") from exc
        if existing is not None:
            if not self._same_identity(existing, message):
                raise ConversationConflict("idempotency_key was reused with different content")
            if existing.sequence <= thread.message_sequence:
                return thread, existing

        if not thread.writable:
            raise ConversationConflict("thread is not writable")
        if thread.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        if message.sequence != thread.message_sequence + 1:
            raise ConversationConflict(f"message sequence must be exact-next ({thread.message_sequence + 1})")

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
                    raise ConversationConflict("parent message is missing or invalid")
                if message.author_type is ConversationAuthorType.ASSISTANT:
                    parent_message = _message_from_doc(parent)
                    if (
                        message.causal_user_message_id != message.parent_message_id
                        or parent_message.author_type is not ConversationAuthorType.USER
                        or parent_message.message_id != message.causal_user_message_id
                    ):
                        raise ConversationConflict("assistant result must bind its causal user message")

            if message.supersedes_message_id is not None:
                prior_doc = await self.messages.find_one(
                    {
                        "_id": message.supersedes_message_id,
                        "thread_id": message.thread_id,
                        "sequence": {"$lte": thread.message_sequence},
                    }
                )
                if prior_doc is None:
                    raise ConversationConflict("superseded message does not exist")
                prior = _message_from_doc(prior_doc)
                if prior.author_type != message.author_type:
                    raise ConversationConflict("superseding message must preserve author type")
                if (
                    prior.author_type is ConversationAuthorType.ASSISTANT
                    and prior.causal_user_message_id != message.causal_user_message_id
                ):
                    raise ConversationConflict("assistant regeneration must preserve causal user lineage")

            prepared = _message_doc(message)
            prepared["_commit_state"] = "prepared"
            prepared["_expected_thread_version"] = expected_thread_version
            prepared["_activate_branch"] = bool(activate_branch)
            if execution_metadata is not None:
                if message.author_type is not ConversationAuthorType.USER:
                    raise ConversationConflict("only a canonical user message can prepare chat execution")
                prepared["_chat_execution"] = dict(execution_metadata)
                prepared["_chat_dispatch"] = {"state": "ready", "cancel_requested": False}
                if _storage_bytes(prepared["_chat_execution"]) > 2 * 1024 * 1024:
                    raise ConversationConflict("prepared chat command exceeds its byte bound")
            await self._admit_storage(
                tenant_id=tenant_id,
                resource_id="conversation-message",
                write_id=("message:" + message.thread_id + ":" + message.idempotency_key),
                payload={
                    "message": message.as_dict(),
                    **(
                        {"prepared_chat_execution": prepared["_chat_execution"]}
                        if execution_metadata is not None
                        else {}
                    ),
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
                source_ref=("conversation-message://" + message.thread_id + "/" + message.message_id),
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
            raise ConversationConflict("conversation message identity or ordering conflict") from exc
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation append intent could not be prepared") from exc

        committed = await self._recover_prepared(
            message.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if committed.message_sequence < message.sequence:
            raise ConversationConflict("conversation append did not reach commit point")
        await self._after_dragon_commit(committed)
        return committed, message

    async def chat_execution(self, thread_id: str, message_id: str, *, tenant_id: str, owner_id: str):
        """Read private execution metadata only under canonical message ownership."""
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        try:
            doc = await self.messages.find_one(
                {"_id": message_id, "thread_id": thread_id, "sequence": {"$lte": thread.message_sequence}}
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("prepared chat execution is unavailable") from exc
        if doc is None or _message_from_doc(doc).author_type is not ConversationAuthorType.USER:
            raise ConversationNotFound(message_id)
        return doc.get("_chat_execution")

    async def bind_chat_execution(
        self,
        thread_id: str,
        user_message_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        expected_thread_version: int,
        attachment_refs,
        metadata,
    ):
        """Freeze an edited USER's exact request and command in one same-row CAS."""
        from core.chat_sessions import canonical_bytes, checked_command

        if type(expected_thread_version) is not int or expected_thread_version < 1:
            raise ValueError("expected thread version must be a positive integer")
        desired = _request_refs(attachment_refs)
        thread = await self.authorize_active_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        query = {
            "_id": user_message_id,
            "thread_id": thread_id,
            "sequence": thread.message_sequence,
            "branch_id": thread.active_branch_id,
            "author_type": "user",
        }
        try:
            doc = await self.messages.find_one(query)
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("edited request is unavailable") from exc
        if doc is None:
            raise ConversationConflict("only the current committed USER tip can prepare a request")
        message = _message_from_doc(doc)
        if message.supersedes_message_id is None:
            raise ConversationConflict("only an edited USER may bind a new prepared execution")
        retained = lambda refs: tuple(
            ref
            for ref in refs
            if not ref.startswith(_EXECUTION_REF_PREFIXES) and ref != "chat-prepared-execution:v1"
        )
        if retained(message.attachment_refs) != retained(desired):
            raise ConversationConflict("edited request cannot replace original source attachments")
        message = replace(message, attachment_refs=desired)
        checked_command(metadata, thread=thread, user_message=message, tenant_id=tenant_id, owner_id=owner_id)
        canonical_bytes(metadata)
        existing = doc.get("_chat_execution")
        if existing is not None:
            if existing != metadata or self._bound_user_request_refs(_message_from_doc(doc), doc) != desired:
                raise ConversationConflict("edited request already has different frozen semantics")
            return thread, message
        if doc.get("_chat_engine_command") is not None:
            raise ConversationConflict("edited request already has an original legacy command")
        bound = self._bound_user_request_refs(_message_from_doc(doc), doc)
        if "_chat_request_refs" in doc and bound != desired:
            raise ConversationConflict("edited request already has a different request identity")
        refs_digest = _request_refs_digest(thread_id, user_message_id, desired)
        await self._admit_storage(
            tenant_id=tenant_id,
            resource_id="conversation-turn-command",
            write_id="edited-prepared:" + user_message_id + ":" + metadata["record_digest"],
            payload={"execution_metadata": metadata, "attachment_refs": list(desired)},
        )
        try:
            stored = await self.messages.find_one_and_update(
                {
                    **query,
                    "_chat_execution": {"$exists": False},
                    "_chat_engine_command": {"$exists": False},
                    "_chat_request_refs_digest": doc.get("_chat_request_refs_digest"),
                },
                {
                    "$set": {
                        "_chat_execution": metadata,
                        "_chat_request_refs": list(desired),
                        "_chat_request_refs_digest": refs_digest,
                        "_chat_dispatch": {"state": "ready", "cancel_requested": False},
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
            if stored is None:
                stored = await self.messages.find_one(query)
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("edited request could not be prepared") from exc
        if (
            stored is None
            or stored.get("_chat_execution") != metadata
            or self._bound_user_request_refs(_message_from_doc(stored), stored) != desired
        ):
            raise ConversationConflict("edited request changed while preparing")
        current = await self.authorize_active_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if (
            current.version != thread.version
            or current.active_branch_id != thread.active_branch_id
            or current.message_sequence != message.sequence
        ):
            raise ConversationConflict("thread changed before edited request dispatch")
        return current, message

    async def chat_history_dependencies(self, thread_id, message_ids, *, tenant_id, owner_id):
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        ids = sorted(set(message_ids))
        if len(ids) > 256:
            raise ConversationConflict("selected chat history exceeds causal dependency bounds")
        if not ids:
            return []
        query = {
            "thread_id": thread_id,
            "_id": {"$in": ids},
            "sequence": {"$lte": thread.message_sequence},
            "author_type": "user",
        }
        projection = {"_chat_dispatch": 0}
        try:
            sizes = await self.messages.aggregate(
                [
                    {"$match": query},
                    {"$project": projection},
                    {"$group": {"_id": None, "bytes": {"$sum": {"$bsonSize": "$$ROOT"}}}},
                ],
                maxTimeMS=2000,
            ).to_list(length=1)
            if sizes and sizes[0]["bytes"] > 8 * 1024 * 1024:
                raise ConversationConflict("selected chat dependency metadata exceeds its byte bound")
            rows = (
                await self.messages.find(query, projection).limit(256).max_time_ms(2000).to_list(length=256)
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("selected chat dependencies are unavailable") from exc
        if len(rows) != len(ids):
            raise ConversationConflict("selected chat causal user lineage is incomplete")
        if _storage_bytes(rows) > 8 * 1024 * 1024:
            raise ConversationConflict("selected chat execution metadata exceeds its byte bound")
        return [
            (
                replace(
                    _message_from_doc(record),
                    attachment_refs=self._bound_user_request_refs(_message_from_doc(record), record),
                ),
                record.get("_chat_execution"),
                self._user_engine_command(
                    _message_from_doc(record),
                    record,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                    thread_data_class=thread.data_class,
                ),
            )
            for record in rows
        ]

    async def chat_dispatch(
        self, thread_id, message_id, *, tenant_id, owner_id, record_digest, action="read"
    ):
        """Serialize original command admission and owner cancellation on its row."""
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        query = {
            "_id": message_id,
            "thread_id": thread_id,
            "sequence": {"$lte": thread.message_sequence},
            "_chat_execution.record_digest": record_digest,
        }
        try:
            if action == "claim":
                doc = await self.messages.find_one_and_update(
                    {
                        **query,
                        "_chat_dispatch.state": {"$in": ["ready", "submitting"]},
                        "_chat_dispatch.cancel_requested": False,
                    },
                    {"$set": {"_chat_dispatch.state": "submitting"}},
                    return_document=ReturnDocument.AFTER,
                )
            elif action == "cancel":
                doc = await self.messages.find_one_and_update(
                    {**query, "_chat_dispatch.state": "ready"},
                    {"$set": {"_chat_dispatch.state": "withdrawn", "_chat_dispatch.cancel_requested": True}},
                    return_document=ReturnDocument.AFTER,
                )
                if doc is None:
                    doc = await self.messages.find_one_and_update(
                        query,
                        {"$set": {"_chat_dispatch.cancel_requested": True}},
                        return_document=ReturnDocument.AFTER,
                    )
            elif action == "admitted":
                doc = await self.messages.find_one_and_update(
                    {**query, "_chat_dispatch.state": {"$in": ["submitting", "admitted"]}},
                    {"$set": {"_chat_dispatch.state": "admitted"}},
                    return_document=ReturnDocument.AFTER,
                )
            elif action == "read":
                doc = await self.messages.find_one(query)
            else:
                raise ValueError("unsupported chat dispatch transition")
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("chat admission state is unavailable") from exc
        return None if doc is None else doc.get("_chat_dispatch")

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
        provider_receipt_refs: tuple[str, ...] = (),
        memory_refs: tuple[str, ...] = (),
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
            provider_receipt_refs=provider_receipt_refs,
            memory_refs=memory_refs,
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
        provider_receipt_refs: tuple[str, ...] = (),
        memory_refs: tuple[str, ...] = (),
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
            raise ConversationStorageUnavailable("conversation storage is unavailable") from exc
        if doc is None:
            raise ConversationNotFound(prior_assistant_message_id)
        prior = _message_from_doc(doc)
        if prior.author_type is not ConversationAuthorType.ASSISTANT:
            raise ConversationConflict("only assistant messages can be regenerated")
        if prior.causal_user_message_id is None:
            raise ConversationConflict("assistant message is missing causal user lineage")

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
            provider_receipt_refs=provider_receipt_refs,
            memory_refs=memory_refs,
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
            raise ConversationStorageUnavailable("conversation operation result is unavailable") from exc

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
                    },
                    {
                        "_chat_execution": 0,
                        "_chat_dispatch": 0,
                        "_chat_engine_command": 0,
                        "_regeneration_requests": 0,
                    },
                )
                .sort("sequence", ASCENDING)
                .limit(limit)
                .to_list(length=limit)
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation storage is unavailable") from exc
        return tuple(_message_from_doc(doc) for doc in docs)

    async def active_transcript(
        self, thread_id: str, *, tenant_id: str, owner_id: str
    ) -> tuple[ConversationMessage, ...]:
        thread = await self._recover_prepared(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.message_sequence == 0:
            return ()
        query = {"thread_id": thread_id, "sequence": {"$lte": thread.message_sequence}}
        projection = {
            "_chat_execution": 0,
            "_chat_dispatch": 0,
            "_chat_engine_command": 0,
            "_regeneration_requests": 0,
        }
        try:
            # Count and byte admission happen in Mongo before payload fetch.
            sizes = await self.messages.aggregate(
                [
                    {"$match": query},
                    {"$project": projection},
                    {
                        "$group": {
                            "_id": None,
                            "count": {"$sum": 1},
                            "bytes": {"$sum": {"$bsonSize": "$$ROOT"}},
                        }
                    },
                ],
                maxTimeMS=2000,
            ).to_list(length=1)
            if not sizes or sizes[0]["count"] > 10000 or sizes[0]["bytes"] > 8 * 1024 * 1024:
                raise ConversationStorageUnavailable(
                    "conversation transcript exceeds its complete-read bound"
                )
            docs = (
                await self.messages.find(query, projection)
                .sort("sequence", ASCENDING)
                .limit(10001)
                .max_time_ms(2000)
                .to_list(length=10001)
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("complete conversation transcript is unavailable") from exc
        if len(docs) > 10000 or _storage_bytes(docs) > 8 * 1024 * 1024:
            raise ConversationStorageUnavailable("conversation transcript exceeds its complete-read bound")
        messages = tuple(_message_from_doc(doc) for doc in docs)
        by_id = {message.message_id: message for message in messages}
        candidates = [message for message in messages if message.branch_id == thread.active_branch_id]
        if not candidates:
            raise ConversationStorageUnavailable("active conversation branch has no committed tip")
        current = candidates[-1]
        lineage, seen = [], set()
        while current is not None:
            if current.message_id in seen:
                raise ConversationStorageUnavailable("conversation lineage contains a cycle")
            seen.add(current.message_id)
            lineage.append(current)
            parent_id = current.parent_message_id
            if parent_id is not None and parent_id not in by_id:
                raise ConversationStorageUnavailable("conversation lineage has a missing parent")
            parent = by_id.get(parent_id)
            if parent is not None and parent.sequence >= current.sequence:
                raise ConversationStorageUnavailable("conversation lineage parent ordering differs")
            current = parent
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
            doc = await self.messages.find_one({"_id": message_id, "thread_id": thread_id})
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation storage is unavailable") from exc
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
            attachment_refs=tuple(
                ref
                for ref in prior.attachment_refs
                if not ref.startswith(_EXECUTION_REF_PREFIXES) and ref != "chat-prepared-execution:v1"
            ),
            data_class=prior.data_class,
        )
        return await self.append_message(
            edited,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )

    def _governed_collection(self, kind: str):
        if kind == "message":
            return self.messages
        if kind == "attachment":
            return self.database["chat_attachments"]
        if kind == "thread":
            return self.threads
        raise ConversationStorageUnavailable("conversation governance resource kind is invalid")

    async def authorize_active_thread(
        self, thread_id: str, *, tenant_id: str, owner_id: str
    ) -> ConversationThread:
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if not thread.writable:
            raise ConversationConflict("thread is not writable")
        return thread

    @staticmethod
    def _bound_user_request_refs(message: ConversationMessage, doc: Mapping[str, Any]) -> tuple[str, ...]:
        if "_chat_request_refs" not in doc:
            if "_chat_request_refs_digest" in doc:
                raise ConversationStorageUnavailable("conversation request binding is incomplete")
            if any(ref.startswith("chat-request-sha256:") for ref in message.attachment_refs):
                return _request_refs(message.attachment_refs)
            return message.attachment_refs
        refs = _request_refs(doc["_chat_request_refs"])
        if doc.get("_chat_request_refs_digest") != _request_refs_digest(
            message.thread_id, message.message_id, refs
        ):
            raise ConversationStorageUnavailable("conversation request binding digest mismatch")
        retained = tuple(
            ref
            for ref in message.attachment_refs
            if not ref.startswith(_EXECUTION_REF_PREFIXES) and ref != "chat-prepared-execution:v1"
        )
        requested_sources = tuple(
            ref
            for ref in refs
            if not ref.startswith(_EXECUTION_REF_PREFIXES) and ref != "chat-prepared-execution:v1"
        )
        if retained != requested_sources:
            raise ConversationStorageUnavailable("conversation request binding changed source attachments")
        return refs

    async def user_request_refs(
        self, thread_id: str, user_message_id: str, *, tenant_id: str, owner_id: str
    ) -> tuple[str, ...]:
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        try:
            doc = await self.messages.find_one(
                {
                    "_id": user_message_id,
                    "thread_id": thread_id,
                    "sequence": {"$lte": thread.message_sequence},
                    "author_type": "user",
                }
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation request binding is unavailable") from exc
        if doc is None:
            raise ConversationNotFound(user_message_id)
        return self._bound_user_request_refs(_message_from_doc(doc), doc)

    async def bind_user_request_refs(
        self,
        thread_id: str,
        user_message_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        attachment_refs: tuple[str, ...],
        expected_thread_version: int,
    ) -> tuple[ConversationThread, ConversationMessage]:
        """Bind edited-turn dispatch once without changing immutable message fields."""
        if type(expected_thread_version) is not int or expected_thread_version < 1:
            raise ValueError("expected_thread_version must be a positive integer")
        desired = _request_refs(attachment_refs)
        thread = await self._recover_prepared(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if not thread.writable or thread.version != expected_thread_version:
            raise ConversationConflict("thread state/version conflict")
        query = {
            "_id": user_message_id,
            "thread_id": thread_id,
            "sequence": thread.message_sequence,
            "branch_id": thread.active_branch_id,
            "author_type": "user",
        }
        try:
            doc = await self.messages.find_one(query)
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation request binding is unavailable") from exc
        if doc is None:
            raise ConversationConflict("only the current committed active user tip can bind a request")
        message = _message_from_doc(doc)
        existing = self._bound_user_request_refs(message, doc)
        if "_chat_request_refs" in doc or any(ref.startswith("chat-request-sha256:") for ref in existing):
            if existing != desired:
                raise ConversationConflict(
                    "conversation request identity was reused with different semantics"
                )
        else:
            retained = tuple(
                ref
                for ref in message.attachment_refs
                if not ref.startswith(_EXECUTION_REF_PREFIXES) and ref != "chat-prepared-execution:v1"
            )
            if retained != tuple(
                ref
                for ref in desired
                if not ref.startswith(_EXECUTION_REF_PREFIXES) and ref != "chat-prepared-execution:v1"
            ):
                raise ConversationConflict("edited request cannot substitute source attachments")
            digest = _request_refs_digest(thread_id, user_message_id, desired)
            await self._admit_storage(
                tenant_id=tenant_id,
                resource_id="conversation-turn-request",
                write_id=f"turn-request:{thread_id}:{user_message_id}:{digest}",
                payload={"message_id": user_message_id, "request_refs": list(desired), "digest": digest},
            )
            try:
                stored = await self.messages.find_one_and_update(
                    {
                        **query,
                        "_chat_request_refs": {"$exists": False},
                        "_chat_request_refs_digest": {"$exists": False},
                    },
                    {"$set": {"_chat_request_refs": list(desired), "_chat_request_refs_digest": digest}},
                    return_document=ReturnDocument.AFTER,
                )
                if stored is None:
                    stored = await self.messages.find_one(query)
            except PyMongoError as exc:
                raise ConversationStorageUnavailable(
                    "conversation request binding could not be committed"
                ) from exc
            if stored is None or self._bound_user_request_refs(message, stored) != desired:
                raise ConversationConflict("conversation request binding changed during dispatch")
        current = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if (
            not current.writable
            or current.version != thread.version
            or current.message_sequence != message.sequence
            or current.active_branch_id != message.branch_id
        ):
            raise ConversationConflict("thread changed while the request was bound; refresh before dispatch")
        return current, message

    @staticmethod
    def _user_engine_command(
        message: ConversationMessage,
        doc: Mapping[str, Any],
        *,
        tenant_id: str,
        owner_id: str,
        thread_data_class: str,
    ) -> dict[str, Any] | None:
        from skeleton.api.engine_service import EngineExecutionCommand, EngineServiceError

        if "_chat_engine_command" not in doc:
            if "_chat_engine_command_digest" in doc:
                raise ConversationStorageUnavailable("conversation engine command binding is incomplete")
            return None
        try:
            raw = doc["_chat_engine_command"]
            encoded = json.dumps(
                raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
            if (
                len(encoded) > 2 * 1024 * 1024
                or doc.get("_chat_engine_command_digest") != hashlib.sha256(encoded).hexdigest()
            ):
                raise ValueError("command bytes/digest mismatch")
            command = EngineExecutionCommand.from_dict(raw)
            from uuid import NAMESPACE_URL, uuid5

            operation_id = str(
                uuid5(NAMESPACE_URL, "skeleton-ai-chat:" + message.thread_id + ":" + message.message_id)
            )
            execution_id = str(uuid5(NAMESPACE_URL, "skeleton-ai-chat-execution:" + operation_id))
            classes = ("public", "internal", "confidential", "restricted")
            if (
                command.operation.operation_id != operation_id
                or command.execution_request.execution_id != execution_id
                or command.operation.actor_id != owner_id
                or command.operation.tenant_id != tenant_id
                or command.operation.idempotency_key != message.idempotency_key
                or command.compiled_context.turn_id != message.message_id
                or command.compiled_context.tenant_id != tenant_id
                or "conversation:" + message.thread_id not in command.context_seed_refs
                or command.operation.capability != "assistant.chat"
                or classes.index(command.compiled_context.data_class)
                < max(classes.index(thread_data_class), classes.index(message.data_class), 1)
                or command.as_dict() != raw
            ):
                raise ValueError("command conversation/actor/tenant/classification identity mismatch")
            return dict(raw)
        except (ValueError, TypeError, KeyError, EngineServiceError) as exc:
            raise ConversationStorageUnavailable("conversation stored engine command is malformed") from exc

    async def user_engine_command(
        self, thread_id: str, user_message_id: str, *, tenant_id: str, owner_id: str
    ) -> dict[str, Any] | None:
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
            raise ConversationConflict("conversation is unavailable for recovery")
        try:
            doc = await self.messages.find_one(
                {
                    "_id": user_message_id,
                    "thread_id": thread_id,
                    "author_type": "user",
                    "sequence": {"$lte": thread.message_sequence},
                }
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation engine command is unavailable") from exc
        if doc is None:
            raise ConversationNotFound(user_message_id)
        return self._user_engine_command(
            _message_from_doc(doc),
            doc,
            tenant_id=tenant_id,
            owner_id=owner_id,
            thread_data_class=thread.data_class,
        )

    async def bind_user_engine_command(
        self,
        thread_id: str,
        user_message_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        command,
        expected_thread_version: int,
    ) -> tuple[ConversationThread, ConversationMessage]:
        from skeleton.api.engine_service import EngineExecutionCommand

        if type(expected_thread_version) is not int or expected_thread_version < 1:
            raise ValueError("expected_thread_version must be a positive integer")
        thread = await self.authorize_active_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        query = {
            "_id": user_message_id,
            "thread_id": thread_id,
            "author_type": "user",
            "sequence": thread.message_sequence,
            "branch_id": thread.active_branch_id,
        }
        try:
            doc = await self.messages.find_one(query)
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation engine command is unavailable") from exc
        if doc is None:
            raise ConversationConflict("only the current committed active user tip can bind a command")
        message = _message_from_doc(doc)
        _request_refs(self._bound_user_request_refs(message, doc))
        raw = command.as_dict() if isinstance(command, EngineExecutionCommand) else dict(command)
        encoded = json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        self._user_engine_command(
            message,
            {"_chat_engine_command": raw, "_chat_engine_command_digest": digest},
            tenant_id=tenant_id,
            owner_id=owner_id,
            thread_data_class=thread.data_class,
        )
        existing = self._user_engine_command(
            message, doc, tenant_id=tenant_id, owner_id=owner_id, thread_data_class=thread.data_class
        )
        if existing is not None:
            if existing != raw:
                raise ConversationConflict("conversation command is already bound to different semantics")
        else:
            await self._admit_storage(
                tenant_id=tenant_id,
                resource_id="conversation-turn-command",
                write_id=f"turn-command:{user_message_id}:{digest}",
                payload=raw,
            )
            try:
                stored = await self.messages.find_one_and_update(
                    {
                        **query,
                        "_chat_engine_command": {"$exists": False},
                        "_chat_engine_command_digest": {"$exists": False},
                    },
                    {"$set": {"_chat_engine_command": raw, "_chat_engine_command_digest": digest}},
                    return_document=ReturnDocument.AFTER,
                )
                if stored is None:
                    stored = await self.messages.find_one(query)
            except PyMongoError as exc:
                raise ConversationStorageUnavailable(
                    "conversation engine command could not be committed"
                ) from exc
            if (
                stored is None
                or self._user_engine_command(
                    message,
                    stored,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                    thread_data_class=thread.data_class,
                )
                != raw
            ):
                raise ConversationConflict("conversation command changed during binding")
        current = await self.authorize_active_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if (
            current.version != thread.version
            or current.message_sequence != message.sequence
            or current.active_branch_id != message.branch_id
        ):
            raise ConversationConflict("thread changed before command dispatch")
        return current, message

    @staticmethod
    def _regeneration_record(
        raw: object, *, thread_id: str, message_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        if not isinstance(raw, Mapping) or set(raw) != {
            "schema_version",
            "thread_id",
            "message_id",
            "causal_user_message_id",
            "idempotency_key",
            "request_digest",
            "initial_thread_version",
            "initial_message_sequence",
            "initial_active_branch_id",
            "command",
            "record_digest",
        }:
            raise ConversationStorageUnavailable("conversation regeneration record is malformed")
        record = dict(raw)
        identity = {key: value for key, value in record.items() if key != "record_digest"}
        try:
            encoded = json.dumps(
                identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        except (ValueError, TypeError) as exc:
            raise ConversationStorageUnavailable(
                "conversation regeneration record is not canonical JSON"
            ) from exc
        if (
            record["schema_version"] != "skeleton.conversation.regeneration_request.v1"
            or record["thread_id"] != thread_id
            or record["message_id"] != message_id
            or record["idempotency_key"] != idempotency_key
            or record["record_digest"] != hashlib.sha256(encoded).hexdigest()
            or len(encoded) > 2 * 1024 * 1024
            or not isinstance(record["request_digest"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["request_digest"])
            or type(record["initial_thread_version"]) is not int
            or record["initial_thread_version"] < 1
            or type(record["initial_message_sequence"]) is not int
            or record["initial_message_sequence"] < 1
        ):
            raise ConversationStorageUnavailable("conversation regeneration record identity is invalid")
        return record

    async def regeneration_request(
        self, thread_id: str, message_id: str, idempotency_key: str, *, tenant_id: str, owner_id: str
    ) -> dict[str, Any] | None:
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
            raise ConversationConflict("conversation is unavailable for regeneration recovery")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 1024:
            raise ValueError("regeneration idempotency key is invalid")
        try:
            doc = await self.messages.find_one(
                {
                    "_id": message_id,
                    "thread_id": thread_id,
                    "sequence": {"$lte": thread.message_sequence},
                    "author_type": "assistant",
                }
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation regeneration state is unavailable") from exc
        if doc is None:
            raise ConversationNotFound(message_id)
        key = hashlib.sha256(idempotency_key.encode()).hexdigest()
        requests = doc.get("_regeneration_requests", {})
        if not isinstance(requests, dict):
            raise ConversationStorageUnavailable("conversation regeneration state is malformed")
        raw = requests.get(key)
        return (
            None
            if raw is None
            else self._regeneration_record(
                raw, thread_id=thread_id, message_id=message_id, idempotency_key=idempotency_key
            )
        )

    async def bind_regeneration_request(
        self,
        thread_id: str,
        message_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        expected_thread_version: int,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        candidate = self._regeneration_record(
            record,
            thread_id=thread_id,
            message_id=message_id,
            idempotency_key=str(record.get("idempotency_key", "")),
        )
        thread = await self.authorize_active_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.version != expected_thread_version or candidate["initial_thread_version"] != thread.version:
            raise ConversationConflict("thread version conflict")
        if (
            candidate["initial_message_sequence"] != thread.message_sequence
            or candidate["initial_active_branch_id"] != thread.active_branch_id
        ):
            raise ConversationConflict("regeneration request thread fence changed")
        query = {
            "_id": message_id,
            "thread_id": thread_id,
            "sequence": {"$lte": thread.message_sequence},
            "author_type": "assistant",
        }
        key = hashlib.sha256(candidate["idempotency_key"].encode()).hexdigest()
        try:
            doc = await self.messages.find_one(query)
            if doc is None:
                raise ConversationNotFound(message_id)
            if doc.get("causal_user_message_id") != candidate["causal_user_message_id"]:
                raise ConversationConflict("regeneration causal user identity mismatch")
            requests = doc.get("_regeneration_requests", {})
            count = doc.get("_regeneration_request_count", 0)
            if not isinstance(requests, dict) or type(count) is not int or count != len(requests):
                raise ConversationStorageUnavailable("conversation regeneration metadata is malformed")
            if key in requests:
                existing = self._regeneration_record(
                    requests[key],
                    thread_id=thread_id,
                    message_id=message_id,
                    idempotency_key=candidate["idempotency_key"],
                )
                if existing["request_digest"] != candidate["request_digest"]:
                    raise ConversationConflict("regeneration key was reused with different settings")
                return existing
            if count >= 16:
                raise ConversationConflict("assistant regeneration history limit reached")
            metadata = {**requests, key: candidate}
            if _storage_bytes(metadata) > 8 * 1024 * 1024:
                raise ConversationConflict("assistant regeneration metadata limit reached")
            await self._admit_storage(
                tenant_id=tenant_id,
                resource_id="conversation-regeneration",
                write_id=f"regeneration:{message_id}:{candidate['request_digest']}",
                payload=candidate,
            )
            stored = await self.messages.find_one_and_update(
                {
                    **query,
                    "_regeneration_request_count": (
                        count if "_regeneration_request_count" in doc else {"$exists": False}
                    ),
                    "_regeneration_requests." + key: {"$exists": False},
                },
                {
                    "$set": {
                        "_regeneration_requests." + key: candidate,
                        "_regeneration_dispatch."
                        + key: {
                            "state": "ready",
                            "record_digest": candidate["record_digest"],
                            "cancel_requested": False,
                        },
                    },
                    "$inc": {"_regeneration_request_count": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation regeneration could not be persisted") from exc
        if stored is None:
            existing = await self.regeneration_request(
                thread_id, message_id, candidate["idempotency_key"], tenant_id=tenant_id, owner_id=owner_id
            )
            if existing is None or existing["request_digest"] != candidate["request_digest"]:
                raise ConversationConflict("concurrent regeneration admission changed; refresh before retry")
            return existing
        current = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if not current.writable or current.version != thread.version:
            raise ConversationConflict("thread changed before regeneration admission")
        return candidate

    async def regeneration_dispatch_state(
        self, record: Mapping[str, Any], *, tenant_id: str, owner_id: str
    ) -> dict[str, Any]:
        await self.get_thread(record["thread_id"], tenant_id=tenant_id, owner_id=owner_id)
        key = hashlib.sha256(record["idempotency_key"].encode()).hexdigest()
        try:
            doc = await self.messages.find_one(
                {"_id": record["message_id"], "thread_id": record["thread_id"], "author_type": "assistant"}
            )
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("regeneration dispatch state is unavailable") from exc
        if doc is None:
            raise ConversationNotFound(record["message_id"])
        states = doc.get("_regeneration_dispatch", {})
        state = states.get(key) if isinstance(states, dict) else None
        if (
            not isinstance(state, dict)
            or set(state) != {"state", "record_digest", "cancel_requested"}
            or state["state"] not in {"ready", "submitting", "admitted", "withdrawn"}
            or state["record_digest"] != record["record_digest"]
            or type(state["cancel_requested"]) is not bool
        ):
            raise ConversationStorageUnavailable("regeneration dispatch state is malformed")
        return dict(state)

    async def transition_regeneration_dispatch(
        self,
        record: Mapping[str, Any],
        *,
        tenant_id: str,
        owner_id: str,
        cancel: bool = False,
        admitted: bool = False,
    ) -> dict[str, Any]:
        key = hashlib.sha256(record["idempotency_key"].encode()).hexdigest()
        field = "_regeneration_dispatch." + key
        for _attempt in range(3):
            state = await self.regeneration_dispatch_state(record, tenant_id=tenant_id, owner_id=owner_id)
            if cancel:
                next_state = {
                    **state,
                    "cancel_requested": True,
                    "state": "withdrawn" if state["state"] == "ready" else state["state"],
                }
            elif admitted:
                if state["state"] not in {"submitting", "admitted"}:
                    return state
                next_state = {**state, "state": "admitted"}
            else:
                if state["cancel_requested"] or state["state"] != "ready":
                    return state
                next_state = {**state, "state": "submitting"}
            if next_state == state:
                return state
            await self._admit_storage(
                tenant_id=tenant_id,
                resource_id="conversation-regeneration-dispatch",
                write_id=f"regen-dispatch:{record['record_digest']}:{next_state['state']}:{next_state['cancel_requested']}",
                payload=next_state,
            )
            try:
                updated = await self.messages.find_one_and_update(
                    {"_id": record["message_id"], "thread_id": record["thread_id"], field: state},
                    {"$set": {field: next_state}},
                    return_document=ReturnDocument.AFTER,
                )
            except PyMongoError as exc:
                raise ConversationStorageUnavailable(
                    "regeneration dispatch transition is unavailable"
                ) from exc
            if updated is not None:
                return next_state
        raise ConversationConflict("regeneration dispatch changed concurrently; retry the same request")

    async def _active_lineage_page(
        self, thread: ConversationThread, *, limit: int, before_message_id: str | None = None
    ) -> tuple[tuple[ConversationMessage, ...], str | None, ConversationMessage | None]:
        """Walk committed immutable parents; a page never crosses into a sibling branch."""
        if thread.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
            raise ConversationConflict("conversation content is unavailable")
        if thread.message_sequence == 0:
            if before_message_id is not None:
                raise ConversationNotFound(before_message_id)
            return (), None, None
        try:
            doc = await self.messages.find_one(
                {
                    "thread_id": thread.thread_id,
                    "branch_id": thread.active_branch_id,
                    "sequence": {"$lte": thread.message_sequence},
                },
                projection={
                    "_chat_execution": 0,
                    "_chat_dispatch": 0,
                    "_chat_engine_command": 0,
                    "_regeneration_requests": 0,
                },
                sort=[("sequence", DESCENDING)],
            )
            if doc is None:
                raise ConversationStorageUnavailable("conversation active branch tip is missing")
            tip = _message_from_doc(doc)
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
                    raise ConversationStorageUnavailable("conversation parent lineage is invalid")
                seen.add(current.message_id)
                previous_sequence = current.sequence
                started = started or current.message_id == before_message_id
                if started:
                    content_bytes += _storage_bytes(current.as_dict())
                    if content_bytes > 8 * 1024 * 1024:
                        raise ConversationStorageUnavailable(
                            "conversation projection exceeds its content bound"
                        )
                    page.append(current)
                parent_id = current.parent_message_id
                if parent_id is None:
                    if not started:
                        raise ConversationNotFound(str(before_message_id))
                    return tuple(reversed(page)), None, tip
                parent = await self.messages.find_one(
                    {
                        "_id": parent_id,
                        "thread_id": thread.thread_id,
                        "sequence": {"$lt": current.sequence, "$lte": thread.message_sequence},
                    },
                    {
                        "_chat_execution": 0,
                        "_chat_dispatch": 0,
                        "_chat_engine_command": 0,
                        "_regeneration_requests": 0,
                    },
                )
                if parent is None:
                    raise ConversationStorageUnavailable("conversation parent lineage is incomplete")
                if started and len(page) == limit:
                    return tuple(reversed(page)), parent_id, tip
                current = _message_from_doc(parent)
            raise ConversationStorageUnavailable("conversation lineage exceeds the recovery bound")
        except PyMongoError as exc:
            raise ConversationStorageUnavailable("conversation snapshot is unavailable") from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise ConversationStorageUnavailable("conversation persisted lineage is malformed") from exc

    async def conversation_snapshot(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        limit: int = 100,
        before_message_id: str | None = None,
        expected_thread_version: int | None = None,
    ) -> Mapping[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("snapshot limit must be between 1 and 500")
        if expected_thread_version is not None and (
            type(expected_thread_version) is not int or expected_thread_version < 1
        ):
            raise ValueError("expected_thread_version must be a positive integer")
        for _attempt in range(3):
            thread = await self._recover_prepared(thread_id, tenant_id=tenant_id, owner_id=owner_id)
            if expected_thread_version is not None and thread.version != expected_thread_version:
                raise ConversationConflict("thread version conflict; reconstruct the current conversation")
            messages, cursor, tip = await self._active_lineage_page(
                thread,
                limit=limit,
                before_message_id=before_message_id,
            )
            current = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
            if current.version != thread.version:
                continue
            pending = None
            if tip is not None and tip.author_type is ConversationAuthorType.USER:
                pending = {
                    "message_id": tip.message_id,
                    "idempotency_key": tip.idempotency_key,
                    "sequence": tip.sequence,
                    "attachment_refs": list(tip.attachment_refs),
                    "can_retry": thread.writable,
                }
            regeneration_requests, requests_truncated = await self._regeneration_recovery_refs(thread)
            current = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
            if current.version != thread.version:
                continue
            return {
                "thread": thread.as_dict(),
                "messages": [message.as_dict() for message in messages],
                "last_sequence": 0 if tip is None else tip.sequence,
                "next_before_message_id": cursor,
                "pending_turn": pending,
                "projection": "active",
                "snapshot_version": thread.version,
                "regeneration_requests": regeneration_requests,
                "recovery_requests_truncated": requests_truncated,
            }
        raise ConversationConflict("conversation changed while its snapshot was reconstructed")

    async def _regeneration_recovery_refs(
        self, thread: ConversationThread
    ) -> tuple[list[dict[str, Any]], bool]:
        """Project bounded durable request identities; only engine status can label them running."""
        pipeline = [
            {
                "$match": {
                    "thread_id": thread.thread_id,
                    "author_type": "assistant",
                    "sequence": {"$lte": thread.message_sequence},
                    "_regeneration_requests": {"$exists": True},
                }
            },
            {"$sort": {"sequence": -1}},
            {"$limit": 64},
            {
                "$project": {
                    "_id": 0,
                    "requests": {
                        "$map": {
                            "input": {"$objectToArray": "$_regeneration_requests"},
                            "as": "item",
                            "in": {
                                "message_id": "$message_id",
                                "idempotency_key": "$item.v.idempotency_key",
                                "initial_message_sequence": "$item.v.initial_message_sequence",
                                "initial_active_branch_id": "$item.v.initial_active_branch_id",
                                "operation_id": "$item.v.command.operation.operation_id",
                                "engine_execution_id": "$item.v.command.execution_request.execution_id",
                            },
                        }
                    },
                }
            },
        ]
        try:
            rows = await self.messages.aggregate(pipeline).to_list(length=64)
        except PyMongoError as exc:
            raise ConversationStorageUnavailable(
                "conversation recovery request inventory is unavailable"
            ) from exc
        requests: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row.get("requests"), list) or len(row["requests"]) > 16:
                raise ConversationStorageUnavailable("conversation recovery request inventory is malformed")
            for record in row["requests"]:
                if not isinstance(record, dict):
                    raise ConversationStorageUnavailable(
                        "conversation recovery request identity is malformed"
                    )
                if (
                    record.get("initial_message_sequence") != thread.message_sequence
                    or record.get("initial_active_branch_id") != thread.active_branch_id
                ):
                    continue
                identity = {
                    key: record.get(key)
                    for key in ("message_id", "idempotency_key", "operation_id", "engine_execution_id")
                }
                if any(
                    not isinstance(value, str) or not value or len(value) > 1024
                    for value in identity.values()
                ):
                    raise ConversationStorageUnavailable(
                        "conversation recovery request identity is malformed"
                    )
                requests.append({**identity, "state": "status_required"})
                if len(requests) > 32:
                    return requests[:32], True
        return requests, len(rows) == 64

    async def export_thread(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        format: str = "json",
        expected_thread_version: int | None = None,
    ) -> Mapping[str, Any]:
        """Export only a coherent owned active lineage after live governance admission."""
        if format not in {"json", "markdown"}:
            raise ValueError("conversation export format is invalid")
        initial = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if initial.state not in {ConversationThreadState.ACTIVE, ConversationThreadState.ARCHIVED}:
            raise ConversationConflict("conversation is unavailable for export")
        if expected_thread_version is not None and initial.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        messages = [
            message.as_dict()
            for message in await self.active_transcript(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        ]
        if _storage_bytes(messages) > 8 * 1024 * 1024:
            raise ConversationConflict("conversation export exceeds its bounded transcript size")
        reader = self.governance_inventory_reader
        if reader is None:
            raise ConversationStorageUnavailable("conversation governed export authority is unavailable")
        try:
            inventory = await reader(tenant_id=tenant_id)
        except Exception as exc:
            raise ConversationStorageUnavailable(
                "conversation governed export authority is unavailable"
            ) from exc
        if (
            not isinstance(inventory, Mapping)
            or inventory.get("tenant_id") != tenant_id
            or not isinstance(inventory.get("records"), list)
        ):
            raise ConversationStorageUnavailable("conversation governed export inventory is malformed")
        expected = {thread_id: "conversation-thread://" + thread_id}
        expected.update(
            {
                message["message_id"]: "conversation-message://" + thread_id + "/" + message["message_id"]
                for message in messages
            }
        )
        admitted: set[str] = set()
        now = _utcnow()
        for record in inventory["records"]:
            if not isinstance(record, Mapping) or record.get("record_id") not in expected:
                continue
            retention = record.get("retention_until")
            if (
                record.get("tenant_id") != tenant_id
                or record.get("owner_plane") != "conversation"
                or record.get("source_ref") != expected[record["record_id"]]
                or record.get("state") != "active"
                or record.get("exportable") is not True
                or (
                    retention is not None
                    and (
                        type(retention) not in {int, float}
                        or not math.isfinite(retention)
                        or retention <= now.timestamp()
                    )
                )
            ):
                raise ConversationConflict("conversation content is not currently exportable")
            if record["record_id"] in admitted:
                raise ConversationStorageUnavailable(
                    "conversation governed export inventory has duplicate identities"
                )
            admitted.add(record["record_id"])
        if admitted != set(expected):
            raise ConversationStorageUnavailable("conversation governed export records are incomplete")
        current = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if current.version != initial.version or current.state != initial.state:
            raise ConversationConflict("conversation changed during export; refresh before retry")
        timestamp = now.isoformat()
        if format == "json":
            content = json.dumps(
                {
                    "schema_version": "skeleton.conversation.transcript_export.v1",
                    "exported_at": timestamp,
                    "thread": initial.as_dict(),
                    "projection": "active",
                    "messages": messages,
                    "attachments_embedded": False,
                },
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            media_type, extension = "application/json", "json"
        else:
            sections = [
                "# " + initial.title,
                f"Conversation: {thread_id}",
                f"Version: {initial.version}",
                "Projection: canonical active lineage",
                "",
            ]
            for message in messages:
                sections.extend(
                    [
                        f"## {message['author_type']} — {message['created_at']}",
                        f"Message: {message['message_id']} | branch: {message['branch_id']} | sequence: {message['sequence']}",
                        "",
                    ]
                )
                if message.get("content") is not None:
                    sections.append(message["content"])
                elif message.get("content_ref"):
                    sections.append("Content reference: " + message["content_ref"])
                for name in (
                    "parent_message_id",
                    "supersedes_message_id",
                    "causal_user_message_id",
                    "operation_id",
                    "ai_result_id",
                    "context_id",
                    "context_digest",
                ):
                    if message.get(name):
                        sections.append(name + ": " + str(message[name]))
                for name in (
                    "attachment_refs",
                    "provider_receipt_refs",
                    "tool_receipt_refs",
                    "memory_refs",
                    "citation_refs",
                    "artifact_refs",
                ):
                    if message.get(name):
                        sections.append(name + ": " + json.dumps(message[name], ensure_ascii=False))
                sections.append("")
            content = "\n\n".join(sections)
            media_type, extension = "text/markdown", "md"
        encoded = content.encode("utf-8")
        if len(encoded) > 8 * 1024 * 1024:
            raise ConversationConflict("conversation export exceeds its response size bound")
        return {
            "schema_version": "skeleton.conversation.export.v1",
            "thread_id": thread_id,
            "snapshot_version": initial.version,
            "scope": "canonical_active_lineage",
            "format": format,
            "filename": "conversation_" + thread_id + "." + extension,
            "media_type": media_type,
            "content": content,
            "content_digest": hashlib.sha256(encoded).hexdigest(),
            "exported_at": timestamp,
            "message_count": len(messages),
            "attachments_embedded": False,
        }

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
            write_id=("state:" + str(thread_id) + ":" + str(expected_version) + ":" + state.value),
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
            raise ConversationStorageUnavailable("conversation storage is unavailable") from exc
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
        None if _conversation_engine_client is None else _conversation_engine_client.admit_storage_write
    ),
    governance_registrar=(
        None if _conversation_engine_client is None else _conversation_engine_client.reconcile_governed_write
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
        None if _conversation_engine_client is None else _conversation_engine_client.governance_inventory
    ),
    governance_engine_target_executor=(
        None
        if _conversation_engine_client is None
        else _conversation_engine_client.execute_governance_deletion_engine_targets
    ),
    governance_retention_planner=(
        None if _conversation_engine_client is None else _conversation_engine_client.plan_governance_retention
    ),
)


__all__ = [
    "ConversationStorageUnavailable",
    "MongoConversationAuthority",
    "conversation_authority",
]
