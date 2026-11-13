"""Native Jeeves chat post-I/O epoch swap safety, synthetic source tests.

Even committed SQLite output cannot be disclosed or rebound to a different
operator/model/tokenizer. No physical model inference or device qualification.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.jeeves.agent.native_chat import NativeChatHold, NativeJeevesChat
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, MODEL, TOKENIZER,
)


class ClosePostMutationFence(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.chat=NativeJeevesChat(self.worker)

    def test_model_epoch_change_after_close_is_not_falsely_reported(self):
        native=self.worker.spine.close
        def changed(*args,**kwargs):
            status=native(*args,**kwargs)
            self.worker.spine.backend.model_digest="c"*64
            return status
        with mock.patch.object(self.worker.spine,"close",side_effect=changed) as close:
            with self.assertRaises(NativeChatHold):
                self.chat.close()
            close.assert_called_once()
        self.assertTrue(self.chat._closed)
        self.assertIn(self.chat.session_id,self.worker.spine.closed_sessions)

    def test_tokenizer_swap_during_close_is_held(self):
        native=self.worker.spine.close
        def changed(*args,**kwargs):
            status=native(*args,**kwargs)
            self.worker.spine.backend.tokenizer_digest="d"*64
            return status
        with mock.patch.object(self.worker.spine,"close",side_effect=changed) as close:
            with self.assertRaises(NativeChatHold):
                self.chat.close()
            close.assert_called_once()
        self.assertTrue(self.chat._closed)

    def test_close_after_owner_restored_cannot_repeat_sqlite_mutation(self):
        native=self.worker.spine.close
        def changed(*args,**kwargs):
            status=native(*args,**kwargs)
            self.worker.spine.backend.model_digest="c"*64
            return status
        with mock.patch.object(self.worker.spine,"close",side_effect=changed):
            with self.assertRaises(NativeChatHold):
                self.chat.close()
        self.worker.spine.backend.model_digest=MODEL
        self.assertFalse(self.chat.close())
        self.assertIn(self.chat.session_id,self.worker.spine.closed_sessions)

    def test_normal_close_returns_real_boolean(self):
        self.assertTrue(self.chat.close())
        self.assertFalse(self.chat.close())
        self.assertEqual(self.worker.spine.generations,0)

if __name__=="__main__":
    unittest.main()
