from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from backend.core.conversations import MongoConversationAuthority
from skeleton.contracts.conversation import ConversationAuthorType, ConversationMessage


def _assistant(*, provider_receipt_refs: tuple[str, ...]) -> ConversationMessage:
    user_message_id = str(uuid4())
    return ConversationMessage(
        message_id=str(uuid4()),
        thread_id=str(uuid4()),
        branch_id=str(uuid4()),
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=datetime(2026, 10, 3, 18, 0, tzinfo=timezone.utc),
        idempotency_key="assistant-provider-identity",
        content="answer",
        causal_user_message_id=user_message_id,
        operation_id=str(uuid4()),
        ai_result_id="engine-result:provider-identity",
        provider_receipt_refs=provider_receipt_refs,
    )


def test_provider_receipts_are_part_of_mongo_retry_identity() -> None:
    first = _assistant(
        provider_receipt_refs=("provider:local:model-a:receipt-1",),
    )
    same = replace(
        first,
        provider_receipt_refs=(
            "provider:local:model-a:receipt-1",
            "provider:local:model-a:receipt-1",
        ),
    )
    different = replace(
        first,
        provider_receipt_refs=("provider:local:model-b:receipt-2",),
    )

    assert same.provider_receipt_refs == first.provider_receipt_refs
    assert MongoConversationAuthority._same_identity(first, same) is True
    assert MongoConversationAuthority._same_identity(first, different) is False
    assert first.as_dict()["provider_receipt_refs"] == [
        "provider:local:model-a:receipt-1"
    ]
