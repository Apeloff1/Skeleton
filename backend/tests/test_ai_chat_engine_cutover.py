from __future__ import annotations

import pytest
from backend.tests.chat_runtime_fixtures import chat_http_client as chat_http_client
from backend.tests.chat_runtime_fixtures import chat_runtime as chat_runtime
from fastapi import HTTPException

from core.engine_client import EngineUnavailableError


def test_configured_chat_routes_through_engine_and_commits_engine_lineage(chat_runtime, chat_http_client, monkeypatch):
    h = chat_runtime

    async def forbidden_legacy(*args, **kwargs):
        raise AssertionError("backend provider must not execute")

    monkeypatch.setattr(h.route, "call_llm", forbidden_legacy)
    response = chat_http_client.post("/ai/chat", json=h.request().model_dump(mode="json"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["success"] and result["provider"] == "skeleton-engine"
    command = h.engine.commands[0]
    assistant = h.transcript()[-1]
    assert assistant.operation_id == command.operation.operation_id
    assert assistant.ai_result_id == "engine-result:" + command.execution_request.execution_id
    assert assistant.provider_receipt_refs == h.engine.provider_receipts
    assert command.operation.tenant_id == "tenant-a" and command.operation.actor_id == "owner-a"
    assert command.operation.capability == "assistant.chat"
    assert command.execution_request.context_policy["verification_profile"] == "assistant_proposal"
    assert command.delegated_authority.service_principal == "codedock-backend"
    assert command.compiled_context.context_id == result["context"]["context_id"]
    assert command.compiled_context.context_digest == result["context"]["context_digest"]
    assert "conversation:" + h.thread.thread_id in command.context_seed_refs
    assert command.compiled_context.prompt == h.request().message
    assert "memory_write_intent" not in command.execution_request.context_policy
    assert "engine:memory" not in command.delegated_authority.scopes
    assert result["model"] == "engine-routed" and result["provider_request_id"] is None
    assert result["engine_execution_id"] == command.execution_request.execution_id


@pytest.mark.asyncio
async def test_configured_engine_outage_never_falls_back_to_backend_provider(chat_runtime, monkeypatch):
    h = chat_runtime

    async def forbidden_legacy(*args, **kwargs):
        raise AssertionError("engine outage must not activate backend provider")

    monkeypatch.setattr(h.route, "call_llm", forbidden_legacy)
    h.engine.submit_error = EngineUnavailableError("offline")
    result = await h.route.ai_chat(h.request(), user=h.user)
    assert result["success"] is False
    assert len(h.transcript()) == 1


@pytest.mark.asyncio
async def test_explicit_chat_memory_policy_delegates_verified_memory_and_commits_refs(chat_runtime):
    h = chat_runtime
    h.engine.memory_refs = ("memory:canonical-1",)
    result = await h.route.ai_chat(
        h.request(
            memory_policy={
                "persist_verified_response": True,
                "kind": "semantic",
                "namespace": "assistant",
            }
        ),
        user=h.user,
    )
    assert result["success"]
    command = h.engine.commands[0]
    assert "engine:memory" in command.delegated_authority.scopes
    intent = command.execution_request.context_policy["memory_write_intent"]
    assert intent["subject_id"] == "owner-a" and intent["content_from"] == "verified_final_output"
    assert h.transcript()[-1].memory_refs == h.engine.memory_refs
    assert result["engine_memory_refs"] == list(h.engine.memory_refs)


@pytest.mark.asyncio
async def test_memory_opt_in_without_canonical_engine_fails_closed(chat_runtime, monkeypatch):
    h = chat_runtime
    monkeypatch.setattr(h.route.EngineClient, "from_env", lambda: None)
    with pytest.raises(HTTPException) as error:
        await h.route.ai_chat(h.request(memory_policy={"persist_verified_response": True}), user=h.user)
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "engine_unavailable"
    assert h.transcript() == ()


@pytest.mark.asyncio
async def test_replayed_chat_preserves_local_provider_provenance_without_engine_call(chat_runtime, monkeypatch):
    h = chat_runtime
    h.engine.provider_receipts = ("provider:local:response-1",)
    first = await h.route.ai_chat(h.request(), user=h.user)
    monkeypatch.setattr(h.route.EngineClient, "from_env", lambda: None)
    replay = await h.route.ai_chat(h.request(), user=h.user)
    assert replay["replayed"]
    assert replay["engine_runtime_provider"] == "local"
    assert replay["engine_provider_receipts"] == first["engine_provider_receipts"]
    assert len(h.engine.commands) == 1
