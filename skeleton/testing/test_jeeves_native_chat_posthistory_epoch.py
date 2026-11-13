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


class HistoryPostReadFence(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.chat=NativeJeevesChat(self.worker)
        self.chat.turn("private content",request_id="first")

    def test_backend_swap_during_sqlite_read_denies_private_history(self):
        prior=self.worker.spine.history
        def changed(*args,**kwargs):
            result=prior(*args,**kwargs)
            self.worker.spine.backend.model_digest="c"*64
            return result
        with mock.patch.object(self.worker.spine,"history",side_effect=changed):
            with self.assertRaises(NativeChatHold):
                self.chat.history()
        self.assertEqual(self.worker.spine.generations,1)

    def test_tokenizer_swap_during_history_read_also_denies(self):
        prior=self.worker.spine.history
        def changed(*args,**kwargs):
            result=prior(*args,**kwargs)
            self.worker.spine.backend.tokenizer_digest="d"*64
            return result
        with mock.patch.object(self.worker.spine,"history",side_effect=changed):
            with self.assertRaises(NativeChatHold):
                self.chat.history()
        self.assertEqual(self.worker.spine.generations,1)

    def test_same_principal_read_remains_available(self):
        self.assertEqual(len(self.chat.history()),2)
        self.assertEqual(self.worker.spine.generations,1)

    def test_restored_identity_does_not_generate_again(self):
        self.worker.spine.backend.model_digest="c"*64
        with self.assertRaises(NativeChatHold):
            self.chat.history()
        self.worker.spine.backend.model_digest=MODEL
        self.assertEqual(len(self.chat.history()),2)
        self.assertEqual(self.worker.spine.generations,1)

if __name__=="__main__":
    unittest.main()
