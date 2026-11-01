"""Fail-closed pressure latch contracts; no real device qualification."""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from unittest import TestCase
from unittest.mock import patch

from skeleton.ai.model_runtime import LongContextPressureLatch as Exported
from skeleton.ai.model_runtime.long_context_cli import main
from skeleton.ai.model_runtime.long_context_pressure_latch import (
    LongContextPressureLatch, _inspect,
)
from skeleton.ai.model_runtime.long_context_telemetry_fusion import (
    LongContextTelemetryFusion,
)


def envelope(*, state="observed", event_state="observed", cpu="normal",
             memory="normal", thermal="normal", energy="normal",
             deltas=None, reasons=None):
    result = {
        "schema": "skeleton.ai.long-context-telemetry-fusion.v1",
        "state": state,
        "signals": {"cpu": cpu, "memory": memory, "thermal": thermal,
                    "energy": energy},
        "reasons": [] if reasons is None else reasons,
        "event_state": event_state,
        "event_deltas": ({"oom": 0, "oom_kill": 0, "nr_throttled": 0}
                         if event_state == "observed" and deltas is None else deltas),
        "sources": ("host_psi", "cgroup_v2", "cgroup_events"),
        "cross_source_snapshot_atomic": False,
        "scope_membership_attested": False,
        "pressure_signals_attested": False,
        "device_qualified": False,
        "is_admission_grant": False,
        "is_execution_lease": False,
        "requires_live_backend_revalidation": True,
    }
    return resign(result)


def resign(value):
    result = {k: v for k, v in value.items() if k != "observation_digest"}
    result["observation_digest"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


class TestPressureLatch(TestCase):
    def setUp(self):
        self.monitor = LongContextTelemetryFusion()
        self.ticks = iter(range(100, 10000, 100))
        self.latch = LongContextPressureLatch(
            self.monitor, clock=lambda: next(self.ticks))
        self.mock = patch.object(self.monitor, "sample", return_value=envelope())
        self.observer = self.mock.start()
        self.addCleanup(self.mock.stop)

    def test_three_samples_only_diagnostic(self):
        self.assertIs(Exported, LongContextPressureLatch)
        self.assertEqual([self.latch.sample()["state"] for _ in range(4)],
                         ["warming", "warming", "repeated_normal_observed",
                          "repeated_normal_observed"])
        result = self.latch.sample()
        for key in ("is_admission_grant", "is_execution_lease",
                    "device_qualified", "pressure_signals_attested",
                    "restart_state_durable", "cross_source_snapshot_atomic"):
            self.assertIs(result[key], False)
        self.assertIs(result["requires_live_backend_revalidation"], True)
        self.assertIs(result["observation_digest_is_authenticity_proof"], False)

    def test_unknown_thermal_energy_never_clear(self):
        self.observer.return_value = envelope(thermal="unknown", energy="unknown")
        for _ in range(8):
            self.assertEqual(self.latch.sample()["state"], "hold")

    def test_pressure_reset_and_recovery(self):
        self.latch.sample()
        self.latch.sample()
        for level in ("elevated", "critical", "unknown"):
            self.observer.return_value = envelope(memory=level)
            self.assertEqual(self.latch.sample()["state"], "hold")
            self.observer.return_value = envelope()
            self.assertEqual(self.latch.sample()["state"], "warming")

    def test_oom_throttle_and_baseline_hold(self):
        for delta in ({"oom": 1, "oom_kill": 0, "nr_throttled": 0},
                      {"oom": 0, "oom_kill": 1, "nr_throttled": 0},
                      {"oom": 0, "oom_kill": 0, "nr_throttled": 1}):
            self.observer.return_value = envelope(deltas=delta)
            self.assertEqual(self.latch.sample()["state"], "hold")
        self.observer.return_value = envelope(
            state="baseline_required", event_state="baseline_required")
        self.assertEqual(self.latch.sample()["state"], "hold")

    def test_forged_authority_and_extra_keys(self):
        for key in ("is_admission_grant", "is_execution_lease",
                    "device_qualified", "pressure_signals_attested",
                    "scope_membership_attested", "cross_source_snapshot_atomic"):
            self.observer.return_value = resign({**envelope(), key: True})
            self.assertEqual(self.latch.sample()["reasons"], ["forged_authority"])
        self.observer.return_value = resign({**envelope(), "authorized": True})
        self.assertEqual(self.latch.sample()["state"], "hold")

    def test_digest_tamper_and_bad_counter_type(self):
        valid = envelope()
        self.assertEqual(_inspect(valid)[0], "normal_observed")
        self.observer.return_value = {**valid, "signals": {
            **valid["signals"], "cpu": "critical"}}
        self.assertEqual(self.latch.sample()["reasons"], ["digest_mismatch"])
        self.observer.return_value = resign({
            **valid, "event_deltas": {"oom": True, "oom_kill": 0,
                                     "nr_throttled": 0}})
        self.assertEqual(self.latch.sample()["state"], "hold")

    def test_clock_regression_does_not_rebase(self):
        ticks = iter((100, 200, 150, 250, 175, 275, 300, 400))
        latch = LongContextPressureLatch(self.monitor, clock=lambda: next(ticks))
        self.assertEqual(latch.sample()["state"], "warming")
        self.assertEqual(latch.sample()["state"], "warming")
        self.assertEqual(latch.sample()["reasons"], ["clock_invalid"])
        self.assertEqual(latch.sample()["state"], "warming")
        self.assertEqual(latch.sample()["reasons"], ["clock_invalid"])
        self.assertEqual(latch.sample()["state"], "warming")
        self.assertEqual(latch.sample()["state"], "warming")
        self.assertEqual(latch.sample()["state"], "repeated_normal_observed")

    def test_clock_gap_and_monitor_exception(self):
        ticks = iter((100, 200, 5000, 5100, 5200))
        latch = LongContextPressureLatch(
            self.monitor, max_gap_ns=300, clock=lambda: next(ticks))
        latch.sample()
        latch.sample()
        self.assertIn("clock_gap_reset", latch.sample()["reasons"])
        self.observer.side_effect = RuntimeError("missing")
        self.assertEqual(latch.sample()["reasons"], ["monitor_unavailable"])
        self.observer.side_effect = None
        self.assertEqual(latch.sample()["state"], "warming")

    def test_fork_before_lock_and_bad_constructor(self):
        with patch("skeleton.ai.model_runtime.long_context_pressure_latch.os.getpid",
                   return_value=os.getpid() + 1):
            with self.assertRaisesRegex(OSError, "fork"):
                self.latch.sample()
        for kwargs in ({"required_samples": True}, {"required_samples": 1},
                       {"required_samples": 17}, {"max_gap_ns": 0},
                       {"max_gap_ns": 10_000_000_001}, {"clock": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LongContextPressureLatch(self.monitor, **kwargs)

    def test_cli_one_shot_without_spool(self):
        output = StringIO()
        with patch("skeleton.ai.model_runtime.long_context_cli.LongContextTelemetryFusion",
                   return_value=self.monitor), patch(
            "skeleton.ai.model_runtime.long_context_cli.LongContextSpool",
            side_effect=AssertionError("spool must remain closed"),
        ), redirect_stdout(output):
            self.assertEqual(main(["--root", "/nonexistent-spool",
                                   "--tokenizer-digest", "a" * 64,
                                   "head-observe-latched"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "warming")
        self.assertFalse(result["is_execution_lease"])
