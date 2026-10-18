"""Replay identity must remain persisted and fail closed across authorities."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from routes.ai import _user_request_refs_for_replay


@pytest.mark.asyncio
async def test_sqlite_style_message_refs_are_used_when_lookup_is_absent():
    thread_id, message_id = str(uuid4()), str(uuid4())
    stored = SimpleNamespace(
        message_id=message_id,
        attachment_refs=("chat-request-sha256:" + "a" * 64,),
    )
    assert await _user_request_refs_for_replay(
        SimpleNamespace(),
        stored,
        thread_id=thread_id,
        tenant_id="tenant",
        owner_id="owner",
    ) == stored.attachment_refs


@pytest.mark.asyncio
async def test_authoritative_lookup_takes_precedence_over_embedded_refs():
    observed = {}

    async def user_request_refs(thread_id, message_id, *, tenant_id, owner_id):
        observed.update(
            thread_id=thread_id,
            message_id=message_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        return ["chat-request-sha256:" + "b" * 64]

    stored = SimpleNamespace(
        message_id=str(uuid4()),
        attachment_refs=("chat-request-sha256:" + "a" * 64,),
    )
    thread_id = str(uuid4())
    refs = await _user_request_refs_for_replay(
        SimpleNamespace(user_request_refs=user_request_refs),
        stored,
        thread_id=thread_id,
        tenant_id="tenant",
        owner_id="owner",
    )
    assert refs == ("chat-request-sha256:" + "b" * 64,)
    assert observed == dict(
        thread_id=thread_id,
        message_id=stored.message_id,
        tenant_id="tenant",
        owner_id="owner",
    )


@pytest.mark.asyncio
async def test_authoritative_storage_failure_never_uses_stale_message_refs():
    async def user_request_refs(*args, **kwargs):
        raise OSError("stored request metadata unavailable")

    with pytest.raises(OSError, match="stored request metadata unavailable"):
        await _user_request_refs_for_replay(
            SimpleNamespace(user_request_refs=user_request_refs),
            SimpleNamespace(
                message_id=str(uuid4()),
                attachment_refs=("chat-request-sha256:" + "a" * 64,),
            ),
            thread_id=str(uuid4()),
            tenant_id="tenant",
            owner_id="owner",
        )


@pytest.mark.asyncio
async def test_missing_identity_is_not_synthesized_from_incoming_request():
    refs = await _user_request_refs_for_replay(
        SimpleNamespace(),
        SimpleNamespace(message_id=str(uuid4()), attachment_refs=()),
        thread_id=str(uuid4()),
        tenant_id="tenant",
        owner_id="owner",
    )
    assert refs == ()
