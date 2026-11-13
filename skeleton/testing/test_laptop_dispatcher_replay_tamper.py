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


class ReplayTamperTests(unittest.TestCase):
    def test_replay_wrong_model_digest_denied(self):
        worker,api,request=fixture()
        api.dispatch("turn",request)
        old=worker.spine.replay
        def fake(*args,**kwargs):
            saved=old(*args,**kwargs)
            saved["model_sha256"]="e"*64
            return saved
        with mock.patch.object(worker.spine,"replay",side_effect=fake):
            with self.assertRaises(ContractViolation):
                api.dispatch("replay",request)
        self.assertEqual(worker.generation_calls,1)

    def test_replay_wrong_tokenizer_digest_denied(self):
        worker,api,request=fixture()
        api.dispatch("turn",request)
        old=worker.spine.replay
        def fake(*args,**kwargs):
            saved=old(*args,**kwargs)
            saved["tokenizer_sha256"]="e"*64
            return saved
        with mock.patch.object(worker.spine,"replay",side_effect=fake):
            with self.assertRaises(ContractViolation):
                api.dispatch("replay",request)
        self.assertEqual(worker.generation_calls,1)

    def test_replay_corrupted_payload_hash_denied(self):
        worker,api,request=fixture()
        api.dispatch("turn",request)
        old=worker.spine.replay
        def fake(*args,**kwargs):
            saved=old(*args,**kwargs)
            saved["text"]="not the committed text"
            return saved
        with mock.patch.object(worker.spine,"replay",side_effect=fake):
            with self.assertRaises(ContractViolation):
                api.dispatch("replay",request)
        self.assertEqual(worker.generation_calls,1)

    def test_read_only_missing_replay_is_a_negative_result(self):
        worker,api,request=fixture()
        report=api.dispatch("replay",request)
        self.assertFalse(report["found"])
        self.assertIsNone(report["replay"])
        self.assertEqual(worker.generation_calls,0)

    def test_no_new_sqlite_session_on_replay_probe(self):
        worker,api,request=fixture()
        before=set(worker.spine.created)
        for _ in range(8):
            output=api.dispatch("replay",request)
            self.assertFalse(output["found"])
            self.assertEqual(worker.spine.created,before)
        self.assertEqual(worker.generation_calls,0)

    def test_changed_prompt_is_not_treated_as_a_committed_replay(self):
        worker,api,request=fixture()
        api.dispatch("turn",request)
        changed=dict(request)
        changed["prompt"]="unrelated"
        output=api.dispatch("replay",changed)
        self.assertFalse(output["found"])
        self.assertEqual(worker.generation_calls,1)

if __name__ == "__main__":
    unittest.main()
