"""Offline HTTP contracts for the Jeeves workspace; no MongoDB or provider calls."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationNotFound,
)


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

    async def generate(*args, **kwargs):
        del args, kwargs
        return {
            "text": "A grounded answer",
            "tier": "local",
            "model": "test-extractive",
        }

    legacy = _MemoryChatCollection()
    canonical = _CanonicalConversationAuthority()
    monkeypatch.setattr(route, "_generate_text", generate)
    monkeypatch.setattr(route, "_chat_col", lambda: legacy)
    monkeypatch.setattr(route, "_canonical_authority", lambda: canonical)
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


def test_client_history_is_ignored_but_project_context_is_used(
    client,
    route,
    monkeypatch,
):
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
    assert response.json()["history_messages_used"] == 0
    assert response.json()["history_source"] == "canonical"
    assert "Godot 2D platformer" in captured["retrieval"]
    assert "move the player" not in captured["retrieval"]
    assert '"role": "assistant"' not in captured["prompt"]
    assert '"current_question": "What about collisions?"' in captured["prompt"]
    assert captured["query"] == "What about collisions?"


def test_retired_legacy_store_failure_does_not_block_canonical_chat(
    client,
    route,
    monkeypatch,
):
    def unavailable():
        raise OSError("legacy database down")

    monkeypatch.setattr(route, "_chat_col", unavailable)
    response = client.post("/api/jeeves/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["persisted"] is True
    assert response.json()["history_source"] == "canonical"
    assert response.json()["reply"]
    assert "database down" not in response.text


@pytest.mark.parametrize("limit", [0, -1, 101, "many"])
def test_history_limit_is_validated(client, limit):
    assert client.get(f"/api/jeeves/chat/session?limit={limit}").status_code == 422


def test_history_returns_latest_canonical_window_in_order(
    client,
    route,
    monkeypatch,
):
    rows = [
        {
            "session_id": "session",
            "client_message_id": f"legacy-{i}",
            "role_user": f"question-{i}",
            "role_jeeves": f"answer-{i}",
            "status": "complete",
            "ts": float(i),
        }
        for i in range(10)
    ]
    monkeypatch.setattr(
        route,
        "_chat_col",
        lambda: _MemoryChatCollection(rows),
    )
    body = client.get("/api/jeeves/chat/session?limit=3").json()
    assert [turn["role_user"] for turn in body["turns"]] == [
        "question-7",
        "question-8",
        "question-9",
    ]
    assert body["available"] is True
    assert body["history_source"] == "canonical"


def test_retired_legacy_history_unavailability_keeps_empty_canonical_history_available(
    client,
    route,
    monkeypatch,
):
    def fail():
        raise OSError("secret legacy connection details")

    monkeypatch.setattr(route, "_chat_col", fail)
    response = client.get("/api/jeeves/chat/session")
    assert response.json()["available"] is True
    assert response.json()["ok"] is True
    assert response.json()["turns"] == []
    assert response.json()["history_source"] == "canonical"
    assert "secret" not in response.text


def test_local_response_does_not_claim_to_have_answered_without_evidence(route, monkeypatch):
    monkeypatch.setattr(route.free_tier, "decide", lambda _: "local")
    result = asyncio.run(route._generate_text("unknown topic", [], False))
    assert "couldn't find relevant material" in result["text"]
    assert result["model"] == "local-extractive"


def test_unavailable_paid_engine_is_not_labeled_as_paid_generation(
    route,
    monkeypatch,
):
    class UnavailableChat:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def with_max_tokens(self, _value):
            return self

        async def send_message(self, _message):
            raise route.EngineTextError("engine unavailable")

    monkeypatch.setattr(route.free_tier, "decide", lambda _: "paid")
    monkeypatch.setattr(route, "EngineChat", UnavailableChat)

    result = asyncio.run(route._generate_text("question", [], True))

    assert result["tier"] == "local"
    assert result["model"] == "unavailable-fallback"


def test_paid_generation_uses_engine_and_keeps_context_as_user_data(
    route,
    monkeypatch,
):
    seen = {}

    class RecordingChat:
        def __init__(self, *args, **kwargs):
            seen["init"] = {"args": args, **kwargs}

        def with_max_tokens(self, value):
            seen["max_tokens"] = value
            return self

        async def send_message(self, message):
            seen["message"] = message
            return SimpleNamespace(
                text="engine answer",
                execution_id="engine-exec-jeeves-1",
                verification="verification:jeeves",
                evidence_refs=("evidence:jeeves",),
            )

    monkeypatch.setattr(route.free_tier, "decide", lambda _: "paid")
    monkeypatch.setattr(route, "EngineChat", RecordingChat)

    result = asyncio.run(
        route._generate_text(
            "follow-up",
            [],
            True,
            "PROJECT_CONTEXT_SENTINEL",
        )
    )

    assert "PROJECT_CONTEXT_SENTINEL" in seen["message"].text
    policy = seen["init"]["instruction_policy"]
    assert "PROJECT_CONTEXT_SENTINEL" not in policy.instructions
    assert policy.policy_id == "backend.jeeves.chat"
    assert policy.version == "1"
    assert seen["init"]["actor_id"] == "jeeves-compose"
    assert seen["init"]["capability"] == "assistant.compat"
    assert seen["max_tokens"] == 8_192
    assert result["text"] == "engine answer"
    assert result["tier"] == "paid"
    assert result["model"] == "skeleton-engine"
    assert result["engine_execution_id"] == "engine-exec-jeeves-1"
    assert result["engine_verification"] == "verification:jeeves"
    assert result["engine_evidence_refs"] == ["evidence:jeeves"]



class _MemoryChatCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.key = "ts"
        self.order = -1

    def sort(self, key, order):
        self.key = key
        self.order = order
        return self

    async def to_list(self, limit):
        rows = sorted(
            self.rows,
            key=lambda item: item.get(self.key, 0),
            reverse=self.order < 0,
        )
        return [dict(item) for item in rows[:limit]]


class _MemoryChatCollection:
    def __init__(self, rows=None):
        self.rows = [dict(row) for row in rows or []]
        self._counter = 0

    @staticmethod
    def _matches(row, query):
        if "_id" in query and row.get("_id") != query["_id"]:
            return False
        if "session_id" in query and row.get("session_id") != query["session_id"]:
            return False
        if "status" in query and isinstance(query["status"], str):
            if row.get("status") != query["status"]:
                return False
        if "legacy_history.0" in query:
            history = row.get("legacy_history")
            if not isinstance(history, list) or not history:
                return False
        if "$or" in query:
            allowed = False
            for option in query["$or"]:
                if option.get("status") == "complete" and row.get("status") == "complete":
                    allowed = True
                exists = option.get("status", {}).get("$exists") if isinstance(option.get("status"), dict) else None
                if exists is False and "status" not in row:
                    allowed = True
            if not allowed:
                return False
        return True

    async def insert_one(self, document):
        row = dict(document)
        if "_id" not in row:
            self._counter += 1
            row["_id"] = f"auto-{self._counter}"
        if any(existing.get("_id") == row["_id"] for existing in self.rows):
            raise RuntimeError("duplicate key")
        self.rows.append(row)
        return SimpleNamespace(inserted_id=row["_id"])

    async def find_one(self, query, projection=None):
        del projection
        for row in self.rows:
            if self._matches(row, query):
                return dict(row)
        return None

    def find(self, query, projection=None):
        del projection
        return _MemoryChatCursor(
            row for row in self.rows if self._matches(row, query)
        )

    async def update_one(self, query, update):
        for row in self.rows:
            if self._matches(row, query):
                row.update(dict(update.get("$set") or {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


def _chat_client(
    route,
    monkeypatch,
    collection,
    generate,
    *,
    canonical=None,
):
    canonical = canonical or _CanonicalConversationAuthority()
    monkeypatch.setattr(route, "_chat_col", lambda: collection)
    monkeypatch.setattr(route, "_canonical_authority", lambda: canonical)
    monkeypatch.setattr(route, "_canon_context", lambda query: [])
    monkeypatch.setattr(route, "_derive_dataset", lambda recalled: {})
    monkeypatch.setattr(route, "_build_artifacts", lambda *args: [])
    monkeypatch.setattr(route, "_generate_text", generate)
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


def test_server_transcript_overrides_conflicting_client_history(route, monkeypatch):
    collection = _MemoryChatCollection([
        {
            "_id": "existing-turn",
            "session_id": "conversation-1",
            "role_user": "SERVER QUESTION",
            "role_jeeves": "SERVER ANSWER",
            "status": "complete",
            "ts": 1.0,
        }
    ])
    captured = {}

    async def generate(query, recalled, needs_reasoning, conversation_context=""):
        captured["context"] = conversation_context
        return {"text": "next answer", "tier": "free", "model": "test"}

    with _chat_client(route, monkeypatch, collection, generate) as transport:
        response = transport.post(
            "/api/jeeves/chat",
            json={
                "session_id": "conversation-1",
                "client_message_id": "message-2",
                "message": "follow up",
                "history": [
                    {"role": "user", "content": "CLIENT FAKE"},
                    {"role": "assistant", "content": "CLIENT FAKE ANSWER"},
                ],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["history_source"] == "canonical"
    assert body["history_messages_used"] == 2
    assert "SERVER QUESTION" in captured["context"]
    assert "SERVER ANSWER" in captured["context"]
    assert "CLIENT FAKE" not in captured["context"]


def test_stable_client_message_id_replays_without_second_generation(route, monkeypatch):
    collection = _MemoryChatCollection()
    calls = {"count": 0}

    async def generate(query, recalled, needs_reasoning, conversation_context=""):
        calls["count"] += 1
        return {"text": "stable answer", "tier": "free", "model": "test"}

    payload = {
        "session_id": "conversation-1",
        "client_message_id": "message-1",
        "message": "hello",
    }
    with _chat_client(route, monkeypatch, collection, generate) as transport:
        first = transport.post("/api/jeeves/chat", json=payload)
        second = transport.post("/api/jeeves/chat", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["reply"] == "stable answer"
    assert calls["count"] == 1


def test_client_message_id_conflict_is_rejected(route, monkeypatch):
    collection = _MemoryChatCollection()

    async def generate(query, recalled, needs_reasoning, conversation_context=""):
        return {"text": "stable answer", "tier": "free", "model": "test"}

    with _chat_client(route, monkeypatch, collection, generate) as transport:
        first = transport.post(
            "/api/jeeves/chat",
            json={
                "session_id": "conversation-1",
                "client_message_id": "message-1",
                "message": "first content",
            },
        )
        conflict = transport.post(
            "/api/jeeves/chat",
            json={
                "session_id": "conversation-1",
                "client_message_id": "message-1",
                "message": "different content",
            },
        )

    assert first.status_code == 200
    assert conflict.status_code == 409


def test_legacy_history_is_never_model_visible_or_persisted(
    route,
    monkeypatch,
):
    collection = _MemoryChatCollection()
    contexts = []

    async def generate(query, recalled, needs_reasoning, conversation_context=""):
        contexts.append(conversation_context)
        return {
            "text": f"answer-{len(contexts)}",
            "tier": "free",
            "model": "test",
        }

    with _chat_client(route, monkeypatch, collection, generate) as transport:
        first = transport.post(
            "/api/jeeves/chat",
            json={
                "session_id": "conversation-1",
                "client_message_id": "message-1",
                "message": "new question",
                "history": [
                    {"role": "user", "content": "legacy question"},
                    {"role": "assistant", "content": "legacy answer"},
                ],
            },
        )
        second = transport.post(
            "/api/jeeves/chat",
            json={
                "session_id": "conversation-1",
                "client_message_id": "message-2",
                "message": "next question",
                "history": [
                    {"role": "user", "content": "tampered replacement"},
                ],
            },
        )

    assert first.status_code == 200
    assert first.json()["history_source"] == "canonical"
    assert contexts[0] == ""
    assert all("legacy_history" not in row for row in collection.rows)

    assert second.status_code == 200
    assert second.json()["history_source"] == "canonical"
    assert "new question" in contexts[1]
    assert "answer-1" in contexts[1]
    assert "legacy question" not in contexts[1]
    assert "legacy answer" not in contexts[1]
    assert "tampered replacement" not in contexts[1]


def test_client_history_is_ignored_when_legacy_migration_store_is_unavailable(
    route,
    monkeypatch,
):
    captured = {}
    canonical = _CanonicalConversationAuthority()

    def unavailable_collection():
        raise OSError("legacy storage unavailable")

    async def generate(query, recalled, needs_reasoning, conversation_context=""):
        captured["context"] = conversation_context
        return {"text": "canonical", "tier": "free", "model": "test"}

    monkeypatch.setattr(route, "_chat_col", unavailable_collection)
    monkeypatch.setattr(route, "_canonical_authority", lambda: canonical)
    monkeypatch.setattr(route, "_canon_context", lambda query: [])
    monkeypatch.setattr(route, "_derive_dataset", lambda recalled: {})
    monkeypatch.setattr(route, "_build_artifacts", lambda *args: [])
    monkeypatch.setattr(route, "_generate_text", generate)
    app = FastAPI()
    app.include_router(route.router)

    with TestClient(app) as transport:
        response = transport.post(
            "/api/jeeves/chat",
            json={
                "session_id": "conversation-2",
                "message": "current question",
                "history": [
                    {"role": "user", "content": "ATTACKER HISTORY"},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["history_source"] == "canonical"
    assert response.json()["persisted"] is True
    assert captured["context"] == ""
    assert "ATTACKER HISTORY" not in response.text



class _CanonicalConversationAuthority:
    def __init__(self):
        self.threads = {}
        self.messages = {}

    async def get_thread(self, thread_id, *, tenant_id, owner_id):
        thread = self.threads.get(thread_id)
        if (
            thread is None
            or thread.tenant_id != tenant_id
            or thread.owner_id != owner_id
        ):
            raise ConversationNotFound(thread_id)
        return thread

    async def create_thread(
        self,
        *,
        tenant_id,
        owner_id,
        title,
        data_class,
        thread_id,
        branch_id,
    ):
        if thread_id in self.threads:
            raise ConversationConflict("thread identity already exists")
        now = datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc)
        thread = ConversationThread(
            thread_id=thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
            version=1,
            message_sequence=0,
            active_branch_id=branch_id,
            state=ConversationThreadState.ACTIVE,
            title=title,
            data_class=data_class,
        )
        self.threads[thread_id] = thread
        self.messages[thread_id] = []
        return thread

    async def active_transcript(self, thread_id, *, tenant_id, owner_id):
        await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        return tuple(
            sorted(
                self.messages.get(thread_id, []),
                key=lambda item: item.sequence,
            )
        )

    def _existing(self, thread_id, idempotency_key):
        return next(
            (
                message
                for message in self.messages.get(thread_id, [])
                if message.idempotency_key == idempotency_key
            ),
            None,
        )

    async def append_user_message(
        self,
        thread_id,
        *,
        tenant_id,
        owner_id,
        content,
        idempotency_key,
        expected_thread_version,
        data_class,
        **_kwargs,
    ):
        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        existing = self._existing(thread_id, idempotency_key)
        if existing is not None:
            if (
                existing.author_type is not ConversationAuthorType.USER
                or existing.content != content
            ):
                raise ConversationConflict(
                    "idempotency_key was reused with different content"
                )
            return thread, existing
        if thread.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.USER,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
            content=content,
            data_class=data_class,
        )
        updated = replace(
            thread,
            version=thread.version + 1,
            message_sequence=message.sequence,
            updated_at=message.created_at,
        )
        self.threads[thread_id] = updated
        self.messages[thread_id].append(message)
        return updated, message

    async def commit_assistant_message(
        self,
        thread_id,
        *,
        tenant_id,
        owner_id,
        content,
        idempotency_key,
        expected_thread_version,
        causal_user_message_id,
        operation_id,
        ai_result_id,
        data_class,
        citation_refs=(),
        **_kwargs,
    ):
        thread = await self.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        existing = self._existing(thread_id, idempotency_key)
        if existing is not None:
            if (
                existing.author_type
                is not ConversationAuthorType.ASSISTANT
                or existing.content != content
                or existing.causal_user_message_id
                != causal_user_message_id
            ):
                raise ConversationConflict(
                    "idempotency_key was reused with different content"
                )
            return thread, existing
        if thread.version != expected_thread_version:
            raise ConversationConflict("thread version conflict")
        causal = next(
            (
                message
                for message in self.messages.get(thread_id, [])
                if message.message_id == causal_user_message_id
            ),
            None,
        )
        if (
            causal is None
            or causal.author_type is not ConversationAuthorType.USER
        ):
            raise ConversationConflict("causal user message is unavailable")
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=causal_user_message_id,
            causal_user_message_id=causal_user_message_id,
            operation_id=operation_id,
            ai_result_id=ai_result_id,
            citation_refs=tuple(citation_refs),
            data_class=data_class,
        )
        updated = replace(
            thread,
            version=thread.version + 1,
            message_sequence=message.sequence,
            updated_at=message.created_at,
        )
        self.threads[thread_id] = updated
        self.messages[thread_id].append(message)
        return updated, message


def test_canonical_jeeves_mode_migrates_legacy_then_owns_new_turns(
    route,
    monkeypatch,
):
    legacy = _MemoryChatCollection(
        [
            {
                "_id": "legacy-turn",
                "session_id": "conversation-canonical",
                "client_message_id": "legacy-1",
                "role_user": "legacy question",
                "role_jeeves": "legacy answer",
                "status": "complete",
                "model": "legacy-model",
                "ts": 1.0,
            }
        ]
    )
    canonical = _CanonicalConversationAuthority()
    calls = {"count": 0}

    async def generate(
        query,
        recalled,
        needs_reasoning,
        conversation_context="",
    ):
        calls["count"] += 1
        assert "legacy question" in conversation_context
        assert "legacy answer" in conversation_context
        return {
            "text": "canonical next answer",
            "tier": "free",
            "model": "test",
            "engine_execution_id": None,
            "engine_verification": None,
            "engine_evidence_refs": [],
        }

    with _chat_client(
        route,
        monkeypatch,
        legacy,
        generate,
        canonical=canonical,
    ) as transport:
        payload = {
            "session_id": "conversation-canonical",
            "client_message_id": "message-2",
            "message": "follow up",
        }
        first = transport.post("/api/jeeves/chat", json=payload)
        replay = transport.post("/api/jeeves/chat", json=payload)
        history = transport.get(
            "/api/jeeves/chat/conversation-canonical?limit=10"
        )

    assert first.status_code == 200
    assert first.json()["history_source"] == "canonical"
    assert first.json()["canonical_thread_id"]
    assert first.json()["canonical_message_id"]
    assert first.json()["reply"] == "canonical next answer"
    assert calls["count"] == 1

    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["history_source"] == "canonical"
    assert replay.json()["reply"] == "canonical next answer"
    assert calls["count"] == 1

    body = history.json()
    assert body["available"] is True
    assert body["history_source"] == "canonical"
    assert body["canonical_thread_id"]
    assert [row["role_user"] for row in body["turns"]] == [
        "legacy question",
        "follow up",
    ]
    assert [row["role_jeeves"] for row in body["turns"]] == [
        "legacy answer",
        "canonical next answer",
    ]

    thread_id = first.json()["canonical_thread_id"]
    messages = canonical.messages[thread_id]
    assert [message.author_type.value for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert all(
        message.idempotency_key.startswith(
            ("jeeves-user:", "jeeves-assistant:")
        )
        for message in messages
    )


def test_canonical_jeeves_mode_fails_closed_if_authority_is_unavailable(
    route,
    monkeypatch,
):
    legacy = _MemoryChatCollection()

    class BrokenAuthority:
        async def get_thread(self, *args, **kwargs):
            raise RuntimeError("canonical authority unavailable")

    async def generate(*_args, **_kwargs):
        raise AssertionError("generation must not run without authority")

    with _chat_client(
        route,
        monkeypatch,
        legacy,
        generate,
        canonical=BrokenAuthority(),
    ) as transport:
        response = transport.post(
            "/api/jeeves/chat",
            json={
                "session_id": "conversation-broken",
                "client_message_id": "message-1",
                "message": "hello",
            },
        )

    assert response.status_code == 503
    assert "canonical conversation authority is unavailable" in response.text


def test_jeeves_chat_legacy_collection_is_migration_read_only(route) -> None:
    source = Path(route.__file__).read_text(encoding="utf-8")

    assert "SKL_JEEVES_CANONICAL_CONVERSATIONS" not in source
    assert "_chat_col().insert_one" not in source
    assert "_chat_col().update_one" not in source
    assert "_chat_col().delete_one" not in source
    assert "return core_db[\"jeeves_chat\"]" in source
    assert "_legacy_complete_rows" in source
    assert "_import_legacy_rows_to_canonical" in source
