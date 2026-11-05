"""Bounded in-process native attempt custody; simulated only, not device proof.

Each new native inference attempt consumes one process-scoped reservation.
This never weakens the canonical SQLite replay/commit/pending state. The fence
is not a general cache: entries cannot be evicted to permit duplicate effects.
"""
from __future__ import annotations

import unittest

from skeleton.jeeves.agent.native_provider import NativeJeevesProvider
from skeleton.jeeves.agent.provider import ProviderError
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker,
    request,
)


class NativeAttemptCapacityTests(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()

    def test_reject_zero_bool_large_fraction_and_string_capacity(self):
        for n in (None, False, True, 0, -1, 65537, 1.5, "8"):
            with self.subTest(value=n):
                with self.assertRaises(ProviderError):
                    NativeJeevesProvider(self.worker, maximum_attempts=n)

    def test_single_attempt_budget_blocks_distinct_native_generation(self):
        p = NativeJeevesProvider(self.worker, maximum_attempts=1)
        first = p.complete(request("first prompt", request_id="first"))
        self.assertFalse(first.cached)
        self.assertEqual(self.worker.spine.generations, 1)
        with self.assertRaisesRegex(ProviderError, "safe capacity"):
            p.complete(request("second prompt", request_id="second"))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_committed_replay_remains_readable_at_capacity(self):
        p = NativeJeevesProvider(self.worker, maximum_attempts=1)
        r = request("replay is read-only", request_id="committed")
        first = p.complete(r)
        replayed = p.complete(r)
        self.assertEqual(first.content, replayed.content)
        self.assertTrue(replayed.cached)
        self.assertEqual(self.worker.spine.generations, 1)

    def test_uncertain_first_generation_blocks_identity_and_new_work(self):
        self.worker.spine.fail_uncertain = True
        p = NativeJeevesProvider(self.worker, maximum_attempts=1)
        original = request("uncertain work", request_id="uncertain")
        with self.assertRaises(RuntimeError):
            p.complete(original)
        with self.assertRaises((ProviderError, RuntimeError)):
            p.complete(original)
        with self.assertRaises(ProviderError):
            p.complete(request("new work", request_id="another"))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_no_commit_fabrication_at_capacity(self):
        self.worker.spine.return_without_commit = True
        p = NativeJeevesProvider(self.worker, maximum_attempts=1)
        with self.assertRaises(ProviderError):
            p.complete(request(request_id="uncommitted"))
        with self.assertRaises(ProviderError):
            p.complete(request(request_id="other"))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_capacity_is_per_provider_instance_but_db_still_owns_replay(self):
        p = NativeJeevesProvider(self.worker, maximum_attempts=1)
        r = request(request_id="existing")
        p.complete(r)
        second = NativeJeevesProvider(self.worker, maximum_attempts=1)
        already_committed = second.complete(r)
        self.assertTrue(already_committed.cached)
        self.assertEqual(self.worker.spine.generations, 1)


if __name__ == "__main__":
    unittest.main()
