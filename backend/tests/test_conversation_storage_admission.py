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
    inserted = {"value": False}

    async def admit(**kwargs):
        admitted.append(dict(kwargs))
        return {
            "receipt_id": "storage-admission:test",
            "storage_bytes": kwargs["storage_bytes"],
        }

    authority = object.__new__(MongoConversationAuthority)
    authority.storage_admitter = admit

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
