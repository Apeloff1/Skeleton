"""Regression coverage for exact-owner chat preparation and replay recovery.

Prepared execution reads must use the same canonical conversation authority
that admitted the user turn; a split database may never supply its command.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.chat_sessions import read_prepared
from core.engine_client import EngineProtocolError


def _user(*, prepared: bool = False):
    refs = ("chat-request-sha256:" + ("1" * 64),)
    if prepared:
        refs += ("chat-prepared-execution:v1",)
    return SimpleNamespace(message_id="user-1", attachment_refs=refs)


def _thread():
    return SimpleNamespace(thread_id="thread-1")


@pytest.mark.asyncio
async def test_prepared_lookup_uses_explicit_admission_owner() -> None:
    hits = []

    async def refs(thread_id, message_id, *, tenant_id, owner_id):
        hits.append(("refs", thread_id, message_id, tenant_id, owner_id))
        return _user().attachment_refs

    async def execution(thread_id, message_id, *, tenant_id, owner_id):
        hits.append(("execution", thread_id, message_id, tenant_id, owner_id))
        return None

    owner = SimpleNamespace(user_request_refs=refs, chat_execution=execution)
    metadata, command = await read_prepared(
        authority=owner,
        thread=_thread(),
        user_message=_user(),
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert metadata is None and command is None
    assert hits == [
        ("refs", "thread-1", "user-1", "tenant-a", "owner-a"),
        ("execution", "thread-1", "user-1", "tenant-a", "owner-a"),
    ]


@pytest.mark.asyncio
async def test_prepared_marker_with_missing_command_fails_closed() -> None:
    async def execution(*_args, **_kwargs):
        return None

    owner = SimpleNamespace(chat_execution=execution)
    with pytest.raises(EngineProtocolError, match="prepared chat command is missing"):
        await read_prepared(
            authority=owner,
            thread=_thread(),
            user_message=_user(prepared=True),
            tenant_id="tenant-a",
            owner_id="owner-a",
        )


@pytest.mark.asyncio
async def test_request_ref_storage_failure_is_not_silently_fallbacked() -> None:
    async def unavailable(*_args, **_kwargs):
        raise OSError("simulated authoritative storage outage")

    owner = SimpleNamespace(user_request_refs=unavailable)
    with pytest.raises(OSError, match="authoritative storage outage"):
        await read_prepared(
            authority=owner,
            thread=_thread(),
            user_message=_user(),
            tenant_id="tenant-a",
            owner_id="owner-a",
        )


@pytest.mark.asyncio
async def test_reference_repository_can_use_immutable_message_refs() -> None:
    """SQLite-like owners can persist refs on the signed canonical message."""
    owner = SimpleNamespace()
    metadata, command = await read_prepared(
        authority=owner,
        thread=_thread(),
        user_message=_user(),
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert metadata is None and command is None
