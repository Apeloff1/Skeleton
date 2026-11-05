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

class NativeChatHistoryFenceTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.chat=NativeJeevesChat(self.worker)
        self.chat.turn("private history",request_id="history1")

    def test_model_change_denies_history_before_authoritative_read(self):
        self.worker.spine.backend.model_digest="c"*64
        with mock.patch.object(self.worker.spine,"history") as history:
            with self.assertRaises(NativeChatHold):
                self.chat.history()
            history.assert_not_called()
        self.assertEqual(self.worker.spine.generations,1)

    def test_tokenizer_change_denies_history_before_sqlite_read(self):
        self.worker.spine.backend.tokenizer_digest="d"*64
        with mock.patch.object(self.worker.spine,"history") as history:
            with self.assertRaises(NativeChatHold):
                self.chat.history(maximum_messages=3)
            history.assert_not_called()

    def test_recovery_restores_authoritative_read_without_new_generation(self):
        self.worker.spine.backend.model_digest="e"*64
        with self.assertRaises(NativeChatHold):
            self.chat.history()
        self.worker.spine.backend.model_digest=MODEL
        records=self.chat.history(maximum_messages=2)
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]["content"],"private history")
        self.assertEqual(self.worker.spine.generations,1)

    def test_foreign_active_identity_cannot_read_existing_session(self):
        self.worker.spine.identity=self.worker.spine.identity.__class__(
            "local","different",MODEL,TOKENIZER
        )
        with mock.patch.object(self.worker.spine,"history") as history:
            with self.assertRaises(NativeChatHold):
                self.chat.history()
            history.assert_not_called()

if __name__=="__main__":
    unittest.main()
