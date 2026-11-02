"""CPU capacity guard: conservative simulated state-machine regression."""
from __future__ import annotations

from hashlib import sha256
import json
import unittest
from unittest.mock import MagicMock, patch

from skeleton.ai.model_runtime.long_context_cpu_guard import (
    CpuCapacityLimits, CpuCapacityRequest, LongContextCpuCapacityGuard,
)
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError, _canonical
from skeleton.ai.model_runtime.long_context_progress import _name
from skeleton.ai.model_runtime.long_context_telemetry_fusion import LongContextTelemetryFusion


class Tick:
    def __init__(self):
        self.value = 1_000_000

    def __call__(self):
        self.value += 1000
        return self.value


def envelope(level="normal", event=0):
    obj = {
        "schema": "skeleton.ai.long-context-telemetry-fusion.v1",
        "state": "observed",
        "signals": {k: level for k in ("cpu", "memory", "thermal", "energy")},
        "reasons": [], "event_state": "observed",
        "event_deltas": {"oom": event, "oom_kill": 0, "nr_throttled": 0},
        "sources": ("host_psi", "cgroup_v2", "cgroup_events"),
        "cross_source_snapshot_atomic": False,
        "scope_membership_attested": False,
        "pressure_signals_attested": False,
        "device_qualified": False,
        "is_admission_grant": False,
        "is_execution_lease": False,
        "requires_live_backend_revalidation": True,
    }
    obj["observation_digest"] = sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return obj


def head_receipt(stream_id="stream"):
    body = {
        "schema": "skeleton.ai.long-context-head.v1",
        "stream_digest": _name(stream_id),
        "checkpoint_digest": "a" * 64, "tokenizer_digest": "b" * 64,
        "generation": 4,
    }
    window = {
        "start": 0, "stop": 8, "token_ids": list(range(8)),
        "source_sequence_digest": "d" * 64,
    }
    return {
        **body, "record_digest": sha256(_canonical(body)).hexdigest(),
        "is_execution_lease": False,
        "window": {**window, "digest": sha256(_canonical(window)).hexdigest()},
    }


class CpuCapacityGuardTests(unittest.TestCase):
    def setUp(self):
        self.clock = Tick()
        self.monitor = LongContextTelemetryFusion()
        self.monitor.sample = MagicMock(return_value=envelope())
        self.heads = MagicMock()
        self.heads.compare_window.return_value = head_receipt()
        self.heads.spool.capacity_snapshot.side_effect = lambda requested_bytes: {
            "schema": "skeleton.ai.long-context-capacity.v1",
            "state": "observed_available",
            "is_admission_lease": False,
            "hardware_qualification": "not_assessed",
            "request_observed_sufficient": True,
            "used_bytes": 0,
            "quota_bytes": 4096,
            "quota_remaining_bytes": 4096,
            "volume_available_bytes": 8192,
            "disk_reserve_bytes": 0,
            "observed_publishable_bytes": 4096,
            "requested_bytes": requested_bytes,
        }
        self.authorized = True
        self.verifier = MagicMock(side_effect=lambda _: self.authorized)
        self.request = CpuCapacityRequest("owner", "stream", "a" * 64,
                                          "b" * 64, 4, 8, 64)
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.LongContextProgressHead",
                   MagicMock):
            self.guard = LongContextCpuCapacityGuard(
                self.heads, self.monitor, self.verifier, clock=self.clock)

    def warm(self):
        for _ in range(3):
            self.guard.observe()

    def test_warming_then_reservation_is_not_authority(self):
        self.assertIsNone(self.guard.reserve(self.request)["reservation_id"])
        self.warm()
        result = self.guard.reserve(self.request)
        self.assertEqual(result["state"], "reserved")
        self.assertEqual(len(result["reservation_id"]), 64)
        self.assertFalse(result["is_execution_lease"])
        self.assertFalse(result["is_admission_grant"])
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["cross_process_exclusive"])

    def test_one_shot_claim_and_release(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.assertTrue(self.guard.claim(key, self.request)["claimed"])
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])
        self.assertTrue(self.guard.release(key))
        self.assertFalse(self.guard.release(key))

    def test_sampling_gap_revokes_inflight_capacity(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.clock.value += 3_000_000_000
        self.assertEqual(self.guard.observe()["state"], "warming")
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])
        self.assertEqual(self.guard.status()["active"], 0)

    def test_critical_pressure_revokes(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.monitor.sample.return_value = envelope("critical")
        self.assertEqual(self.guard.observe()["state"], "hold")
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])

    def test_event_pressure_revokes(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.monitor.sample.return_value = envelope(event=1)
        self.guard.observe()
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])

    def test_forged_head_and_token_window_never_reserve(self):
        self.warm()
        for mutate in (
            lambda r: r.update(record_digest="0" * 64),
            lambda r: r.update(stream_digest="0" * 64),
            lambda r: r.update(schema="untrusted"),
            lambda r: r.update(generation=True),
            lambda r: r["window"].update(token_ids=[True] + list(range(1, 8))),
            lambda r: r["window"].update(token_ids=[999] + list(range(1, 8))),
            lambda r: r["window"].update(source_sequence_digest="0" * 64),
            lambda r: r["window"].update(digest="0" * 64),
            lambda r: r["window"].update(stop=9),
            lambda r: r["window"].update(unknown_field=True),
            lambda r: r["window"].update(start=False),
        ):
            with self.subTest(mutate=mutate):
                forged = head_receipt()
                mutate(forged)
                self.heads.compare_window.return_value = forged
                self.assertEqual(self.guard.reserve(self.request)["reason"],
                                 "custody_or_disk_unverified")
                self.assertEqual(self.guard.status()["active"], 0)
        self.heads.compare_window.return_value = head_receipt()
        self.assertIsNotNone(self.guard.reserve(self.request)["reservation_id"])

    def test_stale_head_and_disk_hold(self):
        self.warm()
        self.heads.compare_window.return_value["generation"] = 5
        self.assertEqual(self.guard.reserve(self.request)["reason"],
                         "custody_or_disk_unverified")
        self.heads.compare_window.return_value["generation"] = 4
        self.heads.spool.capacity_snapshot.side_effect = lambda requested_bytes: {
            **self._capacity(requested_bytes),
            "request_observed_sufficient": False, "state": "hold",
        }
        self.assertIsNone(self.guard.reserve(self.request)["reservation_id"])

    def test_claim_revalidates_head(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.heads.compare_window.return_value["window"]["digest"] = "d" * 64
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])
        self.assertFalse(self.guard.release(key))

    def test_principal_revalidated(self):
        self.warm()
        self.authorized = False
        self.assertEqual(self.guard.reserve(self.request)["reason"],
                         "principal_unverified")
        self.authorized = True
        key = self.guard.reserve(self.request)["reservation_id"]
        self.authorized = False
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])

    def test_duplicate_stream_and_bounded_budget(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.assertEqual(self.guard.reserve(self.request)["reason"],
                         "duplicate_stream")
        self.assertTrue(self.guard.release(key))

    def test_fair_cycle_is_all_or_nothing(self):
        self.warm()
        self.heads.compare_window.side_effect = lambda stream_id, **kw: head_receipt(stream_id)
        other = CpuCapacityRequest("owner", "other", "a" * 64, "b" * 64, 4, 8, 64)
        result = self.guard.reserve_fair_cycle((self.request, other),
                                               quantum_tokens=8)
        self.assertEqual(result["state"], "reserved")
        self.assertEqual(len(result["reservations"]), 2)
        self.assertEqual(result["reserved_tokens"], 16)
        self.assertFalse(result["is_execution_lease"])
        for receipt in result["reservations"]:
            self.assertTrue(self.guard.release(receipt["reservation_id"]))

    def test_fair_cycle_rejects_partial_capacity(self):
        self.warm()
        other = CpuCapacityRequest("owner", "other", "a" * 64, "b" * 64, 4, 8, 64)
        held = self.guard.reserve_fair_cycle((self.request, other),
                                             quantum_tokens=4)
        self.assertEqual(held["reason"], "fair_cycle_budget_or_duplicate")
        self.assertEqual(held["reservations"], [])
        self.assertEqual(self.guard.status()["active"], 0)

    def test_fair_cycle_rolls_back_on_stale_head(self):
        self.warm()
        other = CpuCapacityRequest("owner", "other", "a" * 64, "b" * 64, 4, 8, 64)
        self.heads.compare_window.side_effect = [
            head_receipt("other"), LongContextSpoolError("stale head"),
        ]
        result = self.guard.reserve_fair_cycle((self.request, other),
                                               quantum_tokens=8)
        self.assertEqual(result["reason"], "fair_cycle_custody_unverified")
        self.assertEqual(result["reservations"], [])
        self.assertEqual(self.guard.status()["active"], 0)

    def test_fair_cycle_rejects_duplicate_and_wrong_type(self):
        with self.assertRaisesRegex(LongContextSpoolError, "duplicate fair"):
            self.guard.reserve_fair_cycle((self.request, self.request))
        with self.assertRaises(LongContextSpoolError):
            self.guard.reserve_fair_cycle([self.request])
        with self.assertRaises(LongContextSpoolError):
            self.guard.reserve_fair_cycle((self.request, object()))

    def test_clock_regression_and_fork(self):
        self.warm()
        self.guard.reserve(self.request)
        self.clock.value = 0
        with self.assertRaisesRegex(LongContextSpoolError, "clock regressed"):
            self.guard.status()
        self.assertEqual(len(self.guard._reservations), 0)
        self.clock.value = 2_000_000
        self.assertEqual(self.guard.status()["revocations"], 1)
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.os.getpid",
                   return_value=-1):
            with self.assertRaisesRegex(LongContextSpoolError, "after fork"):
                self.guard.observe()

    def test_close_invalidates(self):
        self.warm()
        self.guard.reserve(self.request)
        self.guard.close()
        self.assertEqual(self.guard.status()["active"], 0)
        self.assertEqual(self.guard.status()["revocations"], 1)
        with self.assertRaisesRegex(LongContextSpoolError, "closed"):
            self.guard.reserve(self.request)

    def test_invalid_envelope_and_monitor_exception(self):
        self.monitor.sample.return_value = {**envelope(), "is_execution_lease": True}
        self.assertEqual(self.guard.observe()["state"], "hold")
        self.monitor.sample.side_effect = OSError("sensor")
        self.assertEqual(self.guard.observe()["state"], "hold")

    def test_strict_request_and_limits(self):
        for bad in (True, -1, 0, 4097):
            with self.subTest(bad=bad), self.assertRaises(LongContextSpoolError):
                CpuCapacityRequest("owner", "stream", "a" * 64, "b" * 64, 4, bad)
        with self.assertRaises(LongContextSpoolError):
            CpuCapacityRequest("../owner", "stream", "a" * 64, "b" * 64, 4, 8)
        with self.assertRaises(LongContextSpoolError):
            CpuCapacityLimits(max_active=True)


    def test_expired_reservation_cannot_be_claimed(self):
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.LongContextProgressHead",
                   MagicMock):
            guard = LongContextCpuCapacityGuard(
                self.heads, self.monitor, self.verifier,
                limits=CpuCapacityLimits(lifetime_ns=5_000), clock=self.clock)
        for _ in range(3):
            guard.observe()
        key = guard.reserve(self.request)["reservation_id"]
        self.assertIsNotNone(key)
        self.clock.value += 10_000
        self.assertFalse(guard.claim(key, self.request)["claimed"])
        self.assertEqual(guard.status()["active"], 0)

    def test_budget_rejects_second_stream_without_overbooking(self):
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.LongContextProgressHead",
                   MagicMock):
            guard = LongContextCpuCapacityGuard(
                self.heads, self.monitor, self.verifier,
                limits=CpuCapacityLimits(max_active=1, max_tokens=8,
                                         max_bytes=64), clock=self.clock)
        for _ in range(3):
            guard.observe()
        self.assertIsNotNone(guard.reserve(self.request)["reservation_id"])
        other = CpuCapacityRequest("owner", "other", "a" * 64, "b" * 64, 4, 8, 64)
        self.assertEqual(guard.reserve(other)["reason"], "budget_exhausted")
        self.assertEqual(guard.status()["reserved_tokens"], 8)

    def test_claim_rejects_wrong_principal_and_request(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        wrong = CpuCapacityRequest("other", "stream", "a" * 64, "b" * 64, 4, 8, 64)
        self.assertFalse(self.guard.claim(key, wrong)["claimed"])
        self.assertTrue(self.guard.claim(key, self.request)["claimed"])

    def test_verifier_exception_is_not_permission(self):
        self.warm()
        self.verifier.side_effect = RuntimeError("auth service unavailable")
        self.assertEqual(self.guard.reserve(self.request)["reason"],
                         "principal_unverified")

    def _capacity(self, requested_bytes: int) -> dict:
        return {
            "schema": "skeleton.ai.long-context-capacity.v1",
            "state": "observed_available",
            "is_admission_lease": False,
            "hardware_qualification": "not_assessed",
            "request_observed_sufficient": True,
            "used_bytes": 0, "quota_bytes": 4096,
            "quota_remaining_bytes": 4096,
            "volume_available_bytes": 8192,
            "disk_reserve_bytes": 0,
            "observed_publishable_bytes": 4096,
            "requested_bytes": requested_bytes,
        }

    def test_claim_rechecks_disk_after_reservation(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.assertIsNotNone(key)
        self.heads.spool.capacity_snapshot.side_effect = lambda requested_bytes: {
            **self._capacity(requested_bytes),
            "volume_available_bytes": 0,
            "observed_publishable_bytes": 0,
            "state": "hold", "request_observed_sufficient": False,
        }
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])
        self.assertFalse(self.guard.release(key))
        self.assertEqual(self.guard.status()["active"], 0)

    def test_claim_rejects_changed_quota_and_sensor_failure(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.heads.spool.capacity_snapshot.side_effect = OSError("volume gone")
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])
        self.assertFalse(self.guard.release(key))
        self.heads.spool.capacity_snapshot.side_effect = (
            lambda requested_bytes: self._capacity(requested_bytes))
        key = self.guard.reserve(self.request)["reservation_id"]
        self.heads.spool.capacity_snapshot.side_effect = lambda requested_bytes: {
            **self._capacity(requested_bytes), "quota_remaining_bytes": 0,
        }
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])

    def test_disk_snapshot_forged_lease_and_inconsistent_arithmetic_hold(self):
        self.warm()
        for changes in (
            {"is_admission_lease": True},
            {"hardware_qualification": "certified"},
            {"observed_publishable_bytes": True},
            {"observed_publishable_bytes": 999999},
            {"requested_bytes": 0},
            {"used_bytes": -1},
            {"schema": "unexpected"},
        ):
            with self.subTest(changes=changes):
                self.heads.spool.capacity_snapshot.side_effect = (
                    lambda requested_bytes, changes=changes: {
                        **self._capacity(requested_bytes), **changes})
                self.assertEqual(
                    self.guard.reserve(self.request)["reason"],
                    "custody_or_disk_unverified")
                self.assertEqual(self.guard.status()["active"], 0)

    def test_fair_cycle_rechecks_disk_independently_on_each_claim(self):
        self.warm()
        other = CpuCapacityRequest(
            "owner", "other", "a" * 64, "b" * 64, 4, 8, 64)
        receipts = self.guard.reserve_fair_cycle(
            (self.request, other), quantum_tokens=8)["reservations"]
        self.assertEqual(len(receipts), 2)
        self.heads.spool.capacity_snapshot.side_effect = (
            lambda requested_bytes: self._capacity(requested_bytes))
        self.assertTrue(self.guard.claim(
            receipts[0]["reservation_id"], other)["claimed"])
        self.heads.spool.capacity_snapshot.side_effect = OSError("disk offline")
        self.assertFalse(self.guard.claim(
            receipts[1]["reservation_id"], self.request)["claimed"])
        self.assertEqual(self.guard.status()["active"], 1)


    def test_clock_exception_accounts_for_revoked_claim(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.assertTrue(self.guard.claim(key, self.request)["claimed"])
        self.guard._clock = MagicMock(side_effect=OSError("monotonic unavailable"))
        with self.assertRaisesRegex(LongContextSpoolError, "clock unavailable"):
            self.guard.status()
        self.guard._clock = self.clock
        self.assertEqual(self.guard.status()["active"], 0)
        self.assertEqual(self.guard.status()["revocations"], 1)
        self.assertFalse(self.guard.release(key))

    def test_principal_quota_preserves_capacity_for_other_verified_owner(self):
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.LongContextProgressHead",
                   MagicMock):
            guard = LongContextCpuCapacityGuard(
                self.heads, self.monitor, self.verifier,
                limits=CpuCapacityLimits(max_active=8, max_active_per_principal=2),
                clock=self.clock)
        for _ in range(3):
            guard.observe()
        one = self.request
        two = CpuCapacityRequest("owner", "stream2", "a" * 64, "b" * 64, 4, 8, 64)
        three = CpuCapacityRequest("owner", "stream3", "a" * 64, "b" * 64, 4, 8, 64)
        other = CpuCapacityRequest("other", "stream4", "a" * 64, "b" * 64, 4, 8, 64)
        self.assertIsNotNone(guard.reserve(one)["reservation_id"])
        self.assertIsNotNone(guard.reserve(two)["reservation_id"])
        self.assertEqual(guard.reserve(three)["reason"],
                         "principal_capacity_exhausted")
        self.assertIsNotNone(guard.reserve(other)["reservation_id"])
        self.assertEqual(guard.status()["active"], 3)

    def test_fair_cycle_principal_quota_is_atomic(self):
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.LongContextProgressHead",
                   MagicMock):
            guard = LongContextCpuCapacityGuard(
                self.heads, self.monitor, self.verifier,
                limits=CpuCapacityLimits(max_active=8, max_active_per_principal=2),
                clock=self.clock)
        for _ in range(3):
            guard.observe()
        requests = tuple(CpuCapacityRequest(
            "owner", f"stream{i}", "a" * 64, "b" * 64, 4, 8, 64)
            for i in range(3))
        result = guard.reserve_fair_cycle(requests, quantum_tokens=8)
        self.assertEqual(result["reason"], "fair_cycle_principal_capacity")
        self.assertEqual(result["reservations"], [])
        self.assertEqual(guard.status()["active"], 0)

    def test_slow_volume_probe_cannot_publish_expired_reservation(self):
        self.warm()
        def slow_capacity(requested_bytes):
            self.clock.value += 3_000_000_000
            return self._capacity(requested_bytes)
        self.heads.spool.capacity_snapshot.side_effect = slow_capacity
        result = self.guard.reserve(self.request)
        self.assertIsNone(result["reservation_id"])
        self.assertEqual(self.guard.status()["active"], 0)

    def test_pressure_transition_during_reservation_fails_closed(self):
        self.warm()
        observations = iter((envelope(), envelope("critical")))
        self.monitor.sample.side_effect = lambda: next(observations)
        result = self.guard.reserve(self.request)
        self.assertEqual(result["reason"], "pressure_changed_during_reservation")
        self.assertIsNone(result["reservation_id"])

    def test_slow_claim_revalidation_revokes_before_claim(self):
        self.warm()
        key = self.guard.reserve(self.request)["reservation_id"]
        self.assertIsNotNone(key)
        def slow_capacity(requested_bytes):
            self.clock.value += 3_000_000_000
            return self._capacity(requested_bytes)
        self.heads.spool.capacity_snapshot.side_effect = slow_capacity
        self.assertFalse(self.guard.claim(key, self.request)["claimed"])
        self.assertFalse(self.guard.release(key))

    def test_legacy_positional_capacity_limits_remain_stable(self):
        limits = CpuCapacityLimits(2, 16, 4096, 100000)
        self.assertEqual(limits.max_active, 2)
        self.assertEqual(limits.max_tokens, 16)
        self.assertEqual(limits.max_bytes, 4096)
        self.assertEqual(limits.lifetime_ns, 100000)
        self.assertEqual(limits.max_active_per_principal, 4)

    def test_forged_pressure_receipt_cannot_create_capacity(self):
        self.warm()
        valid = self.guard._latch.sample()
        self.assertEqual(valid["state"], "repeated_normal_observed")
        forged = (
            {"is_admission_grant": True},
            {"observation_digest_is_authenticity_proof": True},
            {"pressure_signals_attested": True},
            {"restart_state_durable": True},
            {"consecutive_normal_observations": 1},
            {"signals": {"cpu": "normal", "memory": "normal",
                         "thermal": "unknown", "energy": "normal"}},
            {"required_observations": True},
            {"schema": "untrusted"},
        )
        for changes in forged:
            with self.subTest(changes=changes):
                self.guard._latch.sample = MagicMock(return_value={
                    **valid, **changes})
                result = self.guard.reserve(self.request)
                self.assertIsNone(result["reservation_id"])
                self.assertEqual(result["state"], "hold")
                self.assertEqual(self.guard.status()["active"], 0)

    def test_principal_token_budget_prevents_single_owner_monopoly(self):
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.LongContextProgressHead",
                   MagicMock):
            guard = LongContextCpuCapacityGuard(
                self.heads, self.monitor, self.verifier,
                limits=CpuCapacityLimits(max_tokens=64,
                                         max_tokens_per_principal=8),
                clock=self.clock)
        for _ in range(3):
            guard.observe()
        self.assertIsNotNone(guard.reserve(self.request)["reservation_id"])
        same = CpuCapacityRequest("owner", "otherstream", "a" * 64,
                                  "b" * 64, 4, 8, 64)
        self.assertEqual(guard.reserve(same)["reason"],
                         "principal_capacity_exhausted")
        different = CpuCapacityRequest("other", "another", "a" * 64,
                                       "b" * 64, 4, 8, 64)
        self.assertIsNotNone(guard.reserve(different)["reservation_id"])

    def test_principal_byte_budget_blocks_atomic_fair_cycle(self):
        with patch("skeleton.ai.model_runtime.long_context_cpu_guard.LongContextProgressHead",
                   MagicMock):
            guard = LongContextCpuCapacityGuard(
                self.heads, self.monitor, self.verifier,
                limits=CpuCapacityLimits(max_bytes=4096,
                                         max_bytes_per_principal=64),
                clock=self.clock)
        for _ in range(3):
            guard.observe()
        other = CpuCapacityRequest("owner", "another", "a" * 64,
                                   "b" * 64, 4, 8, 64)
        result = guard.reserve_fair_cycle(
            (self.request, other), quantum_tokens=8)
        self.assertEqual(result["reason"], "fair_cycle_principal_capacity")
        self.assertEqual(guard.status()["active"], 0)

if __name__ == "__main__":
    unittest.main()
