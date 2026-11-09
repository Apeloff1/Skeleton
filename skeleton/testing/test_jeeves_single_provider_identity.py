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


class SingleNativeAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()

    def test_runtime_and_agent_router_hold_exact_same_instance(self):
        runtime=NativeJeevesRuntime(self.worker)
        self.assertIsInstance(runtime.provider,NativeJeevesProvider)
        self.assertEqual(len(runtime.agent.providers._providers),1)
        self.assertIs(runtime.agent.providers._providers[0],runtime.provider)
        self.assertEqual(runtime.identity,runtime.provider.identity)
        self.assertTrue(runtime.provider.available())

    def test_standalone_configured_agent_still_creates_one_provider(self):
        runtime=configured_native_agent(self.worker)
        self.assertEqual(len(runtime.providers._providers),1)
        self.assertIsInstance(runtime.providers._providers[0],NativeJeevesProvider)
        self.assertEqual(runtime.providers._providers[0].identity.tenant,"local")

    def test_injected_same_worker_provider_is_reused(self):
        owner=NativeJeevesProvider(self.worker)
        runtime=configured_native_agent(self.worker,native_provider=owner)
        self.assertIs(runtime.providers._providers[0],owner)
        router=native_provider_router(self.worker,provider=owner)
        self.assertIs(router._providers[0],owner)

    def test_cross_worker_provider_never_becomes_generation_authority(self):
        foreign=SimulatedWorker()
        foreign_provider=NativeJeevesProvider(foreign)
        with self.assertRaises(ProviderError):
            native_provider_router(self.worker,provider=foreign_provider)
        with self.assertRaises(NativeRuntimeHold):
            configured_native_agent(self.worker,native_provider=foreign_provider)
        self.assertEqual(self.worker.spine.generations,0)
        self.assertEqual(foreign.spine.generations,0)

    def test_provider_identity_changes_deny_future_routing(self):
        native=NativeJeevesProvider(self.worker)
        self.worker.spine.backend.model_digest="c"*64
        self.assertFalse(native.available())
        with self.assertRaises(ProviderError):
            native_provider_router(self.worker,provider=native)
        with self.assertRaises(NativeRuntimeHold):
            configured_native_agent(self.worker,native_provider=native)
        self.assertEqual(self.worker.spine.generations,0)

    def test_injected_non_native_provider_is_rejected(self):
        with self.assertRaises(ProviderError):
            native_provider_router(self.worker,provider=object())
        with self.assertRaises(NativeRuntimeHold):
            configured_native_agent(self.worker,native_provider=object())

if __name__ == "__main__":
    unittest.main()
