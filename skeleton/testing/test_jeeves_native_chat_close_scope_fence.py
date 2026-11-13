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

class NativeChatCloseFenceTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.chat=NativeJeevesChat(self.worker)

    def test_changed_backend_cannot_close_existing_durable_session(self):
        self.worker.spine.backend.model_digest="f"*64
        with mock.patch.object(self.worker.spine,"close") as close:
            with self.assertRaises(NativeChatHold):
                self.chat.close()
            close.assert_not_called()
        self.assertNotIn(self.chat.session_id,self.worker.spine.closed_sessions)

    def test_changed_tokenizer_cannot_close_chat(self):
        self.worker.spine.backend.tokenizer_digest="c"*64
        with mock.patch.object(self.worker.spine,"close") as close:
            with self.assertRaises(NativeChatHold):
                self.chat.close()
            close.assert_not_called()

    def test_restored_owner_can_close_the_exact_session_once(self):
        self.worker.spine.backend.model_digest="d"*64
        with self.assertRaises(NativeChatHold):
            self.chat.close()
        self.worker.spine.backend.model_digest=MODEL
        self.assertTrue(self.chat.close())
        self.assertIn(self.chat.session_id,self.worker.spine.closed_sessions)
        self.assertFalse(self.chat.close())

    def test_already_closed_chat_returns_false_without_new_io(self):
        self.assertTrue(self.chat.close())
        self.worker.spine.backend.model_digest="e"*64
        with mock.patch.object(self.worker.spine,"close") as close:
            self.assertFalse(self.chat.close())
            close.assert_not_called()

if __name__=="__main__":
    unittest.main()
