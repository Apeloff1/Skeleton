from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.ai.assistant.turn_ownership import (
    TurnLeaseBusy,
    TurnLeaseExpired,
    TurnLeasePolicy,
    TurnLeaseStale,
)
from skeleton.ai.assistant.turn_runtime import TurnState, make_event
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.chat_turn_repository import (
    ChatTurnBinding,
    SQLiteChatTurnRepository,
)


NOW = datetime(2026, 10, 6, 12, 30, tzinfo=timezone.utc)
TENANT = "tenant-a"
OWNER = "owner-a"
POLICY = TurnLeasePolicy(
    default_ttl_seconds=30,
    max_ttl_seconds=120,
    minimum_renewal_seconds=5,
)


def _turn(repo: SQLiteChatTurnRepository):
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        created_at=NOW,
        updated_at=NOW,
        version=2,
        message_sequence=1,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="ownership",
    )
    user = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="ownership-1",
        content="run",
    )
    turn = repo.create_operation(
        operation_id=str(uuid4()),
        request_digest="a" * 64,
        binding=ChatTurnBinding.from_conversation(thread, user),
        created_at=NOW,
    )
    return turn


def test_live_owner_blocks_competing_worker() -> None:
    repo = SQLiteChatTurnRepository()
    turn = _turn(repo)
    lease = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        policy=POLICY,
        now=NOW,
    )
    assert lease.epoch == 1

    with pytest.raises(TurnLeaseBusy):
        repo.acquire_lease(
            turn.snapshot.operation_id,
            tenant_id=TENANT,
            owner_id=OWNER,
            holder_id="worker-b",
            policy=POLICY,
            now=NOW + timedelta(seconds=1),
        )

    same = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        policy=POLICY,
        now=NOW + timedelta(seconds=1),
    )
    assert same == lease


def test_expired_lease_takeover_increments_epoch_and_fences_old_worker() -> None:
    repo = SQLiteChatTurnRepository()
    turn = _turn(repo)
    old = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=10,
        policy=POLICY,
        now=NOW,
    )

    new = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-b",
        ttl_seconds=30,
        policy=POLICY,
        now=NOW + timedelta(seconds=11),
    )
    assert new.epoch == old.epoch + 1
    assert new.previous_lease_digest == old.digest

    with pytest.raises(TurnLeaseStale):
        repo.assert_lease(old, now=NOW + timedelta(seconds=11))
    assert repo.assert_lease(new, now=NOW + timedelta(seconds=11)) == new


def test_heartbeat_invalidates_previous_token_same_epoch() -> None:
    repo = SQLiteChatTurnRepository()
    turn = _turn(repo)
    first = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        policy=POLICY,
        now=NOW,
    )
    renewed = repo.renew_lease(
        first,
        policy=POLICY,
        ttl_seconds=60,
        now=NOW + timedelta(seconds=10),
    )
    assert renewed.epoch == first.epoch
    assert renewed.heartbeat_sequence == first.heartbeat_sequence + 1
    assert renewed.previous_lease_digest == first.digest

    with pytest.raises(TurnLeaseStale):
        repo.assert_lease(first, now=NOW + timedelta(seconds=11))
    assert repo.assert_lease(renewed, now=NOW + timedelta(seconds=11)) == renewed


def test_event_append_validates_fence_inside_transaction() -> None:
    repo = SQLiteChatTurnRepository()
    turn = _turn(repo)
    stale = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=10,
        policy=POLICY,
        now=NOW,
    )
    current = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-b",
        ttl_seconds=30,
        policy=POLICY,
        now=NOW + timedelta(seconds=11),
    )

    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=12),
    )
    with pytest.raises(TurnLeaseStale):
        repo.append_event(
            event,
            tenant_id=TENANT,
            owner_id=OWNER,
            lease=stale,
        )

    advanced = repo.append_event(
        event,
        tenant_id=TENANT,
        owner_id=OWNER,
        lease=current,
    )
    assert advanced.snapshot.state is TurnState.ADMITTED


def test_expired_current_holder_cannot_append_without_takeover() -> None:
    repo = SQLiteChatTurnRepository()
    turn = _turn(repo)
    lease = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        ttl_seconds=10,
        policy=POLICY,
        now=NOW,
    )
    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=10),
    )
    with pytest.raises(TurnLeaseExpired):
        repo.append_event(
            event,
            tenant_id=TENANT,
            owner_id=OWNER,
            lease=lease,
        )


def test_release_then_reacquire_advances_epoch_and_audit_chain() -> None:
    repo = SQLiteChatTurnRepository()
    turn = _turn(repo)
    first = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-a",
        policy=POLICY,
        now=NOW,
    )
    release = repo.release_lease(
        first,
        now=NOW + timedelta(seconds=1),
    )
    second = repo.acquire_lease(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        holder_id="worker-b",
        policy=POLICY,
        now=NOW + timedelta(seconds=2),
    )

    assert second.epoch == first.epoch + 1
    assert second.previous_lease_digest == first.digest
    receipts = repo.list_ownership_receipts(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert [receipt["action"] for receipt in receipts] == [
        "acquire",
        "release",
        "takeover",
    ]
    assert receipts[1]["previous_receipt_digest"] == receipts[0]["digest"]
    assert receipts[2]["previous_receipt_digest"] == receipts[1]["digest"]
    assert receipts[1]["digest"] == release.digest
