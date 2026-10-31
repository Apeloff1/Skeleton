"""Deterministic energy anti-thrash and stale telemetry regressions."""
from __future__ import annotations

from unittest import TestCase

from skeleton.app.offline_cpu_budget import (
    CpuTopology, MemoryTopology, plan_cpu_workers,
)
from skeleton.app.offline_energy_budget import (
    PowerObservation, plan_energy_workers,
)
from skeleton.app.offline_energy_hysteresis import (
    EnergyHysteresis, HysteresisError, HysteresisPolicy,
)

CPU = CpuTopology(8, 4, 8.0, None, "test", "test", "unavailable", "Linux")
MEM = MemoryTopology(8 * 1024**3, 4 * 1024**3, "test")
BASE = plan_cpu_workers(CPU, MEM, operator_max_workers=8,
                        bytes_per_worker=256 * 1024**2,
                        memory_reserve_bytes=512 * 1024**2,
                        thermal_state="normal")


def candidate(temp=40, battery=90, ac=True):
    return plan_energy_workers(BASE, PowerObservation(
        battery, ac, temp, "test-battery", "test-ac", "test-thermal",
    ))


class TestEnergyHysteresis(TestCase):
    def test_recovery_requires_multiple_samples(self):
        gate = EnergyHysteresis(HysteresisPolicy(recovery_samples=3, recovery_cooldown_ns=0))
        healthy = candidate()
        self.assertEqual(gate.step(healthy, now_ns=1, sampled_ns=1).admitted_workers, 0)
        self.assertEqual(gate.step(healthy, now_ns=2, sampled_ns=2).admitted_workers, 0)
        self.assertEqual(gate.step(healthy, now_ns=3, sampled_ns=3).admitted_workers, 1)
        self.assertEqual(gate.step(healthy, now_ns=4, sampled_ns=4).admitted_workers, 1)
        self.assertEqual(gate.step(healthy, now_ns=5, sampled_ns=5).admitted_workers, 1)
        self.assertEqual(gate.step(healthy, now_ns=6, sampled_ns=6).admitted_workers, 2)

    def test_critical_sheds_immediately(self):
        gate = EnergyHysteresis(HysteresisPolicy(recovery_samples=2, recovery_cooldown_ns=0))
        gate.step(candidate(), now_ns=1, sampled_ns=1)
        gate.step(candidate(), now_ns=2, sampled_ns=2)
        self.assertEqual(gate.workers, 1)
        receipt = gate.step(candidate(temp=95), now_ns=3, sampled_ns=3)
        self.assertEqual(receipt.admitted_workers, 0)
        self.assertEqual(receipt.healthy_streak, 0)

    def test_stale_telemetry_denied(self):
        gate = EnergyHysteresis(HysteresisPolicy(recovery_samples=2,
                                                 recovery_cooldown_ns=0,
                                                 max_sample_age_ns=10))
        gate.step(candidate(), now_ns=1, sampled_ns=1)
        gate.step(candidate(), now_ns=2, sampled_ns=2)
        self.assertEqual(gate.workers, 1)
        result = gate.step(candidate(), now_ns=100, sampled_ns=1)
        self.assertEqual(result.admitted_workers, 0)
        self.assertEqual(result.reason, "stale_or_future_telemetry")

    def test_future_telemetry_denied(self):
        gate = EnergyHysteresis()
        result = gate.step(candidate(), now_ns=1, sampled_ns=2)
        self.assertEqual(result.admitted_workers, 0)

    def test_cooldown_prevents_oscillation(self):
        gate = EnergyHysteresis(HysteresisPolicy(recovery_samples=2,
                                                 recovery_cooldown_ns=100))
        gate.step(candidate(), now_ns=1, sampled_ns=1)
        gate.step(candidate(), now_ns=2, sampled_ns=2)
        gate.step(candidate(temp=95), now_ns=3, sampled_ns=3)
        for now in range(4, 20):
            self.assertEqual(gate.step(candidate(), now_ns=now, sampled_ns=now).admitted_workers, 0)
        self.assertEqual(gate.step(candidate(), now_ns=103, sampled_ns=103).admitted_workers, 1)

    def test_step_cap(self):
        gate = EnergyHysteresis(HysteresisPolicy(recovery_samples=2,
                                                 recovery_cooldown_ns=0,
                                                 max_recovery_step=2))
        gate.step(candidate(), now_ns=1, sampled_ns=1)
        result = gate.step(candidate(), now_ns=2, sampled_ns=2)
        self.assertEqual(result.admitted_workers, 2)
        self.assertLessEqual(result.admitted_workers, result.candidate_workers)

    def test_deterministic_receipt(self):
        first = EnergyHysteresis()
        second = EnergyHysteresis()
        a = first.step(candidate(), now_ns=100, sampled_ns=100)
        b = second.step(candidate(), now_ns=100, sampled_ns=100)
        self.assertEqual(a.digest, b.digest)

    def test_clock_regression_rejected(self):
        gate = EnergyHysteresis()
        gate.step(candidate(), now_ns=10, sampled_ns=10)
        with self.assertRaises(HysteresisError):
            gate.step(candidate(), now_ns=9, sampled_ns=9)


    def test_installed_energy_cli_hysteresis(self):
        import io
        import json
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from skeleton.app.offline_energy_budget import main
        out = io.StringIO()
        with patch("skeleton.app.offline_energy_budget.probe_cpu_topology", return_value=CPU), \
             patch("skeleton.app.offline_energy_budget.probe_memory_topology", return_value=MEM), \
             patch("skeleton.app.offline_energy_budget.probe_power",
                   return_value=PowerObservation(95, True, 40, "test", "test", "test")), \
             patch("skeleton.app.offline_energy_budget.time.monotonic_ns",
                   side_effect=[1, 2, 3]), \
             redirect_stdout(out):
            self.assertEqual(main(["--hysteresis-samples", "3",
                                   "--hysteresis-interval-ms", "0"]), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data["hysteresis"]), 3)
        self.assertEqual(data["allowed_workers"], 1)

    def test_duplicate_sample_clock_cannot_accelerate_recovery(self):
        gate = EnergyHysteresis(HysteresisPolicy(recovery_samples=2, recovery_cooldown_ns=0))
        gate.step(candidate(), now_ns=10, sampled_ns=10)
        with self.assertRaises(HysteresisError):
            gate.step(candidate(), now_ns=10, sampled_ns=10)
        self.assertEqual(gate.workers, 0)

    def test_invalid_policy(self):
        for options in (
            {"recovery_samples": 1},
            {"recovery_cooldown_ns": -1},
            {"max_sample_age_ns": 0},
            {"max_recovery_step": 0},
        ):
            with self.assertRaises(HysteresisError):
                HysteresisPolicy(**options)

    def test_restart_receipt_requires_new_recovery_samples(self):
        gate = EnergyHysteresis(HysteresisPolicy(
            recovery_samples=2, recovery_cooldown_ns=0,
        ))
        gate.step(candidate(), now_ns=10, sampled_ns=10)
        gate.step(candidate(), now_ns=20, sampled_ns=20)
        self.assertEqual(gate.workers, 1)
        state = gate.checkpoint()
        recovered = EnergyHysteresis.restart_from_checkpoint(
            state, expected_digest=state["digest"],
        )
        self.assertEqual(recovered.workers, 0)
        self.assertIsNone(recovered.last_seen_ns)
        self.assertEqual(recovered.step(
            candidate(), now_ns=1, sampled_ns=1,
        ).admitted_workers, 0)
        self.assertEqual(recovered.step(
            candidate(), now_ns=2, sampled_ns=2,
        ).admitted_workers, 1)

    def test_checkpoint_tamper_and_wrong_anchor_rejected(self):
        gate = EnergyHysteresis()
        gate.step(candidate(), now_ns=5, sampled_ns=5)
        state = gate.checkpoint()
        tampered = dict(state, workers=12)
        with self.assertRaises(HysteresisError):
            EnergyHysteresis.restart_from_checkpoint(
                tampered, expected_digest=state["digest"],
            )
        with self.assertRaises(HysteresisError):
            EnergyHysteresis.restart_from_checkpoint(
                state, expected_digest="0" * 64,
            )

    def test_invalid_worker_grant_does_not_consume_sample_clock(self):
        from dataclasses import replace
        gate = EnergyHysteresis()
        original = candidate()
        invalid = replace(original, allowed_workers=original.base_workers + 1)
        with self.assertRaises(HysteresisError):
            gate.step(invalid, now_ns=100, sampled_ns=100)
        self.assertIsNone(gate.last_seen_ns)
        gate.step(original, now_ns=100, sampled_ns=100)
        self.assertEqual(gate.last_seen_ns, 100)
