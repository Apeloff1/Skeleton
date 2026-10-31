"""Source-backed power telemetry and energy admission regressions."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from unittest import TestCase
from unittest.mock import patch

from skeleton.app.offline_cpu_budget import (
    CpuTopology, MemoryTopology, plan_cpu_workers,
)
from skeleton.app.offline_energy_budget import (
    EnergyError, EnergyPolicy, PowerObservation, _percent, main,
    plan_energy_workers, probe_power,
)

CPU = CpuTopology(8, 4, 8.0, None, "test", "test", "unavailable", "Linux")
MEM = MemoryTopology(8 * 1024**3, 4 * 1024**3, "test")
BASE = plan_cpu_workers(CPU, MEM, operator_max_workers=8,
                        bytes_per_worker=256 * 1024**2,
                        memory_reserve_bytes=512 * 1024**2,
                        thermal_state="normal")


def observation(battery=None, ac=True, temp=None):
    return PowerObservation(battery, ac, temp, "test-battery", "test-ac", "test-thermal")


class TestOfflineEnergyBudget(TestCase):
    def test_ac_and_cool(self):
        result = plan_energy_workers(BASE, observation(90, True, 45))
        self.assertEqual(result.allowed_workers, BASE.workers)
        self.assertEqual(len(result.digest), 64)

    def test_critical_thermal_denies(self):
        result = plan_energy_workers(BASE, observation(90, True, 90))
        self.assertEqual(result.allowed_workers, 0)
        self.assertEqual(result.reason, "cpu_thermal_critical")

    def test_warm_thermal_halves(self):
        result = plan_energy_workers(BASE, observation(90, True, 80))
        self.assertEqual(result.allowed_workers, BASE.workers // 2)

    def test_low_battery(self):
        result = plan_energy_workers(BASE, observation(15, False, 40))
        self.assertEqual(result.allowed_workers, 1)
        self.assertEqual(result.reason, "battery_low")

    def test_critical_battery(self):
        result = plan_energy_workers(BASE, observation(5, False, 40))
        self.assertEqual(result.allowed_workers, 0)
        self.assertEqual(result.reason, "battery_critical")

    def test_unknown_battery_while_unplugged(self):
        result = plan_energy_workers(BASE, observation(None, False, 40))
        self.assertEqual(result.allowed_workers, 1)
        self.assertEqual(result.reason, "battery_telemetry_unavailable")

    def test_unknown_ac_limits_workers(self):
        result = plan_energy_workers(BASE, observation(90, None, 40))
        self.assertEqual(result.allowed_workers, 1)
        self.assertEqual(result.reason, "ac_telemetry_unavailable")

    def test_unknown_thermal_limits_workers(self):
        result = plan_energy_workers(BASE, observation(90, True, None))
        self.assertEqual(result.allowed_workers, 2)
        self.assertEqual(result.reason, "thermal_telemetry_unavailable")

    def test_deterministic_receipt(self):
        power = observation(45, False, 70)
        self.assertEqual(plan_energy_workers(BASE, power).digest,
                         plan_energy_workers(BASE, power).digest)

    def test_invalid_measurements_and_policy(self):
        with self.assertRaises(EnergyError):
            observation(101, True, 50)
        with self.assertRaises(EnergyError):
            observation(50, 1, 50)
        with self.assertRaises(EnergyError):
            observation(50, True, float("nan"))
        with self.assertRaises(EnergyError):
            EnergyPolicy(low_battery_pct=8, critical_battery_pct=20)
        with self.assertRaises(EnergyError):
            EnergyPolicy(warm_cpu_c=95, critical_cpu_c=90)

    def test_percent_parser(self):
        self.assertEqual(_percent("0"), 0)
        self.assertEqual(_percent("100"), 100)
        self.assertIsNone(_percent("255"))
        self.assertIsNone(_percent("-1"))

    def test_linux_platform_probe(self):
        with patch("skeleton.app.offline_energy_budget.platform.system", return_value="Linux"), \
             patch("skeleton.app.offline_energy_budget._linux_power",
                   return_value=(80, True, "linux-sysfs-battery", "linux-sysfs-line-power")), \
             patch("skeleton.app.offline_energy_budget._linux_thermal",
                   return_value=(55.0, "linux-sysfs-cpu-labelled-thermal-zone")):
            power = probe_power()
        self.assertEqual(power.battery_percent, 80)
        self.assertEqual(power.cpu_temperature_c, 55.0)

    def test_unavailable_platform(self):
        with patch("skeleton.app.offline_energy_budget.platform.system", return_value="Other"):
            power = probe_power()
        self.assertIsNone(power.battery_percent)
        self.assertIsNone(power.on_ac)
        self.assertIsNone(power.cpu_temperature_c)

    def test_cli(self):
        out = io.StringIO()
        with patch("skeleton.app.offline_energy_budget.probe_cpu_topology", return_value=CPU), \
             patch("skeleton.app.offline_energy_budget.probe_memory_topology", return_value=MEM), \
             patch("skeleton.app.offline_energy_budget.probe_power", return_value=observation(95, True, 40)), \
             redirect_stdout(out):
            self.assertEqual(main([]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["schema"], "skeleton.offline.energy-admission.v1")
        self.assertLessEqual(result["allowed_workers"], result["base_workers"])
