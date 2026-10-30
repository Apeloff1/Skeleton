"""Apple Silicon native-KV qualification receipts require real backend evidence."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from skeleton.app.offline_metal_qualification import (
    _validated_shared_fence_receipt, evaluate_host_kv_qualification,
    qualify_apple_shared_buffer_fence,
)


def inputs(**overrides):
    value = {
        "pinned_manifest_digest": "a" * 64,
        "runtime_digest": "b" * 64,
        "model_digest": "c" * 64,
        "execution_receipt": "d" * 64,
        "requested_kv_location": "host",
        "selected_gpu_layers": 7,
        "observed": {
            "backend_reported": True,
            "reported_host_kv_bytes": 1024 * 1024,
            "reported_device_kv_bytes": 0,
        },
        "metal_present": True,
    }
    value.update(overrides)
    return value


class AppleKVQualificationTests(unittest.TestCase):
    def test_qualified_only_for_real_host_kv_native_report(self):
        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=True,
        ):
            report = evaluate_host_kv_qualification(**inputs())
        self.assertTrue(report["qualification_accepted"])
        self.assertEqual(report["status"], "qualified_host_kv_diagnostic")
        self.assertEqual(len(report["qualification_receipt_sha256"]), 64)
        self.assertFalse(report["driver_coherency_verified"])
        self.assertFalse(report["device_tensor_migration_verified"])
        self.assertFalse(report["metal_event_fence_verified"])

    def test_missing_or_contradictory_native_evidence_fails_closed(self):
        changes = (
            {"observed": None},
            {"observed": {"backend_reported": False,
                          "reported_host_kv_bytes": 0,
                          "reported_device_kv_bytes": 0}},
            {"observed": {"backend_reported": True,
                          "reported_host_kv_bytes": 1024,
                          "reported_device_kv_bytes": 1024}},
            {"requested_kv_location": "backend"},
            {"selected_gpu_layers": 0},
            {"metal_present": False},
            {"observed": {"backend_reported": True,
                          "reported_host_kv_bytes": 1024,
                          "reported_device_kv_bytes": 0,
                          "unrecognized_allocation_lines": 1}},
        )
        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=True,
        ):
            for case in changes:
                with self.subTest(case=case):
                    report = evaluate_host_kv_qualification(**inputs(**case))
                    self.assertFalse(report["qualification_accepted"])

    def test_non_apple_host_cannot_claim_metal_device_qualification(self):
        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=False,
        ):
            self.assertFalse(evaluate_host_kv_qualification(
                **inputs()
            )["qualification_accepted"])

    def test_real_metal_shared_buffer_proof_requires_exact_known_digest(self):
        proof = {
            "schema": "skeleton.apple.metal-shared-fence.v1",
            "passed": True,
            "shared_metal_buffers": 2,
            "synchronized_command_buffers": 2,
            "verified_values": 128,
            "output_sha256":
                "a6d248f975ab3b8adf09ce0beef4493c7cda5827b19f277728fa28c38708b286",
            "model_tensor_fence_verified": False,
            "llama_kv_cache_fence_verified": False,
        }
        self.assertTrue(_validated_shared_fence_receipt(proof)["passed"])
        for changed in (
            {"output_sha256": "0" * 64},
            {"synchronized_command_buffers": 1},
            {"verified_values": 0},
            {"model_tensor_fence_verified": True},
            {"llama_kv_cache_fence_verified": True},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(RuntimeError):
                    _validated_shared_fence_receipt({**proof, **changed})
        with self.assertRaises(RuntimeError):
            _validated_shared_fence_receipt({**proof, "extra": True})

    def test_opt_in_native_metal_probe_process_receipt_is_bounded(self):
        proof = {
            "schema": "skeleton.apple.metal-shared-fence.v1",
            "passed": True,
            "shared_metal_buffers": 2,
            "synchronized_command_buffers": 2,
            "verified_values": 128,
            "output_sha256":
                "a6d248f975ab3b8adf09ce0beef4493c7cda5827b19f277728fa28c38708b286",
            "model_tensor_fence_verified": False,
            "llama_kv_cache_fence_verified": False,
        }
        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=True,
        ), patch(
            "skeleton.app.offline_metal_qualification.os.access",
            return_value=True,
        ), patch(
            "skeleton.app.offline_metal_qualification.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(proof).encode("utf-8"),
            ),
        ) as called:
            receipt = qualify_apple_shared_buffer_fence()
        self.assertTrue(receipt["passed"])
        self.assertEqual(len(receipt["qualification_source_sha256"]), 64)
        self.assertFalse(receipt["llama_kv_cache_fence_verified"])
        argv = called.call_args.args[0]
        self.assertEqual(argv[:2], ["/usr/bin/xcrun", "swift"])
        self.assertTrue(argv[2].endswith("qualify_metal_shared.swift"))
        self.assertFalse(called.call_args.kwargs["check"] is True)

    def test_metal_probe_fails_closed_without_apple_machine(self):
        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "Apple Silicon"):
                qualify_apple_shared_buffer_fence()

    def test_invalid_hashes_and_impossible_native_counters_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_host_kv_qualification(**inputs(
                runtime_digest="not-a-sha",
            ))
        with self.assertRaises(ValueError):
            evaluate_host_kv_qualification(**inputs(
                observed={"backend_reported": True,
                          "reported_host_kv_bytes": -5,
                          "reported_device_kv_bytes": 0},
            ))


if __name__ == "__main__":
    unittest.main()
