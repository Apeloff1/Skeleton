"""Adversarial cancellation controls for the real thread-backed local inference plane.

An asyncio cancellation MUST wait for the native worker to observe its token
and finish. Otherwise closing the offline desktop can leave an orphaned
llama.cpp process or concurrent model activity outside app custody.
"""
from __future__ import annotations

import asyncio
import threading
import time
import unittest

from skeleton.ai.runtime.inference.local import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
)


class LocalInferenceCancellationDrainTests(unittest.TestCase):
    def test_cancel_does_not_return_until_cooperative_worker_exits(self):
        entered = threading.Event()
        observed_cancel = threading.Event()
        terminated = threading.Event()
        requests = []

        def infer(request, cancellation):
            requests.append(request)
            entered.set()
            try:
                while not cancellation.is_set():
                    time.sleep(0.002)
                observed_cancel.set()
                # Model-owned process cleanup must finish before the task can
                # return cancellation to the desktop and permit SQLite close.
                time.sleep(0.025)
                return LocalInferenceResult(
                    text="uncommitted cancelled model output",
                    model_id="cancel-probe", model_digest="a" * 64,
                    input_tokens=1, output_tokens=1,
                )
            finally:
                terminated.set()

        model = CallableLocalModel(
            model_id="cancel-probe", model_digest="a" * 64, runner=infer,
        )
        engine = LocalInferenceEngine(model, cache_size=4)

        async def exercise():
            task = asyncio.create_task(engine.generate(
                LocalInferenceRequest(prompt="hello", max_output_tokens=1)
            ))
            self.assertTrue(await asyncio.to_thread(entered.wait, 2.0))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(observed_cancel.is_set())
            self.assertTrue(terminated.is_set())
            self.assertEqual(len(requests), 1)
            self.assertEqual(len(engine._cache), 0)

        asyncio.run(exercise())

    def test_repeated_cancel_during_worker_cleanup_cannot_detach_worker(self):
        started = threading.Event()
        cleanup_started = threading.Event()
        release_cleanup = threading.Event()
        done = threading.Event()

        def infer(request, cancellation):
            started.set()
            try:
                while not cancellation.is_set():
                    time.sleep(0.002)
                cleanup_started.set()
                # A second cancel arrives while the OS worker remains alive.
                release_cleanup.wait(timeout=2.0)
                return LocalInferenceResult(
                    text="not committed", model_id="multi-cancel",
                    model_digest="c" * 64, input_tokens=1, output_tokens=1,
                )
            finally:
                done.set()

        engine = LocalInferenceEngine(
            CallableLocalModel(
                model_id="multi-cancel", model_digest="c" * 64,
                runner=infer,
            ), cache_size=2,
        )

        async def exercise():
            task = asyncio.create_task(engine.generate(
                LocalInferenceRequest(prompt="hello", max_output_tokens=1)
            ))
            self.assertTrue(await asyncio.to_thread(started.wait, 2.0))
            task.cancel()
            self.assertTrue(await asyncio.to_thread(cleanup_started.wait, 2.0))
            task.cancel()
            await asyncio.sleep(0.02)
            self.assertFalse(task.done(), "second cancel detached live model worker")
            self.assertFalse(done.is_set())
            release_cleanup.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2.0)
            self.assertTrue(done.is_set())
            self.assertEqual(len(engine._cache), 0)

        try:
            asyncio.run(exercise())
        finally:
            release_cleanup.set()

    def test_non_cancelled_generation_still_returns_and_caches(self):
        def infer(request, cancellation):
            self.assertFalse(cancellation.is_set())
            return LocalInferenceResult(
                text="completed output",
                model_id="success-probe", model_digest="b" * 64,
                input_tokens=1, output_tokens=1,
            )
        engine = LocalInferenceEngine(
            CallableLocalModel(
                model_id="success-probe", model_digest="b" * 64,
                runner=infer,
            ), cache_size=4,
        )

        async def exercise():
            prompt = LocalInferenceRequest(prompt="hello", max_output_tokens=1)
            first = await engine.generate(prompt)
            second = await engine.generate(prompt)
            self.assertEqual(first.text, "completed output")
            self.assertTrue(second.cached)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
