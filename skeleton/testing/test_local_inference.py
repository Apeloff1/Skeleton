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
from skeleton.provider_runtime import ProviderRequest
from skeleton.providers.contract import ProviderToolDefinition


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
                    description="Read one repository file.",
                    input_schema={
                        "type": "object",
                        "required": ["path"],
                        "properties": {"path": {"type": "string"}},
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

@pytest.mark.asyncio
async def test_local_engine_rejects_undeclared_tool_call():
    digest=hashlib.sha256(b"undeclared-tool").hexdigest()

    def runner(request:LocalInferenceRequest,cancel:threading.Event)->LocalInferenceResult:
        return LocalInferenceResult(
            text=None,
            model_id="tool-boundary",
            model_digest=digest,
            input_tokens=1,
            output_tokens=1,
            finish_reason="tool_calls",
            tool_calls=(
                LocalToolCall(
                    call_id="call-1",
                    tool_id="repo.write",
                    arguments={"path":"README.md"},
                ),
            ),
        )

    engine=LocalInferenceEngine(
        CallableLocalModel(
            model_id="tool-boundary",
            model_digest=digest,
            runner=runner,
        )
    )
    request=LocalInferenceRequest(
        prompt="use a tool",
        tools=(
            {
                "tool_id":"repo.read",
                "description":"read only",
                "input_schema":{
                    "type":"object",
                    "required":["path"],
                    "properties":{"path":{"type":"string"}},
                    "additionalProperties":False,
                },
            },
        ),
    )
    with pytest.raises(ValueError,match="undeclared tool_id"):
        await engine.generate(request)


@pytest.mark.asyncio
async def test_local_engine_validates_tool_argument_schema():
    digest=hashlib.sha256(b"tool-schema").hexdigest()

    def runner(request:LocalInferenceRequest,cancel:threading.Event)->LocalInferenceResult:
        return LocalInferenceResult(
            text=None,
            model_id="schema-boundary",
            model_digest=digest,
            input_tokens=1,
            output_tokens=1,
            finish_reason="tool_calls",
            tool_calls=(
                LocalToolCall(
                    call_id="call-1",
                    tool_id="calculator",
                    arguments={"value":"not-an-integer"},
                ),
            ),
        )

    engine=LocalInferenceEngine(
        CallableLocalModel(
            model_id="schema-boundary",
            model_digest=digest,
            runner=runner,
        )
    )
    request=LocalInferenceRequest(
        prompt="calculate",
        tools=(
            {
                "tool_id":"calculator",
                "input_schema":{
                    "type":"object",
                    "required":["value"],
                    "properties":{"value":{"type":"integer"}},
                    "additionalProperties":False,
                },
            },
        ),
    )
    with pytest.raises(ValueError,match="tool arguments violate schema"):
        await engine.generate(request)


@pytest.mark.asyncio
async def test_local_engine_validates_structured_output_schema():
    digest=hashlib.sha256(b"structured-schema").hexdigest()

    def runner(request:LocalInferenceRequest,cancel:threading.Event)->LocalInferenceResult:
        return LocalInferenceResult(
            text=None,
            model_id="structured-boundary",
            model_digest=digest,
            input_tokens=1,
            output_tokens=1,
            structured_output={"answer":"wrong-type"},
        )

    engine=LocalInferenceEngine(
        CallableLocalModel(
            model_id="structured-boundary",
            model_digest=digest,
            runner=runner,
        )
    )
    request=LocalInferenceRequest(
        prompt="return structured output",
        structured_output_schema={
            "type":"object",
            "required":["answer"],
            "properties":{"answer":{"type":"integer"}},
            "additionalProperties":False,
        },
    )
    with pytest.raises(ValueError,match="structured output violates request schema"):
        await engine.generate(request)


@pytest.mark.asyncio
async def test_scheduler_close_during_batch_window_does_not_deadlock():
    scheduler=LocalInferenceScheduler(
        LocalInferenceEngine(_math_model()),
        max_batch_size=4,
        batch_window_ms=500,
    )
    pending=asyncio.create_task(
        scheduler.submit(LocalInferenceRequest(prompt="two plus two",seed=9))
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await asyncio.wait_for(scheduler.close(),timeout=1.0)
    result=await asyncio.wait_for(pending,timeout=1.0)
    assert result.model_id=="skeleton-reference-ngram-v1"

def test_reference_model_artifact_rejects_boolean_numeric_coercion() -> None:
    model=ReferenceNGramModel.train(("alpha beta",),order=2)
    payload=model.to_dict()
    payload["order"]=True

    with pytest.raises(ValueError,match="order must be an integer"):
        ReferenceNGramModel.from_dict(payload)

    payload=model.to_dict()
    payload["transitions"][0]["counts"][
        next(iter(payload["transitions"][0]["counts"]))
    ]=True
    with pytest.raises(ValueError,match="counts must be positive integers"):
        ReferenceNGramModel.from_dict(payload)


def test_reference_model_artifact_rejects_fractional_count_coercion() -> None:
    model=ReferenceNGramModel.train(("alpha beta",),order=2)
    payload=model.to_dict()
    token=next(iter(payload["transitions"][0]["counts"]))
    payload["transitions"][0]["counts"][token]=1.9

    with pytest.raises(ValueError,match="counts must be positive integers"):
        ReferenceNGramModel.from_dict(payload)


def test_reference_model_artifact_rejects_duplicate_context_rows() -> None:
    model=ReferenceNGramModel.train(("alpha beta",),order=2)
    payload=model.to_dict()
    payload["transitions"].append(dict(payload["transitions"][0]))

    with pytest.raises(ValueError,match="duplicate transition context"):
        ReferenceNGramModel.from_dict(payload)


def test_reference_model_artifact_requires_schema_version() -> None:
    model=ReferenceNGramModel.train(("alpha beta",),order=2)
    payload=model.to_dict()
    payload["schema_version"]=2

    with pytest.raises(ValueError,match="schema_version"):
        ReferenceNGramModel.from_dict(payload)


def test_reference_model_artifact_rejects_non_string_context_token() -> None:
    model=ReferenceNGramModel.train(("alpha beta",),order=2)
    payload=model.to_dict()
    row=next(item for item in payload["transitions"] if item["context"])
    row["context"][0]=7

    with pytest.raises(ValueError,match="context must contain only strings"):
        ReferenceNGramModel.from_dict(payload)



def test_reference_model_artifact_rejects_unknown_top_level_fields() -> None:
    model=ReferenceNGramModel.train(("alpha beta",),order=2)
    payload=model.to_dict()
    payload["download_url"]="https://example.invalid/model.bin"

    with pytest.raises(ValueError,match="unsupported local model artifact key"):
        ReferenceNGramModel.from_dict(payload)


def test_reference_model_artifact_rejects_unknown_transition_row_fields() -> None:
    model=ReferenceNGramModel.train(("alpha beta",),order=2)
    payload=model.to_dict()
    payload["transitions"][0]["weight"]=1

    with pytest.raises(ValueError,match="contains unsupported key"):
        ReferenceNGramModel.from_dict(payload)
