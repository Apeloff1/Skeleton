"""Deterministic cooperative RAM-budget tests (no device claims)."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from skeleton.ai.model_runtime.long_context_memory_budget import (
    LongContextMemoryBudgetGuard, MemoryBudgetLimits, MemoryBudgetRequest,
)
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError


class Clock:
    def __init__(self):
        self.value = 1000

    def __call__(self):
        self.value += 100
        return self.value


def envelope(required, *, headroom=4096, **changes):
    receipt = {
        "schema": "skeleton.ai.long-context-memory-envelope.v1",
        "state": "observed_headroom",
        "reason": "observed_only",
        "requested_bytes": required,
        "observed_headroom_bytes": headroom,
        "request_observed_sufficient": required <= headroom,
        "host_available_bytes": 8192,
        "host_total_bytes": 16384,
        "cgroup_remaining_bytes": 8192,
        "cgroup_effective_limit_bytes": 16384,
        "reserve_bytes": 4096,
        "device_qualified": False,
        "is_admission_grant": False,
        "is_execution_lease": False,
        "is_memory_reservation": False,
        "cross_source_snapshot_atomic": False,
        "requires_live_backend_revalidation": True,
    }
    receipt.update(changes)
    return receipt


class MemoryBudgetGuardTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.authorized = True
        self.verifier = lambda request: self.authorized
        self.observer = Mock(side_effect=lambda requested_bytes: envelope(requested_bytes))
        self.guard = LongContextMemoryBudgetGuard(
            self.verifier, observer=self.observer,
            limits=MemoryBudgetLimits(max_active=2, max_bytes=1024,
                                      max_bytes_per_principal=768,
                                      lifetime_ns=1000),
            clock=self.clock,
        )
        self.one = MemoryBudgetRequest("owner", "stream-a", 512)
        self.two = MemoryBudgetRequest("owner", "stream-b", 512)
        self.other = MemoryBudgetRequest("other", "stream-c", 512)

    def test_reserve_claim_release_is_not_execution(self):
        receipt = self.guard.reserve(self.one)
        self.assertEqual(receipt["state"], "reserved")
        self.assertFalse(receipt["is_execution_lease"])
        self.assertFalse(receipt["is_memory_allocation"])
        key = receipt["reservation_id"]
        self.assertEqual(self.guard.claim(key, self.one)["state"], "claimed")
        self.assertEqual(self.guard.claim(key, self.one)["state"], "hold")
        self.assertEqual(self.guard.status()["reserved_bytes"], 512)
        self.assertTrue(self.guard.release(key))
        self.assertFalse(self.guard.release(key))
        self.assertEqual(self.guard.status()["active"], 0)

    def test_duplicate_stream_and_owner_quota(self):
        self.guard.reserve(self.one)
        self.assertEqual(self.guard.reserve(self.one)["reason"], "duplicate_stream")
        self.assertEqual(self.guard.reserve(self.two)["reason"], "memory_budget_exhausted")
        self.assertEqual(self.guard.reserve(self.other)["state"], "reserved")
        self.assertEqual(self.guard.status()["active"], 2)

    def test_global_capacity_and_per_principal_limits(self):
        first = MemoryBudgetRequest("owner", "a", 700)
        second = MemoryBudgetRequest("other", "b", 500)
        self.assertEqual(self.guard.reserve(first)["state"], "reserved")
        self.assertEqual(self.guard.reserve(second)["reason"], "memory_budget_exhausted")

    def test_failed_authorization_does_not_grant(self):
        self.authorized = False
        self.assertEqual(self.guard.reserve(self.one)["reason"], "principal_unverified")
        self.authorized = True
        key = self.guard.reserve(self.one)["reservation_id"]
        self.authorized = False
        self.assertEqual(self.guard.claim(key, self.one)["state"], "hold")
        self.assertEqual(self.guard.status()["active"], 0)

    def test_claim_revalidates_all_outstanding_bytes(self):
        key = self.guard.reserve(self.one)["reservation_id"]
        self.observer.side_effect = lambda requested_bytes: envelope(
            requested_bytes, headroom=0)
        self.assertEqual(self.guard.claim(key, self.one)["state"], "hold")
        self.assertEqual(self.guard.status()["revocations"], 1)

    def test_forged_authority_or_inconsistent_counters_holds(self):
        for change in (
            {"is_execution_lease": True},
            {"is_admission_grant": True},
            {"is_memory_reservation": True},
            {"device_qualified": True},
            {"cross_source_snapshot_atomic": True},
            {"requires_live_backend_revalidation": False},
            {"observed_headroom_bytes": 999999},
            {"requested_bytes": 0},
            {"request_observed_sufficient": True, "observed_headroom_bytes": 0},
            {"state": "hold"},
            {"host_available_bytes": True},
            {"reserve_bytes": -1},
            {"reserve_bytes": 0},
            {"host_total_bytes": 1},
            {"cgroup_effective_limit_bytes": 1},
        ):
            with self.subTest(change=change):
                self.observer.side_effect = (
                    lambda requested_bytes, change=change:
                    envelope(requested_bytes, **change)
                )
                self.assertEqual(self.guard.reserve(self.one)["state"], "hold")
                self.assertEqual(self.guard.status()["active"], 0)

    def test_observer_error_revokes_existing_reservations(self):
        key = self.guard.reserve(self.one)["reservation_id"]
        self.observer.side_effect = OSError("telemetry unavailable")
        self.assertEqual(self.guard.claim(key, self.one)["reason"],
                         "memory_telemetry_unverified")
        self.assertEqual(self.guard.status()["active"], 0)

    def test_expiry_and_slow_observer(self):
        key = self.guard.reserve(self.one)["reservation_id"]
        self.clock.value += 1000
        self.assertEqual(self.guard.claim(key, self.one)["state"], "hold")
        self.assertEqual(self.guard.status()["active"], 0)
        def slow(requested_bytes):
            self.clock.value += 1500
            return envelope(requested_bytes)
        self.observer.side_effect = slow
        self.assertEqual(self.guard.reserve(self.one)["reason"],
                         "memory_observation_expired")
        self.assertEqual(self.guard.status()["active"], 0)

    def test_clock_failure_revokes_claim(self):
        key = self.guard.reserve(self.one)["reservation_id"]
        self.assertEqual(self.guard.claim(key, self.one)["state"], "claimed")
        self.guard._clock = Mock(side_effect=OSError("clock"))
        with self.assertRaises(LongContextSpoolError):
            self.guard.status()
        self.guard._clock = self.clock
        self.assertEqual(self.guard.status()["active"], 0)

    def test_wrong_principal_or_stream_cannot_claim(self):
        key = self.guard.reserve(self.one)["reservation_id"]
        self.assertEqual(self.guard.claim(key, self.other)["state"], "hold")
        self.assertEqual(self.guard.claim(key, self.one)["state"], "claimed")

    def test_close_and_fork_fail_closed(self):
        self.guard.reserve(self.one)
        self.guard.close()
        self.assertEqual(self.guard._revocations, 1)
        with self.assertRaises(LongContextSpoolError):
            self.guard.reserve(self.one)
        fresh = LongContextMemoryBudgetGuard(
            self.verifier, observer=self.observer, clock=self.clock)
        with patch("skeleton.ai.model_runtime.long_context_memory_budget.os.getpid",
                   return_value=-1):
            with self.assertRaises(LongContextSpoolError):
                fresh.status()

    def test_invalid_requests_and_limits(self):
        for bad in (0, -1, True, 1024**3 + 1):
            with self.subTest(bad=bad), self.assertRaises(LongContextSpoolError):
                MemoryBudgetRequest("owner", "stream", bad)
        for bad in ("../owner", "", "é", ".hidden"):
            with self.subTest(bad=bad), self.assertRaises(LongContextSpoolError):
                MemoryBudgetRequest(bad, "stream", 10)
        with self.assertRaises(LongContextSpoolError):
            MemoryBudgetLimits(max_active=True)


if __name__ == "__main__":
    unittest.main()
