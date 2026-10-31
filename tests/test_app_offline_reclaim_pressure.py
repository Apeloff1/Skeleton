"""Kernel reclaim pressure and real offline resource-fabric integration."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from skeleton.app.offline_reclaim_pressure import (
    ReclaimCounters, ReclaimPressureController, probe_reclaim_counters,
)
from skeleton.app.offline_resource_fabric import AdaptiveResourceFabric, GPUResource
from skeleton.app.offline_resources import LocalResourceSnapshot


def sample(scanned: int, reclaimed: int, faults: int = 0, scope: str = "cgroup_v2"):
    return ReclaimCounters(scope, scanned, reclaimed, faults)


def host():
    return LocalResourceSnapshot(
        total_ram_bytes=8_000_000_000, available_ram_bytes=5_000_000_000,
        total_disk_bytes=200_000_000_000, free_disk_bytes=100_000_000_000,
        cpu_count=8, cpu_load_ratio=0, total_swap_bytes=0,
        free_swap_bytes=0, memory_pressure_ratio=0,
    )


class KernelProbeTests(unittest.TestCase):
    def test_cgroup_counters_preferred_and_scope_declared(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "memory.stat").write_text(
                "pgscan 123\npgsteal 78\npgmajfault 9\n", encoding="ascii"
            )
            (root / "vmstat").write_text(
                "pgscan_kswapd 999\npgscan_direct 1\n"
                "pgsteal_kswapd 900\npgsteal_direct 1\npgmajfault 100\n",
                encoding="ascii",
            )
            with patch("skeleton.app.offline_reclaim_pressure.sys.platform", "linux"):
                reading = probe_reclaim_counters(root / "memory.stat", root / "vmstat")
            self.assertEqual(reading, sample(123, 78, 9))

    def test_host_fallback_never_double_counts_aggregate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vmstat").write_text(
                "pgscan 90\npgscan_kswapd 50\npgscan_direct 40\n"
                "pgsteal 60\npgsteal_kswapd 40\npgsteal_direct 20\n"
                "pgmajfault 8\n", encoding="ascii",
            )
            with patch("skeleton.app.offline_reclaim_pressure.sys.platform", "linux"):
                reading = probe_reclaim_counters(root / "missing", root / "vmstat")
            self.assertEqual(reading, sample(90, 60, 8, "host_vmstat"))

    def test_bad_or_oversized_kernel_data_cannot_claim_telemetry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cgroup = root / "memory.stat"
            hostfile = root / "vmstat"
            hostfile.write_text("garbage\n", encoding="ascii")
            for invalid in (
                "pgscan 1\npgscan 2\npgsteal 1\npgmajfault 1\n",
                "pgscan -1\npgsteal 1\npgmajfault 1\n",
                "pgscan 1\npgsteal NaN\npgmajfault 1\n",
                "pgscan 1\n" * 10000,
            ):
                cgroup.write_text(invalid, encoding="ascii")
                with patch("skeleton.app.offline_reclaim_pressure.sys.platform", "linux"):
                    self.assertIsNone(probe_reclaim_counters(cgroup, hostfile))

    def test_unsupported_platform_has_no_fabricated_counters(self):
        with patch("skeleton.app.offline_reclaim_pressure.sys.platform", "darwin"):
            self.assertIsNone(probe_reclaim_counters())


class ReclaimControllerTests(unittest.TestCase):
    def test_hysteresis_and_missing_telemetry_do_not_clear_hold(self):
        tracker = ReclaimPressureController()
        ram = 4096 * 10000
        tracker.observe(sample(0, 0), physical_ram_bytes=ram, now_ns=1_000_000_000)
        self.assertFalse(tracker.snapshot()["backpressure"])
        tracker.observe(sample(1000, 20), physical_ram_bytes=ram, now_ns=2_000_000_000)
        self.assertTrue(tracker.snapshot()["backpressure"])
        self.assertEqual(tracker.snapshot()["reclaim_efficiency"], 0.02)
        tracker.observe(None, physical_ram_bytes=ram, now_ns=3_000_000_000)
        self.assertTrue(tracker.snapshot()["backpressure"])
        self.assertEqual(tracker.snapshot()["scope"], "unavailable")
        tracker.observe(sample(2000, 50), physical_ram_bytes=ram, now_ns=4_000_000_000)
        for step in range(1, 4):
            tracker.observe(
                sample(2000, 50), physical_ram_bytes=ram,
                now_ns=(4 + step) * 1_000_000_000,
            )
            self.assertEqual(tracker.snapshot()["backpressure"], step < 3)

    def test_major_faults_trigger_even_without_reclaim_scans(self):
        tracker = ReclaimPressureController()
        tracker.observe(sample(0, 0), physical_ram_bytes=4096 * 10000, now_ns=1_000_000_000)
        tracker.observe(sample(0, 0, 20), physical_ram_bytes=4096 * 10000, now_ns=2_000_000_000)
        self.assertTrue(tracker.snapshot()["backpressure"])

    def test_counter_reset_or_scope_change_cannot_fake_recovery(self):
        tracker = ReclaimPressureController()
        ram = 4096 * 10000
        tracker.observe(sample(0, 0), physical_ram_bytes=ram, now_ns=1_000_000_000)
        tracker.observe(sample(1000, 20), physical_ram_bytes=ram, now_ns=2_000_000_000)
        tracker.observe(sample(2, 1), physical_ram_bytes=ram, now_ns=3_000_000_000)
        self.assertTrue(tracker.snapshot()["backpressure"])
        self.assertEqual(tracker.snapshot()["counter_resets"], 1)
        tracker.observe(sample(3, 2, scope="host_vmstat"), physical_ram_bytes=ram, now_ns=4_000_000_000)
        self.assertTrue(tracker.snapshot()["backpressure"])
        self.assertEqual(tracker.snapshot()["counter_resets"], 2)

    def test_rapid_polling_does_not_miscompute_rates(self):
        tracker = ReclaimPressureController()
        ram = 4096 * 10000
        tracker.observe(sample(0, 0), physical_ram_bytes=ram, now_ns=1_000_000_000)
        tracker.observe(sample(1000, 0), physical_ram_bytes=ram, now_ns=1_000_000_001)
        self.assertIsNone(tracker.snapshot()["scanned_ram_fraction_per_s"])
        tracker.observe(sample(1000, 0), physical_ram_bytes=ram, now_ns=2_000_000_000)
        self.assertTrue(tracker.snapshot()["backpressure"])

    def test_rejects_untyped_or_negative_measurements(self):
        with self.assertRaises(ValueError):
            sample(-1, 0)
        with self.assertRaises(ValueError):
            sample(1, 0, scope="other")
        tracker = ReclaimPressureController()
        for kwargs in (
            {"physical_ram_bytes": 0},
            {"physical_ram_bytes": True},
            {"physical_ram_bytes": 100, "now_ns": -1},
        ):
            with self.assertRaises(ValueError):
                tracker.observe(sample(1, 0), **kwargs)


class ResourceFabricIntegrationTests(unittest.TestCase):
    def test_real_plan_reduces_streams_and_vetoes_shared_gpu_when_reclaiming(self):
        with TemporaryDirectory() as directory:
            fabric = AdaptiveResourceFabric(directory)
            # Simulated kernel counters; no hardware qualification claimed.
            fabric._reclaim.observe(
                sample(0, 0), physical_ram_bytes=4096 * 10000, now_ns=1_000_000_000,
            )
            fabric._reclaim.observe(
                sample(1000, 0), physical_ram_bytes=4096 * 10000, now_ns=2_000_000_000,
            )
            gpu = GPUResource(
                device="simulated-metal", vendor="apple", dedicated_total_bytes=0,
                dedicated_free_bytes=0, shared_with_system_ram=True,
                measurement="simulated", recommended_working_set_bytes=1_000_000_000,
                current_allocated_bytes=0,
            )
            probes = [
                patch("skeleton.app.offline_resource_fabric.probe_local_resources", return_value=host()),
                patch("skeleton.app.offline_resource_fabric.probe_gpu_resources", return_value=(gpu,)),
                patch("skeleton.app.offline_resource_fabric.probe_reclaim_counters", return_value=None),
                patch("skeleton.app.offline_resource_fabric.probe_cgroup_events", return_value=None),
                patch("skeleton.app.offline_resource_fabric.probe_io_pressure", return_value=None),
                patch("skeleton.app.offline_resource_fabric.probe_cpu_throttle", return_value=None),
                patch("skeleton.app.offline_resource_fabric.probe_swap_counters", return_value=None),
                patch("skeleton.app.offline_resource_fabric.probe_cpu_thermal", return_value=()),
            ]
            for guard in probes:
                guard.start()
                self.addCleanup(guard.stop)
            plan = fabric.plan(
                10_000_000, desired_streams=8,
                requested_gpu_bytes=100_000_000, allow_gpu=True, readonly_stream=True,
            )
            self.assertEqual(plan.stream_count, 1)
            self.assertFalse(plan.gpu_eligible)
            self.assertTrue(plan.as_dict()["reclaim_backpressure"])
            self.assertTrue(fabric.monitor()["controller"]["reclaim_pressure"]["backpressure"])


if __name__ == "__main__":
    unittest.main()
