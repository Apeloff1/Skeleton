"""Conservative cross-source telemetry fusion regressions (no device claims)."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from skeleton.ai.model_runtime import LongContextTelemetryFusion as ExportedFusion
from skeleton.ai.model_runtime.long_context_cli import main as long_context_main
from skeleton.ai.model_runtime.long_context_telemetry_fusion import (
    LongContextTelemetryFusion, _event, _source,
)


def observation(cpu="normal", memory="normal", thermal="unknown", energy="unknown"):
    return {
        "signals": {
            "cpu": cpu, "memory": memory, "thermal": thermal, "energy": energy,
        },
        "is_admission_grant": False, "is_execution_lease": False,
        "pressure_signals_attested": False, "device_qualified": False,
    }


def event(state="observed", deltas=None):
    return {
        "state": state, "reasons": [] if state == "observed"
        else ["first_sample_unproven"],
        "event_deltas": ({"oom": 0, "oom_kill": 0, "nr_throttled": 0}
                         if state == "observed" and deltas is None else deltas),
        "is_admission_grant": False,
    }


class TestTelemetryFusion(TestCase):
    def setUp(self):
        self.ticks = iter(range(100, 10000, 100))
        self.monitor = LongContextTelemetryFusion(clock=lambda: next(self.ticks))
        self.host = patch(
            "skeleton.ai.model_runtime.long_context_telemetry_fusion.observe_host_pressure",
            return_value=observation(),
        )
        self.cgroup = patch(
            "skeleton.ai.model_runtime.long_context_telemetry_fusion.observe_cgroup_pressure",
            return_value=observation(),
        )
        self.host.start()
        self.cgroup.start()
        self.addCleanup(self.host.stop)
        self.addCleanup(self.cgroup.stop)
        self.events = patch.object(self.monitor._events, "sample", return_value=event())
        self.mock_events = self.events.start()
        self.addCleanup(self.events.stop)

    def test_payload_free_non_authorizing_observation(self):
        result = self.monitor.sample()
        self.assertEqual(result["state"], "observed")
        self.assertEqual(result["signals"]["cpu"], "normal")
        self.assertEqual(result["signals"]["thermal"], "unknown")
        self.assertIn("thermal_unknown", result["reasons"])
        self.assertFalse(result["is_admission_grant"])
        self.assertFalse(result["is_execution_lease"])
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["cross_source_snapshot_atomic"])
        self.assertEqual(len(result["observation_digest"]), 64)
        self.assertEqual(json.loads(json.dumps(result))["state"], "observed")

    def test_unknown_dominates_even_normal_other_source(self):
        with patch(
            "skeleton.ai.model_runtime.long_context_telemetry_fusion.observe_cgroup_pressure",
            return_value=observation(cpu="unknown", memory="critical"),
        ):
            result = self.monitor.sample()
        self.assertEqual(result["signals"]["cpu"], "unknown")
        self.assertEqual(result["signals"]["memory"], "critical")

    def test_missing_source_never_falls_back_to_normal(self):
        with patch(
            "skeleton.ai.model_runtime.long_context_telemetry_fusion.observe_host_pressure",
            side_effect=OSError("unavailable"),
        ):
            result = self.monitor.sample()
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["signals"]["cpu"], "unknown")
        self.assertIn("host_observation_unavailable", result["reasons"])

    def test_event_baseline_not_accepted_as_proof(self):
        self.mock_events.return_value = event("baseline_required")
        result = self.monitor.sample()
        self.assertEqual(result["state"], "baseline_required")
        self.assertIsNone(result["event_deltas"])
        self.assertIn("first_sample_unproven", result["reasons"])

    def test_oom_and_throttle_raise_severity(self):
        self.mock_events.return_value = event(
            deltas={"oom": 1, "oom_kill": 0, "nr_throttled": 2})
        result = self.monitor.sample()
        self.assertEqual(result["signals"]["memory"], "critical")
        self.assertEqual(result["signals"]["cpu"], "elevated")
        self.assertIn("memory_oom_event", result["reasons"])
        self.assertIn("cpu_throttle_event", result["reasons"])

    def test_forged_authority_and_incomplete_source_rejected(self):
        for bad in (
            {"signals": {}},
            {**observation(), "is_admission_grant": True},
            {**observation(), "pressure_signals_attested": True},
            {**observation(), "signals": {**observation()["signals"], "cpu": True}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _source(bad)
        with patch(
            "skeleton.ai.model_runtime.long_context_telemetry_fusion.observe_host_pressure",
            return_value={**observation(), "is_execution_lease": True},
        ):
            result = self.monitor.sample()
        self.assertEqual(result["signals"]["cpu"], "unknown")
        self.assertEqual(result["state"], "unavailable")

    def test_bad_event_payload_is_held(self):
        for bad in (
            event(deltas={"oom": True, "oom_kill": 0, "nr_throttled": 0}),
            {"state": "observed", "reasons": [], "event_deltas": None},
            {"state": "baseline_required", "reasons": [], "event_deltas": {}},
            {"state": "observed", "reasons": ["bad\nreason"],
             "event_deltas": {"oom": 0, "oom_kill": 0, "nr_throttled": 0}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _event(bad)
            self.mock_events.return_value = bad
            result = self.monitor.sample()
            self.assertEqual(result["event_state"], "baseline_required")
            self.assertIn("event_observation_unavailable", result["reasons"])

    def test_nonmonotonic_and_slow_observation_holds_unknown(self):
        for clock in (iter([100, 100]), iter([100, 1_000_000])):
            monitor = LongContextTelemetryFusion(
                clock=lambda: next(clock), max_sample_ns=100)
            with patch.object(monitor._events, "sample", return_value=event()):
                result = monitor.sample()
            self.assertEqual(result["state"], "unavailable")
            self.assertEqual(result["signals"]["memory"], "unknown")
            self.assertIn("observation_clock_invalid", result["reasons"])

    def test_forked_monitor_rejected_before_inherited_lock(self):
        with patch(
            "skeleton.ai.model_runtime.long_context_telemetry_fusion.os.getpid",
            return_value=os.getpid() + 1,
        ):
            with self.assertRaisesRegex(OSError, "fork"):
                self.monitor.sample()

    def test_bad_constructor_bounds(self):
        for invalid in (0, True, -1, 10_000_000_001, "10"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                LongContextTelemetryFusion(max_sample_ns=invalid)

    def test_cli_fused_diagnostics_never_opens_spool(self):
        self.assertIs(ExportedFusion, LongContextTelemetryFusion)
        output = StringIO()
        with patch("skeleton.ai.model_runtime.long_context_cli.LongContextSpool",
                   side_effect=AssertionError("must not open spool")):
            with patch(
                "skeleton.ai.model_runtime.long_context_cli.LongContextTelemetryFusion",
                return_value=self.monitor,
            ):
                with redirect_stdout(output):
                    code = long_context_main([
                        "--root", "/nonexistent-spool",
                        "--tokenizer-digest", "a" * 64,
                        "head-observe-fused",
                    ])
        self.assertEqual(code, 0)
        observed = json.loads(output.getvalue())
        self.assertEqual(observed["state"], "observed")
        self.assertFalse(observed["is_execution_lease"])

    def test_event_authority_spoof_rejected(self):
        for key in (
            "is_admission_grant", "is_execution_lease", "device_qualified",
            "pressure_signals_attested", "scope_membership_attested",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                _event({**event(), key: 1})
        self.mock_events.return_value = {
            **event(), "is_execution_lease": True,
        }
        observed = self.monitor.sample()
        self.assertEqual(observed["event_state"], "baseline_required")
        self.assertIn("event_observation_unavailable", observed["reasons"])

    def test_clock_regression_does_not_rebase_last_good_sample(self):
        times = iter((100, 200, 150, 250, 175, 275, 300, 400))
        monitor = LongContextTelemetryFusion(clock=lambda: next(times))
        with patch.object(monitor._events, "sample", return_value=event()):
            first = monitor.sample()
            second = monitor.sample()
            third = monitor.sample()
            fourth = monitor.sample()
        self.assertEqual(first["state"], "observed")
        self.assertEqual(second["state"], "unavailable")
        self.assertEqual(third["state"], "unavailable")
        self.assertEqual(fourth["state"], "observed")

    def test_observations_do_not_mutate_spool(self):
        self.assertFalse(hasattr(self.monitor, "spool"))
        self.assertEqual(self.monitor.sample()["sources"],
                         ("host_psi", "cgroup_v2", "cgroup_events"))
