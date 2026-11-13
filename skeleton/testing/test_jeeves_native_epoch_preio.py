"""Fail-closed source/model epoch guards around real native generation path.

These tests use deterministic simulated backends. No live GGUF, installed
rights, device-pressure, Windows/WSL2 or release certification is inferred.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.jeeves.agent.native_provider import NativeJeevesProvider
from skeleton.jeeves.agent.provider import ProviderError
from skeleton.testing.test_jeeves_native_provider_bridge import (
    MODEL, SimulatedWorker, request,
)

class EpochBeforeIOTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.native=NativeJeevesProvider(self.worker)

    def test_model_epoch_change_after_initial_admission_blocks_session_create(self):
        with mock.patch.object(
            self.native,"available",side_effect=(True,False)
        ) as check:
            with self.assertRaisesRegex(ProviderError,"before admission"):
                self.native.complete(request())
        self.assertEqual(check.call_count,2)
        self.assertEqual(len(self.worker.spine.sessions),0)
        self.assertEqual(self.worker.spine.generations,0)

    def test_tokenizer_change_before_io_never_starts_native(self):
        original=self.native.available
        state={"calls":0}
        def change_on_second_check():
            state["calls"]+=1
            if state["calls"]==2:
                self.worker.spine.backend.tokenizer_digest="c"*64
            return original()
        with mock.patch.object(self.native,"available",side_effect=change_on_second_check):
            with self.assertRaises(ProviderError):
                self.native.complete(request(request_id="tokenizer_changed"))
        self.assertFalse(self.worker.spine.sessions)
        self.assertEqual(self.worker.spine.generations,0)

    def test_backend_identity_failure_is_not_a_prompt_fallback(self):
        self.worker.spine.backend.model_digest="d"*64
        with self.assertRaises(ProviderError):
            self.native.complete(request())
        self.assertEqual(self.worker.spine.generations,0)
        self.assertEqual(len(self.native._attempted),0)

if __name__=="__main__":
    unittest.main()
