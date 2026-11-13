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


class NativeQuotaReplayTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()

    def test_committed_result_can_replay_after_process_reaches_capacity(self):
        producer=NativeJeevesProvider(self.worker,maximum_attempts=4)
        prior=request("already committed",request_id="prior")
        first=producer.complete(prior)
        limited=NativeJeevesProvider(self.worker,maximum_attempts=1)
        limited.complete(request("fills local ledger",request_id="fill"))
        baseline=set(self.worker.spine.sessions)
        old=limited.complete(prior)
        self.assertEqual(old.content,first.content)
        self.assertTrue(old.cached)
        self.assertEqual(self.worker.spine.sessions,baseline)
        self.assertEqual(self.worker.spine.generations,2)

    def test_no_new_attempt_capacity_is_needed_for_read_only_old_replay(self):
        producer=NativeJeevesProvider(self.worker,maximum_attempts=4)
        old=request("text one",request_id="history")
        producer.complete(old)
        limited=NativeJeevesProvider(self.worker,maximum_attempts=1)
        limited.complete(request("new",request_id="limit"))
        before=set(limited._attempted)
        for _ in range(10):
            out=limited.complete(old)
            self.assertTrue(out.cached)
            self.assertEqual(set(limited._attempted),before)
        self.assertEqual(self.worker.spine.generations,2)

    def test_at_capacity_prompt_collision_denies_without_new_inference(self):
        producer=NativeJeevesProvider(self.worker,maximum_attempts=2)
        producer.complete(request("original text",request_id="original"))
        limited=NativeJeevesProvider(self.worker,maximum_attempts=1)
        limited.complete(request("quota",request_id="quota"))
        sessions=set(self.worker.spine.sessions)
        with self.assertRaises(ProviderError):
            limited.complete(request("altered text",request_id="original"))
        self.assertEqual(self.worker.spine.sessions,sessions)
        self.assertEqual(self.worker.spine.generations,2)

    def test_failed_native_effect_is_still_unreplayable(self):
        limited=NativeJeevesProvider(self.worker,maximum_attempts=1)
        self.worker.spine.fail_uncertain=True
        pending=request(request_id="uncertain")
        with self.assertRaises(RuntimeError):
            limited.complete(pending)
        before=set(self.worker.spine.sessions)
        self.worker.spine.fail_uncertain=False
        with self.assertRaises(ProviderError):
            limited.complete(request(request_id="new"))
        self.assertEqual(self.worker.spine.sessions,before)
        self.assertEqual(self.worker.spine.generations,1)

if __name__ == "__main__":
    unittest.main()
