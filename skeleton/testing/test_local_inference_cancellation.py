from __future__ import annotations

from skeleton.testing.local_inference_fixtures import local_serving_resources as local_serving_resources

import asyncio
import hashlib
import threading

import pytest

from skeleton.ai.runtime.inference.local import (
    CallableLocalModel,
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalInferenceOverloaded,
)

@pytest.mark.asyncio
@pytest.mark.parametrize("worker_returns", [False, True])
async def test_cancelled_local_inference_drains_real_thread_before_return(
    worker_returns,
) -> None:
    entered = threading.Event()
    cancellation_seen = threading.Event()
    release_cleanup = threading.Event()
    exited = threading.Event()
    digest = hashlib.sha256(b"cancel-drain-weights").hexdigest()

    def infer(_request, cancel):
        entered.set()
        try:
            assert cancel.wait(2.0)
            cancellation_seen.set()
            assert release_cleanup.wait(2.0)
            if not worker_returns:
                raise LocalInferenceCancelled("cooperative worker finished cleanup")
            return LocalInferenceResult(
                text="late local result",
                model_id="cancel-drain",
                model_digest=digest,
                input_tokens=2,
                output_tokens=3,
            )
        finally:
            exited.set()

    engine = LocalInferenceEngine(
        CallableLocalModel(model_id="cancel-drain", model_digest=digest, runner=infer)
    )
    task = asyncio.create_task(engine.generate(LocalInferenceRequest(prompt="cancel me")))
    try:
        assert await asyncio.to_thread(entered.wait, 2.0)
        task.cancel()
        assert await asyncio.to_thread(cancellation_seen.wait, 2.0)
        assert not task.done()
        assert not exited.is_set()

        # A second cancellation must also leave the actual worker joined.
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not exited.is_set()
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)
        assert exited.is_set()
        assert engine._cache == {}
    finally:
        release_cleanup.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_input_preflight_retains_worker_until_engine_close_drains(monkeypatch) -> None:
    from skeleton.ai.runtime.inference.adaptive_serving import ServingResources

    monkeypatch.setattr(
        "skeleton.ai.runtime.inference.local.sample_serving_resources",
        lambda: ServingResources(available_memory_bytes=1024**3, memory_used_fraction=0.1),
    )
    entered, release, exited = (threading.Event() for _ in range(3))
    event_loop_thread = threading.get_ident()
    preparation_threads = []
    inference_calls = []
    digest = "a" * 64

    def count_input(_request):
        preparation_threads.append(threading.get_ident())
        entered.set()
        try:
            assert release.wait(3)
            return 2
        finally:
            exited.set()

    def infer(_request, _cancel):
        inference_calls.append(True)
        return LocalInferenceResult(
            text="answer", model_id="prepare-drain", model_digest=digest, input_tokens=2, output_tokens=1
        )

    model = CallableLocalModel(model_id="prepare-drain", model_digest=digest, runner=infer)
    model.count_input_tokens = count_input
    engine = LocalInferenceEngine(model, cache_size=2)
    adapter = LocalModelAdapter(engine)
    generation = asyncio.create_task(engine.generate(LocalInferenceRequest(prompt="prepare me")))
    closing = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert len(preparation_threads) == 1
        assert preparation_threads[0] != event_loop_thread
        generation.cancel()
        closing = asyncio.create_task(engine.close())
        await asyncio.sleep(0.03)
        generation.cancel()
        closing.cancel()
        await asyncio.sleep(0)
        assert not generation.done()
        assert not closing.done()
        assert engine.snapshot()["active"] == 1
        assert not adapter.available
        release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(generation, closing, return_exceptions=True), 2)
        assert all(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes)
        assert exited.is_set()
        assert not inference_calls
        assert engine.snapshot()["active"] == 0
        assert engine.snapshot()["serving"]["closed"] is True
        assert not engine._cache
        with pytest.raises(LocalInferenceOverloaded, match="closed"):
            engine.maintain("resume")
    finally:
        release.set()
        generation.cancel()
        await asyncio.gather(generation, *(() if closing is None else (closing,)), return_exceptions=True)
