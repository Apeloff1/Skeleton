"""Deterministic, fake-worker first-laptop HTTP dispatcher concurrency checks.

No model bytes, live GGUF, external service or physical-device qualification
is used here. The hardened loopback server owns one shared dispatcher.
"""
from __future__ import annotations

from threading import Event, Thread
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import (
    LaptopDispatcher,
)
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER, OUTPUT_SHA,
)


class BlockingTurn:
    """Pause fake generation before its canonical simulated commit."""

    def __init__(self, worker):
        self.original = worker.turn
        self.started = Event()
        self.release = Event()
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.started.set()
        if not self.release.wait(5):
            raise RuntimeError("test generation barrier expired")
        return self.original(*args, **kwargs)


def initial():
    worker=FakeWorker()
    dispatcher=LaptopDispatcher(worker)
    session=dispatcher.dispatch("create", {})["session_id"]
    payload={
        "session_id":session,
        "request_id":"native_trial_a",
        "prompt":"offline first laptop model request",
    }
    return worker,dispatcher,payload


class SingleFlightMutationTests(unittest.TestCase):
    def test_parallel_client_cannot_close_or_mutate_active_turn(self):
        worker,api,payload=initial()
        slow=BlockingTurn(worker)
        answers=[]
        failures=[]
        worker.turn=slow
        def operate():
            try:
                answers.append(api.dispatch("turn",payload))
            except BaseException as exc:
                failures.append(exc)
        thread=Thread(target=operate, daemon=True)
        thread.start()
        try:
            self.assertTrue(slow.started.wait(5))
            self.assertTrue(api._flight.locked())
            overlapping=(
                ("create",{}),
                ("turn",{**payload,"request_id":"native_trial_b"}),
                ("close",{"session_id":payload["session_id"]}),
                ("outbox_ack",{
                    "event_key":"e_1","event_sha256":OUTPUT_SHA,
                }),
                ("history",{"session_id":payload["session_id"]}),
                ("replay",payload),
                ("status",{}),
                ("doctor",{}),
                ("identity",{}),
                ("outbox_pending",{}),
            )
            for op,data in overlapping:
                with self.subTest(operation=op):
                    with self.assertRaisesRegex(
                        ContractViolation,"active request"
                    ):
                        api.dispatch(op,data)
            self.assertEqual(len(worker.spine.created),1)
            self.assertFalse(worker.spine.closed)
            self.assertFalse(worker.spine.acknowledged)
            self.assertEqual(worker.generation_calls,0)
        finally:
            slow.release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures)
        self.assertEqual(len(answers),1)
        self.assertEqual(answers[0]["receipt"]["model_sha256"],MODEL)
        self.assertEqual(worker.generation_calls,1)
        self.assertFalse(api._flight.locked())

    def test_concurrent_new_session_refused_without_allocating_a_second(self):
        worker,api,payload=initial()
        slow=BlockingTurn(worker)
        worker.turn=slow
        errors=[]
        thread=Thread(
            target=lambda: errors.append(api.dispatch("turn",payload)),
            daemon=True,
        )
        thread.start()
        try:
            self.assertTrue(slow.started.wait(5))
            for _ in range(8):
                with self.assertRaises(ContractViolation):
                    api.dispatch("create",{})
            self.assertEqual(len(worker.spine.created),1)
        finally:
            slow.release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors),1)
        self.assertEqual(worker.generation_calls,1)

    def test_invalid_input_does_not_acquire_or_strand_singleflight_lease(self):
        worker,api,payload=initial()
        with self.assertRaises(ContractViolation):
            api.dispatch("turn",{**payload,"request_id":True})
        self.assertFalse(api._flight.locked())
        result=api.dispatch("status",{})
        self.assertEqual(result["model_sha256"],MODEL)
        self.assertEqual(worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
