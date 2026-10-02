from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import threading
import time

import pytest

from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalToolCall,
)
from skeleton.provider_contract import ProviderToolDefinition
from skeleton.provider_runtime import (
    ProviderInvocationError,
    ProviderProtocolViolationError,
    ProviderRequest,
)


def _adapter(runner, *, model_id: str = "local-invariant-model") -> LocalModelAdapter:
    digest = hashlib.sha256(model_id.encode("utf-8")).hexdigest()
    return LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id=model_id,
                model_digest=digest,
                runner=runner,
            )
        )
    )


def _text_result(
    request: LocalInferenceRequest,
    *,
    model_id: str = "local-invariant-model",
) -> LocalInferenceResult:
    return LocalInferenceResult(
        text="local answer",
        model_id=model_id,
        model_digest=hashlib.sha256(model_id.encode("utf-8")).hexdigest(),
        input_tokens=max(1, len(request.prompt.split())),
        output_tokens=2,
        response_id="local:invariant",
    )


@pytest.mark.asyncio
async def test_local_adapter_rejects_requested_model_identity_drift() -> None:
    def runner(request, cancel):
        return _text_result(request)

    adapter = _adapter(runner)
    with pytest.raises(
        ProviderProtocolViolationError,
        match="identity does not match activated artifact",
    ):
        await adapter.generate(
            ProviderRequest(
                instructions="Answer locally.",
                prompt="hello",
                model="different-model",
            )
        )


@pytest.mark.asyncio
async def test_local_adapter_rejects_unoffered_tool_call() -> None:
    model_id = "local-invariant-model"
    digest = hashlib.sha256(model_id.encode("utf-8")).hexdigest()

    def runner(request, cancel):
        return LocalInferenceResult(
            text=None,
            model_id=model_id,
            model_digest=digest,
            input_tokens=2,
            output_tokens=1,
            finish_reason="tool_calls",
            response_id="local:unoffered-tool",
            tool_calls=(
                LocalToolCall(
                    call_id="call-1",
                    tool_id="repo.delete",
                    arguments={"path": "README.md"},
                ),
            ),
        )

    adapter = _adapter(runner, model_id=model_id)
    offered = ProviderToolDefinition(
        tool_id="repo.read",
        description="Read a file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    with pytest.raises(
        ProviderProtocolViolationError,
        match="unoffered tool",
    ):
        await adapter.generate(
            ProviderRequest(
                instructions="Use only offered tools.",
                prompt="inspect",
                tools=(offered,),
            )
        )


@pytest.mark.asyncio
async def test_local_adapter_enforces_required_and_specific_tool_choice() -> None:
    model_id = "local-invariant-model"
    digest = hashlib.sha256(model_id.encode("utf-8")).hexdigest()
    offered = ProviderToolDefinition(
        tool_id="repo.read",
        description="Read a file.",
        input_schema={"type": "object", "properties": {}},
    )

    def no_tool_runner(request, cancel):
        return LocalInferenceResult(
            text="answered without tool",
            model_id=model_id,
            model_digest=digest,
            input_tokens=2,
            output_tokens=3,
            response_id="local:no-tool",
        )

    adapter = _adapter(no_tool_runner, model_id=model_id)
    with pytest.raises(
        ProviderProtocolViolationError,
        match="omitted a required tool call",
    ):
        await adapter.generate(
            ProviderRequest(
                instructions="Use a tool.",
                prompt="inspect",
                tools=(offered,),
                tool_choice="required",
            )
        )

    with pytest.raises(
        ProviderProtocolViolationError,
        match="specific local tool choice is not offered",
    ):
        await adapter.generate(
            ProviderRequest(
                instructions="Use selected tool.",
                prompt="inspect",
                tools=(offered,),
                tool_choice="specific",
                specific_tool_id="repo.write",
            )
        )


@pytest.mark.asyncio
async def test_local_adapter_deadline_cancels_cooperative_backend() -> None:
    observed = threading.Event()

    def runner(request, cancel):
        while not cancel.wait(0.001):
            pass
        observed.set()
        raise LocalInferenceCancelled("cancelled by deadline")

    adapter = _adapter(runner)
    with pytest.raises(
        ProviderInvocationError,
        match="deadline exceeded",
    ):
        await adapter.generate(
            ProviderRequest(
                instructions="Answer locally.",
                prompt="slow answer",
                deadline=datetime.now(timezone.utc) + timedelta(milliseconds=25),
            )
        )
    assert observed.wait(0.5)


@pytest.mark.asyncio
async def test_cancelled_local_request_is_not_held_by_noncooperative_thread() -> None:
    started = threading.Event()

    def runner(request, cancel):
        started.set()
        time.sleep(0.6)
        return _text_result(request)

    engine = _adapter(runner).engine
    task = asyncio.create_task(
        engine.generate(LocalInferenceRequest(prompt="non cooperative"))
    )
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)
    assert started.is_set()

    loop = asyncio.get_running_loop()
    before = loop.time()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.5)
    elapsed = loop.time() - before
    assert elapsed < 0.45


@pytest.mark.asyncio
async def test_local_adapter_requires_structured_output_when_schema_requested() -> None:
    def runner(request, cancel):
        return _text_result(request)

    adapter = _adapter(runner)
    with pytest.raises(
        ProviderProtocolViolationError,
        match="omitted required structured output",
    ):
        await adapter.generate(
            ProviderRequest(
                instructions="Return JSON.",
                prompt="answer",
                structured_output_schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            )
        )
