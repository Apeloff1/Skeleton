"""Adversarial read-only laptop capacity selection, no model invocation.

All receipts and host controller values are synthetic test inputs; these
checks never qualify physical GPU/CPU performance or independent rights.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
    InstalledModelReport,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan import (
    DesktopCapacityHold, CgroupObservation,
    _quota, _int, observe_cgroup, recommend, observe_cpu,
)

MIB = 1024**2
GIB = 1024**3


def model(*, bytes=2*GIB, rights=True, verified=True):
    return InstalledModelReport(
        model_id="trusted_local",
        model_sha256="a"*64,
        manifest_sha256="b"*64,
        shard_count=1,
        model_bytes=bytes,
        rights_approved=rights,
        content_verified=verified,
        native_inference_tested=False,
        release_certified=False,
        archive_sha256="c"*64,
        source_sha="d"*40,
    )


def host(*, memory=12*GIB, disk=4*GIB):
    return {
        "schema":"laptop-device-observation.v1",
        "memory_total_bytes":32*GIB,
        "memory_available_bytes":memory,
        "swap_free_bytes":8*GIB,
        "state_storage_available_bytes":disk,
        "measurement_only":True,
        "qualified_device":False,
    }


def controller(*, remaining=8*GIB, cpu=2):
    return CgroupObservation(
        remaining, cpu, True, True, "cgroup-v2",
    )


class NativeLaptopCapacityPolicyTests(unittest.TestCase):
    def test_typical_cgroup_constrained_laptop_selects_finite_cpu_only(self):
        result = recommend(model(), host(), controller(), available_cores=12)
        self.assertEqual(result["status"], "conservative-advisory-profile-not-native-proof")
        self.assertEqual(result["effective_available_bytes"], 8*GIB)
        self.assertEqual(result["effective_cpu_cores"], 2)
        self.assertEqual(result["recommendation"]["threads"], 1)
        self.assertEqual(result["recommendation"]["gpu_layers"], 0)
        self.assertEqual(result["recommendation"]["context"], 2048)
        self.assertEqual(result["recommendation"]["max_output_tokens"], 256)
        self.assertFalse(result["gpu_memory_measured"])
        self.assertFalse(result["release_certified"])
        self.assertLess(result["recommendation"]["capacity_budget_bytes"], 8*GIB)

    def test_unconstrained_controller_uses_host_ram_but_does_not_guess_gpu(self):
        free = CgroupObservation(None, None, False, False, "no-cgroup-controller")
        result = recommend(model(), host(), free, available_cores=16)
        self.assertEqual(result["effective_available_bytes"], 12*GIB)
        self.assertEqual(result["recommendation"]["threads"], 8)
        self.assertEqual(result["recommendation"]["gpu_layers"], 0)
        self.assertFalse(result["device_pressure_qualified"])

    def test_insufficient_memory_refuses_even_if_swap_is_abundant(self):
        with self.assertRaises(DesktopCapacityHold):
            recommend(
                model(bytes=4*GIB),
                host(memory=16*GIB),
                controller(remaining=3*GIB, cpu=4),
                available_cores=12,
            )

    def test_insufficient_state_storage_refuses_before_native_activation(self):
        with self.assertRaises(DesktopCapacityHold):
            recommend(
                model(), host(disk=255*MIB),
                controller(), available_cores=12,
            )

    def test_unreviewed_rights_or_content_cannot_get_capacity_profile(self):
        for installed in (
            model(rights=False),
            model(verified=False),
        ):
            with self.subTest(installed=installed), self.assertRaises(DesktopCapacityHold):
                recommend(installed, host(), controller(), available_cores=8)

    def test_untrusted_host_telemetry_and_boolean_ints_are_refused(self):
        for observed in (
            None, {}, host(memory=True), host(memory=-1),
            dict(host(), measurement_only=False),
            dict(host(), qualified_device=True),
            dict(host(), state_storage_available_bytes="unlimited"),
        ):
            with self.subTest(observed=observed), self.assertRaises(DesktopCapacityHold):
                recommend(model(), observed, controller(), available_cores=8)
        with self.assertRaises(DesktopCapacityHold):
            recommend(model(), host(), controller(), available_cores=True)

    def test_absent_or_fabricated_cgroup_evidence_is_denied(self):
        for invalid in (
            dict(memory_available_bytes=None, cpu_quota_cores=2,
                 memory_bounded=True, cpu_bounded=True,
                 source="cgroup-v2"),
            dict(memory_available_bytes=8*GIB, cpu_quota_cores=True,
                 memory_bounded=True, cpu_bounded=True,
                 source="cgroup-v2"),
            dict(memory_available_bytes=8*GIB, cpu_quota_cores=-1,
                 memory_bounded=True, cpu_bounded=True,
                 source="cgroup-v2"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(DesktopCapacityHold):
                CgroupObservation(**invalid)

    def test_numeric_control_parsing_is_strict(self):
        for invalid in ("-12", "1.0", "5 GiB", "NaN", "2e9", "0x10", "2\n3", " "):
            with self.subTest(invalid=invalid), self.assertRaises(DesktopCapacityHold):
                _int(invalid)
        self.assertEqual(_int("128"), 128)
        self.assertEqual(_int("-1", allow_negative_one=True), -1)
        with self.assertRaises(DesktopCapacityHold):
            _quota(0, 100000)
        with self.assertRaises(DesktopCapacityHold):
            _quota(20000, 0)
        self.assertEqual(_quota(150000, 100000), 1)
        self.assertIsNone(_quota(-1, 100000))

    def test_v2_process_memory_and_cpu_are_observed_without_model_call(self):
        lookup={
            "memory.max": str(8*GIB),
            "memory.current": str(2*GIB),
            "cpu.max": "150000 100000",
        }
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan._process_cgroup",
                return_value=("cgroup-v2", "/local"),
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan._read_kernel",
                side_effect=lambda path: lookup[path.name],
            ) as kernel,
        ):
            result=observe_cgroup()
        self.assertEqual(result.memory_available_bytes, 6*GIB)
        self.assertEqual(result.cpu_quota_cores, 1)
        self.assertTrue(result.memory_bounded)
        self.assertEqual(kernel.call_count, 3)

    def test_v2_unbounded_resources_are_not_invented(self):
        lookup={
            "memory.max": "max",
            "memory.current": str(2*GIB),
            "cpu.max": "max 100000",
        }
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan._process_cgroup",
                return_value=("cgroup-v2", "/"),
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan._read_kernel",
                side_effect=lambda path: lookup[path.name],
            ),
        ):
            result=observe_cgroup()
        self.assertIsNone(result.memory_available_bytes)
        self.assertIsNone(result.cpu_quota_cores)
        self.assertFalse(result.memory_bounded)

    def test_cgroup_controller_usage_above_limit_refused(self):
        lookup={
            "memory.max": str(2*GIB),
            "memory.current": str(3*GIB),
            "cpu.max": "200000 100000",
        }
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan._process_cgroup",
                return_value=("cgroup-v2", "/"),
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan._read_kernel",
                side_effect=lambda path: lookup[path.name],
            ),
        ):
            with self.assertRaises(DesktopCapacityHold):
                observe_cgroup()

    def test_observed_cpu_affinity_is_not_exceeded(self):
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan.os.cpu_count",
                return_value=32,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan.os.sched_getaffinity",
                return_value={1,2,3},
                create=True,
            ),
        ):
            self.assertEqual(observe_cpu(), 3)


if __name__=="__main__":
    unittest.main()
