"""Apple Silicon native-KV qualification receipts require real backend evidence."""
from __future__ import annotations

from unittest.mock import patch
import unittest

from skeleton.app.offline_metal_qualification import (
    evaluate_host_kv_qualification,
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
