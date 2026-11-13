"""Admission ordering for canonical local-first one-shot native inference.

The in-memory worker is a test double; results are not installed GGUF,
rights review, device qualification or release certification.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.run_once import (
    generate_once,
)
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER, OUTPUT_SHA,
)


class OneShotNewSessionAdmission(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()

    def test_valid_new_work_creates_one_session_and_one_commit(self):
        response=generate_once(self.worker,"private test-only task")
        self.assertIn(response["session_id"],self.worker.spine.created)
        self.assertTrue(response["request_id"].startswith("r_"))
        self.assertEqual(len(response["request_id"]),34)
        self.assertEqual(response["model_source"],"actual-offline-GGUF")
        self.assertEqual(response["receipt"]["output_sha256"],OUTPUT_SHA)
        self.assertFalse(response["receipt"]["replayed"])
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.receipts),1)

    def test_custom_request_identity_never_generates_more_than_once(self):
        response=generate_once(
            self.worker,"private",request_id="caller_chosen"
        )
        self.assertEqual(response["request_id"],"caller_chosen")
        self.assertEqual(len(self.worker.spine.created),1)
        self.assertEqual(self.worker.generation_calls,1)

    def test_random_request_generated_before_any_spine_write(self):
        class WatchCreate:
            saw_random=False
            def __init__(self,original):
                self.original=original
            def __call__(self,*args,**kwargs):
                self.saw_random=True
                return self.original(*args,**kwargs)
        watcher=WatchCreate(self.worker.spine.create)
        with mock.patch.object(self.worker.spine,"create",side_effect=watcher):
            result=generate_once(self.worker,"private")
        self.assertTrue(watcher.saw_random)
        self.assertTrue(result["request_id"].startswith("r_"))
        self.assertEqual(self.worker.generation_calls,1)

    def test_model_epoch_change_rejects_before_new_session(self):
        self.worker.spine.backend.tokenizer_digest="c"*64
        with self.assertRaises(ContractViolation):
            generate_once(self.worker,"private")
        self.assertEqual(self.worker.generation_calls,0)
        self.assertFalse(self.worker.spine.created)

    def test_source_output_does_not_claim_device_or_release_certification(self):
        result=generate_once(self.worker,"private")
        self.assertNotIn("release_certified",result)
        self.assertNotIn("device_qualified",result)
        self.assertEqual(result["receipt"]["model_sha256"],MODEL)
        self.assertEqual(result["receipt"]["tokenizer_sha256"],TOKENIZER)

if __name__ == "__main__":
    unittest.main()
