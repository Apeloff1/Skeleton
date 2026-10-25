from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from core.chat_turns import MongoChatTurnAuthority
from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.turn_ownership import (
    TurnLeaseBusy,
    TurnLeaseStale,
)
from skeleton.ai.assistant.turn_runtime import (
    RecoveryAction,
    TurnState,
    make_event,
)
from skeleton.persistence.chat_turn_repository import (
    ChatTurnBinding,
    ChatTurnConflict,
    ChatTurnCorruption,
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



def _expression_operand(doc, operand, now):
    """Minimal Mongo expression evaluator for the lease CAS test double."""
    if isinstance(operand, str):
        if operand == "$$NOW":
            return now
        if operand.startswith("$"):
            return doc.get(operand[1:])
    if isinstance(operand, dict) and set(operand) == {"$ifNull"}:
        values = operand["$ifNull"]
        if len(values) != 2:
            raise AssertionError("unsupported $ifNull form")
        value = _expression_operand(doc, values[0], now)
        return value if value is not None else _expression_operand(doc, values[1], now)
    return operand


def _matches_expression(doc, expression):
    # Mongo evaluates $$NOW at the server's comparison point. Tests freeze the
    # authority clock, so the fake storage uses that same deterministic clock.
    from core import chat_turns as chat_turn_module

    now = chat_turn_module._utcnow()
    if not isinstance(expression, dict) or len(expression) != 1:
        raise AssertionError("unsupported Mongo expression")
    operation, arguments = next(iter(expression.items()))
    if operation in {"$or", "$and"}:
        results = (_matches_expression(doc, expression) for expression in arguments)
        return any(results) if operation == "$or" else all(results)
    if operation in {"$gt", "$lte", "$eq"}:
        if not isinstance(arguments, list) or len(arguments) != 2:
            raise AssertionError("unsupported Mongo comparison")
        left, right = (_expression_operand(doc, item, now) for item in arguments)
        if operation == "$eq":
            return left == right
        if left is None or right is None or type(left) is not type(right):
            return False
        return left > right if operation == "$gt" else left <= right
    raise AssertionError(f"unsupported Mongo expression operator: {operation}")


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$expr":
            if not _matches_expression(doc, expected):
                return False
            continue
        actual = doc.get(key)
        if isinstance(expected, dict):
            if not any(str(field).startswith("$") for field in expected):
                if actual != expected:
                    return False
                continue
            if "$gt" in expected:
                threshold = expected["$gt"]
                # Mongo compares only compatible BSON types for order queries.
                # A missing field must not raise while examining another doc.
                if actual is None or type(actual) is not type(threshold):
                    return False
                if not actual > threshold:
                    return False
            if "$exists" in expected:
                exists = key in doc
                if exists is not bool(expected["$exists"]):
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


@pytest.mark.asyncio
async def test_mongo_live_owner_blocks_competing_worker():
    authority = MongoChatTurnAuthority(FakeDatabase())
    operation_id = str(uuid4())
    await authority.create_operation(
        operation_id=operation_id,
        request_digest="e" * 64,
        binding=_binding(),
        created_at=NOW,
    )
    first = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=30,
        now=NOW,
    )
    assert first.epoch == 1

    with pytest.raises(TurnLeaseBusy):
        await authority.acquire_lease(
            operation_id,
            tenant_id=TENANT,
            owner_id=OWNER,
            holder_id="worker-b",
            ttl_seconds=30,
            now=NOW + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_mongo_renewal_invalidates_previous_lease_token():
    authority = MongoChatTurnAuthority(FakeDatabase())
    operation_id = str(uuid4())
    await authority.create_operation(
        operation_id=operation_id,
        request_digest="f" * 64,
        binding=_binding(),
        created_at=NOW,
    )
    first = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=30,
        now=NOW,
    )
    renewed = await authority.renew_lease(
        first,
        ttl_seconds=60,
        now=NOW + timedelta(seconds=10),
    )
    assert renewed.epoch == first.epoch
    assert renewed.heartbeat_sequence == first.heartbeat_sequence + 1

    with pytest.raises(TurnLeaseStale):
        await authority.assert_lease(
            first,
            now=NOW + timedelta(seconds=11),
        )
    assert (
        await authority.assert_lease(
            renewed,
            now=NOW + timedelta(seconds=11),
        )
        == renewed
    )


@pytest.mark.asyncio
async def test_mongo_expiry_takeover_fences_stale_event_append(monkeypatch):
    from core import chat_turns as chat_turn_module

    # The lease timestamps are deliberately fixed; validation must use the
    # same simulated clock, not the calendar date on the CI runner.
    monkeypatch.setattr(
        chat_turn_module,
        "_utcnow",
        lambda: NOW + timedelta(seconds=12),
    )
    authority = MongoChatTurnAuthority(FakeDatabase())
    operation_id = str(uuid4())
    turn = await authority.create_operation(
        operation_id=operation_id,
        request_digest="1" * 64,
        binding=_binding(),
        created_at=NOW,
    )
    stale = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=10,
        now=NOW,
    )
    current = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-b",
        ttl_seconds=30,
        now=NOW + timedelta(seconds=11),
    )
    assert current.epoch == stale.epoch + 1

    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=12),
    )
    with pytest.raises(TurnLeaseStale):
        await authority.append_event(
            event,
            tenant_id=TENANT,
            owner_id=OWNER,
            lease=stale,
        )

    advanced = await authority.append_event(
        event,
        tenant_id=TENANT,
        owner_id=OWNER,
        lease=current,
    )
    assert advanced.snapshot.state is TurnState.ADMITTED


@pytest.mark.asyncio
async def test_mongo_crash_recovery_discards_prepared_event_after_takeover():
    from core.chat_turns import _event_doc

    database = FakeDatabase()
    authority = MongoChatTurnAuthority(database)
    operation_id = str(uuid4())
    turn = await authority.create_operation(
        operation_id=operation_id,
        request_digest="2" * 64,
        binding=_binding(),
        created_at=NOW,
    )
    stale = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=10,
        now=NOW,
    )
    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=5),
    )
    await authority.events.insert_one(_event_doc(event, stale))

    current = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-b",
        ttl_seconds=30,
        now=NOW + timedelta(seconds=11),
    )
    assert current.epoch == stale.epoch + 1

    recovered = await authority.get_operation(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert recovered.snapshot.state is TurnState.RECEIVED
    assert (
        await authority.events.find_one(
            {"_id": f"{operation_id}:1"}
        )
        is None
    )


@pytest.mark.asyncio
async def test_mongo_crash_recovery_commits_prepared_event_with_live_lease(
    monkeypatch,
):
    from core import chat_turns as chat_turn_module

    database = FakeDatabase()
    authority = MongoChatTurnAuthority(database)
    operation_id = str(uuid4())
    turn = await authority.create_operation(
        operation_id=operation_id,
        request_digest="3" * 64,
        binding=_binding(),
        created_at=NOW,
    )
    lease = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=30,
        now=NOW,
    )
    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=5),
    )
    await authority.events.insert_one(
        chat_turn_module._event_doc(event, lease)
    )
    monkeypatch.setattr(
        chat_turn_module,
        "_utcnow",
        lambda: NOW + timedelta(seconds=6),
    )

    recovered = await authority.get_operation(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert recovered.snapshot.state is TurnState.ADMITTED
    persisted_event = await authority.events.find_one(
        {"_id": f"{operation_id}:1"}
    )
    assert persisted_event["_commit_state"] == "committed"


@pytest.mark.asyncio
async def test_mongo_legacy_operation_gets_atomic_ownership_schema():
    database = FakeDatabase()
    authority = MongoChatTurnAuthority(database)
    operation_id = str(uuid4())
    await authority.create_operation(
        operation_id=operation_id,
        request_digest="4" * 64,
        binding=_binding(),
        created_at=NOW,
    )

    raw = authority.operations.docs[operation_id]
    for field in (
        "lease_epoch",
        "lease_holder_id",
        "lease_granted_at",
        "lease_expires_at",
        "lease_heartbeat_sequence",
        "lease_previous_digest",
        "lease_digest",
        "lease_token",
        "ownership_receipt_digest",
        "ownership_audit_sequence",
    ):
        raw.pop(field, None)

    lease = await authority.acquire_lease(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=30,
        now=NOW,
    )
    assert lease.epoch == 1
    initialized = authority.operations.docs[operation_id]
    assert initialized["lease_epoch"] == 1
    assert initialized["lease_holder_id"] == "worker-a"


def test_mongo_authority_pins_primary_reads_and_aware_timestamps():
    from pymongo import ReadPreference

    class ConfigurableDatabase(FakeDatabase):
        def with_options(self, **options):
            self.options = options
            return self

    database = ConfigurableDatabase()
    authority = MongoChatTurnAuthority(database)
    assert authority.database is database
    assert database.options["read_preference"] == ReadPreference.PRIMARY
    assert database.options["codec_options"].tz_aware is True
    assert database.options["codec_options"].tzinfo is timezone.utc


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_content", [False, True])
async def test_stale_recovery_cannot_delete_replacement_preparation(monkeypatch, changed_content):
    from core import chat_turns as module

    monkeypatch.setattr(module, "_utcnow", lambda: NOW + timedelta(seconds=12))
    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="5" * 64, binding=_binding(), created_at=NOW,
    )
    operation_id = turn.snapshot.operation_id
    stale = await authority.acquire_lease(
        operation_id, tenant_id=TENANT, owner_id=OWNER, holder_id="old", ttl_seconds=10, now=NOW,
    )
    current = await authority.acquire_lease(
        operation_id, tenant_id=TENANT, owner_id=OWNER, holder_id="current", ttl_seconds=30,
        now=NOW + timedelta(seconds=11),
    )
    event = make_event(turn.snapshot, TurnState.ADMITTED, observed_at=NOW + timedelta(seconds=12))
    replacement_event = (
        make_event(turn.snapshot, TurnState.ADMITTED, observed_at=event.observed_at, reason_code="replacement")
        if changed_content else event
    )
    prepared = module._event_doc(event, stale)
    replacement = module._event_doc(replacement_event, current)
    await authority.events.insert_one(prepared)
    original_delete = authority.events.delete_one

    async def replace_before_delete(query):
        authority.events.docs[prepared["_id"]] = deepcopy(replacement)
        return await original_delete(query)

    monkeypatch.setattr(authority.events, "delete_one", replace_before_delete)
    recovered = await authority.get_operation(operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert recovered.snapshot.state is TurnState.RECEIVED
    assert authority.events.docs[prepared["_id"]] == replacement

    recovered = await authority.get_operation(operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert recovered.snapshot.last_event_digest == replacement_event.digest
    assert authority.events.docs[prepared["_id"]]["_commit_state"] == "committed"


@pytest.mark.asyncio
async def test_recovery_refreshes_snapshot_after_preparation_lookup(monkeypatch):
    from core import chat_turns as module

    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="6" * 64, binding=_binding(), created_at=NOW,
    )
    operation_id = turn.snapshot.operation_id
    first = make_event(turn.snapshot, TurnState.ADMITTED, observed_at=NOW + timedelta(seconds=1))
    admitted = turn.snapshot.apply(first)
    second = make_event(admitted, TurnState.USER_MESSAGE_COMMITTED, observed_at=NOW + timedelta(seconds=2))
    original_find = authority.events.find_one
    advanced = False

    async def advance_between_reads(query, *args, **kwargs):
        nonlocal advanced
        if query.get("_commit_state") == "prepared" and not advanced:
            advanced = True
            authority.operations.docs[operation_id].update(module.MongoChatTurnAuthority._snapshot_update(admitted, NOW))
            committed = module._event_doc(first)
            committed["_commit_state"] = "committed"
            authority.events.docs[committed["_id"]] = committed
            prepared = module._event_doc(second)
            authority.events.docs[prepared["_id"]] = prepared
        return await original_find(query, *args, **kwargs)

    monkeypatch.setattr(authority.events, "find_one", advance_between_reads)
    recovered = await authority.get_operation(operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert recovered.snapshot.state is TurnState.USER_MESSAGE_COMMITTED
    assert authority.events.docs[f"{operation_id}:2"]["_commit_state"] == "committed"


@pytest.mark.asyncio
async def test_recovery_uses_database_clock_instead_of_skewed_process_clock(monkeypatch):
    from core import chat_turns as module

    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="7" * 64, binding=_binding(), created_at=NOW,
    )
    operation_id = turn.snapshot.operation_id
    lease = await authority.acquire_lease(
        operation_id, tenant_id=TENANT, owner_id=OWNER, holder_id="worker", ttl_seconds=30, now=NOW,
    )
    event = make_event(turn.snapshot, TurnState.ADMITTED, observed_at=NOW + timedelta(seconds=1))
    await authority.events.insert_one(module._event_doc(event, lease))
    original_operand = _expression_operand

    def database_clock(doc, operand, now):
        return NOW + timedelta(seconds=5) if operand == "$$NOW" else original_operand(doc, operand, now)

    monkeypatch.setitem(globals(), "_expression_operand", database_clock)
    monkeypatch.setattr(module, "_utcnow", lambda: NOW + timedelta(minutes=5))
    recovered = await authority.get_operation(operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert recovered.snapshot.state is TurnState.ADMITTED
    assert authority.events.docs[f"{operation_id}:1"]["_commit_state"] == "committed"


@pytest.mark.asyncio
async def test_failed_ownership_probe_preserves_commit_racing_before_expiry(monkeypatch):
    from core import chat_turns as module

    monkeypatch.setattr(module, "_utcnow", lambda: NOW + timedelta(seconds=31))
    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="8" * 64, binding=_binding(), created_at=NOW,
    )
    operation_id = turn.snapshot.operation_id
    lease = await authority.acquire_lease(
        operation_id, tenant_id=TENANT, owner_id=OWNER, holder_id="worker", ttl_seconds=30, now=NOW,
    )
    event = make_event(turn.snapshot, TurnState.ADMITTED, observed_at=NOW + timedelta(seconds=29))
    await authority.events.insert_one(module._event_doc(event, lease))
    original_find = authority.operations.find_one

    async def commit_at_probe(query, *args, **kwargs):
        if "$expr" in query:
            authority.operations.docs[operation_id].update(
                module.MongoChatTurnAuthority._snapshot_update(turn.snapshot.apply(event), NOW + timedelta(seconds=29))
            )
            return None
        return await original_find(query, *args, **kwargs)

    monkeypatch.setattr(authority.operations, "find_one", commit_at_probe)
    recovered = await authority.get_operation(operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert recovered.snapshot.state is TurnState.ADMITTED
    assert authority.events.docs[f"{operation_id}:1"]["_commit_state"] == "committed"


@pytest.mark.asyncio
async def test_blocked_unowned_intent_survives_until_database_lease_expiry(monkeypatch):
    from core import chat_turns as module

    monkeypatch.setattr(module, "_utcnow", lambda: NOW + timedelta(seconds=5))
    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="9" * 64, binding=_binding(), created_at=NOW,
    )
    operation_id = turn.snapshot.operation_id
    await authority.acquire_lease(
        operation_id, tenant_id=TENANT, owner_id=OWNER, holder_id="worker", ttl_seconds=30, now=NOW,
    )
    event = make_event(turn.snapshot, TurnState.ADMITTED, observed_at=NOW + timedelta(seconds=1))
    prepared = module._event_doc(event)
    await authority.events.insert_one(prepared)

    with pytest.raises(ChatTurnConflict, match="blocked"):
        await authority.get_operation(operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert authority.events.docs[prepared["_id"]] == prepared

    monkeypatch.setattr(module, "_utcnow", lambda: NOW + timedelta(seconds=31))
    recovered = await authority.get_operation(operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert recovered.snapshot.state is TurnState.ADMITTED


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("lease_epoch", True), ("lease_epoch", "1"), ("lease_epoch", None),
    ("lease_epoch", -1), ("ownership_audit_sequence", False), ("lease_digest", "not-a-digest"),
])
async def test_malformed_fencing_header_cannot_be_reset(field, value):
    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="a" * 64, binding=_binding(), created_at=NOW,
    )
    operation_id = turn.snapshot.operation_id
    authority.operations.docs[operation_id][field] = value
    before = deepcopy(authority.operations.docs[operation_id])
    with pytest.raises(ChatTurnCorruption):
        await authority.acquire_lease(
            operation_id, tenant_id=TENANT, owner_id=OWNER, holder_id="worker", now=NOW,
        )
    assert authority.operations.docs[operation_id] == before


@pytest.mark.asyncio
async def test_partial_legacy_header_is_not_reinitialized():
    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="b" * 64, binding=_binding(), created_at=NOW,
    )
    operation_id = turn.snapshot.operation_id
    authority.operations.docs[operation_id].pop("ownership_audit_sequence")
    before = deepcopy(authority.operations.docs[operation_id])
    with pytest.raises(ChatTurnCorruption, match="partially"):
        await authority.acquire_lease(
            operation_id, tenant_id=TENANT, owner_id=OWNER, holder_id="worker", now=NOW,
        )
    assert authority.operations.docs[operation_id] == before


@pytest.mark.asyncio
async def test_future_preparation_is_retained_for_inspection():
    from core import chat_turns as module

    authority = MongoChatTurnAuthority(FakeDatabase())
    turn = await authority.create_operation(
        operation_id=str(uuid4()), request_digest="c" * 64, binding=_binding(), created_at=NOW,
    )
    first = make_event(turn.snapshot, TurnState.ADMITTED, observed_at=NOW + timedelta(seconds=1))
    future = make_event(turn.snapshot.apply(first), TurnState.USER_MESSAGE_COMMITTED,
                        observed_at=NOW + timedelta(seconds=2))
    prepared = module._event_doc(future)
    await authority.events.insert_one(prepared)
    with pytest.raises(ChatTurnCorruption, match="sequence gap"):
        await authority.get_operation(turn.snapshot.operation_id, tenant_id=TENANT, owner_id=OWNER)
    assert authority.events.docs[prepared["_id"]] == prepared


def test_fake_mongo_server_clock_uses_double_dollar_now():
    """Lease fences must compare against server time, not a missing field."""
    from core import chat_turns as turn_module

    doc = {"lease_expires_at": turn_module._utcnow() + timedelta(seconds=10)}
    assert _expression_operand(doc, "$$NOW", turn_module._utcnow()) is not None
    assert _expression_operand(doc, "$NOW", turn_module._utcnow()) is None
