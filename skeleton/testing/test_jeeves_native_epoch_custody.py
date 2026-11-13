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

class EpochCustodyRegression(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()

    def test_replay_first_after_restore_never_generates_again(self):
        r=request(request_id="committed")
        provider=NativeJeevesProvider(self.worker)
        first=provider.complete(r)
        self.worker.spine.backend.model_digest="b"*64
        with self.assertRaises(ProviderError):
            provider.complete(r)
        self.worker.spine.backend.model_digest=MODEL
        again=NativeJeevesProvider(self.worker).complete(r)
        self.assertTrue(again.cached)
        self.assertEqual(first.content,again.content)
        self.assertEqual(self.worker.spine.generations,1)
        self.assertFalse(again.metadata["device_qualified"])

    def test_duplicate_request_id_with_changed_prompt_never_becomes_replay(self):
        provider=NativeJeevesProvider(self.worker)
        provider.complete(request("one",request_id="repeat"))
        with self.assertRaises(Exception):
            provider.complete(request("two",request_id="repeat"))
        self.assertEqual(self.worker.spine.generations,1)

    def test_uncertain_effect_remains_held_after_epoch_restoration(self):
        provider=NativeJeevesProvider(self.worker)
        self.worker.spine.fail_uncertain=True
        r=request(request_id="pending")
        with self.assertRaises(RuntimeError):
            provider.complete(r)
        self.worker.spine.fail_uncertain=False
        self.worker.spine.backend.model_digest="d"*64
        with self.assertRaises(ProviderError):
            provider.complete(r)
        self.worker.spine.backend.model_digest=MODEL
        with self.assertRaises(ProviderError):
            provider.complete(r)
        self.assertEqual(self.worker.spine.generations,1)

    def test_valid_principal_stays_available_without_remote_fallback(self):
        provider=NativeJeevesProvider(self.worker)
        result=provider.complete(request(request_id="healthy"))
        self.assertTrue(provider.available())
        self.assertEqual(result.provider,"jeeves_native")
        self.assertFalse(result.metadata["release_certified"])

if __name__=="__main__":
    unittest.main()
