"""No orphan native sessions on finite attempt quota denial.

The simulator is not a GGUF or device qualification witness. These tests
enforce a production state-mutation boundary against the canonical SQLite
spine contract and the existing host-guarded native provider.
"""
from __future__ import annotations

import unittest

from skeleton.jeeves.agent.native_provider import NativeJeevesProvider, native_provider_router
from skeleton.jeeves.agent.provider import ProviderError, ProviderExhausted
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, request,
)


class NativeQuotaIdentityTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()

    def test_missing_session_at_quota_never_becomes_a_sqlite_write(self):
        provider=NativeJeevesProvider(self.worker,maximum_attempts=1)
        provider.complete(request(request_id="first"))
        count=len(self.worker.spine.sessions)
        for n in range(5):
            with self.subTest(n=n),self.assertRaises(ProviderError):
                provider.complete(request(request_id="new_" + str(n)))
        self.assertEqual(len(self.worker.spine.sessions),count)

    def test_committed_replay_has_same_tenant_model_and_tokenizer(self):
        producer=NativeJeevesProvider(self.worker)
        old=request(request_id="saved")
        receipt=producer.complete(old)
        limited=NativeJeevesProvider(self.worker,maximum_attempts=1)
        limited.complete(request(request_id="fill"))
        replay=limited.complete(old)
        self.assertEqual(replay.metadata["native_model_sha256"],
                         receipt.metadata["native_model_sha256"])
        self.assertEqual(replay.metadata["native_tokenizer_sha256"],
                         receipt.metadata["native_tokenizer_sha256"])
        self.assertTrue(replay.metadata["authoritative_commit"])
        self.assertFalse(replay.metadata["release_certified"])

    def test_model_identity_change_still_disables_read_only_replay(self):
        producer=NativeJeevesProvider(self.worker)
        prior=request(request_id="committed")
        producer.complete(prior)
        limited=NativeJeevesProvider(self.worker,maximum_attempts=1)
        limited.complete(request(request_id="full"))
        self.worker.spine.backend.model_digest="c"*64
        with self.assertRaises(ProviderError):
            limited.complete(prior)
        self.assertEqual(self.worker.spine.generations,2)

    def test_quota_denial_never_converts_simulator_into_a_device_pass(self):
        p=NativeJeevesProvider(self.worker,maximum_attempts=1)
        r=p.complete(request(request_id="first"))
        self.assertFalse(r.metadata["device_qualified"])
        self.assertFalse(r.metadata["release_certified"])
        with self.assertRaises(ProviderError):
            p.complete(request(request_id="second"))

if __name__ == "__main__":
    unittest.main()
