from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.context.compiler import COMPILER_VERSION, ContextCompiler
from skeleton.context.instruction_policy import INSTRUCTION_POLICIES
from skeleton.context.sources.request import user_input_segment
from skeleton.contracts.ai_execution import AIExecutionRequest, ExecutionState
from skeleton.contracts.context import ContextBudget
from skeleton.intelligence.execution_runtime import CognitiveExecutionRuntime
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderUsage,
)
from skeleton.provider_runtime import ProviderResponse, provider_request_from_context
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
        return self.responses.pop(0)


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
