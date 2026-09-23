from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.ai_execution import AIExecutionRequest, ExecutionState
from skeleton.intelligence.execution_runtime import CognitiveExecutionRuntime
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderUsage,
)
from skeleton.provider_runtime import ProviderResponse
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _now() -> datetime:
    return datetime(2026, 9, 23, 19, 30, tzinfo=timezone.utc)


def _request(
    *,
    execution_id: str = "exec-1",
    allowed_tools=(),
    stop_policy=None,
    budget=None,
) -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id=str(uuid4()),
        execution_id=execution_id,
        objective="Complete the requested task.",
        context_policy={
            "tenant_id": "tenant-a",
            "data_class": "internal",
        },
        tool_policy={
            "tenant_id": "tenant-a",
            "allowed_tool_ids": list(allowed_tools),
        },
        resource_budget=budget
        or {
            "max_model_turns": 6,
            "max_tool_calls": 8,
        },
        stop_policy=stop_policy or {"max_repeat_tool_batches": 1},
        created_at=_now(),
    )


class FakeProvider:
    provider_id = "fake"
    model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("provider called more times than expected")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _text_response(text: str, *, response_id: str) -> ProviderResponse:
    return ProviderResponse(
        text=text,
        provider="fake",
        model="fake-model",
        request_id=response_id,
        response_id=response_id,
        finish_reason=FinishReason.COMPLETED,
        usage=ProviderUsage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            usage_source="provider",
        ),
    )


def _tool_response(
    call_id: str,
    *,
    tool_id: str = "repo.read",
    arguments=None,
    response_id: str = "resp-tool",
) -> ProviderResponse:
    return ProviderResponse(
        text=None,
        provider="fake",
        model="fake-model",
        request_id=response_id,
        response_id=response_id,
        tool_calls=(
            ProviderToolCall(
                call_id=call_id,
                tool_id=tool_id,
                arguments=arguments or {"path": "README.md"},
            ),
        ),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=ProviderUsage(
            input_tokens=8,
            output_tokens=3,
            total_tokens=11,
            usage_source="provider",
        ),
    )


def _manifest(
    tool_id: str = "repo.read",
    *,
    approval_required: bool = False,
) -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        version="1.0.0",
        description="Read repository data",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=(
            ToolEffect.REVERSIBLE
            if approval_required
            else ToolEffect.READ_ONLY
        ),
        approval_required=approval_required,
    )


@pytest.mark.asyncio
async def test_direct_provider_completion_is_verified_and_atomically_finalized() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("done", response_id="resp-1")])
    runtime = CognitiveExecutionRuntime(repo, provider, tools)
    request = _request()

    result = await runtime.start(
        request,
        instructions="Answer concisely.",
        prompt="Do the task.",
        context_digest="a" * 64,
        now=_now(),
    )

    assert result.completed is True
    assert result.state is ExecutionState.COMPLETED
    assert result.result is not None
    assert result.result.final_output == "done"
    assert result.result.verification is not None
    assert result.result.verification_receipt["outcome"] == "verified"
    assert result.result.stream_terminal_event.startswith("stream-terminal:exec-1:")
    assert len(repo.pending_outbox(execution_id="exec-1")) == 1
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_model_tool_model_round_trip_uses_canonical_receipt_lineage() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    tool_calls = []

    async def handler(request):
        tool_calls.append(dict(request.arguments))
        return "artifact:readme"

    await tools.register(_manifest(), handler)
    provider = FakeProvider(
        [
            _tool_response("call-1"),
            _text_response("final answer", response_id="resp-2"),
        ]
    )
    runtime = CognitiveExecutionRuntime(repo, provider, tools)
    request = _request(allowed_tools=("repo.read",))

    result = await runtime.start(
        request,
        instructions="Use tools when needed.",
        prompt="Read the file and answer.",
        context_digest="b" * 64,
        now=_now(),
    )

    assert result.result.final_output == "final answer"
    assert tool_calls == [{"path": "README.md"}]
    assert result.result.usage["model_turns"] == 2
    assert result.result.usage["tool_calls"] == 1
    assert len(result.result.tool_receipts) == 1
    assert len(repo.turns("exec-1")) == 3
    assert provider.requests[1].prompt.startswith("Tool results from the previous provider turn")


@pytest.mark.asyncio
async def test_approval_required_suspends_before_effect_and_resumes_once(
    tmp_path,
) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(
            tmp_path / "approval-tool-receipts.sqlite3"
        )
    )
    effects = []

    async def handler(request):
        effects.append(request.approval_ref)
        return "artifact:write"

    await tools.register(
        _manifest("repo.write", approval_required=True),
        handler,
    )
    provider = FakeProvider(
        [
            _tool_response("call-write", tool_id="repo.write"),
            _text_response("write confirmed", response_id="resp-final"),
        ]
    )
    runtime = CognitiveExecutionRuntime(repo, provider, tools)
    request = _request(allowed_tools=("repo.write",))

    suspended = await runtime.start(
        request,
        instructions="Use the authorized tool.",
        prompt="Write the change.",
        context_digest="c" * 64,
        now=_now(),
    )

    assert suspended.completed is False
    assert suspended.state is ExecutionState.WAITING_FOR_USER
    assert [item.call_id for item in suspended.pending_approvals] == ["call-write"]
    assert effects == []

    completed = await runtime.resume(
        "exec-1",
        approval_refs={"call-write": "approval:confirmed"},
        now=_now(),
    )

    assert completed.completed is True
    assert completed.result.final_output == "write confirmed"
    assert effects == ["approval:confirmed"]
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_crash_after_provider_checkpoint_resumes_without_second_provider_call(
    monkeypatch,
) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("checkpointed", response_id="resp-1")])
    runtime = CognitiveExecutionRuntime(repo, provider, tools)
    request = _request()

    async def crash(*args, **kwargs):
        raise RuntimeError("simulated crash after provider checkpoint")

    monkeypatch.setattr(runtime, "_classify_provider_output", crash)

    with pytest.raises(RuntimeError, match="simulated crash"):
        await runtime.start(
            request,
            instructions="Answer.",
            prompt="Do it.",
            context_digest="d" * 64,
            now=_now(),
        )

    assert repo.get("exec-1").state is ExecutionState.CLASSIFYING_OUTPUT
    assert len(provider.requests) == 1

    resumed_provider = FakeProvider([])
    recovered = CognitiveExecutionRuntime(repo, resumed_provider, tools)
    result = await recovered.resume("exec-1", now=_now())

    assert result.completed is True
    assert result.result.final_output == "checkpointed"
    assert resumed_provider.requests == []


@pytest.mark.asyncio
async def test_crash_after_tool_effect_resumes_without_duplicate_tool_effect() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    effects = []

    async def handler(request):
        effects.append(request.idempotency_key)
        return "artifact:read"

    await tools.register(_manifest(), handler)
    first_provider = FakeProvider(
        [
            _tool_response("call-1"),
            RuntimeError("simulated crash after tool checkpoint"),
        ]
    )
    runtime = CognitiveExecutionRuntime(repo, first_provider, tools)
    request = _request(allowed_tools=("repo.read",))

    with pytest.raises(RuntimeError, match="simulated crash"):
        await runtime.start(
            request,
            instructions="Use tool.",
            prompt="Read and continue.",
            context_digest="e" * 64,
            now=_now(),
        )

    assert effects and len(effects) == 1
    assert repo.get("exec-1").state is ExecutionState.PROVIDER_PENDING

    restarted_tools = AsyncToolRuntime()

    async def duplicate_guard(request):
        effects.append("DUPLICATE")
        return "artifact:read"

    await restarted_tools.register(_manifest(), duplicate_guard)
    second_provider = FakeProvider(
        [_text_response("recovered final", response_id="resp-final")]
    )
    recovered = CognitiveExecutionRuntime(
        repo,
        second_provider,
        restarted_tools,
    )

    result = await recovered.resume("exec-1", now=_now())

    assert result.result.final_output == "recovered final"
    assert effects == [effects[0]]
    assert len(second_provider.requests) == 1


@pytest.mark.asyncio
async def test_repeated_identical_tool_batches_trip_cycle_limit() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    calls = []

    async def handler(request):
        calls.append(request.idempotency_key)
        return "artifact:read"

    await tools.register(_manifest(), handler)
    provider = FakeProvider(
        [
            _tool_response("call-1"),
            _tool_response("call-2", response_id="resp-tool-2"),
            _tool_response("call-3", response_id="resp-tool-3"),
        ]
    )
    runtime = CognitiveExecutionRuntime(repo, provider, tools)
    request = _request(
        allowed_tools=("repo.read",),
        stop_policy={"max_repeat_tool_batches": 1},
    )

    result = await runtime.start(
        request,
        instructions="Use tool if necessary.",
        prompt="Keep reading.",
        context_digest="f" * 64,
        now=_now(),
    )

    assert result.result.status == "failed"
    assert result.result.usage["error_code"] == "tool_cycle_detected"
    assert len(calls) == 2
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_cancellation_while_waiting_for_approval_finalizes_without_effect(
    tmp_path,
) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(
            tmp_path / "cancel-tool-receipts.sqlite3"
        )
    )
    effects = []

    async def handler(request):
        effects.append("effect")
        return "artifact:write"

    await tools.register(
        _manifest("repo.write", approval_required=True),
        handler,
    )
    provider = FakeProvider(
        [_tool_response("call-write", tool_id="repo.write")]
    )
    runtime = CognitiveExecutionRuntime(repo, provider, tools)
    request = _request(allowed_tools=("repo.write",))

    suspended = await runtime.start(
        request,
        instructions="Use authorized tools only.",
        prompt="Write.",
        context_digest="1" * 64,
        now=_now(),
    )
    current = repo.get("exec-1")
    repo.request_cancel(
        "exec-1",
        expected_version=current.version,
        now=_now(),
    )

    cancelled = await runtime.resume("exec-1", now=_now())

    assert suspended.state is ExecutionState.WAITING_FOR_USER
    assert cancelled.result.status == "cancelled"
    assert cancelled.state is ExecutionState.CANCELLED
    assert effects == []


@pytest.mark.asyncio
async def test_expired_deadline_fails_before_provider_io() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([])
    request = _request(
        stop_policy={
            "max_repeat_tool_batches": 1,
            "deadline": (_now() - timedelta(seconds=1)).isoformat(),
        }
    )
    runtime = CognitiveExecutionRuntime(repo, provider, tools)

    result = await runtime.start(
        request,
        instructions="Answer.",
        prompt="Do it.",
        context_digest="2" * 64,
        now=_now(),
    )

    assert result.result.status == "failed"
    assert result.result.usage["error_code"] == "execution_deadline_exceeded"
    assert provider.requests == []



@pytest.mark.asyncio
async def test_tool_handler_outage_becomes_durable_execution_failure() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()

    async def unavailable_handler(_request):
        raise RuntimeError("tool unavailable")

    await tools.register(_manifest(), unavailable_handler)
    provider = FakeProvider([_tool_response("call-outage")])
    runtime = CognitiveExecutionRuntime(repo, provider, tools)
    request = _request(allowed_tools=("repo.read",))

    result = await runtime.start(
        request,
        instructions="Use the tool if required.",
        prompt="Read the file.",
        context_digest="3" * 64,
        now=_now(),
    )

    assert result.completed is True
    assert result.result is not None
    assert result.result.status == "failed"
    assert result.result.usage["error_code"] == "RuntimeError"
    assert len(result.result.tool_receipts) == 1
    assert len(provider.requests) == 1
    assert repo.result("exec-1") == result.result
