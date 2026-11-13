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

class EpochAfterCommitTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.native=NativeJeevesProvider(self.worker)

    def test_committed_output_is_held_if_model_identity_changes_after_turn(self):
        original=self.worker.turn
        def mutate_after_commit(*args,**kwargs):
            result=original(*args,**kwargs)
            self.worker.spine.backend.model_digest="c"*64
            return result
        self.worker.turn=mutate_after_commit
        r=request("private native task",request_id="transition")
        with self.assertRaisesRegex(ProviderError,"during generation"):
            self.native.complete(r)
        self.assertEqual(self.worker.spine.generations,1)
        self.assertEqual(len(self.worker.spine.turns),1)
        self.assertEqual(len(self.native._attempted),1)
        self.worker.spine.backend.model_digest=MODEL
        self.worker.turn=original
        replay=NativeJeevesProvider(self.worker).complete(r)
        self.assertTrue(replay.cached)
        self.assertEqual(self.worker.spine.generations,1)
        self.assertFalse(replay.metadata["release_certified"])

    def test_read_only_replay_is_also_bound_to_active_principal(self):
        r=request(request_id="saved")
        self.native.complete(r)
        observed=set(self.worker.spine.sessions)
        with mock.patch.object(
            self.native,"available",side_effect=(True,True,False)
        ):
            with self.assertRaisesRegex(ProviderError,"during generation"):
                self.native.complete(r)
        self.assertEqual(self.worker.spine.sessions,observed)
        self.assertEqual(self.worker.spine.generations,1)

    def test_committed_native_effect_not_retried_after_held_output(self):
        r=request(request_id="one_generation")
        original=self.worker.turn
        def swap(*args,**kwargs):
            out=original(*args,**kwargs)
            self.worker.spine.backend.model_digest="e"*64
            return out
        self.worker.turn=swap
        with self.assertRaises(ProviderError):
            self.native.complete(r)
        with self.assertRaises(ProviderError):
            self.native.complete(r)
        self.assertEqual(self.worker.spine.generations,1)

if __name__=="__main__":
    unittest.main()
