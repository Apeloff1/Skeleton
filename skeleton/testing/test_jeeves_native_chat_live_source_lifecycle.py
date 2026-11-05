"""Native chat source/SQLite lifecycle regressions with an explicitly mocked GGUF.

This runs source-only; installed source, rights, real model, device and release
readiness are never certified by these deterministic test doubles.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.jeeves.agent.native_chat import NativeChatHold, NativeJeevesChat
from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker, MODEL, TOKENIZER

SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64, "archive_sha256": "d" * 64,
    "source_sha": "e" * 40, "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


class LiveSourceChatTests(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.state = {"live": True, "checks": 0}
        def witness(*args):
            self.state["checks"] += 1
            if not self.state["live"]:
                raise ContractViolation("capacity lease revoked")
            return dict(SOURCE)
        self.witness = witness
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=witness,
        ):
            self.fence = NativeSourceFence(
                self.worker, object(), expected_tenant="local",
                expected_subject="operator",
            )

    def guarded(self):
        return mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=self.witness,
        )

    def chat(self):
        with self.guarded():
            return NativeJeevesChat(self.worker, source_fence=self.fence)

    def test_live_activated_chat_opens_one_session_without_generation(self):
        chat = self.chat()
        self.assertIs(chat.source_fence, self.fence)
        self.assertEqual(len(self.worker.spine.sessions), 1)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_revoked_installer_source_cannot_allocate_session(self):
        old = set(self.worker.spine.sessions)
        self.state["live"] = False
        with self.guarded(), self.assertRaises(ContractViolation):
            NativeJeevesChat(self.worker, source_fence=self.fence)
        self.assertEqual(set(self.worker.spine.sessions), old)

    def test_foreign_worker_fence_denies_session_creation(self):
        other = SimulatedWorker()
        with self.assertRaises(ContractViolation):
            NativeJeevesChat(other, source_fence=self.fence)
        self.assertEqual(len(other.spine.sessions), 0)

    def test_forged_fence_denied_without_session(self):
        with self.assertRaises(NativeChatHold):
            NativeJeevesChat(self.worker, source_fence=mock.Mock())
        self.assertEqual(len(self.worker.spine.sessions), 0)

    def test_source_revoked_during_replay_never_starts_native_inference(self):
        chat = self.chat()
        replay = self.worker.spine.replay
        def changed(*args, **kwargs):
            result = replay(*args, **kwargs)
            self.state["live"] = False
            return result
        with self.guarded(), mock.patch.object(
            self.worker.spine, "replay", side_effect=changed,
        ):
            with self.assertRaises(ContractViolation):
                chat.turn("private", request_id="one")
        self.assertEqual(self.worker.spine.generations, 0)

    def test_source_revoked_after_commit_never_returns_private_answer(self):
        chat = self.chat()
        original = self.worker.turn
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.state["live"] = False
            return result
        with self.guarded(), mock.patch.object(
            self.worker, "turn", side_effect=changed,
        ):
            with self.assertRaises(ContractViolation):
                chat.turn("secret task", request_id="one")
        self.assertEqual(self.worker.spine.generations, 1)

    def test_live_source_read_then_revoked_history_is_held(self):
        chat = self.chat()
        with self.guarded():
            chat.turn("private", request_id="one")
        prior = self.worker.spine.history
        def changed(*args, **kwargs):
            result = prior(*args, **kwargs)
            self.state["live"] = False
            return result
        with self.guarded(), mock.patch.object(
            self.worker.spine, "history", side_effect=changed,
        ):
            with self.assertRaises(ContractViolation):
                chat.history()
        self.assertEqual(self.worker.spine.generations, 1)

    def test_close_revocation_not_acknowledged(self):
        chat = self.chat()
        prior = self.worker.spine.close
        def changed(*args, **kwargs):
            result = prior(*args, **kwargs)
            self.state["live"] = False
            return result
        with self.guarded(), mock.patch.object(
            self.worker.spine, "close", side_effect=changed,
        ):
            with self.assertRaises(ContractViolation):
                chat.close()
        self.assertTrue(chat._closed)
        self.assertIn(chat.session_id, self.worker.spine.closed_sessions)


    def test_revoked_chat_fence_cannot_resurrect_same_session(self):
        chat = self.chat()
        self.state["live"] = False
        with self.guarded(), self.assertRaises(ContractViolation):
            chat.history()
        self.state["live"] = True
        with self.guarded(), self.assertRaisesRegex(
            ContractViolation, "permanently revoked",
        ):
            chat.turn("new request", request_id="after")
        self.assertEqual(self.worker.spine.generations, 0)

    def test_model_swap_denied_without_touching_source_witness(self):
        chat = self.chat()
        self.worker.spine.backend.model_digest = "f" * 64
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=AssertionError("must not run for stale model"),
        ) as witness:
            with self.assertRaises(NativeChatHold):
                chat.history()
            witness.assert_not_called()

    def test_exact_duplicate_replay_uses_only_one_forward_pass(self):
        chat = self.chat()
        with self.guarded():
            first = chat.turn("hello", request_id="one")
            second = chat.turn("hello", request_id="one")
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(first.output_sha256, second.output_sha256)
        self.assertEqual(self.worker.spine.generations, 1)


if __name__ == "__main__":
    unittest.main()
