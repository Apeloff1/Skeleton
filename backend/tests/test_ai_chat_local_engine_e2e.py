from __future__ import annotations

import asyncio
import hashlib
import importlib
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
)
from skeleton.api import engine_routes
from skeleton.api.engine_authority import (
    EngineAuthorityRegistry,
    EngineServiceGrant,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
)
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationNotFound,
    ConversationRepositoryError,
    SQLiteConversationRepository,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import ProviderRegistry
from skeleton.skills.tool_runtime import AsyncToolRuntime


SERVICE_TOKEN = "local-engine-e2e-" + ("x" * 48)
TENANT = "default"
OWNER = "local-e2e@example.invalid"


class ConversationStorageUnavailable(ConversationRepositoryError):
    pass


class SQLiteAsyncConversationAuthority:
    """Async facade over the canonical SQLite conversation reference authority."""

    def __init__(self, repository: SQLiteConversationRepository) -> None:
        self.repository = repository

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
    ):
        return self.repository.append_message(
            message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )

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


class FailAssistantCommitOnceAuthority(SQLiteAsyncConversationAuthority):
    def __init__(self, repository: SQLiteConversationRepository) -> None:
        super().__init__(repository)
        self.fail_once = True

    async def commit_assistant_message(self, *args, **kwargs):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated assistant commit crash")
        return await super().commit_assistant_message(*args, **kwargs)


def _load_backend_ai_route(monkeypatch):
    """Load the route without requiring the production Mongo adapter."""

    backend_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(backend_root))

    if "core.conversations" not in sys.modules:
        conversations = ModuleType("core.conversations")
        conversations.ConversationStorageUnavailable = ConversationStorageUnavailable
        conversations.conversation_authority = object()
        monkeypatch.setitem(sys.modules, "core.conversations", conversations)

    if "routes.gameforge_auth" not in sys.modules:
        auth = ModuleType("routes.gameforge_auth")
        auth.require_role = lambda _role: (lambda: {"email": OWNER, "tenant_id": TENANT})
        monkeypatch.setitem(sys.modules, "routes.gameforge_auth", auth)

    return importlib.import_module("routes.ai")


def _local_registry() -> tuple[ProviderRegistry, list[LocalInferenceRequest]]:
    calls: list[LocalInferenceRequest] = []
    model_digest = hashlib.sha256(b"backend-chat-local-engine-e2e-v1").hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        assert not cancel.is_set()
        calls.append(request)
        assert request.prompt == "Answer through the assembled local engine."
        return LocalInferenceResult(
            text="Assembled local engine answer.",
            model_id="backend-chat-local-e2e",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=4,
            response_id="local:backend-chat-e2e",
        )

    adapter = LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="backend-chat-local-e2e",
                model_digest=model_digest,
                runner=runner,
            )
        )
    )
    return ProviderRegistry([adapter], active="local"), calls


def _gated_local_registry():
    calls: list[LocalInferenceRequest] = []
    entered = threading.Event()
    release = threading.Event()
    model_digest = hashlib.sha256(
        b"backend-chat-local-engine-deferred-v1"
    ).hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        calls.append(request)
        entered.set()
        while not release.wait(0.005):
            if cancel.is_set():
                raise LocalInferenceCancelled("deferred local turn cancelled")
        if cancel.is_set():
            raise LocalInferenceCancelled("deferred local turn cancelled")
        return LocalInferenceResult(
            text="Deferred local engine answer.",
            model_id="backend-chat-local-deferred",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=4,
            response_id="local:backend-chat-deferred",
        )

    adapter = LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="backend-chat-local-deferred",
                model_digest=model_digest,
                runner=runner,
            )
        )
    )
    return (
        ProviderRegistry([adapter], active="local"),
        calls,
        entered,
        release,
    )


def _cancel_then_answer_registry():
    calls: list[LocalInferenceRequest] = []
    first_entered = threading.Event()
    model_digest = hashlib.sha256(
        b"backend-chat-local-engine-cancel-v1"
    ).hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        calls.append(request)
        if len(calls) == 1:
            first_entered.set()
            while not cancel.wait(0.005):
                pass
            raise LocalInferenceCancelled("first turn cancelled")
        assert not cancel.is_set()
        return LocalInferenceResult(
            text="Conversation continued after cancellation.",
            model_id="backend-chat-local-cancel",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=5,
            response_id="local:backend-chat-after-cancel",
        )

    adapter = LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="backend-chat-local-cancel",
                model_digest=model_digest,
                runner=runner,
            )
        )
    )
    return ProviderRegistry([adapter], active="local"), calls, first_entered


def _verified(
    _request,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    # Individual end-to-end tests assert the expected local output. The shared
    # verification fixture should validate whatever candidate that scenario
    # produced rather than hard-coding the first scenario's answer and turning
    # legitimate deferred/cancellation flows into engine_execution_exception.
    assert candidate.strip()
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:backend-chat-local-e2e",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:backend-chat-local-e2e",),
    )


def _engine_boundary(
    *,
    execution_path: Path,
    submission_path: Path,
    registry: ProviderRegistry,
):
    execution_repository = SQLiteExecutionRepository(execution_path)
    submissions = SQLiteEngineSubmissionStore(submission_path)
    service = EngineExecutionService(
        execution_repository,
        submissions,
        EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal="codedock-backend",
                    scopes=frozenset(
                        {
                            "engine:submit",
                            "engine:read",
                            "engine:cancel",
                            "engine:events",
                            "engine:approve",
                            "engine:memory",
                        }
                    ),
                    tenant_ids=frozenset({TENANT}),
                    capabilities=frozenset({"assistant.chat"}),
                )
            ]
        ),
    )
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=registry,
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified,
    )
    engine_app = FastAPI()
    engine_app.include_router(engine_routes.router, prefix="/api/v1")
    engine_app.dependency_overrides[engine_routes._engine_service] = lambda: service
    engine_app.dependency_overrides[engine_routes._engine_service_token] = (
        lambda: SERVICE_TOKEN
    )
    engine_app.dependency_overrides[engine_routes._engine_coordinator] = (
        lambda: coordinator
    )

    from core.engine_client import EngineClient, EngineClientConfig

    client = EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=SERVICE_TOKEN,
            service_principal="codedock-backend",
            request_timeout_s=5,
            poll_interval_s=0.001,
            execution_timeout_s=10,
        ),
        transport=httpx.ASGITransport(app=engine_app),
    )
    return service, coordinator, client, execution_repository, submissions


def test_backend_chat_request_identity_changes_with_execution_semantics(monkeypatch) -> None:
    route = _load_backend_ai_route(monkeypatch)
    thread_id = str(uuid4())
    base = route.AIChatRequest(
        message="same message",
        thread_id=thread_id,
        idempotency_key="same-idem",
        expected_thread_version=1,
        context="context-a",
    )
    stale = route.AIChatRequest(
        message=base.message,
        thread_id=thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=99,
        context=base.context,
    )
    changed_context = route.AIChatRequest(
        message=base.message,
        thread_id=thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=1,
        context="context-b",
    )
    changed_memory = route.AIChatRequest(
        message=base.message,
        thread_id=thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=1,
        context=base.context,
        memory_policy=route.AIChatMemoryPolicy(
            persist_verified_response=True,
            kind="semantic",
            namespace="assistant",
        ),
    )

    identity = route._chat_request_identity_ref(base)
    assert identity == route._chat_request_identity_ref(stale)
    assert identity != route._chat_request_identity_ref(changed_context)
    assert identity != route._chat_request_identity_ref(changed_memory)


@pytest.mark.asyncio
async def test_backend_chat_incomplete_user_without_engine_execution_submits_once(
    tmp_path,
    monkeypatch,
) -> None:
    route = _load_backend_ai_route(monkeypatch)
    monkeypatch.setenv(
        "AI_ARCHITECTURE_ROOT",
        str(Path(__file__).resolve().parents[2]),
    )

    conversations = SQLiteConversationRepository(
        tmp_path / "presubmit-conversation.sqlite3"
    )
    thread = conversations.create_thread(
        tenant_id=TENANT,
        owner_id=OWNER,
        title="Pre-submit recovery",
        data_class="confidential",
    )
    request = route.AIChatRequest(
        message="Answer through the assembled local engine.",
        thread_id=thread.thread_id,
        idempotency_key="presubmit-recovery",
        expected_thread_version=thread.version,
        context="Untrusted evidence for the local execution.",
    )
    refs = (
        "ephemeral-context-sha256:"
        + hashlib.sha256(request.context.encode("utf-8")).hexdigest(),
        route._chat_request_identity_ref(request),
    )
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=datetime.now(timezone.utc),
        idempotency_key=request.idempotency_key,
        content=request.message,
        attachment_refs=refs,
        data_class=thread.data_class,
    )
    conversations.append_message(
        user_message,
        tenant_id=TENANT,
        owner_id=OWNER,
        expected_thread_version=thread.version,
    )
    authority = SQLiteAsyncConversationAuthority(conversations)

    registry, local_calls = _local_registry()
    (
        service,
        coordinator,
        engine_client,
        execution_repository,
        submissions,
    ) = _engine_boundary(
        execution_path=tmp_path / "presubmit-execution.sqlite3",
        submission_path=tmp_path / "presubmit-submission.sqlite3",
        registry=registry,
    )
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: engine_client),
    )
    monkeypatch.setattr(route, "conversation_authority", authority)

    recovered = await route.ai_chat(
        route.AIChatRequest(
            message=request.message,
            thread_id=request.thread_id,
            idempotency_key=request.idempotency_key,
            expected_thread_version=thread.version,
            context=request.context,
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )

    assert recovered["success"] is True
    assert recovered["response"] == "Assembled local engine answer."
    assert recovered["engine_runtime_provider"] == "local"
    assert len(local_calls) == 1
    assert execution_repository.result(recovered["engine_execution_id"]) is not None

    transcript = conversations.active_transcript(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert [item.author_type.value for item in transcript] == [
        "user",
        "assistant",
    ]

    await coordinator.shutdown()
    conversations.close()
    execution_repository.close()
    submissions.close()


@pytest.mark.asyncio
async def test_backend_chat_crosses_real_engine_http_boundary_and_commits_local_result(
    tmp_path,
    monkeypatch,
) -> None:
    route = _load_backend_ai_route(monkeypatch)
    monkeypatch.setenv(
        "AI_ARCHITECTURE_ROOT",
        str(Path(__file__).resolve().parents[2]),
    )

    conversations = SQLiteConversationRepository(
        tmp_path / "conversation.sqlite3"
    )
    thread = conversations.create_thread(
        tenant_id=TENANT,
        owner_id=OWNER,
        title="Local engine E2E",
        data_class="confidential",
    )
    authority = SQLiteAsyncConversationAuthority(conversations)

    execution_repository = SQLiteExecutionRepository(
        tmp_path / "execution.sqlite3"
    )
    submissions = SQLiteEngineSubmissionStore(
        tmp_path / "submission.sqlite3"
    )
    service = EngineExecutionService(
        execution_repository,
        submissions,
        EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal="codedock-backend",
                    scopes=frozenset(
                        {
                            "engine:submit",
                            "engine:read",
                            "engine:cancel",
                            "engine:events",
                            "engine:approve",
                            "engine:memory",
                        }
                    ),
                    tenant_ids=frozenset({TENANT}),
                    capabilities=frozenset({"assistant.chat"}),
                )
            ]
        ),
    )
    registry, local_calls = _local_registry()
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=registry,
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified,
    )

    engine_app = FastAPI()
    engine_app.include_router(engine_routes.router, prefix="/api/v1")
    engine_app.dependency_overrides[engine_routes._engine_service] = lambda: service
    engine_app.dependency_overrides[engine_routes._engine_service_token] = (
        lambda: SERVICE_TOKEN
    )
    engine_app.dependency_overrides[engine_routes._engine_coordinator] = (
        lambda: coordinator
    )

    from core.engine_client import EngineClient, EngineClientConfig

    engine_client = EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=SERVICE_TOKEN,
            service_principal="codedock-backend",
            request_timeout_s=5,
            poll_interval_s=0.001,
            execution_timeout_s=10,
        ),
        transport=httpx.ASGITransport(app=engine_app),
    )
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: engine_client),
    )
    monkeypatch.setattr(route, "conversation_authority", authority)

    first = await route.ai_chat(
        route.AIChatRequest(
            message="Answer through the assembled local engine.",
            thread_id=thread.thread_id,
            idempotency_key="local-e2e-1",
            expected_thread_version=thread.version,
            context="Untrusted evidence for the local execution.",
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )

    assert first["success"] is True
    assert first["provider"] == "skeleton-engine"
    assert first["model"] == "engine-routed"
    assert first["response"] == "Assembled local engine answer."
    assert first["replayed"] is False
    assert first["engine_runtime_provider"] == "local"
    assert first["engine_provider_receipts"]
    assert all(
        receipt.startswith("provider:local:")
        for receipt in first["engine_provider_receipts"]
    )
    assert len(local_calls) == 1

    execution_id = first["engine_execution_id"]
    assert execution_id
    durable = execution_repository.result(execution_id)
    assert durable is not None
    assert durable.status == "completed"
    assert durable.final_output == first["response"]
    assert durable.provider_receipts
    assert all(
        receipt.startswith("provider:local:")
        for receipt in durable.provider_receipts
    )
    assert durable.evidence_refs == ("evidence:backend-chat-local-e2e",)

    transcript = conversations.active_transcript(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert [item.author_type.value for item in transcript] == [
        "user",
        "assistant",
    ]
    assistant = transcript[-1]
    assert assistant.content == first["response"]
    assert assistant.operation_id == first["operation_id"]
    assert assistant.ai_result_id == first["ai_result_id"]
    assert assistant.context_digest == first["context"]["context_digest"]
    assert assistant.provider_receipt_refs == durable.provider_receipts
    assert assistant.citation_refs == ("evidence:backend-chat-local-e2e",)

    replay = await route.ai_chat(
        route.AIChatRequest(
            message="Answer through the assembled local engine.",
            thread_id=thread.thread_id,
            idempotency_key="local-e2e-1",
            expected_thread_version=thread.version,
            context="Untrusted evidence for the local execution.",
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )

    assert replay["success"] is True
    assert replay["replayed"] is True
    assert replay["response"] == first["response"]
    assert replay["operation_id"] == first["operation_id"]
    assert replay["ai_result_id"] == first["ai_result_id"]
    assert replay["engine_runtime_provider"] == "local"
    assert replay["engine_provider_receipts"] == first["engine_provider_receipts"]
    assert len(local_calls) == 1

    await coordinator.shutdown()
    conversations.close()
    execution_repository.close()
    submissions.close()


@pytest.mark.asyncio
async def test_backend_chat_recovers_durable_local_result_after_commit_crash_and_restart(
    tmp_path,
    monkeypatch,
) -> None:
    route = _load_backend_ai_route(monkeypatch)
    monkeypatch.setenv(
        "AI_ARCHITECTURE_ROOT",
        str(Path(__file__).resolve().parents[2]),
    )

    conversation_path = tmp_path / "restart-conversation.sqlite3"
    execution_path = tmp_path / "restart-execution.sqlite3"
    submission_path = tmp_path / "restart-submission.sqlite3"

    conversations = SQLiteConversationRepository(conversation_path)
    thread = conversations.create_thread(
        tenant_id=TENANT,
        owner_id=OWNER,
        title="Local engine restart recovery",
        data_class="confidential",
    )
    authority = FailAssistantCommitOnceAuthority(conversations)

    registry, first_calls = _local_registry()
    (
        service,
        coordinator,
        engine_client,
        execution_repository,
        submissions,
    ) = _engine_boundary(
        execution_path=execution_path,
        submission_path=submission_path,
        registry=registry,
    )
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: engine_client),
    )
    monkeypatch.setattr(route, "conversation_authority", authority)

    request = route.AIChatRequest(
        message="Answer through the assembled local engine.",
        thread_id=thread.thread_id,
        idempotency_key="restart-crash-1",
        expected_thread_version=thread.version,
        context="Untrusted evidence for the local execution.",
    )

    with pytest.raises(HTTPException) as failed_commit:
        await route.ai_chat(
            request,
            user={"email": OWNER, "tenant_id": TENANT},
        )
    assert failed_commit.value.status_code == 500
    assert len(first_calls) == 1

    user_only = conversations.active_transcript(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert len(user_only) == 1
    user_message = user_only[0]
    assert user_message.author_type is ConversationAuthorType.USER

    operation_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-ai-chat:" + thread.thread_id + ":" + user_message.message_id,
        )
    )
    execution_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-ai-chat-execution:" + operation_id,
        )
    )
    durable_before_restart = execution_repository.result(execution_id)
    assert durable_before_restart is not None
    assert durable_before_restart.status == "completed"
    assert durable_before_restart.final_output == "Assembled local engine answer."

    await coordinator.shutdown()
    conversations.close()
    execution_repository.close()
    submissions.close()

    reopened_conversations = SQLiteConversationRepository(conversation_path)
    reopened_authority = SQLiteAsyncConversationAuthority(reopened_conversations)
    restart_registry, restart_calls = _local_registry()
    (
        restarted_service,
        restarted_coordinator,
        restarted_client,
        restarted_execution_repository,
        restarted_submissions,
    ) = _engine_boundary(
        execution_path=execution_path,
        submission_path=submission_path,
        registry=restart_registry,
    )
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: restarted_client),
    )
    monkeypatch.setattr(route, "conversation_authority", reopened_authority)

    recovered = await route.ai_chat(
        route.AIChatRequest(
            message=request.message,
            thread_id=request.thread_id,
            idempotency_key=request.idempotency_key,
            expected_thread_version=thread.version,
            context=request.context,
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )

    assert recovered["success"] is True
    assert recovered["response"] == "Assembled local engine answer."
    assert recovered["engine_execution_id"] == execution_id
    assert recovered["operation_id"] == operation_id
    assert recovered["engine_runtime_provider"] == "local"
    assert restart_calls == []

    transcript = reopened_conversations.active_transcript(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert [item.author_type.value for item in transcript] == [
        "user",
        "assistant",
    ]
    assert transcript[-1].provider_receipt_refs
    assert all(
        ref.startswith("provider:local:")
        for ref in transcript[-1].provider_receipt_refs
    )
    assert (
        restarted_execution_repository.result(execution_id).as_dict()
        == durable_before_restart.as_dict()
    )

    await restarted_coordinator.shutdown()
    reopened_conversations.close()
    restarted_execution_repository.close()
    restarted_submissions.close()


@pytest.mark.asyncio
async def test_deferred_chat_reconnect_finalizes_from_engine_handoff_without_original_context(
    tmp_path,
    monkeypatch,
) -> None:
    route = _load_backend_ai_route(monkeypatch)
    monkeypatch.setenv(
        "AI_ARCHITECTURE_ROOT",
        str(Path(__file__).resolve().parents[2]),
    )

    conversation_path = tmp_path / "deferred-conversation.sqlite3"
    conversations = SQLiteConversationRepository(conversation_path)
    thread = conversations.create_thread(
        tenant_id=TENANT,
        owner_id=OWNER,
        title="Deferred reconnect",
        data_class="internal",
    )
    authority = SQLiteAsyncConversationAuthority(conversations)
    registry, local_calls, entered, release = _gated_local_registry()
    (
        service,
        coordinator,
        engine_client,
        execution_repository,
        submissions,
    ) = _engine_boundary(
        execution_path=tmp_path / "deferred-execution.sqlite3",
        submission_path=tmp_path / "deferred-submission.sqlite3",
        registry=registry,
    )
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: engine_client),
    )
    monkeypatch.setattr(route, "conversation_authority", authority)

    started = await route.ai_chat(
        route.AIChatRequest(
            message="Deferred canonical request.",
            thread_id=thread.thread_id,
            idempotency_key="deferred-1",
            expected_thread_version=thread.version,
            context="Ephemeral context that will not be resent after reconnect.",
            response_mode="deferred",
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )

    assert started["success"] is True
    assert started["accepted"] is True
    assert started["terminal"] is False
    assert started["response"] is None
    execution_id = started["engine_execution_id"]
    assert execution_id
    assert await asyncio.to_thread(entered.wait, 2.0)
    assert len(local_calls) == 1

    in_flight = await route.get_ai_chat_turn(
        thread.thread_id,
        "deferred-1",
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert in_flight["terminal"] is False
    assert in_flight["engine_execution_id"] == execution_id

    # Finish in the engine, then drop/reopen conversation process state. The
    # finalizer receives only thread/idempotency identity: context provenance
    # must come from the engine's durable non-content handoff binding.
    release.set()
    durable = await engine_client.wait_for_terminal(
        execution_id=execution_id,
        actor_id=OWNER,
        tenant_id=TENANT,
        trace_id="deferred-reconnect-test",
    )
    assert durable.final_output == "Deferred local engine answer."

    conversations.close()
    reopened = SQLiteConversationRepository(conversation_path)
    reopened_authority = SQLiteAsyncConversationAuthority(reopened)
    monkeypatch.setattr(route, "conversation_authority", reopened_authority)

    finalized = await route.get_ai_chat_turn(
        thread.thread_id,
        "deferred-1",
        user={"email": OWNER, "tenant_id": TENANT},
    )

    assert finalized["success"] is True
    assert finalized["terminal"] is True
    assert finalized["state"] == "completed"
    assert finalized["response"] == "Deferred local engine answer."
    assert finalized["engine_execution_id"] == execution_id
    assert (
        finalized["context"]["context_digest"]
        == started["context"]["context_digest"]
    )
    assert finalized["context"]["source_snapshot"]
    assert finalized["engine_runtime_provider"] == "local"
    assert len(local_calls) == 1

    transcript = reopened.active_transcript(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert [item.author_type.value for item in transcript] == [
        "user",
        "assistant",
    ]
    assert transcript[-1].parent_message_id == transcript[0].message_id
    assert transcript[-1].data_class == "internal"
    assert transcript[-1].context_digest == started["context"]["context_digest"]

    replay = await route.get_ai_chat_turn(
        thread.thread_id,
        "deferred-1",
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert replay["terminal"] is True
    assert replay["replayed"] is True
    assert replay["assistant_message"]["message_id"] == finalized["assistant_message"]["message_id"]
    assert len(local_calls) == 1

    await coordinator.shutdown()
    reopened.close()
    execution_repository.close()
    submissions.close()


@pytest.mark.asyncio
async def test_chat_lineage_preserves_prior_successful_turn_in_local_model_history(
    tmp_path,
    monkeypatch,
) -> None:
    route = _load_backend_ai_route(monkeypatch)
    conversations = SQLiteConversationRepository(
        tmp_path / "lineage-conversation.sqlite3"
    )
    thread = conversations.create_thread(
        tenant_id=TENANT,
        owner_id=OWNER,
        title="Lineage preservation",
        data_class="confidential",
    )
    authority = SQLiteAsyncConversationAuthority(conversations)
    registry, local_calls = _local_registry()
    (
        service,
        coordinator,
        engine_client,
        execution_repository,
        submissions,
    ) = _engine_boundary(
        execution_path=tmp_path / "lineage-execution.sqlite3",
        submission_path=tmp_path / "lineage-submission.sqlite3",
        registry=registry,
    )
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: engine_client),
    )
    monkeypatch.setattr(route, "conversation_authority", authority)

    first = await route.ai_chat(
        route.AIChatRequest(
            message="Answer through the assembled local engine.",
            thread_id=thread.thread_id,
            idempotency_key="lineage-1",
            expected_thread_version=thread.version,
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert first["success"] is True

    after_first = conversations.get_thread(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    second = await route.ai_chat(
        route.AIChatRequest(
            message="Answer through the assembled local engine.",
            thread_id=thread.thread_id,
            idempotency_key="lineage-2",
            expected_thread_version=after_first.version,
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert second["success"] is True
    assert len(local_calls) == 2
    assert local_calls[1].history == (
        ("user", "Answer through the assembled local engine."),
        ("assistant", "Assembled local engine answer."),
    )

    transcript = conversations.active_transcript(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert [item.author_type.value for item in transcript] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert transcript[1].parent_message_id == transcript[0].message_id
    assert transcript[2].parent_message_id == transcript[1].message_id
    assert transcript[3].parent_message_id == transcript[2].message_id

    await coordinator.shutdown()
    conversations.close()
    execution_repository.close()
    submissions.close()


@pytest.mark.asyncio
async def test_cancelled_deferred_turn_closes_lineage_and_does_not_poison_next_history(
    tmp_path,
    monkeypatch,
) -> None:
    route = _load_backend_ai_route(monkeypatch)
    conversations = SQLiteConversationRepository(
        tmp_path / "cancel-chat-conversation.sqlite3"
    )
    thread = conversations.create_thread(
        tenant_id=TENANT,
        owner_id=OWNER,
        title="Cancellation recovery",
        data_class="confidential",
    )
    authority = SQLiteAsyncConversationAuthority(conversations)
    registry, local_calls, first_entered = _cancel_then_answer_registry()
    (
        service,
        coordinator,
        engine_client,
        execution_repository,
        submissions,
    ) = _engine_boundary(
        execution_path=tmp_path / "cancel-chat-execution.sqlite3",
        submission_path=tmp_path / "cancel-chat-submission.sqlite3",
        registry=registry,
    )
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: engine_client),
    )
    monkeypatch.setattr(route, "conversation_authority", authority)

    started = await route.ai_chat(
        route.AIChatRequest(
            message="This turn should be cancelled.",
            thread_id=thread.thread_id,
            idempotency_key="cancel-turn-1",
            expected_thread_version=thread.version,
            response_mode="deferred",
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert started["terminal"] is False
    assert await asyncio.to_thread(first_entered.wait, 2.0)

    cancelled = await route.cancel_ai_chat_turn(
        thread.thread_id,
        route.AIChatCancelRequest(
            idempotency_key="cancel-turn-1",
            reason="user stopped generation",
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert cancelled["state"] == "cancelled"
    assert cancelled["terminal"] is True

    closed = await route.get_ai_chat_turn(
        thread.thread_id,
        "cancel-turn-1",
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert closed["terminal"] is True
    assert closed["state"] == "cancelled"

    after_cancel = conversations.get_thread(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    continued = await route.ai_chat(
        route.AIChatRequest(
            message="Continue after cancellation.",
            thread_id=thread.thread_id,
            idempotency_key="cancel-turn-2",
            expected_thread_version=after_cancel.version,
        ),
        user={"email": OWNER, "tenant_id": TENANT},
    )
    assert continued["success"] is True
    assert continued["response"] == "Conversation continued after cancellation."
    assert len(local_calls) == 2
    assert local_calls[1].history == ()

    transcript = conversations.active_transcript(
        thread.thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert [item.author_type.value for item in transcript] == [
        "user",
        "system-derived",
        "user",
        "assistant",
    ]
    assert transcript[1].artifact_refs[0] == "chat-terminal:cancelled"
    assert transcript[2].parent_message_id == transcript[1].message_id
    assert transcript[3].parent_message_id == transcript[2].message_id

    await coordinator.shutdown()
    conversations.close()
    execution_repository.close()
    submissions.close()
