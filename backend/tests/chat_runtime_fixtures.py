"""Durable test adapters over existing canonical conversation owners.

Production uses Mongo operational metadata on the original USER row. This
reference facade keeps immutable prepared commands in the same SQLite database
used by the conversation conformance repository.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from skeleton.contracts.conversation import ConversationAuthorType, ConversationMessage
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationNotFound,
    SQLiteConversationRepository,
)

from core.engine_client import EngineClient, EngineNotFoundError


class SQLiteAsyncConversationAuthority:
    """Async facade over the canonical SQLite conversation reference authority."""

    def __init__(self, repository: SQLiteConversationRepository) -> None:
        self.repository = repository
        # Production keeps operational metadata on the same Mongo USER row.
        # This reference adapter persists the equivalent private fixture data
        # in its existing temporary SQLite database so reopen tests retain the
        # original immutable command rather than manufacture a fresh grant.
        with repository._lock:
            repository._connection.execute(
                "CREATE TABLE IF NOT EXISTS fixture_chat_execution ("
                "namespace TEXT NOT NULL, message_id TEXT NOT NULL, metadata TEXT NOT NULL, "
                "dispatch TEXT NOT NULL, PRIMARY KEY(namespace, message_id), "
                "FOREIGN KEY(namespace, message_id) REFERENCES "
                "conversation_message(namespace, message_id) ON DELETE CASCADE)"
            )

    async def _user(self, thread_id, message_id, *, tenant_id, owner_id):
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        row = self.repository._message_row(message_id)
        if row is None:
            raise ConversationNotFound(message_id)
        message = self.repository._message_from_row(row)
        if message.thread_id != thread_id or message.sequence > thread.message_sequence:
            raise ConversationNotFound(message_id)
        return message

    async def user_request_refs(self, thread_id, message_id, *, tenant_id, owner_id):
        message = await self._user(thread_id, message_id, tenant_id=tenant_id, owner_id=owner_id)
        return message.attachment_refs

    async def chat_execution(self, thread_id, message_id, *, tenant_id, owner_id):
        await self._user(thread_id, message_id, tenant_id=tenant_id, owner_id=owner_id)
        row = self.repository._connection.execute(
            "SELECT metadata FROM fixture_chat_execution WHERE namespace=? AND message_id=?",
            (self.repository.namespace, message_id),
        ).fetchone()
        return None if row is None else json.loads(row["metadata"])

    async def user_engine_command(self, thread_id, message_id, *, tenant_id, owner_id):
        metadata = await self.chat_execution(thread_id, message_id, tenant_id=tenant_id, owner_id=owner_id)
        return None if metadata is None else metadata["command"]

    async def chat_dispatch(self, thread_id, message_id, *, tenant_id, owner_id, record_digest, action="read"):
        metadata = await self.chat_execution(thread_id, message_id, tenant_id=tenant_id, owner_id=owner_id)
        if metadata is None or metadata["record_digest"] != record_digest:
            return None
        with self.repository._lock:
            row = self.repository._connection.execute(
                "SELECT dispatch FROM fixture_chat_execution WHERE namespace=? AND message_id=?",
                (self.repository.namespace, message_id),
            ).fetchone()
            dispatch = json.loads(row["dispatch"])
            if action == "claim":
                if dispatch["state"] not in {"ready", "submitting"} or dispatch["cancel_requested"]:
                    return None
                dispatch["state"] = "submitting"
            elif action == "admitted":
                if dispatch["state"] not in {"submitting", "admitted"}:
                    return None
                dispatch["state"] = "admitted"
            elif action == "cancel":
                if dispatch["state"] == "ready":
                    dispatch["state"] = "withdrawn"
                dispatch["cancel_requested"] = True
            elif action != "read":
                raise ValueError("unsupported dispatch action")
            self.repository._connection.execute(
                "UPDATE fixture_chat_execution SET dispatch=? WHERE namespace=? AND message_id=?",
                (json.dumps(dispatch), self.repository.namespace, message_id),
            )
        return dispatch

    async def chat_history_dependencies(self, thread_id, message_ids, *, tenant_id, owner_id):
        result = []
        for message_id in sorted(set(message_ids)):
            message = await self._user(thread_id, message_id, tenant_id=tenant_id, owner_id=owner_id)
            metadata = await self.chat_execution(thread_id, message_id, tenant_id=tenant_id, owner_id=owner_id)
            result.append((message, metadata, None))
        return result

    async def dragon_context_segments(self, thread, query):
        return ()

    async def active_transcript(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ):
        return self.repository.active_transcript(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    async def get_thread(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ):
        return self.repository.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    async def append_message(
        self,
        message,
        *,
        tenant_id: str,
        owner_id: str,
        expected_thread_version: int,
        execution_metadata=None,
    ):
        if execution_metadata is None:
            return self.repository.append_message(
                message,
                tenant_id=tenant_id,
                owner_id=owner_id,
                expected_thread_version=expected_thread_version,
            )

        from core.chat_sessions import checked_command

        checked_command(
            execution_metadata,
            thread=await self.get_thread(message.thread_id, tenant_id=tenant_id, owner_id=owner_id),
            user_message=message,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        encoded = json.dumps(execution_metadata, sort_keys=True, separators=(",", ":"))
        repository = self.repository
        with repository._lock:
            connection = repository._connection
            retained = connection.execute(
                "SELECT metadata FROM fixture_chat_execution WHERE namespace=? AND message_id=?",
                (repository.namespace, message.message_id),
            ).fetchone()
            if repository._message_row(message.message_id) is not None and (
                retained is None or retained["metadata"] != encoded
            ):
                raise ConversationConflict("fixture command identity changed")

            class PreparedAppendConnection:
                """Join private fixture metadata to the canonical append transaction."""

                def __getattr__(self, name):
                    return getattr(connection, name)

                def execute(self, statement, *args):
                    if statement == "COMMIT":
                        connection.execute(
                            "INSERT OR IGNORE INTO fixture_chat_execution VALUES (?, ?, ?, ?)",
                            (
                                repository.namespace,
                                message.message_id,
                                encoded,
                                json.dumps({"state": "ready", "cancel_requested": False}),
                            ),
                        )
                        actual = connection.execute(
                            "SELECT metadata FROM fixture_chat_execution WHERE namespace=? AND message_id=?",
                            (repository.namespace, message.message_id),
                        ).fetchone()
                        if actual["metadata"] != encoded:
                            raise ConversationConflict("fixture command identity changed")
                    return connection.execute(statement, *args)

            # The reference repository already owns sequencing, authorization
            # and its BEGIN/COMMIT boundary. Intercept only its commit while
            # holding the same lock, so a metadata failure rolls back both rows.
            repository._connection = PreparedAppendConnection()
            try:
                return repository.append_message(
                    message,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                    expected_thread_version=expected_thread_version,
                )
            finally:
                repository._connection = connection

    async def append_user_message(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
        parent_message_id: str | None = None,
        branch_id: str | None = None,
        supersedes_message_id: str | None = None,
        attachment_refs: tuple[str, ...] = (),
        data_class: str = "confidential",
    ):
        thread = self.repository.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=branch_id or thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.USER,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=parent_message_id,
            supersedes_message_id=supersedes_message_id,
            attachment_refs=attachment_refs,
            data_class=thread.data_class,
        )
        return self.repository.append_message(
            message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )

    async def commit_assistant_message(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
        causal_user_message_id: str,
        operation_id: str,
        ai_result_id: str,
        context_id: str | None = None,
        context_digest: str | None = None,
        context_source_snapshot: tuple[tuple[str, str], ...] = (),
        context_compiler_version: str | None = None,
        branch_id: str | None = None,
        supersedes_message_id: str | None = None,
        tool_receipt_refs: tuple[str, ...] = (),
        provider_receipt_refs: tuple[str, ...] = (),
        memory_refs: tuple[str, ...] = (),
        citation_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        data_class: str = "confidential",
    ):
        thread = self.repository.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=branch_id or thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=causal_user_message_id,
            supersedes_message_id=supersedes_message_id,
            causal_user_message_id=causal_user_message_id,
            operation_id=operation_id,
            ai_result_id=ai_result_id,
            context_id=context_id,
            context_digest=context_digest,
            context_source_snapshot=context_source_snapshot,
            context_compiler_version=context_compiler_version,
            tool_receipt_refs=tool_receipt_refs,
            provider_receipt_refs=provider_receipt_refs,
            memory_refs=memory_refs,
            citation_refs=citation_refs,
            artifact_refs=artifact_refs,
            data_class=thread.data_class,
        )
        return self.repository.append_message(
            message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )


# Route scenarios retain actual conversation and turn owners while replacing
# only the authenticated engine HTTP transport.
class EngineStub:
    """Scoped engine transport fixture retaining exact submitted commands/results."""

    config = SimpleNamespace(service_principal="codedock-backend", execution_timeout_s=30.0)
    _validate_ack_identity = staticmethod(EngineClient._validate_ack_identity)

    def __init__(self):
        self.commands = []
        self.results = {}
        self.admitted = {}
        self.cancelled = []
        self.complete_on_submit = True
        self.submit_error = None
        self.verification = "verified"
        self.output = "Verified terminal answer."
        self.provider_receipts = ("provider:test:receipt-1",)
        self.memory_refs = ()

    async def admit_storage_write(self, *args, **kwargs):
        raise AssertionError("route fixture must not make unrelated memory writes")

    async def reconcile_governed_write(self, *args, **kwargs):
        raise AssertionError("route fixture must not reconcile unrelated memory writes")

    async def tenant_model_inventory(self, *, actor_id, tenant_id):
        assert actor_id and tenant_id
        return {
            "available": True,
            "active": "openai",
            "providers": [
                {
                    "id": "openai",
                    "model": "test-model",
                    "available": True,
                    "architecture_acknowledged": True,
                    "execution_mode": "hosted",
                    "credential_free": False,
                    "configured": True,
                    "context_window": 32768,
                    "max_output_tokens": 4096,
                    "default_output_tokens": 1024,
                    "limits_source": "engine_chat_policy",
                    "tokenizer": "approximate_text",
                    "capabilities": ["text-generation"],
                    "supports_temperature": True,
                }
            ],
        }

    def complete(self, command=None):
        command = command or self.commands[-1]
        result = SimpleNamespace(
            operation_id=command.operation.operation_id,
            execution_id=command.execution_request.execution_id,
            final_output=self.output,
            verification=self.verification,
            evidence_refs=("evidence:test",),
            provider_receipts=self.provider_receipts,
            tool_receipts=(),
            memory_refs=self.memory_refs,
            artifact_refs=(),
            usage={},
        )
        self.results[result.execution_id] = result
        return result

    async def submit(self, command):
        self.commands.append(command)
        if self.submit_error is not None:
            raise self.submit_error
        self.admitted[command.execution_request.execution_id] = command
        if self.complete_on_submit:
            self.complete(command)
        return {
            "operation_id": command.operation.operation_id,
            "execution_id": command.execution_request.execution_id,
            "state": "admitted",
        }

    async def wait_for_terminal(self, *, execution_id, **kwargs):
        if execution_id not in self.admitted:
            raise EngineNotFoundError("not admitted")
        return self.results.get(execution_id)

    async def terminal_result_if_available(self, *, execution_id, **kwargs):
        return await self.wait_for_terminal(execution_id=execution_id, **kwargs)

    async def status(self, execution_id, **kwargs):
        if execution_id not in self.admitted:
            raise EngineNotFoundError("not admitted")
        return {"execution_state": "completed" if execution_id in self.results else "running"}

    async def handoff_binding(self, execution_id, **kwargs):
        command = self.admitted[execution_id]
        handoff = command.compiled_context
        return SimpleNamespace(
            **{
                name: getattr(handoff, name)
                for name in (
                    "operation_id",
                    "execution_id",
                    "turn_id",
                    "tenant_id",
                    "context_id",
                    "context_digest",
                    "compiler_version",
                    "source_snapshot",
                    "data_class",
                    "purpose",
                    "handoff_digest",
                )
            },
            actor_id=command.operation.actor_id,
            capability=command.operation.capability,
            idempotency_key=command.operation.idempotency_key,
            trace_id=command.operation.trace_id,
        )

    async def cancel(self, execution_id, **kwargs):
        self.cancelled.append(execution_id)
        return {"cancellation_requested": True}


@pytest.fixture
def chat_runtime(tmp_path, monkeypatch):
    import routes.ai as route
    import routes.gameforge_auth as auth

    # Initialize the existing memory singleton before replacing the engine
    # transport so its long-lived writer cannot capture a per-test stub.
    importlib.import_module("core.canonical_memory")
    repository = SQLiteConversationRepository(tmp_path / "chat.sqlite3")
    authority = SQLiteAsyncConversationAuthority(repository)
    thread = repository.create_thread(tenant_id="tenant-a", owner_id="owner-a")
    engine = EngineStub()
    monkeypatch.setattr(auth, "_enforced", lambda: False)
    monkeypatch.setattr(route, "conversation_authority", authority)
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: engine)
    value = SimpleNamespace(
        route=route,
        repository=repository,
        authority=authority,
        thread=thread,
        engine=engine,
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )
    value.request = lambda **kwargs: route.AIChatRequest(
        **{
            "message": "Build it.",
            "thread_id": thread.thread_id,
            "idempotency_key": "turn-1",
            "expected_thread_version": 1,
            **kwargs,
        }
    )
    value.transcript = lambda: repository.active_transcript(thread.thread_id, tenant_id="tenant-a", owner_id="owner-a")
    yield value
    repository.close()


@pytest.fixture
def chat_http_client(chat_runtime):
    h = chat_runtime
    app = FastAPI()
    app.include_router(h.route.router)
    import routes.gameforge_auth as auth

    app.dependency_overrides[auth.get_current_user] = lambda: h.user
    with TestClient(app) as client:
        yield client
