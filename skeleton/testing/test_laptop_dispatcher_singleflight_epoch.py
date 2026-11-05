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


class SingleFlightEpochTests(unittest.TestCase):
    def test_model_change_during_native_turn_holds_committed_publication(self):
        worker,api,payload=initial()
        slow=BlockingTurn(worker)
        worker.turn=slow
        errors=[]
        answers=[]
        def generate():
            try:
                answers.append(api.dispatch("turn",payload))
            except BaseException as exc:
                errors.append(exc)
        thread=Thread(target=generate,daemon=True)
        thread.start()
        try:
            self.assertTrue(slow.started.wait(5))
            worker.spine.backend.model_digest="c"*64
        finally:
            slow.release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(answers)
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],ContractViolation)
        self.assertFalse(api._flight.locked())
        self.assertEqual(worker.generation_calls,1)
        worker.spine.backend.model_digest=MODEL
        stored=api.dispatch("replay",payload)
        self.assertTrue(stored["found"])
        self.assertTrue(stored["replay"]["replayed"])
        self.assertEqual(worker.generation_calls,1)

    def test_tokenizer_change_before_new_turn_denies_without_generation(self):
        worker,api,payload=initial()
        worker.spine.backend.tokenizer_digest="d"*64
        with self.assertRaises(ContractViolation):
            api.dispatch("turn",payload)
        self.assertEqual(worker.generation_calls,0)
        self.assertFalse(api._flight.locked())

    def test_closed_native_session_is_not_reopened_implicitly(self):
        worker,api,payload=initial()
        first=api.dispatch("turn",payload)
        self.assertEqual(first["receipt"]["model_sha256"],MODEL)
        result=api.dispatch(
            "close",{"session_id":payload["session_id"]}
        )
        self.assertTrue(result["closed"])
        with self.assertRaises(Exception):
            api.dispatch("turn",{**payload,"request_id":"new_after_close"})
        self.assertEqual(worker.generation_calls,1)
        self.assertFalse(api._flight.locked())

    def test_never_upgrade_simulated_client_to_real_device_certification(self):
        worker,api,payload=initial()
        snapshot=api.dispatch("doctor",{})
        self.assertIs(snapshot["release_certified"],False)
        self.assertEqual(snapshot["doctor"]["integrity_checked"],False)
        self.assertFalse(api._flight.locked())

if __name__=="__main__":
    unittest.main()
