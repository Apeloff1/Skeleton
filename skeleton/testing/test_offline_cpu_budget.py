"""Canonical source-backed CPU topology and worker-budget regressions."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from unittest import TestCase
from unittest.mock import patch

from skeleton.app.offline_cpu_budget import (
    CpuBudgetError, CpuTopology, MemoryTopology, _cache_size, _cgroup_cpu_quota,
    _linux_physical, main, plan_cpu_workers, probe_cpu_topology, probe_memory_topology,
)


CPU = CpuTopology(8, 4, 6.5, 12 * 1024**2, "test-affinity",
                  "test-quota", "test-l3", "Linux")
MEM = MemoryTopology(8 * 1024**3, 4 * 1024**3, "test-meminfo")


class TestCpuBudget(TestCase):
    def test_measured_admission(self):
        result = plan_cpu_workers(CPU, MEM, operator_max_workers=16,
                                  bytes_per_worker=512 * 1024**2,
                                  memory_reserve_bytes=1024**3,
                                  thermal_state="normal")
        self.assertEqual(result.cpu_limit, 5)
        self.assertEqual(result.memory_limit, 6)
        self.assertEqual(result.workers, 5)
        self.assertEqual(len(result.digest), 64)

    def test_unknown_thermal_conservative(self):
        result = plan_cpu_workers(CPU, MEM, operator_max_workers=16,
                                  bytes_per_worker=512 * 1024**2,
                                  memory_reserve_bytes=1024**3)
        self.assertEqual(result.workers, 2)
        self.assertEqual(result.reason, "thermal_conservative")

    def test_critical_thermal_stops(self):
        result = plan_cpu_workers(CPU, MEM, operator_max_workers=16,
                                  bytes_per_worker=1024, memory_reserve_bytes=0,
                                  thermal_state="critical")
        self.assertEqual(result.workers, 0)

    def test_missing_memory_limits_to_one(self):
        result = plan_cpu_workers(CPU, MemoryTopology(None, None, "unavailable"),
                                  operator_max_workers=16, bytes_per_worker=1024,
                                  memory_reserve_bytes=0, thermal_state="normal")
        self.assertEqual(result.workers, 1)
        self.assertEqual(result.reason, "memory_telemetry_unavailable")

    def test_memory_reserve_blocks(self):
        result = plan_cpu_workers(CPU, MemoryTopology(1024, 100, "test"),
                                  operator_max_workers=16, bytes_per_worker=100,
                                  memory_reserve_bytes=101, thermal_state="normal")
        self.assertEqual(result.workers, 0)
        self.assertEqual(result.reason, "memory_budget")

    def test_operator_cap(self):
        result = plan_cpu_workers(CPU, MEM, operator_max_workers=2,
                                  bytes_per_worker=1024, memory_reserve_bytes=0,
                                  thermal_state="normal")
        self.assertEqual(result.workers, 2)

    def test_deterministic_receipt(self):
        args = dict(operator_max_workers=8, bytes_per_worker=1024,
                    memory_reserve_bytes=0, thermal_state="normal")
        self.assertEqual(plan_cpu_workers(CPU, MEM, **args).digest,
                         plan_cpu_workers(CPU, MEM, **args).digest)

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(CpuBudgetError):
            CpuTopology(0, None, 0, None, "test", "test", "test", "Linux")
        with self.assertRaises(CpuBudgetError):
            CpuTopology(8, None, float("nan"), None, "test", "test", "test", "Linux")
        with self.assertRaises(CpuBudgetError):
            MemoryTopology(100, 101, "test")
        for invalid in (True, 0, -1, 257):
            with self.assertRaises(CpuBudgetError):
                plan_cpu_workers(CPU, MEM, operator_max_workers=invalid,
                                 bytes_per_worker=1024, memory_reserve_bytes=0)
        with self.assertRaises(CpuBudgetError):
            plan_cpu_workers(CPU, MEM, operator_max_workers=8,
                             bytes_per_worker=1024, memory_reserve_bytes=0,
                             thermal_state="unverified-normal")

    def test_cache_parser(self):
        self.assertEqual(_cache_size("32M"), 32 * 1024**2)
        self.assertEqual(_cache_size("256K"), 256 * 1024)
        self.assertIsNone(_cache_size("not-a-cache"))
        self.assertIsNone(_cache_size("999999999999G"))

    def test_linux_cgroup_v2_quota(self):
        def fake(path, limit=4096):
            return "150000 100000" if path.endswith("cpu.max") else None
        with patch("skeleton.app.offline_cpu_budget._bounded_text", side_effect=fake):
            self.assertEqual(_cgroup_cpu_quota(), (1.5, "cgroup-v2-cpu.max"))

    def test_linux_unlimited(self):
        def fake(path, limit=4096):
            return "max 100000" if path.endswith("cpu.max") else None
        with patch("skeleton.app.offline_cpu_budget._bounded_text", side_effect=fake):
            self.assertEqual(_cgroup_cpu_quota(), (None, "cgroup-v2-unlimited"))

    def test_linux_physical_core_ids_zero(self):
        def fake(path, limit=4096):
            if path.endswith("physical_package_id"):
                return "0"
            if path.endswith("core_id"):
                return "0" if "cpu0/" in path or "cpu1/" in path else "1"
            return None
        with patch("skeleton.app.offline_cpu_budget._bounded_text", side_effect=fake):
            self.assertEqual(_linux_physical({0, 1, 2}), 2)

    def test_platform_probe_linux(self):
        with patch("skeleton.app.offline_cpu_budget.platform.system", return_value="Linux"), \
             patch("skeleton.app.offline_cpu_budget.os.cpu_count", return_value=8), \
             patch("skeleton.app.offline_cpu_budget._linux_physical", return_value=4), \
             patch("skeleton.app.offline_cpu_budget._linux_l3", return_value=None), \
             patch("skeleton.app.offline_cpu_budget._cgroup_cpu_quota", return_value=(2.5, "test")):
            result = probe_cpu_topology()
        self.assertGreaterEqual(result.logical_visible, 1)
        self.assertLessEqual(result.effective_cpus, result.logical_visible)

    def test_missing_linux_meminfo(self):
        with patch("skeleton.app.offline_cpu_budget.platform.system", return_value="Linux"), \
             patch("skeleton.app.offline_cpu_budget._bounded_text", return_value=None):
            self.assertEqual(probe_memory_topology().source, "unavailable")

    def test_cli_output(self):
        output = io.StringIO()
        with patch("skeleton.app.offline_cpu_budget.probe_cpu_topology", return_value=CPU), \
             patch("skeleton.app.offline_cpu_budget.probe_memory_topology", return_value=MEM), \
             redirect_stdout(output):
            self.assertEqual(main(["--thermal", "normal"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["schema"], "skeleton.offline.cpu-worker-budget.v1")
        self.assertEqual(result["thermal_source"], "operator-supplied")
        self.assertGreater(result["workers"], 0)
