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


class SingleFlightFailureTests(unittest.TestCase):
    def test_uncertain_worker_error_does_not_strand_process_lock(self):
        worker,api,payload=initial()
        with mock.patch.object(worker,"turn",side_effect=RuntimeError(
            "simulated uncertain native failure"
        )):
            with self.assertRaises(RuntimeError):
                api.dispatch("turn",payload)
        self.assertFalse(api._flight.locked())
        record=api.dispatch("status",{})
        self.assertEqual(record["model_sha256"],MODEL)
        self.assertEqual(worker.generation_calls,0)
        self.assertFalse(record.get("release_certified",False))

    def test_missing_sqlite_commit_releases_lock_without_fabricating_answer(self):
        worker,api,payload=initial()
        old=worker.turn
        def uncommitted(*args,**kwargs):
            response=old(*args,**kwargs)
            worker.spine.receipts.clear()
            return response
        worker.turn=uncommitted
        with self.assertRaisesRegex(ContractViolation,"missing a committed"):
            api.dispatch("turn",payload)
        self.assertFalse(api._flight.locked())
        replay=api.dispatch("replay",payload)
        self.assertFalse(replay["found"])
        self.assertEqual(worker.generation_calls,1)

    def test_completed_generation_is_not_repeated_by_contending_client(self):
        worker,api,payload=initial()
        first=api.dispatch("turn",payload)
        second=api.dispatch("turn",payload)
        self.assertTrue(second["receipt"]["replayed"])
        self.assertEqual(
            first["receipt"]["output_sha256"],
            second["receipt"]["output_sha256"],
        )
        self.assertEqual(worker.generation_calls,1)
        self.assertFalse(api._flight.locked())

    def test_history_read_blocks_native_generation_until_read_finishes(self):
        worker,api,payload=initial()
        started=Event()
        release=Event()
        old=worker.spine.history
        reads=[]
        errors=[]
        def held_history(*args,**kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError("test read barrier expired")
            return old(*args,**kwargs)
        def reader():
            try:
                reads.append(api.dispatch(
                    "history",{"session_id":payload["session_id"]}
                ))
            except BaseException as exc:
                errors.append(exc)
        thread=Thread(target=reader,daemon=True)
        with mock.patch.object(worker.spine,"history",side_effect=held_history):
            thread.start()
            try:
                self.assertTrue(started.wait(5))
                with self.assertRaisesRegex(
                    ContractViolation,"active request"
                ):
                    api.dispatch("turn",payload)
                self.assertEqual(worker.generation_calls,0)
            finally:
                release.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(len(reads),1)
        self.assertFalse(api._flight.locked())

if __name__=="__main__":
    unittest.main()
