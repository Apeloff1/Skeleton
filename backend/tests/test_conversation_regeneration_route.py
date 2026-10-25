from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from backend.tests.chat_runtime_fixtures import chat_runtime as chat_runtime
from fastapi import HTTPException
from skeleton.contracts.conversation import ConversationAuthorType, ConversationMessage
from skeleton.persistence.conversation_repository import ConversationConflict

from core.engine_client import EngineUnavailableError


class RegenerationAuthority:
    """Add exact request/dispatch fixture records to the SQLite transcript owner."""

    def __init__(self, authority):
        self.authority = authority
        self.records = {}
        self.dispatch = {}
        self.commits = []

    def __getattr__(self, name):
        return getattr(self.authority, name)

    async def authorize_active_thread(self, *args, **kwargs):
        thread = await self.get_thread(*args, **kwargs)
        if not thread.writable:
            raise ConversationConflict("thread is not writable")
        return thread

    async def regeneration_request(self, thread_id, message_id, idempotency_key, *, tenant_id, owner_id):
        await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        return self.records.get((thread_id, message_id, idempotency_key))

    async def bind_regeneration_request(
        self, thread_id, message_id, *, tenant_id, owner_id, expected_thread_version, record
    ):
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        key = (thread_id, message_id, record["idempotency_key"])
        retained = self.records.setdefault(key, record)
        if retained != record:
            raise ConversationConflict("regeneration command identity changed")
        self.dispatch.setdefault(record["record_digest"], {"state": "ready", "cancel_requested": False})
        return retained

    async def regeneration_dispatch_state(self, record, **kwargs):
        return dict(self.dispatch[record["record_digest"]])

    async def transition_regeneration_dispatch(self, record, *, admitted=False, cancel=False, **kwargs):
        state = self.dispatch[record["record_digest"]]
        if cancel:
            state["cancel_requested"] = True
            if state["state"] == "ready":
                state["state"] = "withdrawn"
        elif admitted:
            state["state"] = "admitted"
        elif state["state"] == "ready":
            state["state"] = "submitting"
        return dict(state)

    async def assistant_message_for_operation(self, operation_id, *, tenant_id, owner_id):
        for record in self.records.values():
            messages = self.repository.list_messages(record["thread_id"], tenant_id=tenant_id, owner_id=owner_id)
            for message in messages:
                if message.operation_id == operation_id and message.author_type is ConversationAuthorType.ASSISTANT:
                    return message
        return None

    async def regenerate_assistant_message(self, thread_id, prior_id, **kwargs):
        self.commits.append({"thread_id": thread_id, "prior_id": prior_id, **kwargs})
        thread = await self.get_thread(thread_id, tenant_id=kwargs["tenant_id"], owner_id=kwargs["owner_id"])
        messages = self.repository.list_messages(thread_id, tenant_id=kwargs["tenant_id"], owner_id=kwargs["owner_id"])
        prior = next(message for message in messages if message.message_id == prior_id)
        metadata = {
            name: kwargs[name]
            for name in (
                "operation_id",
                "ai_result_id",
                "context_id",
                "context_digest",
                "context_source_snapshot",
                "context_compiler_version",
                "provider_receipt_refs",
                "tool_receipt_refs",
                "memory_refs",
                "citation_refs",
                "artifact_refs",
            )
        }
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=str(uuid4()),
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=datetime.now(timezone.utc),
            idempotency_key=kwargs["idempotency_key"],
            content=kwargs["content"],
            parent_message_id=prior.causal_user_message_id,
            causal_user_message_id=prior.causal_user_message_id,
            supersedes_message_id=prior_id,
            data_class=thread.data_class,
            **metadata,
        )
        return self.repository.append_message(
            message,
            tenant_id=kwargs["tenant_id"],
            owner_id=kwargs["owner_id"],
            expected_thread_version=kwargs["expected_thread_version"],
            activate_branch=True,
        )


async def _seed(chat_runtime, monkeypatch):
    import routes.conversations as route

    h = chat_runtime
    await h.route.ai_chat(h.request(message="Explain this again."), user=h.user)
    authority = RegenerationAuthority(h.authority)
    monkeypatch.setattr(route, "conversation_authority", authority)
    monkeypatch.setattr(h.route, "conversation_authority", authority)
    return route, authority, h.transcript()


@pytest.mark.asyncio
async def test_regenerate_route_runs_engine_then_commits_new_branch(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (user_message, assistant) = await _seed(h, monkeypatch)
    h.engine.output = "Regenerated verified answer."
    result = await route.regenerate_assistant_message(
        h.thread.thread_id,
        assistant.message_id,
        route.RegenerateMessageRequest(idempotency_key="regen-1", expected_thread_version=3),
        user=h.user,
    )
    assert result["success"] and result["terminal"]
    assert len(h.engine.commands) == 2 and len(authority.commits) == 1
    command = h.engine.commands[-1]
    commit = authority.commits[0]
    assert commit["content"] == "Regenerated verified answer."
    assert commit["ai_result_id"] == "engine-result:" + command.execution_request.execution_id
    assert commit["operation_id"] == command.operation.operation_id
    assert result["regenerated_from"] == assistant.message_id
    assert result["causal_user_message_id"] == user_message.message_id
    assert result["message"]["supersedes_message_id"] == assistant.message_id
    assert result["thread"]["active_branch_id"] != assistant.branch_id
    replay = await route.regenerate_assistant_message(
        h.thread.thread_id,
        assistant.message_id,
        route.RegenerateMessageRequest(idempotency_key="regen-1", expected_thread_version=3),
        user=h.user,
    )
    assert replay["replayed"] and replay["message"] == result["message"]
    assert len(h.engine.commands) == 2 and len(authority.commits) == 1


@pytest.mark.asyncio
async def test_regenerate_route_never_commits_when_engine_unavailable(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (_user_message, assistant) = await _seed(h, monkeypatch)
    h.engine.submit_error = EngineUnavailableError("engine unavailable")
    with pytest.raises(HTTPException) as error:
        await route.regenerate_assistant_message(
            h.thread.thread_id,
            assistant.message_id,
            route.RegenerateMessageRequest(idempotency_key="regen-2", expected_thread_version=3),
            user=h.user,
        )
    assert error.value.status_code == 503
    assert authority.commits == [] and len(h.transcript()) == 2
    (record,) = authority.records.values()
    assert record["command"] == h.engine.commands[-1].as_dict()


@pytest.mark.asyncio
async def test_regenerate_route_rejects_user_message_source(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (user_message, _assistant) = await _seed(h, monkeypatch)
    with pytest.raises(HTTPException) as error:
        await route.regenerate_assistant_message(
            h.thread.thread_id,
            user_message.message_id,
            route.RegenerateMessageRequest(idempotency_key="regen-user", expected_thread_version=3),
            user=h.user,
        )
    assert error.value.status_code == 409
    assert "only causal assistant messages" in error.value.detail
    assert len(h.engine.commands) == 1 and authority.records == {}


@pytest.mark.asyncio
async def test_regenerate_route_rejects_stale_version_before_engine_resolution(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (_user_message, assistant) = await _seed(h, monkeypatch)

    def forbidden_engine():
        raise AssertionError("stale request must fail before engine configuration")

    monkeypatch.setattr(h.route.EngineClient, "from_env", forbidden_engine)
    with pytest.raises(HTTPException) as error:
        await route.regenerate_assistant_message(
            h.thread.thread_id,
            assistant.message_id,
            route.RegenerateMessageRequest(idempotency_key="regen-stale", expected_thread_version=2),
            user=h.user,
        )
    assert error.value.status_code == 409 and error.value.detail == "thread version conflict"
    assert authority.records == {} and authority.commits == []
