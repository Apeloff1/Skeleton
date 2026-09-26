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


def _now():
    return datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)


class _InsertCollection:
    def __init__(self) -> None:
        self.inserts = []

    async def insert_one(self, payload):
        self.inserts.append(dict(payload))
        return SimpleNamespace(inserted_id=payload.get("_id"))


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

