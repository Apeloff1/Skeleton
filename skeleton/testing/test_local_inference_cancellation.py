from __future__ import annotations

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
