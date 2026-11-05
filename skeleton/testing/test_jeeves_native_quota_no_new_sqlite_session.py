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


class NativeQuotaDenialTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.native=NativeJeevesProvider(self.worker,maximum_attempts=1)

    def test_full_quota_denies_before_creating_another_session(self):
        self.native.complete(request("one",request_id="first"))
        before_sessions=set(self.worker.spine.sessions)
        before_turns=dict(self.worker.spine.turns)
        with self.assertRaisesRegex(ProviderError, "safe capacity"):
            self.native.complete(request("two",request_id="second"))
        self.assertEqual(self.worker.spine.sessions,before_sessions)
        self.assertEqual(self.worker.spine.turns,before_turns)
        self.assertEqual(self.worker.spine.generations,1)

    def test_quota_denial_is_idempotent_without_new_records(self):
        self.native.complete(request(request_id="a"))
        before_sessions=set(self.worker.spine.sessions)
        for n in range(20):
            with self.subTest(run=n):
                with self.assertRaises(ProviderError):
                    self.native.complete(request(
                        "no extra session state",
                        request_id="extra_" + str(n),
                    ))
                self.assertEqual(self.worker.spine.sessions,before_sessions)
                self.assertEqual(self.worker.spine.generations,1)
                self.assertEqual(len(self.native._attempted),1)

    def test_attempt_fence_is_not_evictable_by_new_request(self):
        original=request("first",request_id="first")
        self.native.complete(original)
        recorded=set(self.native._attempted)
        for changed in (
            request("another task",request_id="other"),
            request("still other",request_id="another"),
        ):
            with self.assertRaises(ProviderError):
                self.native.complete(changed)
            self.assertEqual(self.native._attempted,recorded)

    def test_router_cannot_hide_session_mutation_under_provider_exhausted(self):
        router=native_provider_router(self.worker,provider=self.native)
        router.complete(request(request_id="good"))
        snapshot=set(self.worker.spine.sessions)
        with self.assertRaises(ProviderExhausted):
            router.complete(request(request_id="new"))
        self.assertEqual(self.worker.spine.sessions,snapshot)
        self.assertEqual(self.worker.spine.generations,1)

if __name__ == "__main__":
    unittest.main()
