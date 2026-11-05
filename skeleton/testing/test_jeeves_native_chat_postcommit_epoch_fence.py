"""Native chat cannot expose or mutate a stale source/principal session.

All source, inference and SQLite observations are synthetic in these tests.
Neither a fake backend nor an accepted test proves physical GGUF readiness.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.jeeves.agent.native_chat import NativeChatHold, NativeJeevesChat
from skeleton.testing.test_jeeves_native_provider_bridge import (
    MODEL, TOKENIZER, SimulatedWorker,
)

class NativeChatPostCommitIdentityTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.chat=NativeJeevesChat(self.worker)

    def test_model_swap_after_native_commit_holds_output_before_disclosure(self):
        old=self.worker.turn
        def change_on_commit(*args,**kwargs):
            output=old(*args,**kwargs)
            self.worker.spine.backend.model_digest="c"*64
            return output
        self.worker.turn=change_on_commit
        with self.assertRaises(NativeChatHold):
            self.chat.turn("private request",request_id="first")
        self.assertEqual(self.worker.spine.generations,1)
        self.assertEqual(len(self.worker.spine.turns),1)
        self.worker.turn=old
        self.worker.spine.backend.model_digest=MODEL
        replay=self.chat.turn("private request",request_id="first")
        self.assertTrue(replay.replayed)
        self.assertEqual(self.worker.spine.generations,1)
        self.assertFalse(replay.to_record()["release_certified"])

    def test_tokenizer_swap_after_native_commit_is_also_held(self):
        old=self.worker.turn
        def change_on_commit(*args,**kwargs):
            receipt=old(*args,**kwargs)
            self.worker.spine.backend.tokenizer_digest="d"*64
            return receipt
        self.worker.turn=change_on_commit
        with self.assertRaises(NativeChatHold):
            self.chat.turn("private request",request_id="token")
        self.assertEqual(self.worker.spine.generations,1)
        self.worker.turn=old
        self.worker.spine.backend.tokenizer_digest=TOKENIZER
        replay=self.chat.turn("private request",request_id="token")
        self.assertTrue(replay.replayed)
        self.assertEqual(self.worker.spine.generations,1)

    def test_replayed_answer_denied_if_identity_changes_during_read(self):
        old="prior session answer"
        self.chat.turn(old,request_id="replay")
        original=self.worker.spine.replay
        def swap_after_read(*args,**kwargs):
            value=original(*args,**kwargs)
            self.worker.spine.backend.model_digest="e"*64
            return value
        with mock.patch.object(self.worker.spine,"replay",side_effect=swap_after_read):
            with self.assertRaises(NativeChatHold):
                self.chat.turn(old,request_id="replay")
        self.assertEqual(self.worker.spine.generations,1)

    def test_untrusted_chat_history_still_has_no_device_certificate(self):
        result=self.chat.turn("hello",request_id="normal")
        self.assertFalse(result.to_record()["device_qualified"])
        self.assertFalse(result.to_record()["release_certified"])
        self.assertEqual(result.model_sha256,MODEL)

if __name__=="__main__":
    unittest.main()
