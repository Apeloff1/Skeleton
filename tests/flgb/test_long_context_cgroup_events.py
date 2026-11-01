"""Deterministic cgroup event monitor state and descriptor-race regressions."""
from __future__ import annotations

import os
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.long_context_cgroup_events import (
    CgroupEventMonitor, _read_events,
)
from skeleton.ai.model_runtime.long_context_host_pressure import _secure_directory
from skeleton.ai.model_runtime.long_context_cli import main as long_context_main
from skeleton.ai.model_runtime import CgroupEventMonitor as ExportedCgroupEventMonitor


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                     "POSIX cgroup event custody")
class TestCgroupEventMonitor(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "cgroup"
        self.root.mkdir(mode=0o700)
        self.write_memory(0, 0)
        self.write_cpu(0)
        self.monitor = CgroupEventMonitor(self.root)

    def write_memory(self, oom, killed):
        (self.root / "memory.events").write_text(
            f"low 0\nhigh 0\nmax 0\noom {oom}\noom_kill {killed}\n",
            encoding="ascii")

    def write_cpu(self, throttled):
        (self.root / "cpu.stat").write_text(
            f"usage_usec 123\nnr_periods 4\nnr_throttled {throttled}\n",
            encoding="ascii")

    def test_package_export_and_cli_baseline_are_non_authorizing(self):
        self.assertIs(ExportedCgroupEventMonitor, CgroupEventMonitor)
        output = StringIO()
        with patch("skeleton.ai.model_runtime.long_context_cli.LongContextSpool",
                   side_effect=AssertionError("must not open spool")):
            with patch("skeleton.ai.model_runtime.long_context_cli.CgroupEventMonitor",
                       return_value=self.monitor):
                with redirect_stdout(output):
                    code = long_context_main([
                        "--root", str(self.root / "unused"),
                        "--tokenizer-digest", "a" * 64,
                        "head-observe-events",
                    ])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "unused").exists())
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "baseline_required")
        self.assertFalse(result["is_admission_grant"])

    def test_first_sample_is_not_delta_or_grant(self):
        result = self.monitor.sample()
        self.assertEqual(result["state"], "baseline_required")
        self.assertIn("first_sample_unproven", result["reasons"])
        self.assertIsNone(result["event_deltas"])
        self.assertFalse(result["scope_membership_attested"])
        self.assertFalse(result["is_admission_grant"])

    def test_zero_delta_is_observation_not_safety_proof(self):
        with patch("skeleton.ai.model_runtime.long_context_cgroup_events.monotonic_ns",
                   side_effect=[100, 200]):
            self.monitor.sample()
            result = self.monitor.sample()
        self.assertEqual(result["state"], "observed")
        self.assertEqual(result["event_deltas"],
                         {"oom": 0, "oom_kill": 0, "nr_throttled": 0})
        self.assertFalse(result["pressure_signals_attested"])

    def test_oom_and_cpu_throttle_are_explicit_holds(self):
        with patch("skeleton.ai.model_runtime.long_context_cgroup_events.monotonic_ns",
                   side_effect=[100, 200]):
            self.monitor.sample()
            self.write_memory(2, 1)
            self.write_cpu(3)
            result = self.monitor.sample()
        self.assertEqual(result["state"], "observed")
        self.assertEqual(result["event_deltas"]["oom_kill"], 1)
        self.assertIn("memory_oom_event", result["reasons"])
        self.assertIn("cpu_throttle_event", result["reasons"])

    def test_counter_regression_requires_new_baseline(self):
        self.write_memory(5, 1)
        self.write_cpu(9)
        with patch("skeleton.ai.model_runtime.long_context_cgroup_events.monotonic_ns",
                   side_effect=[100, 200, 300]):
            self.monitor.sample()
            self.write_cpu(1)
            reset = self.monitor.sample()
            later = self.monitor.sample()
        self.assertEqual(reset["state"], "baseline_required")
        self.assertIn("event_counter_regressed", reset["reasons"])
        self.assertEqual(later["state"], "observed")
        self.assertEqual(later["event_deltas"]["nr_throttled"], 0)

    def test_expired_and_regressed_clocks_fail_closed(self):
        monitor = CgroupEventMonitor(self.root, max_interval_ns=100)
        with patch("skeleton.ai.model_runtime.long_context_cgroup_events.monotonic_ns",
                   side_effect=[100, 300, 250]):
            monitor.sample()
            expired = monitor.sample()
            regressed = monitor.sample()
        self.assertIn("sample_interval_expired", expired["reasons"])
        self.assertIn("monotonic_clock_regressed", regressed["reasons"])
        self.assertIsNone(regressed["event_deltas"])

    def test_forked_child_cannot_inherit_monitor_baseline(self):
        with patch("skeleton.ai.model_runtime.long_context_cgroup_events.os.getpid",
                   return_value=os.getpid() + 1):
            with self.assertRaisesRegex(OSError, "fork"):
                self.monitor.sample()

    def test_missing_duplicate_and_oversized_events_reset_baseline(self):
        self.monitor.sample()
        for raw in (b"", b"oom 0\noom 1\noom_kill 0\n",
                    b"oom nan\noom_kill 0\n", b"x" * 4097):
            with self.subTest(raw=raw[:20]):
                (self.root / "memory.events").write_bytes(raw)
                result = self.monitor.sample()
                self.assertEqual(result["state"], "baseline_required")
                self.assertIn("event_observation_unavailable", result["reasons"])
        self.write_memory(0, 0)
        self.assertIn("first_sample_unproven", self.monitor.sample()["reasons"])

    def test_symlinked_or_hardlinked_events_rejected(self):
        target = self.root / "cpu.stat"
        target.unlink()
        target.symlink_to(self.root / "memory.events")
        self.assertEqual(self.monitor.sample()["state"], "baseline_required")
        target.unlink()
        self.write_cpu(0)
        os.link(target, self.root / "cpu.alias")
        self.assertEqual(self.monitor.sample()["state"], "baseline_required")

    def test_file_replacement_between_samples_resets_baseline(self):
        with patch("skeleton.ai.model_runtime.long_context_cgroup_events.monotonic_ns",
                   side_effect=[100, 200, 300]):
            self.monitor.sample()
            replacement = self.root / "events.new"
            replacement.write_bytes((self.root / "memory.events").read_bytes())
            os.replace(replacement, self.root / "memory.events")
            result = self.monitor.sample()
            later = self.monitor.sample()
        self.assertEqual(result["state"], "baseline_required")
        self.assertIn("cgroup_identity_changed", result["reasons"])
        self.assertIsNone(result["event_deltas"])
        self.assertEqual(later["state"], "observed")

    def test_source_replacement_between_pair_reads_is_rejected(self):
        from skeleton.ai.model_runtime.long_context_cgroup_events import _read_events
        original = _read_events
        replaced = [False]

        def replace(directory, name):
            value = original(directory, name)
            if name == "memory.events" and not replaced[0]:
                replaced[0] = True
                replacement = self.root / "events.new"
                replacement.write_bytes((self.root / "memory.events").read_bytes())
                os.replace(replacement, self.root / "memory.events")
            return value

        with patch("skeleton.ai.model_runtime.long_context_cgroup_events._read_events",
                   side_effect=replace):
            result = self.monitor.sample()
        self.assertTrue(replaced[0])
        self.assertIn("event_observation_unavailable", result["reasons"])

    def test_event_inode_swap_rejected(self):
        original = os.read
        swapped = [False]

        def replace(fd, size):
            data = original(fd, size)
            if not swapped[0] and b"nr_throttled" in data:
                swapped[0] = True
                new = self.root / "new"
                new.write_bytes(data)
                os.replace(new, self.root / "cpu.stat")
            return data

        with patch("skeleton.ai.model_runtime.long_context_cgroup_events.os.read",
                   side_effect=replace):
            result = self.monitor.sample()
        self.assertTrue(swapped[0])
        self.assertIn("event_observation_unavailable", result["reasons"])

    def test_invalid_source_rejected_without_open(self):
        fd = _secure_directory(self.root)
        try:
            with self.assertRaises(ValueError):
                _read_events(fd, "../cpu.stat")
        finally:
            os.close(fd)

    def test_interval_rejects_bool_and_out_of_range(self):
        for bad in (True, 0, -1, 60_000_000_001, "100"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                CgroupEventMonitor(self.root, max_interval_ns=bad)


if __name__ == "__main__":
    unittest.main()
