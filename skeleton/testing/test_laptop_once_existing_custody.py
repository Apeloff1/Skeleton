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


class OneShotExistingCustody(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.worker.spine.create("s_authorized")

    def test_explicit_existing_session_keeps_exact_identifier(self):
        response=generate_once(
            self.worker,"private local work",
            session="s_authorized",request_id="req_existing",
        )
        self.assertEqual(response["session_id"],"s_authorized")
        self.assertEqual(response["request_id"],"req_existing")
        self.assertEqual(response["receipt"]["model_sha256"],MODEL)
        self.assertEqual(response["receipt"]["tokenizer_sha256"],TOKENIZER)
        self.assertEqual(response["receipt"]["output_sha256"],OUTPUT_SHA)
        self.assertEqual(len(self.worker.spine.created),1)
        self.assertEqual(self.worker.generation_calls,1)

    def test_exact_same_id_is_replayed_without_a_new_native_call(self):
        first=generate_once(self.worker,"private",session="s_authorized",
                            request_id="same")
        replay=generate_once(self.worker,"private",session="s_authorized",
                             request_id="same")
        self.assertEqual(first["receipt"]["output_sha256"],
                         replay["receipt"]["output_sha256"])
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.created),1)

    def test_changed_prompt_with_same_id_cannot_claim_old_commit(self):
        generate_once(self.worker,"first prompt",session="s_authorized",
                      request_id="duplicate")
        with self.assertRaises(Exception):
            generate_once(self.worker,"changed prompt",session="s_authorized",
                          request_id="duplicate")
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.created),1)

    def test_unknown_explicit_session_is_never_created_implicitly(self):
        with self.assertRaises(Exception):
            generate_once(self.worker,"private",session="missing_session",
                          request_id="valid")
        self.assertNotIn("missing_session",self.worker.spine.created)
        self.assertEqual(len(self.worker.spine.created),1)
        self.assertEqual(self.worker.generation_calls,0)

    def test_uncommitted_native_response_is_not_published(self):
        original=self.worker.turn
        def uncommitted(*args,**kwargs):
            output=original(*args,**kwargs)
            self.worker.spine.receipts.clear()
            return output
        self.worker.turn=uncommitted
        with self.assertRaises(ContractViolation):
            generate_once(self.worker,"private",session="s_authorized",
                          request_id="orphan")
        self.assertEqual(self.worker.generation_calls,1)
        self.assertFalse(self.worker.spine.receipts)

    def test_stale_model_cannot_do_native_turn_under_prior_session(self):
        self.worker.spine.backend.model_digest="e"*64
        with mock.patch.object(self.worker,"turn") as inference:
            with self.assertRaises(ContractViolation):
                generate_once(self.worker,"valid",session="s_authorized",
                              request_id="source_change")
            inference.assert_not_called()
        self.assertEqual(len(self.worker.spine.created),1)

if __name__ == "__main__":
    unittest.main()
