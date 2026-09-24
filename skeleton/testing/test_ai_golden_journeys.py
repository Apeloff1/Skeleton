from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.context.compiler import COMPILER_VERSION, ContextCompiler
from skeleton.context.instruction_policy import INSTRUCTION_POLICIES
from skeleton.context.sources.conversation import conversation_message_segment
from skeleton.context.sources.request import user_input_segment
from skeleton.contracts.ai_execution import AIExecutionRequest, ExecutionState
from skeleton.contracts.context import ContextBudget
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
)
from skeleton.intelligence.execution_runtime import CognitiveExecutionRuntime
from skeleton.persistence.conversation_repository import SQLiteConversationRepository
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderUsage,
)
from skeleton.provider_runtime import (
    ProviderResponse,
    ProviderUnavailableError,
    provider_request_from_context,
)
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


NOW = datetime(2026, 9, 24, 1, 50, tzinfo=timezone.utc)


class ScriptedProvider:
    provider_id = "golden-fake"
    model = "golden-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("provider called more times than scripted")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _context_budget() -> ContextBudget:
    return ContextBudget(
        max_context_tokens=4_000,
        reserved_output_tokens=512,
        reserved_tool_result_tokens=512,
        reserved_policy_tokens=256,
        safety_margin_tokens=128,
        max_segment_tokens=2_000,
        max_artifact_tokens=1_000,
        max_tool_result_tokens=1_000,
    )


def _usage() -> ProviderUsage:
    return ProviderUsage(
        input_tokens=12,
        output_tokens=4,
        total_tokens=16,
        usage_source="provider",
    )


def _tool_response() -> ProviderResponse:
    return ProviderResponse(
        text=None,
        provider="golden-fake",
        model="golden-model",
        request_id="provider-tool-1",
        response_id="provider-tool-1",
        tool_calls=(
            ProviderToolCall(
                call_id="call-readme",
                tool_id="repo.read",
                arguments={"path": "README.md"},
            ),
        ),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=_usage(),
    )


def _final_response() -> ProviderResponse:
    return ProviderResponse(
        text="README inspected; canonical answer ready.",
        provider="golden-fake",
        model="golden-model",
        request_id="provider-final-1",
        response_id="provider-final-1",
        finish_reason=FinishReason.COMPLETED,
        usage=_usage(),
    )


def _compile_context(operation_id: str, execution_id: str):
    turn_id = str(uuid4())
    policy = INSTRUCTION_POLICIES.resolve("chat.jeeves")
    envelope = ContextCompiler().compile(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        purpose="model-inference",
        budget=_context_budget(),
        segments=(
            policy.as_segment(
                tenant_id="tenant-a",
                purpose="model-inference",
                created_at=NOW,
            ),
            user_input_segment(
                source_id=turn_id,
                tenant_id="tenant-a",
                purpose="model-inference",
                content="Read README.md and summarize the architecture.",
                created_at=NOW,
            ),
        ),
        compiled_at=NOW,
    )
    return envelope, provider_request_from_context(
        envelope,
        purpose="model-inference",
    )


@pytest.mark.asyncio
async def test_golden_context_tool_execution_restart_journey(tmp_path) -> None:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    envelope, projected = _compile_context(operation_id, execution_id)

    execution_path = tmp_path / "execution.sqlite3"
    receipt_path = tmp_path / "tool-receipts.sqlite3"
    repository = SQLiteExecutionRepository(execution_path)
    receipt_store = SQLiteToolReceiptStore(receipt_path)
    tools = AsyncToolRuntime(receipt_store=receipt_store)
    effects: list[dict[str, str]] = []

    async def read_handler(request):
        effects.append(dict(request.arguments))
        return "artifact:readme:v1"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read one repository artifact.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            effect=ToolEffect.READ_ONLY,
        ),
        read_handler,
    )

    provider = ScriptedProvider([_tool_response(), _final_response()])
    runtime = CognitiveExecutionRuntime(repository, provider, tools)
    request = AIExecutionRequest(
        operation_id=operation_id,
        execution_id=execution_id,
        objective="Answer from canonical repository evidence.",
        context_policy={
            "tenant_id": "tenant-a",
            "data_class": "internal",
            "context_id": envelope.context_id,
            "source_snapshot": [list(item) for item in envelope.source_snapshot],
            "compiler_version": COMPILER_VERSION,
            "provider_purpose": "model-inference",
        },
        tool_policy={
            "tenant_id": "tenant-a",
            "allowed_tool_ids": ["repo.read"],
        },
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 4,
            "max_output_tokens": 1_024,
        },
        stop_policy={"max_repeat_tool_batches": 1},
        created_at=NOW,
    )

    completed = await runtime.start(
        request,
        instructions=projected.instructions,
        prompt=projected.prompt,
        context_digest=envelope.context_digest,
        history=projected.history,
        now=NOW,
    )

    assert completed.completed is True
    assert completed.state is ExecutionState.COMPLETED
    assert completed.result is not None
    assert completed.result.final_output == "README inspected; canonical answer ready."
    assert completed.result.verification_receipt["outcome"] == "verified"
    assert completed.result.stream_terminal_event.startswith(
        f"stream-terminal:{execution_id}:"
    )
    assert effects == [{"path": "README.md"}]
    assert len(provider.requests) == 2
    assert all(
        item.context_id == envelope.context_id
        and item.context_digest == envelope.context_digest
        and item.context_source_snapshot == envelope.source_snapshot
        and item.context_compiler_version == COMPILER_VERSION
        for item in provider.requests
    )
    assert completed.result.tool_receipts
    assert completed.result.provider_receipts

    repository.close()
    receipt_store.close()

    # Restart must replay terminal authority without provider/tool execution.
    reopened_repository = SQLiteExecutionRepository(execution_path)
    reopened_tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(receipt_path)
    )
    replay_provider = ScriptedProvider([])
    replay_runtime = CognitiveExecutionRuntime(
        reopened_repository,
        replay_provider,
        reopened_tools,
    )

    replay = await replay_runtime.resume(execution_id, now=NOW)

    assert replay.completed is True
    assert replay.result == completed.result
    assert replay_provider.requests == []
    assert effects == [{"path": "README.md"}]

    reopened_repository.close()
    reopened_tools.receipt_store.close()



@pytest.mark.asyncio
async def test_golden_provider_outage_is_resumable_without_tool_effect(tmp_path) -> None:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    envelope, projected = _compile_context(operation_id, execution_id)
    path = tmp_path / "outage-execution.sqlite3"

    request = AIExecutionRequest(
        operation_id=operation_id,
        execution_id=execution_id,
        objective="Recover safely from provider outage.",
        context_policy={
            "tenant_id": "tenant-a",
            "data_class": "internal",
            "context_id": envelope.context_id,
            "source_snapshot": [list(item) for item in envelope.source_snapshot],
            "compiler_version": COMPILER_VERSION,
            "provider_purpose": "model-inference",
        },
        tool_policy={"tenant_id": "tenant-a", "allowed_tool_ids": []},
        resource_budget={"max_model_turns": 3, "max_tool_calls": 1},
        stop_policy={"max_repeat_tool_batches": 1},
        created_at=NOW,
    )

    first_repo = SQLiteExecutionRepository(path)
    first_provider = ScriptedProvider(
        [ProviderUnavailableError("simulated provider outage")]
    )
    runtime = CognitiveExecutionRuntime(
        first_repo,
        first_provider,
        AsyncToolRuntime(),
    )

    with pytest.raises(ProviderUnavailableError, match="simulated provider outage"):
        await runtime.start(
            request,
            instructions=projected.instructions,
            prompt=projected.prompt,
            context_digest=envelope.context_digest,
            history=projected.history,
            now=NOW,
        )

    persisted = first_repo.get(execution_id)
    assert persisted.state is ExecutionState.PROVIDER_PENDING
    assert first_repo.latest_checkpoint(execution_id) is not None
    first_repo.close()

    second_repo = SQLiteExecutionRepository(path)
    second_provider = ScriptedProvider([_final_response()])
    resumed_runtime = CognitiveExecutionRuntime(
        second_repo,
        second_provider,
        AsyncToolRuntime(),
    )

    resumed = await resumed_runtime.resume(execution_id, now=NOW)

    assert resumed.completed is True
    assert resumed.result.final_output == "README inspected; canonical answer ready."
    assert len(first_provider.requests) == 1
    assert len(second_provider.requests) == 1
    second_repo.close()


@pytest.mark.asyncio
async def test_golden_approval_wait_survives_restart_and_effect_runs_once(
    tmp_path,
) -> None:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    envelope, projected = _compile_context(operation_id, execution_id)
    execution_path = tmp_path / "approval-execution.sqlite3"
    receipt_path = tmp_path / "approval-receipts.sqlite3"

    request = AIExecutionRequest(
        operation_id=operation_id,
        execution_id=execution_id,
        objective="Run one approved repository mutation.",
        context_policy={
            "tenant_id": "tenant-a",
            "data_class": "internal",
            "context_id": envelope.context_id,
            "source_snapshot": [list(item) for item in envelope.source_snapshot],
            "compiler_version": COMPILER_VERSION,
            "provider_purpose": "model-inference",
        },
        tool_policy={
            "tenant_id": "tenant-a",
            "allowed_tool_ids": ["repo.read"],
        },
        resource_budget={"max_model_turns": 4, "max_tool_calls": 2},
        stop_policy={"max_repeat_tool_batches": 1},
        created_at=NOW,
    )

    first_repo = SQLiteExecutionRepository(execution_path)
    first_receipts = SQLiteToolReceiptStore(receipt_path)
    first_tools = AsyncToolRuntime(receipt_store=first_receipts)
    effects: list[str] = []

    async def first_handler(_request):
        effects.append("unexpected-before-approval")
        return "artifact:mutation"

    await first_tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Approval-gated repository action.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            effect=ToolEffect.REVERSIBLE,
            approval_required=True,
        ),
        first_handler,
    )
    first_provider = ScriptedProvider([_tool_response()])
    first_runtime = CognitiveExecutionRuntime(
        first_repo,
        first_provider,
        first_tools,
    )

    waiting = await first_runtime.start(
        request,
        instructions=projected.instructions,
        prompt=projected.prompt,
        context_digest=envelope.context_digest,
        history=projected.history,
        now=NOW,
    )

    assert waiting.state is ExecutionState.WAITING_FOR_USER
    assert len(waiting.pending_approvals) == 1
    call_id = waiting.pending_approvals[0].call_id
    assert effects == []

    first_repo.close()
    first_receipts.close()

    second_repo = SQLiteExecutionRepository(execution_path)
    second_receipts = SQLiteToolReceiptStore(receipt_path)
    second_tools = AsyncToolRuntime(receipt_store=second_receipts)

    async def approved_handler(_request):
        effects.append("approved")
        return "artifact:mutation"

    await second_tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Approval-gated repository action.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            effect=ToolEffect.REVERSIBLE,
            approval_required=True,
        ),
        approved_handler,
    )
    second_provider = ScriptedProvider([_final_response()])
    resumed_runtime = CognitiveExecutionRuntime(
        second_repo,
        second_provider,
        second_tools,
    )

    completed = await resumed_runtime.resume(
        execution_id,
        approval_refs={call_id: "approval:golden-1"},
        now=NOW,
    )

    assert completed.completed is True
    assert completed.state is ExecutionState.COMPLETED
    assert effects == ["approved"]
    assert len(first_provider.requests) == 1
    assert len(second_provider.requests) == 1
    assert completed.result.tool_receipts

    second_repo.close()
    second_receipts.close()



def test_golden_conversation_restart_rebuilds_canonical_context(tmp_path) -> None:
    conversation_path = tmp_path / "conversation.sqlite3"
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    operation_id = str(uuid4())
    user_message_id = str(uuid4())
    assistant_message_id = str(uuid4())

    first = SQLiteConversationRepository(conversation_path)
    thread = first.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        thread_id=thread_id,
        branch_id=branch_id,
        created_at=NOW,
        title="Golden thread",
    )

    thread, user = first.append_message(
        ConversationMessage(
            message_id=user_message_id,
            thread_id=thread.thread_id,
            branch_id=thread.active_branch_id,
            sequence=1,
            author_type=ConversationAuthorType.USER,
            created_at=NOW,
            idempotency_key="user-1",
            content="What is the canonical architecture?",
        ),
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )
    thread, assistant = first.append_message(
        ConversationMessage(
            message_id=assistant_message_id,
            thread_id=thread.thread_id,
            branch_id=thread.active_branch_id,
            sequence=2,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=NOW,
            idempotency_key="assistant-1",
            content="The server-owned runtime is authoritative.",
            parent_message_id=user.message_id,
            causal_user_message_id=user.message_id,
            operation_id=operation_id,
            ai_result_id="ai-result:golden-1",
            tool_receipt_refs=("tool-receipt:golden-1",),
            citation_refs=("citation:golden-1",),
        ),
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )
    first.close()

    reopened = SQLiteConversationRepository(conversation_path)
    restored_thread = reopened.get_thread(
        thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    transcript = reopened.active_transcript(
        thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )

    assert [item.message_id for item in transcript] == [
        user_message_id,
        assistant_message_id,
    ]
    assert transcript[-1].operation_id == operation_id
    assert transcript[-1].ai_result_id == "ai-result:golden-1"

    policy = INSTRUCTION_POLICIES.resolve("chat.jeeves")
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    envelope = ContextCompiler().compile(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        purpose="model-inference",
        budget=_context_budget(),
        segments=(
            policy.as_segment(
                tenant_id="tenant-a",
                purpose="model-inference",
                created_at=NOW,
            ),
            *(
                conversation_message_segment(
                    restored_thread,
                    message,
                    purpose="model-inference",
                )
                for message in transcript
            ),
        ),
        compiled_at=NOW,
    )
    projected = provider_request_from_context(
        envelope,
        purpose="model-inference",
    )

    assert [(item.role, item.content) for item in projected.history] == [
        ("user", "What is the canonical architecture?"),
        ("assistant", "The server-owned runtime is authoritative."),
    ]
    assistant_segment = next(
        segment
        for segment in envelope.segments
        if segment.source_id == assistant_message_id
    )
    assert f"operation:{operation_id}" in assistant_segment.provenance
    assert "ai-result:ai-result:golden-1" in assistant_segment.provenance
    assert "tool-receipt:tool-receipt:golden-1" in assistant_segment.provenance
    assert "citation:citation:golden-1" in assistant_segment.provenance

    reopened.close()
