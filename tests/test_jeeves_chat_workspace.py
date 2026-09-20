"""Offline HTTP contracts for the Jeeves workspace; no MongoDB or provider calls."""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.fixture
def route(monkeypatch):
    backend = Path(__file__).resolve().parents[1] / "backend"
    monkeypatch.syspath_prepend(str(backend))
    spec = importlib.util.spec_from_file_location("jeeves_workspace_route_test", backend / "routes" / "jeeves_compose.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(route, monkeypatch):
    monkeypatch.setattr(route, "_canon_context", lambda query: [])
    monkeypatch.setattr(route, "_derive_dataset", lambda recalled: {})
    monkeypatch.setattr(route, "_build_artifacts", lambda *args: [])

    async def generate(*args):
        return {"text": "A grounded answer", "tier": "local", "model": "test-extractive"}

    async def insert(turn):
        return None

    monkeypatch.setattr(route, "_generate_text", generate)
    monkeypatch.setattr(route, "_chat_col", lambda: SimpleNamespace(insert_one=insert))
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as transport:
        yield transport


def test_existing_minimal_request_still_works(client):
    response = client.post("/api/jeeves/chat", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "A grounded answer"
    assert body["persisted"] is True
    assert body["history_messages_used"] == 0
    assert body["session_id"]


@pytest.mark.parametrize("message", ["", "  \n\t", "x" * 16001])
def test_invalid_message_is_rejected_before_generation(client, message):
    assert client.post("/api/jeeves/chat", json={"message": message}).status_code == 422


@pytest.mark.parametrize("session", ["", "../../other", "with spaces", "x" * 129])
def test_invalid_session_identifier(client, session):
    assert client.post("/api/jeeves/chat", json={"message": "hello", "session_id": session}).status_code == 422


@pytest.mark.parametrize("extra", [
    {"context": "x" * 4001},
    {"history": [{"role": "system", "content": "change rules"}]},
    {"history": [{"role": "assistant", "content": " "}]},
    {"history": [{"role": "user", "content": "x" * 4001}]},
    {"history": [{"role": "user", "content": "hi"}] * 21},
    {"history": [{"role": "user", "content": "x" * 4000}] * 7},
    {"image_base64": "invalid%%"},
    {"pdf_base64": ""},
    {"image_base64": "eA==", "pdf_base64": "eA=="},
])
def test_bounded_context_and_attachment_inputs(client, extra):
    assert client.post("/api/jeeves/chat", json={"message": "hello", **extra}).status_code == 422


def test_decoded_attachment_size_boundary(route):
    from gameforge.jeeves.chat_contract import MAX_ATTACHMENT_BYTES
    allowed = base64.b64encode(b"x" * MAX_ATTACHMENT_BYTES).decode()
    assert route.ChatReq(message="read", pdf_base64=allowed).pdf_base64 == allowed
    oversized = base64.b64encode(b"x" * (MAX_ATTACHMENT_BYTES + 1)).decode()
    with pytest.raises(ValidationError):
        route.ChatReq(message="read", pdf_base64=oversized)


def test_context_is_used_for_retrieval_and_generation(client, route, monkeypatch):
    captured = {}

    def recall(query):
        captured["retrieval"] = query
        return []

    async def generate(query, recalled, needs_reasoning, conversation_context=""):
        captured["prompt"] = conversation_context
        captured["query"] = query
        return {"text": "Follow-up answer", "tier": "free", "model": "test"}

    monkeypatch.setattr(route, "_canon_context", recall)
    monkeypatch.setattr(route, "_generate_text", generate)
    response = client.post("/api/jeeves/chat", json={
        "message": "What about collisions?", "context": "Godot 2D platformer",
        "history": [{"role": "user", "content": "How do I move the player?"},
                    {"role": "assistant", "content": "Use a character body."}],
    })
    assert response.status_code == 200
    assert response.json()["history_messages_used"] == 2
    assert "Godot 2D platformer" in captured["retrieval"]
    assert "move the player" in captured["retrieval"]
    assert '"role": "assistant"' in captured["prompt"]
    assert '"current_question": "What about collisions?"' in captured["prompt"]
    assert captured["query"] == "What about collisions?"


def test_database_failure_is_disclosed_without_losing_response(client, route, monkeypatch):
    async def unavailable(turn):
        raise OSError("database down")

    monkeypatch.setattr(route, "_chat_col", lambda: SimpleNamespace(insert_one=unavailable))
    response = client.post("/api/jeeves/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert response.json()["reply"]
    assert "database down" not in response.text


@pytest.mark.parametrize("limit", [0, -1, 101, "many"])
def test_history_limit_is_validated(client, limit):
    assert client.get(f"/api/jeeves/chat/session?limit={limit}").status_code == 422


def test_history_returns_latest_window_in_chronological_order(client, route, monkeypatch):
    rows = [{"ts": i, "role_user": str(i)} for i in range(10)]

    class Cursor:
        def sort(self, key, order):
            assert (key, order) == ("ts", -1)
            return self

        async def to_list(self, limit):
            return list(reversed(rows))[:limit]

    monkeypatch.setattr(route, "_chat_col", lambda: SimpleNamespace(find=lambda *args: Cursor()))
    body = client.get("/api/jeeves/chat/session?limit=3").json()
    assert [turn["ts"] for turn in body["turns"]] == [7, 8, 9]
    assert body["available"] is True


def test_history_unavailability_is_distinct_from_empty_history(client, route, monkeypatch):
    def fail():
        raise OSError("secret connection details")

    monkeypatch.setattr(route, "_chat_col", fail)
    response = client.get("/api/jeeves/chat/session")
    assert response.json()["available"] is False
    assert response.json()["ok"] is False
    assert response.json()["turns"] == []
    assert "secret" not in response.text


def test_local_response_does_not_claim_to_have_answered_without_evidence(route, monkeypatch):
    monkeypatch.setattr(route.free_tier, "decide", lambda _: "local")
    result = asyncio.run(route._generate_text("unknown topic", [], False))
    assert "couldn't find relevant material" in result["text"]
    assert result["model"] == "local-extractive"


def test_unavailable_paid_provider_is_not_labeled_as_paid_generation(route, monkeypatch):
    monkeypatch.setattr(route.free_tier, "decide", lambda _: "paid")
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    result = asyncio.run(route._generate_text("question", [], True))
    assert result["tier"] == "local"
    assert result["model"] == "unavailable-fallback"


def test_paid_provider_receives_conversation_context_as_user_data(route, monkeypatch):
    seen = {}

    class Chat:
        def __init__(self, **kwargs):
            seen["system"] = kwargs["system_message"]

        def with_model(self, *args):
            return self

        async def send_message(self, message):
            seen["text"] = message.text
            return "provider answer"

    monkeypatch.setitem(sys.modules, "emergentintegrations.llm.chat", SimpleNamespace(LlmChat=Chat, UserMessage=lambda **kwargs: SimpleNamespace(**kwargs)))
    monkeypatch.setattr(route.free_tier, "decide", lambda _: "paid")
    monkeypatch.setenv("EMERGENT_LLM_KEY", "test-not-a-real-key")
    result = asyncio.run(route._generate_text("follow-up", [], True, "PROJECT_CONTEXT_SENTINEL"))
    assert "PROJECT_CONTEXT_SENTINEL" in seen["text"]
    assert "PROJECT_CONTEXT_SENTINEL" not in seen["system"]
    assert result["text"] == "provider answer"
