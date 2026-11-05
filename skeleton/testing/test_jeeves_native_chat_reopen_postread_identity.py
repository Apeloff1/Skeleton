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


class ReopenPostHistoryFence(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.owner=NativeJeevesChat(self.worker)
        self.owner.turn("previous request",request_id="saved")

    def test_epoch_swapped_during_reopen_is_held(self):
        original=self.worker.spine.history
        def swapped(*args,**kwargs):
            result=original(*args,**kwargs)
            self.worker.spine.backend.model_digest="d"*64
            return result
        with mock.patch.object(self.worker.spine,"history",side_effect=swapped):
            with self.assertRaises(NativeChatHold):
                NativeJeevesChat(self.worker,session_id=self.owner.session_id)
        self.assertEqual(self.worker.spine.generations,1)

    def test_tokenizer_swapped_during_reopen_is_held(self):
        original=self.worker.spine.history
        def swapped(*args,**kwargs):
            result=original(*args,**kwargs)
            self.worker.spine.backend.tokenizer_digest="c"*64
            return result
        with mock.patch.object(self.worker.spine,"history",side_effect=swapped):
            with self.assertRaises(NativeChatHold):
                NativeJeevesChat(self.worker,session_id=self.owner.session_id)
        self.assertEqual(self.worker.spine.generations,1)

    def test_healthy_reopen_reads_durable_history_without_regeneration(self):
        reopened=NativeJeevesChat(self.worker,session_id=self.owner.session_id)
        self.assertEqual(len(reopened.history()),2)
        self.assertEqual(self.worker.spine.generations,1)

    def test_missing_existing_session_never_created_implicitly(self):
        baseline=set(self.worker.spine.sessions)
        with self.assertRaises(Exception):
            NativeJeevesChat(self.worker,session_id="unknown")
        self.assertEqual(self.worker.spine.sessions,baseline)

if __name__=="__main__":
    unittest.main()
