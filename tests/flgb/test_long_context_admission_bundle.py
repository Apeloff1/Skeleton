"""Deterministic fail-closed CPU+RAM+KV bundle tests without hardware."""
from __future__ import annotations

from hashlib import sha256
import unittest
from unittest.mock import Mock, patch

from skeleton.ai.model_runtime.long_context_admission_bundle import (
    AdmissionBundleRequest, LongContextAdmissionBundle,
)
from skeleton.ai.model_runtime.long_context_cpu_guard import CpuCapacityRequest
from skeleton.ai.model_runtime.long_context_kv_compatibility import KvLayout, KvWindowRequest
from skeleton.ai.model_runtime.long_context_memory_budget import MemoryBudgetRequest
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError


class GuardStub:
    def __init__(self, kind, digest):
        self.kind, self.digest = kind, digest
        self.reserved = {}
        self.released = []
        self.fail_reserve = False
        self.fail_claim = False
        self.forge = {}

    def reserve(self, request):
        if self.fail_reserve:
            return {"state": "hold"}
        key = ("a" if self.kind == "cpu" else "b") * (64 if self.kind == "cpu" else 48)
        self.reserved[key] = "reserved"
        if self.kind == "cpu":
            receipt = {
                "schema": "skeleton.ai.cpu-capacity-guard.v1",
                "state": "reserved", "reservation_id": key,
                "window_digest": self.digest, "device": "cpu",
                "device_qualified": False, "is_execution_lease": False,
                "is_admission_grant": False, "cross_process_exclusive": False,
                "requires_live_backend_revalidation": True,
            }
        else:
            receipt = {
                "schema": "skeleton.ai.long-context-memory-budget.v1",
                "state": "reserved", "reservation_id": key,
                "device_qualified": False, "is_execution_lease": False,
                "is_admission_grant": False, "is_memory_allocation": False,
                "requires_live_backend_revalidation": True,
            }
        receipt.update(self.forge)
        return receipt

    def claim(self, key, request):
        if self.fail_claim or self.reserved.get(key) != "reserved":
            return {"state": "hold"}
        self.reserved[key] = "claimed"
        if self.kind == "cpu":
            receipt = {
                "schema": "skeleton.ai.cpu-capacity-guard.v1",
                "state": "claimed", "claimed": True,
                "window_digest": self.digest, "device_qualified": False,
                "is_execution_lease": False, "is_admission_grant": False,
                "cross_process_exclusive": False,
                "requires_live_backend_revalidation": True,
            }
        else:
            receipt = {
                "schema": "skeleton.ai.long-context-memory-budget.v1",
                "state": "claimed", "device_qualified": False,
                "is_execution_lease": False, "is_admission_grant": False,
                "is_memory_allocation": False,
                "requires_live_backend_revalidation": True,
            }
        receipt.update(self.forge)
        return receipt

    def release(self, key):
        self.released.append(key)
        return self.reserved.pop(key, None) is not None


class FairGuardStub(GuardStub):
    def reserve_fair_cycle(self, requests, *, quantum_tokens=256):
        from skeleton.ai.model_runtime.long_context_progress import _name
        receipts = []
        for request in requests:
            key = sha256((self.kind + ":" + request.stream_id).encode()).hexdigest()
            if self.kind == "memory":
                key = key[:48]
            self.reserved[key] = "reserved"
            if self.kind == "cpu":
                receipts.append({
                    "stream_digest": _name(request.stream_id),
                    "reservation_id": key, "window_digest": self.digest,
                    "max_tokens": request.max_tokens,
                })
            else:
                receipts.append({
                    "stream_digest": sha256(request.stream_id.encode()).hexdigest(),
                    "reservation_id": key, "requested_bytes": request.requested_bytes,
                })
        if self.kind == "cpu":
            return {
                "schema": "skeleton.ai.cpu-capacity-guard.v1",
                "state": "reserved", "device": "cpu", "device_qualified": False,
                "is_execution_lease": False, "is_admission_grant": False,
                "cycle_atomic_within_process": True,
                "cross_process_exclusive": False,
                "requires_live_backend_revalidation": True,
                "reservations": receipts,
            }
        return {
            "schema": "skeleton.ai.long-context-memory-budget.v1",
            "state": "reserved", "is_execution_lease": False,
            "is_admission_grant": False, "is_memory_allocation": False,
            "device_qualified": False,
            "cycle_atomic_within_process": True,
            "cross_process_exclusive": False,
            "requires_live_backend_revalidation": True,
            "reservations": receipts,
        }


class KvStub:
    def __init__(self, digest):
        self.digest = digest
        self.fail = False
        self.forge = {}

    def observe(self, layout, request, *, expected_model_digest):
        result = {
            "schema": "skeleton.ai.long-context-kv-compatibility.v1",
            "state": "hold" if self.fail else "compatible_observed",
            "reason": "backend_must_revalidate",
            "estimated_kv_bytes": 1024,
            "window_digest": self.digest,
            "device_qualified": False, "is_admission_grant": False,
            "is_execution_lease": False, "model_snapshot_attested": False,
            "tokenizer_state_attested": False,
            "kv_tensor_contents_verified": False,
            "requires_live_backend_revalidation": True,
        }
        result.update(self.forge)
        return result


class Clock:
    def __init__(self):
        self.value = 1000

    def __call__(self):
        self.value += 100
        return self.value


class AdmissionBundleTests(unittest.TestCase):
    def setUp(self):
        self.digest = "f" * 64
        self.cpu = GuardStub("cpu", self.digest)
        self.memory = GuardStub("memory", self.digest)
        self.kv = KvStub(self.digest)
        self.bundle = LongContextAdmissionBundle(
            self.cpu, self.memory, self.kv, nonce=lambda _: "c" * 64)
        self.request = AdmissionBundleRequest(
            CpuCapacityRequest("owner", "stream", "a" * 64, "b" * 64, 3, 8, 32),
            MemoryBudgetRequest("owner", "stream", 2048),
            KvLayout("d" * 64, "b" * 64, 1, 1, 4, 32, 2048),
            KvWindowRequest("stream", "a" * 64, 3, 8, 2048),
            "d" * 64,
        )

    def fair_setup(self):
        self.cpu = FairGuardStub("cpu", self.digest)
        self.memory = FairGuardStub("memory", self.digest)
        self.bundle = LongContextAdmissionBundle(
            self.cpu, self.memory, self.kv,
            nonce=lambda _: "c" * 64)
        other = AdmissionBundleRequest(
            CpuCapacityRequest("other", "second", "a" * 64, "b" * 64, 3, 8, 32),
            MemoryBudgetRequest("other", "second", 2048),
            self.request.kv_layout,
            KvWindowRequest("second", "a" * 64, 3, 8, 2048),
            "d" * 64,
        )
        return other

    def test_fair_cycle_atomic_reservation_then_individual_claim(self):
        other = self.fair_setup()
        # nonce is called with a byte-count; adapter ignores the argument.
        self.bundle._nonce = lambda n, seq=iter(("c" * 64, "e" * 64)): next(seq)
        result = self.bundle.reserve_fair_cycle((self.request, other),
                                                quantum_tokens=8)
        self.assertEqual(result["state"], "reserved")
        self.assertEqual(len(result["reservations"]), 2)
        self.assertFalse(result["is_execution_lease"])
        self.assertFalse(result["cross_process_exclusive"])
        self.assertEqual(self.bundle.status()["active"], 2)
        for receipt, request in zip(result["reservations"], (other, self.request)):
            self.assertEqual(self.bundle.claim(receipt["bundle_id"], request)["state"],
                             "claimed")
            self.assertTrue(self.bundle.release(receipt["bundle_id"]))
        self.assertEqual(self.bundle.status()["active"], 0)
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_fair_cycle_nonce_collision_rolls_back_both_guards(self):
        other = self.fair_setup()
        result = self.bundle.reserve_fair_cycle((self.request, other),
                                                quantum_tokens=8)
        self.assertEqual(result["state"], "hold")
        self.assertEqual(result["reservations"], [])
        self.assertEqual(self.bundle.status()["active"], 0)
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_fair_cycle_cpu_dependency_failure_rolls_back_ram(self):
        other = self.fair_setup()
        self.cpu.reserve_fair_cycle = Mock(side_effect=OSError("CPU offline"))
        result = self.bundle.reserve_fair_cycle((self.request, other),
                                                quantum_tokens=8)
        self.assertEqual(result["state"], "hold")
        self.assertEqual(result["reservations"], [])
        self.assertFalse(self.memory.reserved)
        self.assertEqual(self.bundle.status()["active"], 0)

    def test_fair_cycle_partial_publication_failure_rolls_back(self):
        other = self.fair_setup()
        self.bundle._nonce = lambda n, seq=iter(("c" * 64, "e" * 64)): next(seq)
        class FailSecond(dict):
            def __setitem__(self, key, value):
                if len(self) >= 1:
                    raise MemoryError("simulated publication failure")
                return super().__setitem__(key, value)
        self.bundle._entries = FailSecond()
        result = self.bundle.reserve_fair_cycle((self.request, other),
                                                quantum_tokens=8)
        self.assertEqual(result["state"], "hold")
        self.assertEqual(self.bundle.status()["active"], 0)
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_fair_cycle_input_validation_and_budget(self):
        other = self.fair_setup()
        with self.assertRaises(LongContextSpoolError):
            self.bundle.reserve_fair_cycle((self.request, self.request))
        with self.assertRaises(LongContextSpoolError):
            self.bundle.reserve_fair_cycle([self.request])
        self.assertEqual(self.bundle.reserve_fair_cycle(
            (self.request, other), quantum_tokens=4)["state"], "hold")
        self.assertFalse(self.memory.reserved)

    def test_bundle_expiry_revokes_both_inner_reservations(self):
        clock = Clock()
        bundle = LongContextAdmissionBundle(
            self.cpu, self.memory, self.kv,
            nonce=lambda _: "c" * 64, clock=clock, lifetime_ns=1000)
        key = bundle.reserve(self.request)["bundle_id"]
        self.assertIsNotNone(key)
        clock.value += 2000
        self.assertEqual(bundle.status()["active"], 0)
        self.assertEqual(bundle.status()["revocations"], 1)
        self.assertEqual(bundle.claim(key, self.request)["state"], "hold")
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_bundle_slow_reservation_fails_closed(self):
        clock = Clock()
        bundle = LongContextAdmissionBundle(
            self.cpu, self.memory, self.kv,
            nonce=lambda _: "c" * 64, clock=clock, lifetime_ns=1000)
        original = self.cpu.reserve
        def slow(request):
            clock.value += 2000
            return original(request)
        self.cpu.reserve = slow
        result = bundle.reserve(self.request)
        self.assertEqual(result["reason"], "bundle_observation_expired")
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_bundle_clock_regression_revokes_claims(self):
        clock = Clock()
        bundle = LongContextAdmissionBundle(
            self.cpu, self.memory, self.kv,
            nonce=lambda _: "c" * 64, clock=clock, lifetime_ns=1000)
        bundle.reserve(self.request)
        clock.value = 0
        with self.assertRaises(LongContextSpoolError):
            bundle.status()
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_reserve_claim_release_never_grants_execution(self):
        first = self.bundle.reserve(self.request)
        self.assertEqual(first["state"], "reserved")
        self.assertFalse(first["is_execution_lease"])
        self.assertFalse(first["is_memory_allocation"])
        self.assertFalse(first["cross_process_exclusive"])
        key = first["bundle_id"]
        claimed = self.bundle.claim(key, self.request)
        self.assertEqual(claimed["state"], "claimed")
        self.assertFalse(claimed["is_admission_grant"])
        self.assertEqual(self.bundle.claim(key, self.request)["state"], "hold")
        self.assertTrue(self.bundle.release(key))
        self.assertFalse(self.bundle.release(key))
        self.assertEqual(self.bundle.status()["active"], 0)
        self.assertEqual(len(self.cpu.released), 1)
        self.assertEqual(len(self.memory.released), 1)

    def test_kv_hold_prevents_any_resource_reservation(self):
        self.kv.fail = True
        self.assertEqual(self.bundle.reserve(self.request)["reason"],
                         "kv_identity_or_memory_unverified")
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_cpu_hold_rolls_back_memory(self):
        self.cpu.fail_reserve = True
        result = self.bundle.reserve(self.request)
        self.assertEqual(result["reason"], "cpu_reservation_unverified")
        self.assertEqual(self.bundle.status()["active"], 0)
        self.assertFalse(self.memory.reserved)
        self.assertEqual(len(self.memory.released), 1)

    def test_memory_hold_never_calls_cpu(self):
        self.memory.fail_reserve = True
        self.assertEqual(self.bundle.reserve(self.request)["reason"],
                         "memory_reservation_unverified")
        self.assertFalse(self.cpu.reserved)

    def test_claim_revalidates_kv_and_releases_both(self):
        key = self.bundle.reserve(self.request)["bundle_id"]
        self.kv.digest = "e" * 64
        self.assertEqual(self.bundle.claim(key, self.request)["reason"],
                         "kv_changed_before_claim")
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_claim_memory_failure_revokes_cpu_claim(self):
        key = self.bundle.reserve(self.request)["bundle_id"]
        self.memory.fail_claim = True
        self.assertEqual(self.bundle.claim(key, self.request)["reason"],
                         "claim_revalidation_failed")
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)

    def test_forged_receipts_hold(self):
        for field, value in (
            ("is_execution_lease", True),
            ("is_admission_grant", True),
            ("device_qualified", True),
            ("requires_live_backend_revalidation", False),
        ):
            with self.subTest(field=field):
                self.cpu.forge = {field: value}
                self.assertEqual(self.bundle.reserve(self.request)["state"], "hold")
                self.assertEqual(self.bundle.status()["active"], 0)
                self.assertFalse(self.cpu.reserved)
                self.assertFalse(self.memory.reserved)
                self.cpu.forge = {}
                self.memory.forge = {field: value}
                self.assertEqual(self.bundle.reserve(self.request)["state"], "hold")
                self.assertEqual(self.bundle.status()["active"], 0)
                self.assertFalse(self.cpu.reserved)
                self.assertFalse(self.memory.reserved)
                self.memory.forge = {}
                self.kv.forge = {field: value}
                self.assertEqual(self.bundle.reserve(self.request)["state"], "hold")
                self.assertEqual(self.bundle.status()["active"], 0)
                self.kv.forge = {}

    def test_kv_budget_and_model_attestation_hold(self):
        for changes in (
            {"estimated_kv_bytes": 4096},
            {"estimated_kv_bytes": True},
            {"window_digest": "0" * 64},
            {"model_snapshot_attested": True},
            {"tokenizer_state_attested": True},
        ):
            with self.subTest(changes=changes):
                self.kv.forge = changes
                result = self.bundle.reserve(self.request)
                if changes.get("window_digest") == "0" * 64:
                    # Digest-shaped but different from CPU: no partial publish.
                    self.assertEqual(result["state"], "hold")
                else:
                    self.assertEqual(result["state"], "hold")
                self.assertEqual(self.bundle.status()["active"], 0)
        self.kv.forge = {}

    def test_duplicate_stream_and_capacity_hold(self):
        first = self.bundle.reserve(self.request)
        self.assertEqual(first["state"], "reserved")
        self.assertEqual(self.bundle.reserve(self.request)["reason"], "duplicate_stream")
        self.assertEqual(self.bundle.status()["active"], 1)

    def test_close_and_fork_do_not_resurrect(self):
        self.bundle.reserve(self.request)
        self.bundle.close()
        self.assertEqual(self.bundle.status()["active"], 0)
        with self.assertRaises(LongContextSpoolError):
            self.bundle.reserve(self.request)
        fresh = LongContextAdmissionBundle(self.cpu, self.memory, self.kv)
        with patch("skeleton.ai.model_runtime.long_context_admission_bundle.os.getpid",
                   return_value=-1):
            with self.assertRaises(LongContextSpoolError):
                fresh.reserve(self.request)

    def test_request_identity_mismatch_and_gpu_hold(self):
        with self.assertRaises(LongContextSpoolError):
            AdmissionBundleRequest(
                self.request.cpu, MemoryBudgetRequest("other", "stream", 2048),
                self.request.kv_layout, self.request.kv_window, "d" * 64)
        with self.assertRaises(LongContextSpoolError):
            AdmissionBundleRequest(
                self.request.cpu, self.request.memory,
                KvLayout("d" * 64, "b" * 64, 1, 1, 4, 32, 2048,
                         device_kind="gpu"),
                self.request.kv_window, "d" * 64)

    def test_nonce_failure_rolls_back_all(self):
        broken = LongContextAdmissionBundle(
            self.cpu, self.memory, self.kv,
            nonce=Mock(side_effect=OSError("entropy unavailable")))
        self.assertEqual(broken.reserve(self.request)["state"], "hold")
        self.assertFalse(self.cpu.reserved)
        self.assertFalse(self.memory.reserved)


if __name__ == "__main__":
    unittest.main()
