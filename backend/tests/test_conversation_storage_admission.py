from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.conversations import (
    ConversationStorageUnavailable,
    MongoConversationAuthority,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import ConversationConflict


def _now():
    return datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)


class _InsertCollection:
    def __init__(self) -> None:
        self.inserts = []
        self.rows = {}

    async def insert_one(self, payload):
        row = dict(payload)
        self.inserts.append(row)
        if row.get("_id") is not None:
            self.rows[str(row["_id"])] = row
        return SimpleNamespace(inserted_id=payload.get("_id"))

    async def find_one(self, query):
        for row in self.rows.values():
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None

    async def delete_one(self, query):
        for key, row in list(self.rows.items()):
            if all(row.get(field) == value for field, value in query.items()):
                del self.rows[key]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _Database:
    def __init__(self) -> None:
        self.collections = {
            "conversation_threads": _InsertCollection(),
            "conversation_messages": _InsertCollection(),
        }

    def __getitem__(self, name):
        return self.collections[name]


def _thread(*, sequence: int = 0, version: int = 1):
    return ConversationThread(
        thread_id=str(uuid4()),
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
        updated_at=_now(),
        version=version,
        message_sequence=sequence,
        active_branch_id=str(uuid4()),
        state=ConversationThreadState.ACTIVE,
        title="Thread",
    )


@pytest.mark.asyncio
async def test_thread_create_admission_failure_prevents_mongo_write() -> None:
    db = _Database()

    async def deny(**_kwargs):
        raise RuntimeError("engine admission unavailable")

    authority = MongoConversationAuthority(
        db,
        storage_admitter=deny,
    )

    with pytest.raises(
        ConversationStorageUnavailable,
        match="storage admission is unavailable",
    ):
        await authority.create_thread(
            tenant_id="tenant-a",
            owner_id="owner-a",
            title="Denied",
            thread_id=str(uuid4()),
            branch_id=str(uuid4()),
        )

    assert db["conversation_threads"].inserts == []


@pytest.mark.asyncio
async def test_message_replay_does_not_readmit_or_reinsert() -> None:
    initial = _thread()
    committed = ConversationThread(
        thread_id=initial.thread_id,
        tenant_id=initial.tenant_id,
        owner_id=initial.owner_id,
        created_at=initial.created_at,
        updated_at=initial.updated_at,
        version=2,
        message_sequence=1,
        active_branch_id=initial.active_branch_id,
        state=initial.state,
        title=initial.title,
        data_class=initial.data_class,
    )
    message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=initial.thread_id,
        branch_id=initial.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="client-message-1",
        content="hello",
    )
    admitted = []
    governed = []
    inserted = {"value": False}

    async def admit(**kwargs):
        admitted.append(dict(kwargs))
        return {
            "receipt_id": "storage-admission:test",
            "storage_bytes": kwargs["storage_bytes"],
        }

    async def govern(**kwargs):
        governed.append(dict(kwargs))
        return {
            "mode": "register",
            "record": {
                "record_id": kwargs["record_id"],
                "tenant_id": kwargs["tenant_id"],
                "owner_plane": "conversation",
                "state": "active",
            },
        }

    authority = object.__new__(MongoConversationAuthority)
    authority.storage_admitter = admit
    authority.governance_registrar = govern

    async def recover(*_args, **_kwargs):
        return committed if inserted["value"] else initial

    async def by_idempotency(*_args, **_kwargs):
        return message if inserted["value"] else None

    async def insert_one(_payload):
        inserted["value"] = True
        return SimpleNamespace(inserted_id=message.message_id)

    authority._recover_prepared = recover
    authority._message_by_idempotency = by_idempotency
    authority.messages = SimpleNamespace(insert_one=insert_one)

    first_thread, first_message = await authority.append_message(
        message,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )
    replay_thread, replay_message = await authority.append_message(
        message,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )

    assert first_thread == committed
    assert replay_thread == committed
    assert first_message == replay_message == message
    assert len(admitted) == 1
    assert admitted[0]["capability"] == "conversation-persistence"
    assert admitted[0]["resource_id"] == "conversation-message"
    assert admitted[0]["write_id"] == (
        "message:" + initial.thread_id + ":client-message-1"
    )
    assert len(governed) == 1
    assert governed[0]["mode"] == "register"
    assert governed[0]["plane"] == "conversation"
    assert governed[0]["record_id"] == message.message_id
    assert governed[0]["source_ref"] == (
        "conversation-message://"
        + message.thread_id
        + "/"
        + message.message_id
    )


@pytest.mark.asyncio
async def test_authority_rejects_under_accounted_storage_receipt() -> None:
    db = _Database()

    async def under_account(**kwargs):
        return {
            "receipt_id": "storage-admission:bad",
            "storage_bytes": max(0, kwargs["storage_bytes"] - 1),
        }

    authority = MongoConversationAuthority(
        db,
        storage_admitter=under_account,
    )

    with pytest.raises(
        ConversationStorageUnavailable,
        match="under-accounted payload",
    ):
        await authority.create_thread(
            tenant_id="tenant-a",
            owner_id="owner-a",
            title="Under-accounted",
            thread_id=str(uuid4()),
            branch_id=str(uuid4()),
        )

    assert db["conversation_threads"].inserts == []

@pytest.mark.asyncio
async def test_thread_governance_failure_prevents_mongo_write() -> None:
    db = _Database()
    admitted = []

    async def admit(**kwargs):
        admitted.append(dict(kwargs))
        return {
            "receipt_id": "storage-admission:test",
            "storage_bytes": kwargs["storage_bytes"],
        }

    async def deny_governance(**_kwargs):
        raise RuntimeError("engine governance unavailable")

    authority = MongoConversationAuthority(
        db,
        storage_admitter=admit,
        governance_registrar=deny_governance,
    )

    with pytest.raises(
        ConversationStorageUnavailable,
        match="governance registration is unavailable",
    ):
        await authority.create_thread(
            tenant_id="tenant-a",
            owner_id="owner-a",
            title="Governed",
            thread_id=str(uuid4()),
            branch_id=str(uuid4()),
        )

    assert len(admitted) == 1
    assert db["conversation_threads"].inserts == []


@pytest.mark.asyncio
async def test_thread_create_registers_governance_before_mongo_write() -> None:
    db = _Database()
    calls = []

    async def admit(**kwargs):
        calls.append(("admit", dict(kwargs)))
        return {
            "receipt_id": "storage-admission:test",
            "storage_bytes": kwargs["storage_bytes"],
        }

    async def govern(**kwargs):
        calls.append(("govern", dict(kwargs)))
        return {
            "mode": "register",
            "record": {
                "record_id": kwargs["record_id"],
                "tenant_id": kwargs["tenant_id"],
                "owner_plane": "conversation",
                "state": "active",
            },
        }

    thread_id = str(uuid4())
    authority = MongoConversationAuthority(
        db,
        storage_admitter=admit,
        governance_registrar=govern,
    )
    thread = await authority.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        title="Governed",
        thread_id=thread_id,
        branch_id=str(uuid4()),
    )

    assert [item[0] for item in calls] == ["admit", "govern"]
    governance = calls[1][1]
    assert governance["record_id"] == thread_id
    assert governance["tenant_id"] == "tenant-a"
    assert governance["source_ref"] == "conversation-thread://" + thread_id
    assert governance["data_class"] == thread.data_class
    assert governance["purposes"] == (
        "model-inference",
        "retrieval-synthesis",
    )
    assert governance["deletion_targets"] == ("conversation",)
    assert db["conversation_threads"].inserts[0]["_id"] == thread_id


@pytest.mark.asyncio
async def test_authority_rejects_mismatched_governance_receipt() -> None:
    db = _Database()

    async def admit(**kwargs):
        return {
            "receipt_id": "storage-admission:test",
            "storage_bytes": kwargs["storage_bytes"],
        }

    async def wrong_identity(**kwargs):
        return {
            "mode": "register",
            "record": {
                "record_id": "wrong-id",
                "tenant_id": kwargs["tenant_id"],
                "owner_plane": "conversation",
                "state": "active",
            },
        }

    authority = MongoConversationAuthority(
        db,
        storage_admitter=admit,
        governance_registrar=wrong_identity,
    )

    with pytest.raises(
        ConversationStorageUnavailable,
        match="identity mismatch",
    ):
        await authority.create_thread(
            tenant_id="tenant-a",
            owner_id="owner-a",
            title="Mismatch",
            thread_id=str(uuid4()),
            branch_id=str(uuid4()),
        )

    assert db["conversation_threads"].inserts == []

@pytest.mark.asyncio
async def test_governed_conversation_deletion_is_physical_then_acknowledged() -> None:
    db = _Database()
    thread = _thread()
    message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="delete-me",
        content="delete me",
    )
    await db["conversation_threads"].insert_one(
        {
            **thread.as_dict(),
            "_id": thread.thread_id,
        }
    )
    await db["conversation_messages"].insert_one(
        {
            **message.as_dict(),
            "_id": message.message_id,
        }
    )

    acknowledgements = []

    async def plan(**kwargs):
        assert kwargs["tenant_id"] == "tenant-a"
        return {
            "plan_id": "plan-1",
            "tenant_id": "tenant-a",
            "actions": [
                {
                    "record_id": thread.thread_id,
                    "tenant_id": "tenant-a",
                    "target": "conversation",
                    "source_ref": (
                        "conversation-thread://" + thread.thread_id
                    ),
                    "reason": "tenant-request",
                },
                {
                    "record_id": message.message_id,
                    "tenant_id": "tenant-a",
                    "target": "conversation",
                    "source_ref": (
                        "conversation-message://"
                        + thread.thread_id
                        + "/"
                        + message.message_id
                    ),
                    "reason": "tenant-request",
                },
            ],
        }

    async def ack(**kwargs):
        acknowledgements.append(dict(kwargs))
        return {
            "plan_id": kwargs["plan_id"],
            "record_id": kwargs["record_id"],
            "target": kwargs["target"],
            "state": "deleted",
        }

    authority = MongoConversationAuthority(
        db,
        governance_deletion_planner=plan,
        governance_deletion_acker=ack,
    )
    result = await authority.execute_governed_deletion(
        tenant_id="tenant-a",
        record_ids=(thread.thread_id, message.message_id),
    )

    assert result["plan_id"] == "plan-1"
    assert result["deleted_record_ids"] == [
        message.message_id,
        thread.thread_id,
    ]
    assert [row["record_id"] for row in acknowledgements] == [
        message.message_id,
        thread.thread_id,
    ]
    assert db["conversation_messages"].rows == {}
    assert db["conversation_threads"].rows == {}


@pytest.mark.asyncio
async def test_governed_conversation_export_uses_registry_inventory() -> None:
    db = _Database()
    thread = _thread()
    message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="export-me",
        content="exported answer",
        parent_message_id=str(uuid4()),
        causal_user_message_id=str(uuid4()),
        operation_id=str(uuid4()),
        ai_result_id="engine-result:export",
    )
    await db["conversation_threads"].insert_one(
        {**thread.as_dict(), "_id": thread.thread_id}
    )
    await db["conversation_messages"].insert_one(
        {**message.as_dict(), "_id": message.message_id}
    )

    async def inventory(**kwargs):
        assert kwargs["tenant_id"] == "tenant-a"
        return {
            "tenant_id": "tenant-a",
            "records": [
                {
                    "record_id": thread.thread_id,
                    "tenant_id": "tenant-a",
                    "owner_plane": "conversation",
                    "source_ref": (
                        "conversation-thread://" + thread.thread_id
                    ),
                },
                {
                    "record_id": message.message_id,
                    "tenant_id": "tenant-a",
                    "owner_plane": "conversation",
                    "source_ref": (
                        "conversation-message://"
                        + thread.thread_id
                        + "/"
                        + message.message_id
                    ),
                },
                {
                    "record_id": "other-plane",
                    "tenant_id": "tenant-a",
                    "owner_plane": "memory",
                    "source_ref": "memory://assistant/other-plane",
                },
            ],
        }

    authority = MongoConversationAuthority(
        db,
        governance_inventory_reader=inventory,
    )
    exported = await authority.export_governed_records(
        tenant_id="tenant-a",
    )

    assert exported["count"] == 2
    payloads = {
        item["governance"]["record_id"]: item["payload"]
        for item in exported["records"]
    }
    assert payloads[thread.thread_id]["thread_id"] == thread.thread_id
    assert payloads[message.message_id]["message_id"] == message.message_id
    assert "_id" not in payloads[thread.thread_id]
    assert "_id" not in payloads[message.message_id]


@pytest.mark.asyncio
async def test_malformed_governance_delete_plan_cannot_mutate_mongo() -> None:
    db = _Database()
    thread = _thread()
    await db["conversation_threads"].insert_one(
        {**thread.as_dict(), "_id": thread.thread_id}
    )

    async def malformed_plan(**_kwargs):
        return {
            "plan_id": "plan-bad",
            "tenant_id": "tenant-a",
            "actions": [
                {
                    "record_id": thread.thread_id,
                    "tenant_id": "tenant-a",
                    "target": "conversation",
                    "source_ref": "conversation-message://wrong/mismatch",
                }
            ],
        }

    async def ack(**_kwargs):
        raise AssertionError("ack must not run for malformed plan")

    authority = MongoConversationAuthority(
        db,
        governance_deletion_planner=malformed_plan,
        governance_deletion_acker=ack,
    )

    with pytest.raises(
        ConversationStorageUnavailable,
        match="source_ref is invalid",
    ):
        await authority.execute_governed_deletion(
            tenant_id="tenant-a",
            record_ids=(thread.thread_id,),
        )

    assert thread.thread_id in db["conversation_threads"].rows


def _assistant_message(
    thread: ConversationThread,
    *,
    parent: ConversationMessage,
    causal_user_message_id: str,
) -> ConversationMessage:
    return ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=thread.message_sequence + 1,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="assistant-causal-fence",
        content="verified assistant result",
        parent_message_id=parent.message_id,
        causal_user_message_id=causal_user_message_id,
        operation_id=str(uuid4()),
        ai_result_id="engine-result:exec-causal-fence",
    )


@pytest.mark.asyncio
async def test_assistant_append_requires_causal_parent_to_be_user_message() -> None:
    thread = _thread(sequence=1, version=2)
    prior_assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="prior-assistant",
        content="prior result",
        parent_message_id=str(uuid4()),
        causal_user_message_id=str(uuid4()),
        operation_id=str(uuid4()),
        ai_result_id="engine-result:prior",
    )
    candidate = _assistant_message(
        thread,
        parent=prior_assistant,
        causal_user_message_id=prior_assistant.message_id,
    )
    authority = object.__new__(MongoConversationAuthority)
    authority.storage_admitter = None
    authority.governance_registrar = None

    async def recover(*_args, **_kwargs):
        return thread

    async def by_idempotency(*_args, **_kwargs):
        return None

    async def find_one(_query):
        doc = prior_assistant.as_dict()
        doc["created_at"] = prior_assistant.created_at
        doc["_id"] = prior_assistant.message_id
        doc["_commit_state"] = "committed"
        return doc

    authority._recover_prepared = recover
    authority._message_by_idempotency = by_idempotency
    authority.messages = SimpleNamespace(find_one=find_one)

    with pytest.raises(
        ConversationConflict,
        match="assistant result must bind its causal user message",
    ):
        await authority.append_message(
            candidate,
            tenant_id="tenant-a",
            owner_id="owner-a",
            expected_thread_version=2,
        )


@pytest.mark.asyncio
async def test_assistant_append_requires_parent_and_causal_user_identity_match() -> None:
    thread = _thread(sequence=1, version=2)
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="causal-user",
        content="question",
    )
    candidate = _assistant_message(
        thread,
        parent=user_message,
        causal_user_message_id=str(uuid4()),
    )
    authority = object.__new__(MongoConversationAuthority)
    authority.storage_admitter = None
    authority.governance_registrar = None

    async def recover(*_args, **_kwargs):
        return thread

    async def by_idempotency(*_args, **_kwargs):
        return None

    async def find_one(_query):
        doc = user_message.as_dict()
        doc["created_at"] = user_message.created_at
        doc["_id"] = user_message.message_id
        doc["_commit_state"] = "committed"
        return doc

    authority._recover_prepared = recover
    authority._message_by_idempotency = by_idempotency
    authority.messages = SimpleNamespace(find_one=find_one)

    with pytest.raises(
        ConversationConflict,
        match="assistant result must bind its causal user message",
    ):
        await authority.append_message(
            candidate,
            tenant_id="tenant-a",
            owner_id="owner-a",
            expected_thread_version=2,
        )
