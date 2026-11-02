"""Deterministic, hardware-free fallback regression tests."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from skeleton.ai.model_runtime.long_context_platform_fallback import (
    LongContextPlatformFallback, PlatformFallbackPolicy, PlatformFallbackRequest,
)
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError


def healthy():
    return {
        "schema": "skeleton.ai.long-context-telemetry-fusion.v1",
        "state": "observed", "event_state": "observed",
        "sources": ("host_psi", "cgroup_v2", "cgroup_events"),
        "signals": dict.fromkeys(("cpu", "memory", "thermal", "energy"), "normal"),
        "event_deltas": {"oom": 0, "oom_kill": 0, "nr_throttled": 0},
        "reasons": [], "cross_source_snapshot_atomic": False,
        "scope_membership_attested": False, "pressure_signals_attested": False,
        "device_qualified": False, "is_admission_grant": False,
        "is_execution_lease": False,
        "requires_live_backend_revalidation": True,
    }


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 100
        return self.value


class Observer:
    def __init__(self):
        self.value = healthy()

    def sample(self):
        return self.value


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.observer = Observer()
        self.clock = Clock()
        self.request = PlatformFallbackRequest("owner", "stream", "m_chip", 32, 4096)
        with patch("skeleton.ai.model_runtime.long_context_platform_fallback.platform.system",
                   return_value="Linux"):
            self.monitor = LongContextPlatformFallback(
                self.observer, clock=self.clock,
                policy=PlatformFallbackPolicy(required_normal_samples=2,
                                              cooldown_ns=100))

    def test_cpu_candidate_never_authorizes_or_qualifies(self):
        self.assertEqual(self.monitor.sample(self.request)["state"], "warming")
        result = self.monitor.sample(self.request)
        self.assertEqual(result["state"], "cpu_candidate")
        self.assertEqual(result["candidate_device"], "cpu")
        self.assertEqual(result["requested_device"], "m_chip")
        for field in ("device_qualified", "gpu_qualified", "m_chip_qualified",
                      "is_execution_lease", "is_admission_grant",
                      "is_memory_allocation", "cross_process_exclusive",
                      "telemetry_attested", "restart_state_durable"):
            self.assertIs(result[field], False)
        self.assertTrue(result["requires_live_backend_revalidation"])
        self.assertNotIn("owner", json.dumps(result))

    def test_pressure_revokes_and_rewarms(self):
        self.monitor.sample(self.request)
        self.assertEqual(self.monitor.sample(self.request)["state"], "cpu_candidate")
        self.observer.value = {**healthy(), "signals": {
            **healthy()["signals"], "memory": "critical"}}
        result = self.monitor.sample(self.request)
        self.assertEqual(result["state"], "hold")
        self.assertEqual(result["revocations"], 1)
        self.observer.value = healthy()
        self.assertEqual(self.monitor.sample(self.request)["state"], "warming")
        self.assertEqual(self.monitor.sample(self.request)["state"], "cpu_candidate")

    def test_forged_or_incomplete_telemetry_never_grants(self):
        for bad in (
            {"device_qualified": True}, {"is_execution_lease": True},
            {"is_admission_grant": True}, {"pressure_signals_attested": True},
            {"cross_source_snapshot_atomic": True},
            {"state": "baseline_required"}, {"event_state": "baseline_required"},
            {"sources": ["host_psi", "cgroup_v2", "cgroup_events"]},
            {"reasons": ["unverified"]},
            {"signals": {"cpu": "normal"}},
            {"signals": {**healthy()["signals"], "thermal": "unknown"}},
            {"event_deltas": {"oom": True, "oom_kill": 0, "nr_throttled": 0}},
            {"event_deltas": {"oom": 1, "oom_kill": 0, "nr_throttled": 0}},
        ):
            with self.subTest(bad=bad):
                self.observer.value = {**healthy(), **bad}
                self.assertEqual(self.monitor.sample(self.request)["state"], "hold")
                self.assertEqual(self.monitor.sample(self.request)["normal_samples"], 0)
        self.observer.value = healthy()
        self.assertEqual(self.monitor.sample(self.request)["state"], "warming")

    def test_identity_change_resets_observations(self):
        self.monitor.sample(self.request)
        other = PlatformFallbackRequest("other", "stream", "cpu", 32, 4096)
        self.assertEqual(self.monitor.sample(other)["state"], "warming")
        self.assertEqual(self.monitor.sample(other)["state"], "cpu_candidate")
        self.assertEqual(self.monitor.sample(self.request)["state"], "warming")

    def test_fork_close_clock_and_policy_fail_closed(self):
        with patch("skeleton.ai.model_runtime.long_context_platform_fallback.os.getpid",
                   return_value=-1):
            with self.assertRaises(LongContextSpoolError):
                self.monitor.sample(self.request)
        self.monitor.sample(self.request)
        self.clock.value = 0
        self.assertEqual(self.monitor.sample(self.request)["reason"], "clock_unverified")
        self.monitor.close()
        with self.assertRaises(LongContextSpoolError):
            self.monitor.sample(self.request)
        with self.assertRaises(LongContextSpoolError):
            PlatformFallbackPolicy(required_normal_samples=1)
        with self.assertRaises(LongContextSpoolError):
            PlatformFallbackRequest("owner", "stream", "cuda", 32, 4096)
        with self.assertRaises(LongContextSpoolError):
            PlatformFallbackRequest("owner", "stream", "cpu", True, 4096)

    def test_cli_does_not_open_spool_or_claim_hardware(self):
        from skeleton.ai.model_runtime.long_context_cli import main
        with patch("skeleton.ai.model_runtime.long_context_platform_fallback.LongContextTelemetryFusion",
                   return_value=self.observer):
            with patch("skeleton.ai.model_runtime.long_context_cli.LongContextSpool",
                       side_effect=AssertionError("unexpected spool access")):
                output = io.StringIO()
                with redirect_stdout(output):
                    status = main(["--root", "/unused", "--tokenizer-digest", "a"*64,
                                   "head-platform-fallback", "--principal", "owner",
                                   "--stream-id", "stream", "--requested-device", "gpu",
                                   "--max-tokens", "8", "--request-bytes", "4096"])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertNotEqual(result["state"], "cpu_candidate")
        self.assertFalse(result["is_execution_lease"])


if __name__ == "__main__":
    unittest.main()
