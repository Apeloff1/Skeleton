"""Conversation authority to canonical context segments."""

from __future__ import annotations

from uuid import uuid5, NAMESPACE_URL

from skeleton.contracts.context import (
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
)


def conversation_message_segment(
    thread: ConversationThread,
    message: ConversationMessage,
    *,
    purpose: str,
    resolved_content: str | None = None,
) -> ContextSegment:
    if message.thread_id != thread.thread_id:
        raise ValueError("conversation message does not belong to thread")
    content = message.content if message.content is not None else resolved_content
    if not isinstance(content, str) or not content:
        raise ValueError("conversation message content is not materialized")

    if message.author_type is ConversationAuthorType.USER:
        kind = ContextKind.USER_MESSAGE
        trust = ContextTrust.AUTHORIZED_USER_DATA
        priority = 800
    elif message.author_type is ConversationAuthorType.ASSISTANT:
        kind = ContextKind.ASSISTANT_MESSAGE
        trust = ContextTrust.DERIVED_UNTRUSTED
        priority = 700
    elif message.author_type is ConversationAuthorType.TOOL:
        kind = ContextKind.TOOL_RESULT
        trust = ContextTrust.UNTRUSTED_EVIDENCE
        priority = 650
    else:
        kind = ContextKind.CONVERSATION_SUMMARY
        trust = ContextTrust.DERIVED_UNTRUSTED
        priority = 550

    provenance = [
        "conversation-thread:" + thread.thread_id,
        "conversation-message:" + message.message_id,
        "conversation-branch:" + message.branch_id,
    ]
    if message.operation_id:
        provenance.append("operation:" + message.operation_id)
    if message.ai_result_id:
        provenance.append("ai-result:" + message.ai_result_id)
    provenance.extend("attachment:" + ref for ref in message.attachment_refs)
    provenance.extend("tool-receipt:" + ref for ref in message.tool_receipt_refs)
    provenance.extend("citation:" + ref for ref in message.citation_refs)
    provenance.extend("artifact:" + ref for ref in message.artifact_refs)

    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "conversation-context:"
            + thread.thread_id
            + ":"
            + message.message_id,
        )
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=kind,
        source_type="conversation",
        source_id=message.message_id,
        content=content,
        trust_level=trust,
        data_class=message.data_class,
        tenant_id=thread.tenant_id,
        purpose=purpose,
        priority=priority,
        relevance=1.0,
        created_at=message.created_at,
        provenance=provenance,
        retention_class="conversation",
        content_ref=message.content_ref,
    )


__all__ = ["conversation_message_segment"]
