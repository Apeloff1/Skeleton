"""Jeeves chat must surface missing native SQLite commits as explicit holds.

Synthetic worker tests only: no real GGUF, Windows device, installer or rights
qualification. The canonical supervisor retains pending/commit/replay authority.
"""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Conflict
from skeleton.jeeves.agent.native_chat import NativeChatHold, NativeJeevesChat
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, MODEL, TOKENIZER,
)


class TestChatCommitHold(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.chat = NativeJeevesChat(self.worker)

    def test_uncommitted_native_output_returns_public_chat_hold(self):
        self.worker.spine.return_without_commit = True
        with self.assertRaisesRegex(NativeChatHold, "durable receipt"):
            self.chat.turn("private question", request_id="missing_commit")
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(len(self.worker.spine.turns), 0)
        self.assertIn(
            (self.chat.session_id, "missing_commit"),
            self.worker.spine.pending,
        )

    def test_uncommitted_attempt_is_never_reissued(self):
        self.worker.spine.return_without_commit = True
        with self.assertRaises(NativeChatHold):
            self.chat.turn("private question", request_id="pending")
        with self.assertRaises(Conflict):
            self.chat.turn("private question", request_id="pending")
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(len(self.worker.spine.turns), 0)

    def test_uncertain_backend_error_is_not_reclassified_or_retried(self):
        self.worker.spine.fail_uncertain = True
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.chat.turn("question", request_id="uncertain")
        self.assertEqual(self.worker.spine.generations, 1)
        with self.assertRaises(Conflict):
            self.chat.turn("question", request_id="uncertain")
        self.assertEqual(self.worker.spine.generations, 1)

    def test_only_lower_contract_violation_is_translated(self):
        # Identity/claim mismatches from the lower native bridge are public
        # holds, but an unrelated backend error cannot be silently changed
        # into a successful or retryable result.
        def deny(*args, **kwargs):
            raise ContractViolation("uncommitted private native evidence")
        self.chat.bridge.turn = deny
        with self.assertRaisesRegex(NativeChatHold, "durable receipt") as cm:
            self.chat.turn("some question", request_id="bad_receipt")
        self.assertIsInstance(cm.exception.__cause__, ContractViolation)
        self.assertEqual(self.worker.spine.generations, 0)
        self.assertEqual(len(self.worker.spine.turns), 0)

    def test_successful_native_and_replay_are_still_single_generation(self):
        first = self.chat.turn("hello", request_id="committed")
        second = self.chat.turn("hello", request_id="committed")
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(first.output_sha256, second.output_sha256)
        self.assertEqual(first.model_sha256, MODEL)
        self.assertEqual(second.tokenizer_sha256, TOKENIZER)
        self.assertFalse(first.to_record()["device_qualified"])
        self.assertFalse(second.to_record()["release_certified"])
        self.assertEqual(self.worker.spine.generations, 1)

    def test_bad_stale_native_source_never_yields_private_chat_answer(self):
        self.worker.spine.backend.model_digest = "c" * 64
        with self.assertRaises(NativeChatHold):
            self.chat.turn("private task", request_id="stale")
        self.assertEqual(self.worker.spine.generations, 0)


if __name__ == "__main__":
    unittest.main()
