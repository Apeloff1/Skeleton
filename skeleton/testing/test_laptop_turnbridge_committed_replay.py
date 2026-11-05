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


class CommittedReplayTests(unittest.TestCase):
    def test_first_turn_matches_independent_native_sqlite_replay(self):
        worker,bridge=fixture()
        produced=turn(bridge)
        self.assertEqual(produced["model_sha256"],MODEL)
        self.assertEqual(produced["tokenizer_sha256"],TOKENIZER)
        self.assertEqual(produced["output_sha256"],OUTPUT_SHA)
        self.assertEqual(worker.generation_calls,1)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

    def test_committed_replay_cannot_trigger_new_generation(self):
        worker,bridge=fixture()
        first=turn(bridge)
        replay=turn(bridge)
        self.assertEqual(first["output_sha256"],replay["output_sha256"])
        self.assertIs(replay["replayed"],True)
        self.assertEqual(worker.generation_calls,1)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

    def test_worker_result_without_durable_commit_is_held(self):
        worker,bridge=fixture()
        original=worker.turn
        def no_commit(*args,**kwargs):
            result=original(*args,**kwargs)
            worker.spine.receipts.clear()
            return result
        worker.turn=no_commit
        with self.assertRaisesRegex(ContractViolation,"authoritative SQLite"):
            turn(bridge)
        self.assertEqual(worker.generation_calls,1)
        self.assertFalse(worker.spine.receipts)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

    def test_valid_but_different_worker_and_committed_results_are_held(self):
        worker,bridge=fixture()
        original=worker.turn
        def altered_native(*args,**kwargs):
            output=original(*args,**kwargs)
            text="different output with a matching self-hash"
            output["text"]=text
            output["output_sha256"]=sha256(text.encode()).hexdigest()
            return output
        worker.turn=altered_native
        with self.assertRaisesRegex(ContractViolation,"differs from durable"):
            turn(bridge)
        self.assertEqual(worker.generation_calls,1)
        self.assertEqual(bridge.guard.snapshot()["pending"],0)

    def test_replayed_receipt_cannot_have_false_replay_marker(self):
        worker,bridge=fixture()
        original=worker.spine.replay
        def bad_flag(*args,**kwargs):
            saved=original(*args,**kwargs)
            saved["replayed"]=False
            return saved
        with mock.patch.object(worker.spine,"replay",side_effect=bad_flag):
            with self.assertRaisesRegex(ContractViolation,"marked committed"):
                turn(bridge)
        self.assertEqual(worker.generation_calls,1)

    def test_corrupted_committed_output_cannot_be_disclosed(self):
        worker,bridge=fixture()
        original=worker.turn
        def corrupt_commit(*args,**kwargs):
            output=original(*args,**kwargs)
            key=next(iter(worker.spine.receipts))
            saved=worker.spine.receipts[key]
            saved["text"]="corrupted private result"
            return output
        worker.turn=corrupt_commit
        with self.assertRaises(ContractViolation):
            turn(bridge)
        self.assertEqual(worker.generation_calls,1)

if __name__=="__main__":
    unittest.main()
