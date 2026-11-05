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


class NativeSourceEpochTests(unittest.TestCase):
    def test_stale_backend_model_denies_before_any_native_call(self):
        worker,bridge=fixture()
        worker.spine.backend.model_digest="c"*64
        with mock.patch.object(worker,"turn") as native:
            with self.assertRaises(ContractViolation):
                turn(bridge)
            native.assert_not_called()
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

    def test_stale_tokenizer_denies_before_model_generation(self):
        worker,bridge=fixture()
        worker.spine.backend.tokenizer_digest="c"*64
        with self.assertRaises(ContractViolation):
            turn(bridge)
        self.assertEqual(worker.generation_calls,0)

    def test_model_switch_between_initial_check_and_guard_denies(self):
        worker,bridge=fixture()
        original=bridge.guard.hold
        @contextmanager
        def switch(*args):
            with original(*args):
                worker.spine.backend.model_digest="d"*64
                yield
        with mock.patch.object(bridge.guard,"hold",side_effect=switch):
            with self.assertRaises(ContractViolation):
                turn(bridge)
        self.assertEqual(worker.generation_calls,0)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

    def test_postcommit_model_swap_holds_output_but_retains_replay(self):
        worker,bridge=fixture()
        original=worker.turn
        def switch_after_commit(*args,**kwargs):
            result=original(*args,**kwargs)
            worker.spine.backend.model_digest="c"*64
            return result
        worker.turn=switch_after_commit
        with self.assertRaises(ContractViolation):
            turn(bridge)
        self.assertEqual(worker.generation_calls,1)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)
        worker.turn=original
        worker.spine.backend.model_digest=MODEL
        replayed=turn(bridge)
        self.assertTrue(replayed["replayed"])
        self.assertEqual(worker.generation_calls,1)

    def test_postcommit_tokenizer_swap_also_holds_native_output(self):
        worker,bridge=fixture()
        original=worker.turn
        def switch_after_commit(*args,**kwargs):
            result=original(*args,**kwargs)
            worker.spine.backend.tokenizer_digest="c"*64
            return result
        worker.turn=switch_after_commit
        with self.assertRaises(ContractViolation):
            turn(bridge)
        self.assertEqual(worker.generation_calls,1)
        worker.turn=original
        worker.spine.backend.tokenizer_digest=TOKENIZER
        self.assertEqual(turn(bridge)["output_sha256"],OUTPUT_SHA)
        self.assertEqual(worker.generation_calls,1)

    def test_foreign_principal_cannot_publish_previous_model_result(self):
        worker,bridge=fixture()
        worker.spine.identity.subject="other_operator"
        with self.assertRaises(ContractViolation):
            turn(bridge)
        self.assertEqual(worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
