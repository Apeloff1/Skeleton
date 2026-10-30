"""Apple Silicon native-KV qualification receipts require real backend evidence."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from skeleton.app.offline_metal_qualification import (
    _expected_multisync_digest, _validated_shared_fence_receipt,
    evaluate_host_kv_qualification, qualify_apple_shared_buffer_fence,
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
            "backend_reported_metal_model_bytes": 1024 * 1024,
            "backend_reported_gpu_layers": 7,
        },
        "metal_present": True,
    }
    value.update(overrides)
    return value


def multisync_proof():
    return {
        "schema": "skeleton.apple.metal-multisync.v2",
        "passed": True,
        "shared_metal_buffers": 13,
        "synchronized_command_buffers": 17,
        "verified_values": 832,
        "serial_cpu_gpu_cpu_round_trips": 4,
        "cross_queue_event_handoffs": 4,
        "parallel_independent_lanes": 3,
        "shared_event_cpu_observations": 2,
        "shared_event_cpu_acknowledgements": 2,
        "output_sha256":
            "7765e4607be2b2849b33bdbd6cff387365600703d14fd49ba17ed0b7b4654a6f",
        "model_tensor_fence_verified": False,
        "llama_kv_cache_fence_verified": False,
    }


class AppleKVQualificationTests(unittest.TestCase):
    def test_qualified_only_for_real_host_kv_native_report(self):
        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=True,
        ):
            report = evaluate_host_kv_qualification(**inputs())
        self.assertTrue(report["qualification_accepted"])
        self.assertTrue(report["offload_count_consistent_with_request"])
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
            {"observed": {"backend_reported": True,
                          "reported_host_kv_bytes": 1024,
                          "reported_device_kv_bytes": 0}},
            {"observed": {"backend_reported": True,
                          "reported_host_kv_bytes": 1024,
                          "reported_device_kv_bytes": 0,
                          "backend_reported_gpu_layers": 8}},
            {"requested_kv_location": "backend"},
            {"selected_gpu_layers": 0},
            {"metal_present": False},
            {"observed": {"backend_reported": True,
                          "reported_host_kv_bytes": 1024,
                          "reported_device_kv_bytes": 0,
                          "backend_reported_metal_model_bytes": 1024,
                          "backend_reported_gpu_layers": 40}},
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

    def test_multisync_independent_expected_digest(self):
        self.assertEqual(
            _expected_multisync_digest(),
            "7765e4607be2b2849b33bdbd6cff387365600703d14fd49ba17ed0b7b4654a6f",
        )

    def test_real_metal_shared_buffer_proof_requires_exact_known_digest(self):
        proof = multisync_proof()
        self.assertTrue(_validated_shared_fence_receipt(proof)["passed"])
        for changed in (
            {"output_sha256": "0" * 64},
            {"synchronized_command_buffers": 1},
            {"verified_values": 0},
            {"serial_cpu_gpu_cpu_round_trips": 2},
            {"cross_queue_event_handoffs": 0},
            {"parallel_independent_lanes": 0},
            {"shared_event_cpu_observations": 0},
            {"shared_event_cpu_acknowledgements": 0},
            {"shared_metal_buffers": 12},
            {"schema": "skeleton.apple.metal-shared-fence.v1"},
            {"model_tensor_fence_verified": True},
            {"llama_kv_cache_fence_verified": True},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(RuntimeError):
                    _validated_shared_fence_receipt({**proof, **changed})
        with self.assertRaises(RuntimeError):
            _validated_shared_fence_receipt({**proof, "extra": True})

    def test_opt_in_native_metal_probe_process_receipt_is_bounded(self):
        proof = multisync_proof()
        def mocked_run(_args, **kwargs):
            kwargs["stdout"].write(json.dumps(proof).encode("utf-8"))
            return SimpleNamespace(returncode=0)

        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=True,
        ), patch(
            "skeleton.app.offline_metal_qualification.os.access",
            return_value=True,
        ), patch(
            "skeleton.app.offline_metal_qualification.subprocess.run",
            side_effect=mocked_run,
        ) as called:
            receipt = qualify_apple_shared_buffer_fence()
        self.assertTrue(receipt["passed"])
        self.assertEqual(len(receipt["qualification_source_sha256"]), 64)
        self.assertFalse(receipt["llama_kv_cache_fence_verified"])
        argv = called.call_args.args[0]
        self.assertEqual(argv[:2], ["/usr/bin/xcrun", "swift"])
        self.assertTrue(argv[2].endswith("qualify_metal_shared.swift"))
        self.assertIn("skeleton-private-metal-", argv[2])
        self.assertFalse(called.call_args.kwargs["check"] is True)

    def test_metal_probe_rejects_oversized_native_output(self):
        def oversized_run(_args, **kwargs):
            kwargs["stdout"].write(b"x" * 8300)
            return SimpleNamespace(returncode=0)

        with patch(
            "skeleton.app.offline_metal_qualification._apple_silicon",
            return_value=True,
        ), patch(
            "skeleton.app.offline_metal_qualification.os.access",
            return_value=True,
        ), patch(
            "skeleton.app.offline_metal_qualification.subprocess.run",
            side_effect=oversized_run,
        ):
            with self.assertRaisesRegex(RuntimeError, "qualification failed"):
                qualify_apple_shared_buffer_fence()

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
