from __future__ import annotations

import hashlib
from uuid import uuid4


def test_chat_binds_ephemeral_context_digest_into_user_idempotency():
    """Inspect real admission references, not a pre-engine legacy mock append."""
    import routes.ai as ai

    request = ai.AIChatRequest(
        message="question",
        thread_id=str(uuid4()),
        idempotency_key="stable-key",
        expected_thread_version=1,
        context="same ephemeral code",
    )
    digest = ai._chat_request_digest(request)
    refs = ai._chat_context_attachment_refs(request, digest, include_prepared=True)
    expected_context = hashlib.sha256(b"same ephemeral code").hexdigest()

    assert refs == (
        "ephemeral-context-sha256:" + expected_context,
        "chat-request-sha256:" + digest,
        "chat-prepared-execution:v1",
    )
    assert ai._chat_request_identity_ref(request) == refs[1]
    changed = request.model_copy(update={"context": "different ephemeral code"})
    assert ai._chat_request_digest(changed) != digest
    assert ai._chat_context_attachment_refs(
        changed, ai._chat_request_digest(changed), include_prepared=True
    ) != refs

    # For legacy stored turns, the prepared-execution marker is not fabricated.
    assert ai._chat_context_attachment_refs(
        request, digest, include_prepared=False
    ) == refs[:2]



def test_chat_request_identity_binds_context_and_memory_policy_but_not_thread_version():

    import routes.ai as ai

    base = ai.AIChatRequest(
        message="question",
        thread_id=str(uuid4()),
        idempotency_key="stable-key",
        expected_thread_version=1,
        context="same ephemeral code",
        memory_policy=ai.AIChatMemoryPolicy(
            persist_verified_response=True,
            kind="semantic",
            namespace="assistant",
        ),
    )
    stale_retry = ai.AIChatRequest(
        message=base.message,
        thread_id=base.thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=99,
        context=base.context,
        memory_policy=base.memory_policy,
    )
    changed_context = ai.AIChatRequest(
        message=base.message,
        thread_id=base.thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=1,
        context="different ephemeral code",
        memory_policy=base.memory_policy,
    )
    changed_policy = ai.AIChatRequest(
        message=base.message,
        thread_id=base.thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=1,
        context=base.context,
        memory_policy=ai.AIChatMemoryPolicy(
            persist_verified_response=False,
            kind="semantic",
            namespace="assistant",
        ),
    )

    identity = ai._chat_request_identity_ref(base)
    assert identity == ai._chat_request_identity_ref(stale_retry)
    assert identity != ai._chat_request_identity_ref(changed_context)
    assert identity != ai._chat_request_identity_ref(changed_policy)
    assert identity.startswith("chat-request-sha256:")
