from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from core.chat_turns import MongoChatTurnAuthority
from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.turn_runtime import (
    RecoveryAction,
    TurnState,
    make_event,
)
from skeleton.persistence.chat_turn_repository import (
    ChatTurnBinding,
    ChatTurnConflict,
)


NOW = datetime(2026, 10, 6, 1, 30, tzinfo=timezone.utc)
TENANT = "tenant-a"
OWNER = "owner-a"


class _Result:
    def __init__(self, *, matched_count=1):
        self.matched_count = matched_count


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self._limit = None

    def sort(self, key, direction):
        self.docs.sort(
            key=lambda doc: doc.get(key),
            reverse=direction < 0,
        )
        return self

    def limit(self, value):
        self._limit = value
        return self

    async def to_list(self, length):
        cap = min(length, self._limit or length)
        return [deepcopy(doc) for doc in self.docs[:cap]]


def _matches(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$gt" in expected and not actual > expected["$gt"]:
                return False
            continue
        if actual != expected:
            return False
    return True


class FakeCollection:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        from pymongo.errors import DuplicateKeyError

        key = doc["_id"]
        if key in self.docs:
            raise DuplicateKeyError("duplicate")
        self.docs[key] = deepcopy(doc)
        return _Result()

    async def find_one(self, query, projection=None, sort=None):
        values = [
            doc for doc in self.docs.values()
            if _matches(doc, query)
        ]
        if sort:
            for key, direction in reversed(sort):
                values.sort(
                    key=lambda doc: doc.get(key),
                    reverse=direction < 0,
                )
        if not values:
            return None
        doc = deepcopy(values[0])
        if projection:
            return {
                key: doc[key]
                for key, include in projection.items()
                if include and key in doc
            }
        return doc

    async def find_one_and_update(
        self,
        query,
        update,
        return_document=None,
    ):
        for key, doc in list(self.docs.items()):
            if _matches(doc, query):
                for field, value in update.get("$set", {}).items():
                    doc[field] = deepcopy(value)
                self.docs[key] = doc
                return deepcopy(doc)
        return None

    async def update_one(self, query, update):
        for key, doc in list(self.docs.items()):
            if _matches(doc, query):
                for field, value in update.get("$set", {}).items():
                    doc[field] = deepcopy(value)
                self.docs[key] = doc
                return _Result(matched_count=1)
        return _Result(matched_count=0)

    async def delete_one(self, query):
        for key, doc in list(self.docs.items()):
            if _matches(doc, query):
                del self.docs[key]
                return _Result(matched_count=1)
        return _Result(matched_count=0)

    def find(self, query):
        return FakeCursor(
            doc for doc in self.docs.values()
            if _matches(doc, query)
        )


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


def _binding():
    return ChatTurnBinding(
        tenant_id=TENANT,
        owner_id=OWNER,
        thread_id=str(uuid4()),
        causal_user_message_id=str(uuid4()),
        admitted_thread_version=2,
    )


@pytest.mark.asyncio
async def test_mongo_turn_append_and_reconstruct():
    authority = MongoChatTurnAuthority(FakeDatabase())
    binding = _binding()
    operation_id = str(uuid4())
    turn = await authority.create_operation(
        operation_id=operation_id,
        request_digest="a" * 64,
        binding=binding,
        created_at=NOW,
    )
    for offset, state in enumerate(
        (
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
            TurnState.VERIFYING,
            TurnState.FINALIZING,
        ),
        start=1,
    ):
        event = make_event(
            turn.snapshot,
            state,
            observed_at=NOW + timedelta(seconds=offset),
        )
        turn = await authority.append_event(
            event,
            tenant_id=TENANT,
            owner_id=OWNER,
        )

    replayed = await authority.reconstruct(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert replayed.snapshot == turn.snapshot
    assert replayed.snapshot.state is TurnState.FINALIZING


@pytest.mark.asyncio
async def test_mongo_prepared_event_is_recovered_after_crash():
    database = FakeDatabase()
    authority = MongoChatTurnAuthority(database)
    binding = _binding()
    operation_id = str(uuid4())
    turn = await authority.create_operation(
        operation_id=operation_id,
        request_digest="b" * 64,
        binding=binding,
        created_at=NOW,
    )
    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=1),
    )

    from core.chat_turns import _event_doc

    await authority.events.insert_one(_event_doc(event))
    recovered = await authority.get_operation(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert recovered.snapshot.state is TurnState.ADMITTED
    event_doc = await authority.events.find_one(
        {"_id": f"{operation_id}:1"}
    )
    assert event_doc["_commit_state"] == "committed"


@pytest.mark.asyncio
async def test_mongo_consequential_ambiguity_survives_restart():
    database = FakeDatabase()
    authority = MongoChatTurnAuthority(database)
    binding = _binding()
    operation_id = str(uuid4())
    turn = await authority.create_operation(
        operation_id=operation_id,
        request_digest="c" * 64,
        binding=binding,
        created_at=NOW,
    )
    for offset, state in enumerate(
        (
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
            TurnState.TOOL_REQUIRED,
        ),
        start=1,
    ):
        event = make_event(
            turn.snapshot,
            state,
            observed_at=NOW + timedelta(seconds=offset),
        )
        turn = await authority.append_event(
            event,
            tenant_id=TENANT,
            owner_id=OWNER,
        )
    event = make_event(
        turn.snapshot,
        TurnState.TOOL_EXECUTING,
        observed_at=NOW + timedelta(seconds=10),
        tool_call_id="write-1",
        tool_side_effect=SideEffectClass.EXTERNAL_WRITE,
        external_effect_started=True,
    )
    turn = await authority.append_event(
        event,
        tenant_id=TENANT,
        owner_id=OWNER,
    )

    restarted = MongoChatTurnAuthority(database)
    persisted, decision = await restarted.recovery_decision(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert persisted.snapshot.has_ambiguous_external_effect is True
    assert decision.action is RecoveryAction.RECONCILE_TOOL
    assert decision.safe_to_retry is False


@pytest.mark.asyncio
async def test_mongo_duplicate_sequence_with_changed_payload_fails():
    authority = MongoChatTurnAuthority(FakeDatabase())
    binding = _binding()
    operation_id = str(uuid4())
    turn = await authority.create_operation(
        operation_id=operation_id,
        request_digest="d" * 64,
        binding=binding,
        created_at=NOW,
    )
    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=1),
    )
    await authority.append_event(
        event,
        tenant_id=TENANT,
        owner_id=OWNER,
    )

    changed = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=1),
        reason_code="different",
    )
    with pytest.raises(ChatTurnConflict):
        await authority.append_event(
            changed,
            tenant_id=TENANT,
            owner_id=OWNER,
        )
