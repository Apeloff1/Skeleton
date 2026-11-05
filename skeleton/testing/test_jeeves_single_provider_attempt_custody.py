"""Single authoritative native provider instance and replay-safe uncertainty fence.

These are simulated provider/SQLite contract tests, not a physical GGUF
generation, source-rights review, Windows laptop pass, or release approval.
"""
from __future__ import annotations

import unittest

from skeleton.jeeves.agent.native_provider import (
    NativeJeevesProvider, native_provider_router,
)
from skeleton.jeeves.agent.native_runtime import (
    NativeJeevesRuntime, NativeRuntimeHold, configured_native_agent,
)
from skeleton.jeeves.agent.provider import (
    ProviderError, ProviderExhausted,
)
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, request,
)


class NativeAttemptCustodyTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.runtime=NativeJeevesRuntime(self.worker)
        self.router=self.runtime.agent.providers

    def test_runtime_provider_ledger_is_the_exact_router_ledger(self):
        self.assertIs(self.router._providers[0],self.runtime.provider)
        self.assertIs(self.runtime.provider._attempted,
                      self.router._providers[0]._attempted)

    def test_fence_capacity_blocks_new_generation_through_real_router(self):
        self.runtime.provider._maximum_attempts=1
        self.router.complete(request("one",request_id="first"))
        self.assertEqual(self.worker.spine.generations,1)
        self.assertEqual(len(self.runtime.provider._attempted),1)
        with self.assertRaises(ProviderExhausted):
            self.router.complete(request("two",request_id="second"))
        self.assertEqual(self.worker.spine.generations,1)

    def test_already_committed_result_replays_at_capacity_without_regeneration(self):
        self.runtime.provider._maximum_attempts=1
        prompt=request("hello local model",request_id="record")
        one=self.router.complete(prompt)
        two=self.router.complete(prompt)
        self.assertEqual(two.content,one.content)
        self.assertTrue(two.cached)
        self.assertEqual(self.worker.spine.generations,1)

    def test_failed_first_generation_never_gets_implicit_retry(self):
        self.worker.spine.fail_uncertain=True
        first=request("uncertain",request_id="uncertain")
        with self.assertRaises(ProviderExhausted):
            self.router.complete(first)
        self.assertEqual(self.worker.spine.generations,1)
        self.assertEqual(len(self.runtime.provider._attempted),1)
        with self.assertRaises(ProviderExhausted):
            self.router.complete(first)
        self.assertEqual(self.worker.spine.generations,1)

    def test_uncertain_attempt_does_not_unlock_after_new_source_request(self):
        self.worker.spine.fail_uncertain=True
        self.runtime.provider._maximum_attempts=1
        with self.assertRaises(ProviderExhausted):
            self.router.complete(request(request_id="uncertain"))
        self.worker.spine.fail_uncertain=False
        with self.assertRaises(ProviderExhausted):
            self.router.complete(request(request_id="different"))
        self.assertEqual(self.worker.spine.generations,1)

if __name__ == "__main__":
    unittest.main()
