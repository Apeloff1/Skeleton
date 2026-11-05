"""Jeeves conversational path against an explicitly fake native turn source.

Tests only receipt-custody behavior, not llama.cpp or device qualification.
"""
from __future__ import annotations

from hashlib import sha256
import unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Conflict
from skeleton.jeeves.agent.native_chat import NativeChatHold, NativeJeevesChat
from skeleton.jeeves.agent.native_receipt_boundary import NativeReceiptError
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


class TestNativeChatSession(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.chat = NativeJeevesChat(self.worker)

    def test_new_native_session_allocates_owned_identity(self):
        self.assertIn(self.chat.session_id, self.worker.spine.sessions)
        self.assertEqual(self.chat.identity.tenant, "local")
        self.assertEqual(self.chat.identity.subject, "operator")

    def test_first_plain_turn_committed_and_mirrored(self):
        out = self.chat.turn("Hello local Jeeves!", request_id="r_first")
        self.assertEqual(out.session_id, self.chat.session_id)
        self.assertEqual(out.request_id, "r_first")
        self.assertEqual(out.text, self.worker.spine.generated_text)
        self.assertEqual(out.output_sha256, sha256(out.text.encode()).hexdigest())
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertFalse(out.replayed)
        self.assertTrue(out.to_record()["authoritative_commit"])
        self.assertFalse(out.to_record()["device_qualified"])

    def test_repeat_receipt_requires_no_second_inference(self):
        first = self.chat.turn("Hello", request_id="r_repeat")
        second = self.chat.turn("Hello", request_id="r_repeat")
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(second.output_sha256, first.output_sha256)
        self.assertEqual(self.worker.spine.generations, 1)

    def test_resume_bound_session_after_reopen(self):
        self.chat.turn("first", request_id="r1")
        resumed = NativeJeevesChat(self.worker, session_id=self.chat.session_id)
        second = resumed.turn("second", request_id="r2")
        self.assertEqual(second.request_id, "r2")
        self.assertEqual(len(resumed.history()), 4)
        self.assertEqual(self.worker.spine.generations, 2)

    def test_foreign_or_missing_session_refused(self):
        with self.assertRaises(Conflict):
            NativeJeevesChat(self.worker, session_id="s_doesnotexist")

    def test_history_bounded_without_silent_drop(self):
        self.chat.turn("first", request_id="r1")
        self.chat.turn("second", request_id="r2")
        with self.assertRaises(NativeChatHold):
            self.chat.history(maximum_messages=2)
        self.assertEqual(len(self.chat.history(maximum_messages=4)), 4)

    def test_changed_prompt_under_same_request_denied(self):
        self.chat.turn("first", request_id="r1")
        with self.assertRaises(Conflict):
            self.chat.turn("second", request_id="r1")
        self.assertEqual(self.worker.spine.generations, 1)

    def test_receipt_hash_tampering_denied(self):
        self.chat.turn("first", request_id="r1")
        self.worker.spine.tamper_committed = True
        with self.assertRaises(NativeReceiptError):
            self.chat.turn("first", request_id="r1")

    def test_worker_claim_without_db_commit_denied(self):
        self.worker.spine.return_without_commit = True
        with self.assertRaises(NativeChatHold):
            self.chat.turn("first", request_id="r_uncommitted")
        self.assertEqual(self.worker.spine.generations, 1)
        with self.assertRaises(Conflict):
            self.chat.turn("first", request_id="r_uncommitted")
        self.assertEqual(self.worker.spine.generations, 1)

    def test_uncertain_native_error_is_never_retried_by_adapter(self):
        self.worker.spine.fail_uncertain = True
        with self.assertRaises(RuntimeError):
            self.chat.turn("first", request_id="r_uncertain")
        with self.assertRaises(Conflict):
            self.chat.turn("first", request_id="r_uncertain")
        self.assertEqual(self.worker.spine.generations, 1)

    def test_session_close_is_durable_and_idempotent(self):
        self.chat.turn("first", request_id="r1")
        self.assertTrue(self.chat.close())
        self.assertFalse(self.chat.close())
        with self.assertRaises(NativeChatHold):
            self.chat.turn("second", request_id="r2")
        with self.assertRaises(NativeChatHold):
            self.chat.history()

    def test_closed_session_cannot_be_reused_for_native_generation(self):
        self.chat.close()
        reopened = NativeJeevesChat(self.worker, session_id=self.chat.session_id)
        with self.assertRaises(Conflict):
            reopened.turn("hello", request_id="r1")

    def test_inactive_model_refused_before_turn(self):
        self.worker.spine.backend.model_digest = "c" * 64
        with self.assertRaises(ValueError):
            self.chat.turn("hello", request_id="r_change")
        self.assertEqual(self.worker.spine.generations, 0)

    def test_invalid_sampler_parameter(self):
        with self.assertRaises(ValueError):
            self.chat.turn("hello", request_id="r1", temperature=0)
        with self.assertRaises(ValueError):
            self.chat.turn("hello", request_id="r1", seed=-1)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_empty_message_refused(self):
        with self.assertRaises(ValueError):
            self.chat.turn(" \n ", request_id="r1")
        self.assertEqual(self.worker.spine.generations, 0)


if __name__ == "__main__":
    unittest.main()
