from __future__ import annotations

import asyncio
import hashlib
import socket
import threading

import pytest

from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalInferenceScheduler,
    LocalModelAdapter,
    LocalToolCall,
    ReferenceNGramModel,
)
from skeleton.provider_contract import ProviderToolDefinition
from skeleton.provider_runtime import ProviderRequest


def _math_model() -> ReferenceNGramModel:
    corpus = [
        "two plus two four",
        "two plus two four",
        "two plus two four",
        "three plus three six",
    ]
    return ReferenceNGramModel.train(corpus, order=2)


def test_reference_model_learns_and_round_trips_identity() -> None:
    model = _math_model()
    payload = model.to_dict()
    restored = ReferenceNGramModel.from_dict(payload)
    assert restored.model_digest == model.model_digest
    assert restored.to_dict() == payload


@pytest.mark.asyncio
async def test_local_adapter_executes_without_network_or_credentials(monkeypatch) -> None:
    original_socket = socket.socket

    def guarded_socket(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("local model path attempted network I/O")
        return original_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)
    engine = LocalInferenceEngine(_math_model())
    adapter = LocalModelAdapter(engine, default_seed=7)

    response = await adapter.generate(
        ProviderRequest(
            instructions="Answer from local learned weights.",
            prompt="two plus two",
            max_output_tokens=4,
        )
    )

    assert response.provider == "local"
    assert response.text is not None
    assert response.text.split()[0] == "four"
    assert response.usage.billed_cost == "0"
    assert response.usage.usage_source == "local_model"


@pytest.mark.asyncio
async def test_local_cache_is_model_and_request_identity_bound() -> None:
    engine = LocalInferenceEngine(_math_model(), cache_size=2)
    request = LocalInferenceRequest(prompt="two plus two", max_output_tokens=4, seed=1)
    first = await engine.generate(request)
    second = await engine.generate(request)
    assert first.cached is False
    assert second.cached is True
    assert first.text == second.text
    assert first.model_digest == second.model_digest


@pytest.mark.asyncio
async def test_scheduler_batches_multiple_local_requests() -> None:
    scheduler = LocalInferenceScheduler(
        LocalInferenceEngine(_math_model()),
        max_batch_size=4,
        batch_window_ms=5,
    )
    try:
        results = await asyncio.gather(
            scheduler.submit(LocalInferenceRequest(prompt="two plus two", seed=1)),
            scheduler.submit(LocalInferenceRequest(prompt="three plus three", seed=2)),
        )
    finally:
        await scheduler.close()
    assert len(results) == 2
    assert all(item.model_id == "skeleton-reference-ngram-v1" for item in results)


@pytest.mark.asyncio
async def test_callable_open_weight_backend_preserves_model_identity() -> None:
    digest = hashlib.sha256(b"weights").hexdigest()

    def runner(request: LocalInferenceRequest, cancel: threading.Event) -> LocalInferenceResult:
        assert not cancel.is_set()
        return LocalInferenceResult(
            text="local open-weight answer",
            model_id="open-weight-fixture",
            model_digest=digest,
            input_tokens=3,
            output_tokens=3,
            response_id="local:fixture",
        )

    backend = CallableLocalModel(
        model_id="open-weight-fixture",
        model_digest=digest,
        runner=runner,
    )
    result = await LocalInferenceEngine(backend).generate(
        LocalInferenceRequest(prompt="answer locally")
    )
    assert result.text == "local open-weight answer"
    assert result.model_digest == digest


@pytest.mark.asyncio
async def test_local_adapter_preserves_tool_call_contract() -> None:
    digest = hashlib.sha256(b"tool-weights").hexdigest()

    def runner(request: LocalInferenceRequest, cancel: threading.Event) -> LocalInferenceResult:
        return LocalInferenceResult(
            text=None,
            model_id="tool-local",
            model_digest=digest,
            input_tokens=2,
            output_tokens=1,
            finish_reason="tool_calls",
            response_id="local:tool",
            tool_calls=(
                LocalToolCall(
                    call_id="call-1",
                    tool_id="repo.read",
                    arguments={"path": "README.md"},
                ),
            ),
        )

    adapter = LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="tool-local",
                model_digest=digest,
                runner=runner,
            )
        )
    )
    response = await adapter.generate(
        ProviderRequest(
            instructions="Use allowed tools.",
            prompt="read",
            tools=(
                ProviderToolDefinition(
                    tool_id="repo.read",
                    description="Read a repository file",
                    input_schema={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                ),
            ),
        )
    )
    assert response.provider == "local"
    assert response.finish_reason.value == "tool_calls"
    assert response.tool_calls[0].tool_id == "repo.read"
    assert response.tool_calls[0].arguments == {"path": "README.md"}
