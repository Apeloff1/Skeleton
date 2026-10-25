"""Production-driver BSON round trips preserve canonical conversation UTC."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from bson import BSON
import pytest

from core.conversations import (
    ConversationStorageUnavailable, _bson_datetime, _message_doc,
    _message_from_doc, _thread_doc, _thread_from_doc,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType, ConversationMessage, ConversationThread,
    ConversationThreadState,
)


def test_thread_survives_default_bson_naive_datetime_decode():
    created = datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc)
    thread = ConversationThread(
        thread_id=str(uuid4()), tenant_id="tenant-e2e", owner_id="owner-e2e",
        created_at=created, updated_at=created, version=1, message_sequence=0,
        active_branch_id=str(uuid4()), state=ConversationThreadState.ACTIVE,
        title="BSON round trip", data_class="confidential",
    )
    document = BSON.encode(_thread_doc(thread)).decode()
    assert document["created_at"].tzinfo is None
    restored = _thread_from_doc(document)
    assert restored.as_dict() == thread.as_dict()
    assert restored.created_at.tzinfo is timezone.utc


def test_message_survives_default_bson_naive_datetime_decode():
    message = ConversationMessage(
        message_id=str(uuid4()), thread_id=str(uuid4()), branch_id=str(uuid4()),
        sequence=1, author_type=ConversationAuthorType.USER,
        created_at=datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc),
        idempotency_key="bson-roundtrip", content="A local fixture message",
        data_class="confidential",
    )
    document = BSON.encode(_message_doc(message)).decode()
    assert document["created_at"].tzinfo is None
    restored = _message_from_doc(document)
    assert restored.as_dict() == message.as_dict()


def test_aware_storage_datetime_normalizes_offset_without_changing_instant():
    timestamp = datetime(2026, 10, 14, 4, 0, tzinfo=timezone(timedelta(hours=2)))
    assert _bson_datetime(timestamp) == datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", [None, True, 123, "2026-10-14T02:00:00Z"])
def test_corrupt_persisted_timestamp_fails_as_storage_unavailable(value):
    with pytest.raises(ConversationStorageUnavailable):
        _bson_datetime(value)


def _lease_document():
    from skeleton.ai.assistant.turn_ownership import TurnLeaseToken
    granted = datetime(2026, 10, 14, 2, 0, 0, 123456, tzinfo=timezone.utc)
    token = TurnLeaseToken(
        operation_id=str(uuid4()), tenant_id="tenant-e2e", owner_id="owner-e2e",
        holder_id="worker-e2e", epoch=1, heartbeat_sequence=0,
        granted_at=granted, expires_at=granted + timedelta(seconds=30),
    )
    document = {
        "operation_id": token.operation_id, "tenant_id": token.tenant_id,
        "owner_id": token.owner_id, "lease_holder_id": token.holder_id,
        "lease_epoch": token.epoch, "lease_heartbeat_sequence": 0,
        "lease_granted_at": token.granted_at, "lease_expires_at": token.expires_at,
        "lease_previous_digest": None, "lease_digest": token.digest,
        "lease_token": token.as_dict(),
        "ownership_audit_sequence": 1,
        "ownership_receipt_digest": "a" * 64,
    }
    return token, BSON.encode(document).decode()


def test_execution_lease_keeps_exact_digest_through_bson_millisecond_dates():
    from core.chat_turns import _assert_lease_doc, _lease_from_doc
    token, document = _lease_document()
    assert document["lease_granted_at"].microsecond == 123000
    restored = _lease_from_doc(document)
    assert restored == token
    assert restored.digest == token.digest
    assert _assert_lease_doc(document, token, now=token.granted_at) == token


@pytest.mark.parametrize("field,value", [
    ("lease_epoch", 2), ("lease_heartbeat_sequence", 1),
    ("lease_epoch", True), ("lease_heartbeat_sequence", False),
    ("lease_digest", "0" * 64),
    ("lease_expires_at", datetime(2027, 1, 1)),
])
def test_materialized_lease_cannot_override_exact_canonical_token(field, value):
    from core.chat_turns import _lease_from_doc
    from skeleton.persistence.chat_turn_repository import ChatTurnCorruption
    _, document = _lease_document()
    document[field] = value
    with pytest.raises(ChatTurnCorruption):
        _lease_from_doc(document)


@pytest.mark.parametrize("field,value", [("epoch", "1"), ("epoch", True),
                                         ("heartbeat_sequence", "0"), ("holder_id", 123)])
def test_canonical_lease_payload_rejects_coerced_identity(field, value):
    from core.chat_turns import _lease_from_doc
    from skeleton.persistence.chat_turn_repository import ChatTurnCorruption
    _, document = _lease_document()
    document["lease_token"][field] = value
    with pytest.raises(ChatTurnCorruption):
        _lease_from_doc(document)


def test_legacy_bson_lease_with_lost_precision_fails_closed():
    from core.chat_turns import _lease_from_doc
    from skeleton.persistence.chat_turn_repository import ChatTurnCorruption
    _, document = _lease_document()
    del document["lease_token"]
    with pytest.raises(ChatTurnCorruption, match="cannot be recovered exactly"):
        _lease_from_doc(document)
