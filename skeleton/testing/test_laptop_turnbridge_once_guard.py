"""Canonical native TurnBridge source/SQLite custody, with a fake worker only.

These regressions do not exercise a real GGUF, installed source rights,
physical memory pressure, Windows/WSL2 or any release qualification.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from threading import Event, Thread
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.turn_bridge import (
    TurnBridge,
)
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER, OUTPUT_SHA,
)


def fixture():
    worker = FakeWorker()
    worker.spine.create("s_local_test")
    bridge = TurnBridge(worker)
    return worker, bridge


def turn(bridge, *, request_id="req_once"):
    return bridge.turn(
        "s_local_test", request_id, "Only use local model bytes",
        seed=17, temperature=0.8,
    )


class TurnConcurrencyTests(unittest.TestCase):
    def test_same_request_during_blocked_native_generation_is_held(self):
        worker,bridge=fixture()
        started=Event()
        finish=Event()
        original=worker.turn
        outcomes=[]
        errors=[]
        def pause(*args,**kwargs):
            started.set()
            if not finish.wait(5):
                raise RuntimeError("fake native test barrier timed out")
            return original(*args,**kwargs)
        worker.turn=pause
        def generate():
            try:
                outcomes.append(turn(bridge))
            except BaseException as exc:
                errors.append(exc)
        thread=Thread(target=generate,daemon=True)
        thread.start()
        try:
            self.assertTrue(started.wait(5))
            self.assertEqual(bridge.guard.snapshot()["pending"],1)
            with self.assertRaisesRegex(ContractViolation,"duplicate"):
                turn(bridge)
            self.assertEqual(worker.generation_calls,0)
        finally:
            finish.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(len(outcomes),1)
        self.assertEqual(worker.generation_calls,1)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

    def test_native_exception_does_not_leave_process_lease_stuck(self):
        worker,bridge=fixture()
        with mock.patch.object(worker,"turn",side_effect=RuntimeError(
            "simulated native interruption"
        )):
            with self.assertRaises(RuntimeError):
                turn(bridge)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)
        self.assertEqual(worker.generation_calls,0)
        result=turn(bridge)
        self.assertEqual(result["output_sha256"],OUTPUT_SHA)
        self.assertEqual(worker.generation_calls,1)

    def test_invalid_task_never_enters_the_once_guard(self):
        worker,bridge=fixture()
        for value in ("", "  ", "\x00", None, []):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ContractViolation):
                    bridge.turn("s_local_test","r_valid",value)
                self.assertEqual(bridge.guard.snapshot()["pending"],0)
        self.assertEqual(worker.generation_calls,0)

    def test_invalid_seed_and_sampler_cannot_start_native_generation(self):
        worker,bridge=fixture()
        for seed,temperature in ((-1,0.8),(True,0.8),(0,0),(0,3)):
            with self.subTest(seed=seed,temperature=temperature):
                with self.assertRaises(ContractViolation):
                    bridge.turn(
                        "s_local_test","r_bad","local request",
                        seed=seed,temperature=temperature,
                    )
        self.assertEqual(worker.generation_calls,0)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

if __name__=="__main__":
    unittest.main()
