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


class NativeRouterNoFallbackTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()

    def test_one_local_provider_and_zero_speculative_cache(self):
        native=NativeJeevesProvider(self.worker)
        router=native_provider_router(self.worker,provider=native)
        self.assertEqual(len(router._providers),1)
        self.assertIs(router._providers[0],native)
        self.assertIsNone(router._cache_ttl)
        self.assertEqual(router._retry.max_attempts,1)

    def test_valid_call_and_read_only_replay_have_same_id(self):
        native=NativeJeevesProvider(self.worker)
        router=native_provider_router(self.worker,provider=native)
        prompt=request("only local",request_id="same")
        first=router.complete(prompt)
        second=router.complete(prompt)
        self.assertEqual(first.request_id,second.request_id)
        self.assertEqual(first.metadata["native_model_sha256"],"a"*64)
        self.assertEqual(first.metadata["native_tokenizer_sha256"],"b"*64)
        self.assertTrue(second.cached)
        self.assertEqual(self.worker.spine.generations,1)

    def test_capacity_bypass_must_not_become_provider_fallback(self):
        native=NativeJeevesProvider(self.worker,maximum_attempts=1)
        router=native_provider_router(self.worker,provider=native)
        router.complete(request(request_id="one"))
        with self.assertRaises(ProviderExhausted):
            router.complete(request(request_id="two"))
        self.assertEqual(self.worker.spine.generations,1)
        self.assertEqual(len(router._providers),1)

    def test_invalid_native_reply_is_not_retried_by_router(self):
        self.worker.spine.return_without_commit=True
        native=NativeJeevesProvider(self.worker)
        router=native_provider_router(self.worker,provider=native)
        with self.assertRaises(ProviderExhausted):
            router.complete(request(request_id="missingcommit"))
        self.assertEqual(self.worker.spine.generations,1)
        self.assertFalse(self.worker.spine.turns)

    def test_guard_still_controls_owner_and_device_status(self):
        runtime=NativeJeevesRuntime(self.worker)
        status=runtime.status()
        self.assertEqual(status["provider"],"jeeves_native")
        self.assertEqual(status["native_execution_source"],"canonical-supervised-ai")
        self.assertFalse(status["device_qualified"])
        self.assertFalse(status["release_certified"])
        self.assertTrue(status["principal_bound"])

if __name__ == "__main__":
    unittest.main()
