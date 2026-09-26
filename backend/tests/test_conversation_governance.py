from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone

import pytest

from core.conversations import (
    ConversationStorageUnavailable,
    MongoConversationAuthority,
)


class _Collection:
    def __init__(self, name: str, log: list[tuple[str, str]], docs=()):
        self.name = name
        self.log = log
        self.docs = [deepcopy(doc) for doc in docs]

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        return all(doc.get(key) == value for key, value in query.items())

    async def find_one(self, query, projection=None, **kwargs):
        del projection, kwargs
        for doc in self.docs:
            if self._matches(doc, query):
                return deepcopy(doc)
        return None

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                deleted = self.docs.pop(index)
                self.log.append((self.name, str(deleted.get("_id"))))
                return SimpleNamespace(deleted_count=1)
        self.log.append((self.name, "missing"))
        return SimpleNamespace(deleted_count=0)


class _Database:
    def __init__(self, *, threads=(), messages=()):
        self.log: list[tuple[str, str]] = []
        self.collections = {
            "conversation_threads": _Collection(
                "conversation_threads",
                self.log,
                threads,
            ),
            "conversation_messages": _Collection(
                "conversation_messages",
                self.log,
                messages,
            ),
        }

    def __getitem__(self, name: str):
        return self.collections[name]


def _records(tenant_id: str):
    thread_id = str(uuid4())
    message_id = str(uuid4())
    governance = [
        {
            "record_id": thread_id,
            "tenant_id": tenant_id,
            "owner_plane": "conversation",
            "source_ref": f"conversation-thread://{thread_id}",
            "state": "active",
        },
        {
            "record_id": message_id,
            "tenant_id": tenant_id,
            "owner_plane": "conversation",
            "source_ref": (
                f"conversation-message://{thread_id}/{message_id}"
            ),
            "state": "active",
        },
    ]
    thread = {
        "_id": thread_id,
        "tenant_id": tenant_id,
        "owner_id": "owner-a",
        "title": "Governed thread",
    }
    message = {
        "_id": message_id,
        "thread_id": thread_id,
        "content": "governed message",
    }
    return thread_id, message_id, governance, thread, message


@pytest.mark.asyncio
async def test_governed_export_reads_only_conversation_records_for_tenant():
    tenant_id = "tenant-a"
    thread_id, message_id, governance, thread, message = _records(tenant_id)
    database = _Database(threads=(thread,), messages=(message,))

    async def inventory_reader(*, tenant_id: str):
        return {
            "tenant_id": tenant_id,
            "records": [
                *governance,
                {
                    "record_id": "artifact-other",
                    "tenant_id": tenant_id,
                    "owner_plane": "artifact",
                    "source_ref": "artifact://other",
                    "state": "active",
                },
                {
                    "record_id": str(uuid4()),
                    "tenant_id": "tenant-b",
                    "owner_plane": "conversation",
                    "source_ref": "conversation-thread://" + str(uuid4()),
                    "state": "active",
                },
            ],
        }

    authority = MongoConversationAuthority(
        database,
        governance_inventory_reader=inventory_reader,
    )

    exported = await authority.export_governed_records(
        tenant_id=tenant_id,
    )

    assert exported["tenant_id"] == tenant_id
    assert exported["count"] == 2
    by_id = {
        row["governance"]["record_id"]: row["payload"]
        for row in exported["records"]
    }
    assert by_id[thread_id]["title"] == "Governed thread"
    assert by_id[message_id]["content"] == "governed message"
    assert all("_id" not in payload for payload in by_id.values())


@pytest.mark.asyncio
async def test_governed_deletion_removes_message_before_thread_and_acks():
    tenant_id = "tenant-a"
    thread_id, message_id, governance, thread, message = _records(tenant_id)
    database = _Database(threads=(thread,), messages=(message,))
    acknowledgements: list[tuple[str, str]] = []

    async def planner(*, tenant_id: str, record_ids, reason: str):
        assert reason == "tenant-request"
        assert record_ids == (thread_id, message_id)
        return {
            "plan_id": "plan-conversation-delete",
            "tenant_id": tenant_id,
            "actions": [
                {
                    "record_id": governance[0]["record_id"],
                    "tenant_id": tenant_id,
                    "target": "conversation",
                    "source_ref": governance[0]["source_ref"],
                },
                {
                    "record_id": governance[1]["record_id"],
                    "tenant_id": tenant_id,
                    "target": "conversation",
                    "source_ref": governance[1]["source_ref"],
                },
            ],
        }

    async def acker(
        *,
        tenant_id: str,
        plan_id: str,
        record_id: str,
        target: str,
    ):
        acknowledgements.append((record_id, target))
        return {
            "plan_id": plan_id,
            "record_id": record_id,
            "target": target,
            "state": "deleted",
            "tenant_id": tenant_id,
        }

    authority = MongoConversationAuthority(
        database,
        governance_deletion_planner=planner,
        governance_deletion_acker=acker,
    )

    result = await authority.execute_governed_deletion(
        tenant_id=tenant_id,
        record_ids=(thread_id, message_id),
    )

    assert database.log == [
        ("conversation_messages", message_id),
        ("conversation_threads", thread_id),
    ]
    assert result["deleted_record_ids"] == [message_id, thread_id]
    assert acknowledgements == [
        (message_id, "conversation"),
        (thread_id, "conversation"),
    ]
    assert database["conversation_messages"].docs == []
    assert database["conversation_threads"].docs == []


@pytest.mark.asyncio
async def test_governed_deletion_fails_closed_on_cross_tenant_action():
    tenant_id = "tenant-a"
    thread_id, _message_id, _governance, thread, _message = _records(
        tenant_id
    )
    database = _Database(threads=(thread,))

    async def planner(*, tenant_id: str, record_ids, reason: str):
        del record_ids, reason
        return {
            "plan_id": "plan-cross-tenant",
            "tenant_id": tenant_id,
            "actions": [
                {
                    "record_id": thread_id,
                    "tenant_id": "tenant-b",
                    "target": "conversation",
                    "source_ref": f"conversation-thread://{thread_id}",
                }
            ],
        }

    async def acker(**kwargs):
        raise AssertionError("ack must not run after tenant mismatch")

    authority = MongoConversationAuthority(
        database,
        governance_deletion_planner=planner,
        governance_deletion_acker=acker,
    )

    with pytest.raises(
        ConversationStorageUnavailable,
        match="tenant mismatch",
    ):
        await authority.execute_governed_deletion(
            tenant_id=tenant_id,
            record_ids=(thread_id,),
        )

    assert database.log == []
    assert len(database["conversation_threads"].docs) == 1


@pytest.mark.asyncio
async def test_thread_governance_selection_includes_only_explicit_linked_records():
    tenant_id = "tenant-a"
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    assistant_id = str(uuid4())
    memory_id = str(uuid4())
    foreign_memory_id = str(uuid4())
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)

    from skeleton.contracts.conversation import (
        ConversationAuthorType,
        ConversationMessage,
        ConversationThread,
        ConversationThreadState,
    )

    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id=tenant_id,
        owner_id="owner-a",
        created_at=now,
        updated_at=now,
        version=3,
        message_sequence=2,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Linked",
    )
    user = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=now,
        idempotency_key="user-linked",
        content="remember this",
    )
    assistant = ConversationMessage(
        message_id=assistant_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=now,
        idempotency_key="assistant-linked",
        content="remembered",
        parent_message_id=user_id,
        causal_user_message_id=user_id,
        operation_id=str(uuid4()),
        ai_result_id="engine-result:linked",
        memory_refs=("memory:" + memory_id,),
    )
    authority = object.__new__(MongoConversationAuthority)

    async def get_thread(*_args, **_kwargs):
        return thread

    async def list_messages(*_args, after_sequence=0, **_kwargs):
        return (user, assistant) if after_sequence == 0 else ()

    async def inventory_reader(*, tenant_id: str):
        return {
            "tenant_id": tenant_id,
            "records": [
                {
                    "record_id": thread_id,
                    "tenant_id": tenant_id,
                    "owner_plane": "conversation",
                    "source_ref": "conversation-thread://" + thread_id,
                    "state": "active",
                },
                {
                    "record_id": user_id,
                    "tenant_id": tenant_id,
                    "owner_plane": "conversation",
                    "source_ref": (
                        "conversation-message://"
                        + thread_id
                        + "/"
                        + user_id
                    ),
                    "state": "active",
                },
                {
                    "record_id": assistant_id,
                    "tenant_id": tenant_id,
                    "owner_plane": "conversation",
                    "source_ref": (
                        "conversation-message://"
                        + thread_id
                        + "/"
                        + assistant_id
                    ),
                    "state": "active",
                },
                {
                    "record_id": memory_id,
                    "tenant_id": tenant_id,
                    "owner_plane": "memory",
                    "source_ref": "memory://assistant/" + memory_id,
                    "state": "active",
                },
                {
                    "record_id": foreign_memory_id,
                    "tenant_id": tenant_id,
                    "owner_plane": "memory",
                    "source_ref": (
                        "memory://assistant/" + foreign_memory_id
                    ),
                    "state": "active",
                },
            ],
        }

    authority.get_thread = get_thread
    authority.list_messages = list_messages
    authority.governance_inventory_reader = inventory_reader

    selected = await authority.governed_record_ids_for_thread(
        thread_id,
        tenant_id=tenant_id,
        owner_id="owner-a",
    )

    assert set(selected) == {
        thread_id,
        user_id,
        assistant_id,
        memory_id,
    }
    assert foreign_memory_id not in selected


@pytest.mark.asyncio
async def test_governed_export_fails_closed_on_inventory_identity_mismatch():
    database = _Database()

    async def inventory_reader(*, tenant_id: str):
        return {
            "tenant_id": tenant_id + "-other",
            "records": [],
        }

    authority = MongoConversationAuthority(
        database,
        governance_inventory_reader=inventory_reader,
    )

    with pytest.raises(
        ConversationStorageUnavailable,
        match="inventory is malformed",
    ):
        await authority.export_governed_records(tenant_id="tenant-a")
