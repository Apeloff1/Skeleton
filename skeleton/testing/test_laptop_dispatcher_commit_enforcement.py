"""Source-bound laptop dispatcher tests, simulated native backend only.

No live GGUF, physical Windows/WSL2, source-rights, device or release claims.
All successful worker responses must independently match durable SQLite replay.
"""
from __future__ import annotations

from hashlib import sha256
from unittest import mock
import unittest

from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER, OUTPUT, OUTPUT_SHA,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import (
    LaptopDispatcher,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)


def fixture():
    worker = FakeWorker()
    api = LaptopDispatcher(worker)
    session = api.dispatch("create", {})["session_id"]
    request = {"session_id": session, "request_id": "test1", "prompt": "private"}
    return worker, api, request


class CommitSafetyTests(unittest.TestCase):
    def test_first_turn_requires_independent_sqlite_commit(self):
        worker,api,request=fixture()
        first=api.dispatch("turn",request)["receipt"]
        self.assertEqual(worker.generation_calls,1)
        self.assertEqual(first["text"],OUTPUT)
        self.assertEqual(first["output_sha256"],OUTPUT_SHA)
        saved=api.dispatch("replay",request)
        self.assertTrue(saved["found"])
        self.assertTrue(saved["replay"]["replayed"])
        self.assertEqual(worker.generation_calls,1)

    def test_native_output_without_commit_denied(self):
        worker,api,request=fixture()
        before=worker.turn
        def uncommitted(*args,**kwargs):
            out=before(*args,**kwargs)
            worker.spine.receipts.clear()
            return out
        worker.turn=uncommitted
        with self.assertRaisesRegex(ContractViolation,"missing a committed"):
            api.dispatch("turn",request)
        self.assertEqual(worker.generation_calls,1)
        self.assertFalse(worker.spine.receipts)

    def test_fake_valid_worker_output_with_mismatched_sqlite_text_denied(self):
        worker,api,request=fixture()
        original=worker.turn
        def tamper_after_commit(*args,**kwargs):
            outcome=original(*args,**kwargs)
            altered="different text but hash aligned"
            key=next(iter(worker.spine.receipts))
            worker.spine.receipts[key]["text"]=altered
            worker.spine.receipts[key]["output_sha256"]=sha256(altered.encode()).hexdigest()
            return outcome
        worker.turn=tamper_after_commit
        with self.assertRaisesRegex(ContractViolation,"differs"):
            api.dispatch("turn",request)
        self.assertEqual(worker.generation_calls,1)

    def test_committed_token_accounting_disagreement_denied(self):
        worker,api,request=fixture()
        real=worker.turn
        def tampered_tokens(*args,**kwargs):
            produced=real(*args,**kwargs)
            key=next(iter(worker.spine.receipts))
            worker.spine.receipts[key]["generated_tokens"]=2
            return produced
        worker.turn=tampered_tokens
        with self.assertRaisesRegex(ContractViolation,"differs"):
            api.dispatch("turn",request)
        self.assertEqual(worker.generation_calls,1)

    def test_duplicate_request_only_replays_no_new_forward_pass(self):
        worker,api,request=fixture()
        first=api.dispatch("turn",request)
        next_=api.dispatch("turn",request)
        self.assertEqual(next_["receipt"]["output_sha256"],
                         first["receipt"]["output_sha256"])
        self.assertTrue(next_["receipt"]["replayed"])
        self.assertEqual(worker.generation_calls,1)

    def test_read_only_replay_requires_explicit_committed_flag(self):
        worker,api,request=fixture()
        api.dispatch("turn",request)
        original=worker.spine.replay
        def falsify(*args,**kwargs):
            result=original(*args,**kwargs)
            result["replayed"]=False
            return result
        with mock.patch.object(worker.spine,"replay",side_effect=falsify):
            with self.assertRaisesRegex(ContractViolation,"marked replayed"):
                api.dispatch("replay",request)
        self.assertEqual(worker.generation_calls,1)

if __name__ == "__main__":
    unittest.main()
