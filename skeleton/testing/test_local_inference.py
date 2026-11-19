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
async def test_local_cache_key_tracks_runtime_identity_changes() -> None:
    calls = []

    def run(request, cancel):
        calls.append(request.digest)
        return LocalInferenceResult(
            text=f"answer-{len(calls)}",
            model_id="test-native",
            model_digest="a" * 64,
            input_tokens=1,
            output_tokens=1,
        )

    model = CallableLocalModel(
        model_id="test-native", model_digest="a" * 64, runner=run
    )
    model.runtime_digest = "b" * 64
    engine = LocalInferenceEngine(model, cache_size=3)
    request = LocalInferenceRequest(prompt="stable request", max_output_tokens=1)
    first = await engine.generate(request)
    repeated = await engine.generate(request)
    assert first.cached is False
    assert repeated.cached is True
    assert len(calls) == 1

    model.runtime_digest = "c" * 64
    updated = await engine.generate(request)
    assert updated.cached is False
    assert len(calls) == 2
    assert updated.text != first.text

    model.runtime_digest = "not-a-digest"
    with pytest.raises(ValueError, match="runtime digest"):
        await engine.generate(request)


@pytest.mark.asyncio
async def test_local_cache_does_not_accept_inflight_runtime_identity_drift() -> None:
    model_holder = {}

    def mutate_during_inference(request, cancel):
        model_holder["model"].runtime_digest = "d" * 64
        return LocalInferenceResult(
            text="untrusted after drift",
            model_id="test-native",
            model_digest="a" * 64,
            input_tokens=1,
            output_tokens=1,
        )

    model = CallableLocalModel(
        model_id="test-native", model_digest="a" * 64,
        runner=mutate_during_inference,
    )
    model.runtime_digest = "b" * 64
    model_holder["model"] = model
    engine = LocalInferenceEngine(model, cache_size=3)
    request = LocalInferenceRequest(prompt="inflight drift", max_output_tokens=1)
    with pytest.raises(ValueError, match="identity changed during inference"):
        await engine.generate(request)
    assert not engine._cache


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


async def _wait_for_signal(signal: threading.Event) -> None:
    async def wait():
        while not signal.is_set():
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), timeout=2)


def _lifecycle_engine(runner) -> LocalInferenceEngine:
    return LocalInferenceEngine(
        CallableLocalModel(model_id="lifecycle", model_digest="a" * 64, runner=runner),
        cache_size=0,
    )


def _lifecycle_result() -> LocalInferenceResult:
    return LocalInferenceResult(
        text="finished", model_id="lifecycle", model_digest="a" * 64,
        input_tokens=1, output_tokens=1,
    )


@pytest.mark.asyncio
async def test_batch_failure_waits_for_other_native_workers() -> None:
    started, release, stopped = (threading.Event() for _ in range(3))

    def run(request, cancel):
        if request.prompt == "fail":
            assert started.wait(2)
            raise ValueError("request failed")
        started.set()
        try:
            assert release.wait(2)
            return _lifecycle_result()
        finally:
            stopped.set()

    engine = _lifecycle_engine(run)
    batch = asyncio.create_task(engine.generate_many((
        LocalInferenceRequest(prompt="slow"), LocalInferenceRequest(prompt="fail"),
    )))
    try:
        await _wait_for_signal(started)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(batch), timeout=0.05)
    finally:
        release.set()
        with pytest.raises(ValueError, match="request failed"):
            await batch
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_scheduler_failure_isolated_to_its_request() -> None:
    def run(request, cancel):
        if request.prompt == "fail":
            raise ValueError("request failed")
        return _lifecycle_result()

    scheduler = LocalInferenceScheduler(_lifecycle_engine(run), batch_window_ms=20)
    try:
        failed, succeeded = await asyncio.gather(
            scheduler.submit(LocalInferenceRequest(prompt="fail")),
            scheduler.submit(LocalInferenceRequest(prompt="ok")),
            return_exceptions=True,
        )
    finally:
        await scheduler.close()
    assert isinstance(failed, ValueError)
    assert isinstance(succeeded, LocalInferenceResult)
    assert succeeded.text == "finished"


@pytest.mark.asyncio
async def test_scheduler_cancellation_stops_active_native_worker() -> None:
    started, stopped = threading.Event(), threading.Event()

    def run(request, cancel):
        started.set()
        try:
            assert cancel.wait(2), "scheduler did not propagate cancellation"
            return _lifecycle_result()
        finally:
            stopped.set()

    scheduler = LocalInferenceScheduler(_lifecycle_engine(run), batch_window_ms=0)
    submitted = asyncio.create_task(scheduler.submit(LocalInferenceRequest(prompt="cancel")))
    try:
        await _wait_for_signal(started)
        submitted.cancel()
        with pytest.raises(asyncio.CancelledError):
            await submitted
        assert stopped.is_set(), "cancellation returned before native worker stopped"
    finally:
        await scheduler.close()


@pytest.mark.asyncio
async def test_concurrent_close_callers_wait_for_native_worker() -> None:
    started, release, stopped = (threading.Event() for _ in range(3))

    def run(request, cancel):
        started.set()
        try:
            assert release.wait(2)
            return _lifecycle_result()
        finally:
            stopped.set()

    scheduler = LocalInferenceScheduler(_lifecycle_engine(run), batch_window_ms=0)
    submitted = asyncio.create_task(scheduler.submit(LocalInferenceRequest(prompt="slow")))
    await _wait_for_signal(started)
    first = asyncio.create_task(scheduler.close())
    await asyncio.sleep(0)
    second = asyncio.create_task(scheduler.close())
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), timeout=0.05)
    finally:
        release.set()
        await asyncio.gather(first, second, submitted)
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_saturated_scheduler_drains_admitted_requests_before_close() -> None:
    started, release = threading.Event(), threading.Event()

    def run(request, cancel):
        started.set()
        assert release.wait(3)
        return _lifecycle_result()

    scheduler = LocalInferenceScheduler(
        _lifecycle_engine(run), max_batch_size=1, batch_window_ms=0,
    )
    first = asyncio.create_task(scheduler.submit(LocalInferenceRequest(prompt="first")))
    await _wait_for_signal(started)
    pending = [asyncio.create_task(scheduler.submit(LocalInferenceRequest(prompt=str(i))))
               for i in range(34)]
    async def wait_for_pressure():
        while not scheduler._queue.full() or not scheduler._admission_lock.locked():
            await asyncio.sleep(0)
    await asyncio.wait_for(wait_for_pressure(), timeout=1)
    closing = asyncio.create_task(scheduler.close())
    await asyncio.sleep(0)
    release.set()
    await asyncio.wait_for(closing, timeout=2)
    results = await asyncio.wait_for(
        asyncio.gather(first, *pending, return_exceptions=True), timeout=2,
    )
    assert sum(isinstance(result, LocalInferenceResult) for result in results) == 34
    assert isinstance(results[-1], RuntimeError)
    assert str(results[-1]) == "local inference scheduler is closed"
    assert scheduler._queue.empty()


@pytest.mark.asyncio
async def test_cancelled_close_keeps_shared_shutdown_owned() -> None:
    started, release, stopped = (threading.Event() for _ in range(3))

    def run(request, cancel):
        started.set()
        try:
            assert release.wait(3)
            return _lifecycle_result()
        finally:
            stopped.set()

    scheduler = LocalInferenceScheduler(_lifecycle_engine(run), batch_window_ms=0)
    submitted = asyncio.create_task(scheduler.submit(LocalInferenceRequest(prompt="slow")))
    await _wait_for_signal(started)
    closing = asyncio.create_task(scheduler.close())
    await asyncio.sleep(0)
    closing.cancel()
    await asyncio.sleep(0)
    closing.cancel()
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(closing, timeout=2)
    await scheduler.close()
    assert stopped.is_set()
    assert (await submitted).text == "finished"
    with pytest.raises(RuntimeError, match="closed"):
        await scheduler.submit(LocalInferenceRequest(prompt="too late"))


@pytest.mark.asyncio
async def test_cancelled_batch_drains_every_native_worker() -> None:
    started = [threading.Event(), threading.Event()]
    stopped = [threading.Event(), threading.Event()]

    def run(request, cancel):
        index = int(request.prompt)
        started[index].set()
        try:
            assert cancel.wait(2)
            return _lifecycle_result()
        finally:
            stopped[index].set()

    # The helper defaults to one native slot. This regression requires both
    # workers to start before cancellation; explicitly provision two slots
    # rather than waiting forever for an impossible second admission.
    engine = LocalInferenceEngine(
        CallableLocalModel(
            model_id="lifecycle", model_digest="a" * 64, runner=run,
        ),
        cache_size=0,
        max_concurrency=2,
    )
    batch = asyncio.create_task(engine.generate_many(tuple(
        LocalInferenceRequest(prompt=str(i)) for i in range(2)
    )))
    for signal in started:
        await _wait_for_signal(signal)
    batch.cancel()
    with pytest.raises(asyncio.CancelledError):
        await batch
    assert all(signal.is_set() for signal in stopped)
