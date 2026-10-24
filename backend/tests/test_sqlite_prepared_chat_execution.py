"""Atomic prepared-command storage in the portable conversation reference authority.

A prepared USER must never become visible without the exact frozen engine
command. These tests use a real on-disk SQLite file and no mocked transaction
boundaries; the model admission validator tests metadata content separately.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

import pytest

from skeleton.contracts.conversation import ConversationAuthorType, ConversationMessage
from skeleton.persistence.conversation_repository import (
    ConversationAuthorizationError,
    ConversationConflict,
    ConversationNotFound,
    SQLiteConversationRepository,
)


def _thread(repo):
    return repo.create_thread(
        tenant_id="tenant-a", owner_id="alice", title="Prepared transaction",
        data_class="confidential",
    )


def _user(thread, *, message_id=None, prepared=True):
    return ConversationMessage(
        message_id=message_id or str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=datetime.now(timezone.utc),
        idempotency_key="chat-1",
        content="Produce an approved response.",
        attachment_refs=(
            ("chat-request-sha256:" + "a" * 64,),
            ("chat-request-sha256:" + "a" * 64, "chat-prepared-execution:v1"),
        )[int(prepared)],
        data_class=thread.data_class,
    )


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _metadata(*, request="stable"):
    payload = {
        "schema_version": "backend.ai.chat-execution.v1",
        "request_digest": "a" * 64,
        "command": {"request": request, "version": 1},
        "dependencies": {},
    }
    payload["command_digest"] = _digest(payload["command"])
    payload["record_digest"] = _digest(payload)
    return payload


def test_atomic_prepared_command_survives_restart(tmp_path):
    path = tmp_path / "prepared.sqlite"
    repo = SQLiteConversationRepository(path)
    thread = _thread(repo)
    user = _user(thread)
    prepared = _metadata()
    next_thread, saved = repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=prepared,
    )
    assert next_thread.message_sequence == 1
    assert saved.message_id == user.message_id
    assert repo.chat_execution(
        thread.thread_id, user.message_id, tenant_id="tenant-a", owner_id="alice",
    ) == prepared
    repo.close()

    reopened = SQLiteConversationRepository(path)
    assert reopened.chat_execution(
        thread.thread_id, user.message_id, tenant_id="tenant-a", owner_id="alice",
    ) == prepared
    assert len(reopened.active_transcript(
        thread.thread_id, tenant_id="tenant-a", owner_id="alice",
    )) == 1
    reopened.close()


def test_prepared_command_cannot_be_replaced_or_dropped_under_same_key(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "retry.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    original = _metadata()
    next_thread, _ = repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=original,
    )
    replay_thread, _ = repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=original,
    )
    assert replay_thread.version == next_thread.version
    changed = _metadata(request="changed")
    with pytest.raises(ConversationConflict, match="replayed execution metadata differs"):
        repo.append_message(
            user, tenant_id="tenant-a", owner_id="alice",
            expected_thread_version=thread.version, execution_metadata=changed,
        )
    with pytest.raises(ConversationConflict, match="prepared USER requires"):
        repo.append_message(
            user, tenant_id="tenant-a", owner_id="alice",
            expected_thread_version=thread.version,
        )
    assert repo.chat_execution(
        thread.thread_id, user.message_id, tenant_id="tenant-a", owner_id="alice",
    ) == original
    repo.close()


def test_unprepared_user_remains_legacy_and_cannot_claim_prepared_command(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "legacy.sqlite")
    thread = _thread(repo)
    user = _user(thread, prepared=False)
    with pytest.raises(ConversationConflict, match="prepared execution must"):
        repo.append_message(
            user, tenant_id="tenant-a", owner_id="alice",
            expected_thread_version=thread.version, execution_metadata=_metadata(),
        )
    assert repo.active_transcript(
        thread.thread_id, tenant_id="tenant-a", owner_id="alice",
    ) == ()
    repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version,
    )
    assert repo.chat_execution(
        thread.thread_id, user.message_id, tenant_id="tenant-a", owner_id="alice",
    ) is None
    repo.close()


def test_tampered_command_digest_is_rejected_without_user_commit(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "tamper.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    invalid = {**_metadata(), "command_digest": "f" * 64}
    with pytest.raises(ConversationConflict, match="prepared execution digest differs"):
        repo.append_message(
            user, tenant_id="tenant-a", owner_id="alice",
            expected_thread_version=thread.version,
            execution_metadata=invalid,
        )
    assert repo.active_transcript(
        thread.thread_id, tenant_id="tenant-a", owner_id="alice",
    ) == ()
    repo.close()


def test_mismatched_request_binding_cannot_publish_user(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "request-binding.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    invalid = _metadata()
    invalid["request_digest"] = "f" * 64
    invalid["record_digest"] = _digest({
        key: value for key, value in invalid.items()
        if key != "record_digest"
    })
    with pytest.raises(ConversationConflict, match="request identity differs"):
        repo.append_message(
            user, tenant_id="tenant-a", owner_id="alice",
            expected_thread_version=thread.version,
            execution_metadata=invalid,
        )
    assert repo.active_transcript(
        thread.thread_id, tenant_id="tenant-a", owner_id="alice",
    ) == ()
    repo.close()


def test_invalid_execution_cannot_publish_a_user(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "malformed.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    with pytest.raises(ConversationConflict, match="not canonical JSON"):
        repo.append_message(
            user, tenant_id="tenant-a", owner_id="alice",
            expected_thread_version=thread.version,
            execution_metadata={"invalid": object()},
        )
    assert repo.active_transcript(
        thread.thread_id, tenant_id="tenant-a", owner_id="alice",
    ) == ()
    repo.close()


def test_prepared_command_is_tenant_and_owner_scoped(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "isolation.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=_metadata(),
    )
    with pytest.raises(ConversationAuthorizationError):
        repo.chat_execution(
            thread.thread_id, user.message_id, tenant_id="tenant-a", owner_id="mallory",
        )
    with pytest.raises(ConversationAuthorizationError):
        repo.chat_execution(
            thread.thread_id, user.message_id, tenant_id="tenant-b", owner_id="alice",
        )
    repo.close()


def test_failed_version_cannot_orphan_prepared_command(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "version.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    with pytest.raises(ConversationConflict, match="thread version conflict"):
        repo.append_message(
            user, tenant_id="tenant-a", owner_id="alice",
            expected_thread_version=thread.version + 1, execution_metadata=_metadata(),
        )
    assert repo.active_transcript(
        thread.thread_id, tenant_id="tenant-a", owner_id="alice",
    ) == ()
    with pytest.raises(ConversationNotFound):
        repo.chat_execution(
            thread.thread_id, user.message_id, tenant_id="tenant-a", owner_id="alice",
        )
    repo.close()


def test_selected_history_returns_only_real_prepared_causal_user(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "causal.sqlite")
    thread = _thread(repo)
    message = _user(thread)
    metadata = _metadata()
    repo.append_message(
        message, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=metadata,
    )
    rows = repo.chat_history_dependencies(
        thread.thread_id, {message.message_id},
        tenant_id="tenant-a", owner_id="alice",
    )
    assert len(rows) == 1
    assert rows[0][0].message_id == message.message_id
    assert rows[0][1] == metadata
    assert rows[0][2] is None  # SQLite cannot fabricate legacy engine commands
    assert repo.chat_history_dependencies(
        thread.thread_id, set(), tenant_id="tenant-a", owner_id="alice",
    ) == []
    with pytest.raises(ConversationConflict, match="lineage is incomplete"):
        repo.chat_history_dependencies(
            thread.thread_id, {str(uuid4())}, tenant_id="tenant-a", owner_id="alice",
        )
    with pytest.raises(ConversationAuthorizationError):
        repo.chat_history_dependencies(
            thread.thread_id, {message.message_id},
            tenant_id="tenant-b", owner_id="alice",
        )
    repo.close()


def test_legacy_causal_history_has_no_invented_command(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "legacy-causal.sqlite")
    thread = _thread(repo)
    user = _user(thread, prepared=False)
    repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version,
    )
    rows = repo.chat_history_dependencies(
        thread.thread_id, {user.message_id}, tenant_id="tenant-a", owner_id="alice",
    )
    assert len(rows) == 1 and rows[0][0].message_id == user.message_id
    assert rows[0][1:] == (None, None)
    repo.close()


def test_dispatch_claim_admit_and_cancel_are_original_command_bound(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "dispatch.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    metadata = _metadata()
    repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=metadata,
    )
    args = {
        "tenant_id": "tenant-a", "owner_id": "alice",
        "record_digest": metadata["record_digest"],
    }
    read = repo.chat_dispatch(thread.thread_id, user.message_id, **args)
    assert read == {"state": "ready", "cancel_requested": False}
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **{**args, "record_digest": "f" * 64},
        action="claim",
    ) is None
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args,
    ) == read
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="claim",
    ) == {"state": "submitting", "cancel_requested": False}
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="admitted",
    ) == {"state": "admitted", "cancel_requested": False}
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="cancel",
    ) == {"state": "admitted", "cancel_requested": True}
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="claim",
    ) is None
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args,
    ) == {"state": "admitted", "cancel_requested": True}
    repo.close()


def test_dispatch_cancel_before_claim_withdraws_command(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "withdraw.sqlite")
    thread = _thread(repo)
    user = _user(thread)
    metadata = _metadata()
    repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=metadata,
    )
    args = {
        "tenant_id": "tenant-a", "owner_id": "alice",
        "record_digest": metadata["record_digest"],
    }
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="cancel",
    ) == {"state": "withdrawn", "cancel_requested": True}
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="claim",
    ) is None
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="admitted",
    ) is None
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args,
    ) == {"state": "withdrawn", "cancel_requested": True}
    repo.close()


def test_dispatch_owner_scope_and_restart_custody(tmp_path):
    path = tmp_path / "dispatch-restart.sqlite"
    repo = SQLiteConversationRepository(path)
    thread = _thread(repo)
    user = _user(thread)
    metadata = _metadata()
    repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version, execution_metadata=metadata,
    )
    args = {
        "tenant_id": "tenant-a", "owner_id": "alice",
        "record_digest": metadata["record_digest"],
    }
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="claim",
    ) == {"state": "submitting", "cancel_requested": False}
    with pytest.raises(ConversationAuthorizationError):
        repo.chat_dispatch(
            thread.thread_id, user.message_id,
            tenant_id="tenant-a", owner_id="mallory",
            record_digest=metadata["record_digest"], action="cancel",
        )
    with pytest.raises(ValueError, match="unsupported chat dispatch transition"):
        repo.chat_dispatch(
            thread.thread_id, user.message_id, **args, action="invent",
        )
    repo.close()
    reopened = SQLiteConversationRepository(path)
    assert reopened.chat_dispatch(
        thread.thread_id, user.message_id, **args,
    ) == {"state": "submitting", "cancel_requested": False}
    assert reopened.chat_dispatch(
        thread.thread_id, user.message_id, **args, action="claim",
    ) == {"state": "submitting", "cancel_requested": False}
    reopened.close()


def test_unprepared_legacy_user_has_no_dispatch_custody(tmp_path):
    repo = SQLiteConversationRepository(tmp_path / "legacy-dispatch.sqlite")
    thread = _thread(repo)
    user = _user(thread, prepared=False)
    repo.append_message(
        user, tenant_id="tenant-a", owner_id="alice",
        expected_thread_version=thread.version,
    )
    assert repo.chat_dispatch(
        thread.thread_id, user.message_id,
        tenant_id="tenant-a", owner_id="alice",
        record_digest="a" * 64,
        action="claim",
    ) is None
    repo.close()
