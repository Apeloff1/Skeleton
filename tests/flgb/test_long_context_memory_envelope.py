"""Memory envelope regression contracts: no telemetry is an execution grant."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.long_context_memory_envelope import (
    _cgroup_counter, _kernel_read, _meminfo, observe_memory_envelope,
)
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError


class Clock:
    def __init__(self):
        self.value = 1_000_000

    def __call__(self):
        self.value += 100
        return self.value


class MemoryEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.host = Path("/virtual/proc")
        self.group = Path("/virtual/cgroup")
        self.values = {
            (self.host, "meminfo"): "MemTotal: 2097152 kB\nMemAvailable: 1048576 kB\n",
            (self.group, "memory.current"): "268435456\n",
            (self.group, "memory.max"): "1073741824\n",
            (self.group, "memory.high"): "805306368\n",
        }
        self.clock = Clock()

    def read(self, root, name):
        return self.values[(root, name)]

    def observe(self, **kwargs):
        with patch("skeleton.ai.model_runtime.long_context_memory_envelope.os.name", "posix"), patch(
            "skeleton.ai.model_runtime.long_context_memory_envelope.sys.platform", "linux"
        ):
            return observe_memory_envelope(
                host_root=self.host, cgroup_root=self.group, reader=self.read,
                clock=self.clock, reserve_bytes=1024, **kwargs
            )

    def test_bounded_observed_headroom(self):
        receipt = self.observe(requested_bytes=512)
        self.assertEqual(receipt["state"], "observed_headroom")
        self.assertEqual(receipt["cgroup_remaining_bytes"], 536870912)
        self.assertEqual(receipt["observed_headroom_bytes"], 536869888)
        self.assertTrue(receipt["request_observed_sufficient"])
        self.assertEqual(len(receipt["observation_digest"]), 64)
        for field in ("is_admission_grant", "is_execution_lease",
                      "is_memory_reservation", "device_qualified",
                      "cross_source_snapshot_atomic"):
            self.assertIs(receipt[field], False)
        self.assertIs(receipt["requires_live_backend_revalidation"], True)

    def test_high_limit_and_host_limit_both_constrain(self):
        self.values[(self.group, "memory.high")] = "max\n"
        receipt = self.observe(requested_bytes=700_000_000)
        self.assertEqual(receipt["cgroup_remaining_bytes"], 805306368)
        self.assertTrue(receipt["request_observed_sufficient"])
        self.values[(self.host, "meminfo")] = (
            "MemTotal: 2097152 kB\nMemAvailable: 64 kB\n"
        )
        receipt = self.observe(requested_bytes=1)
        self.assertFalse(receipt["request_observed_sufficient"])
        self.assertEqual(receipt["observed_headroom_bytes"], 64512)

    def test_missing_or_unbounded_cgroup_holds(self):
        self.values[(self.group, "memory.max")] = "max\n"
        receipt = self.observe()
        self.assertEqual(receipt["state"], "hold")
        self.assertIsNone(receipt["host_available_bytes"])
        self.assertEqual(receipt["observed_headroom_bytes"], 0)

    def test_counter_mutation_during_sampling_holds(self):
        original = self.read
        counter = [0]
        def changed(root, name):
            value = original(root, name)
            if name == "memory.max":
                counter[0] += 1
                return "1073741824" if counter[0] == 1 else "536870912"
            return value
        self.read = changed
        self.assertEqual(self.observe()["state"], "hold")

    def test_clock_regression_and_slow_read_holds(self):
        self.clock = iter((10, 9)).__next__
        self.assertEqual(self.observe()["state"], "hold")
        self.clock = iter((10, 2_000_000_011)).__next__
        self.assertEqual(self.observe()["state"], "hold")

    def test_sensor_failure_and_malformed_counter_holds(self):
        for bad in ("-1", "NaN", "1.5", "1e4", "1 2", "9" * 30):
            with self.subTest(bad=bad):
                self.values[(self.group, "memory.current")] = bad
                self.assertEqual(self.observe()["state"], "hold")
        self.values[(self.group, "memory.current")] = "268435456"
        self.values[(self.host, "meminfo")] = "MemTotal: 20 kB\n"
        self.assertEqual(self.observe()["state"], "hold")

    def test_overused_cgroup_and_invalid_available_holds(self):
        self.values[(self.group, "memory.current")] = "999999999999"
        self.assertEqual(self.observe()["state"], "hold")
        self.values[(self.group, "memory.current")] = "268435456"
        self.values[(self.host, "meminfo")] = (
            "MemTotal: 10 kB\nMemAvailable: 11 kB\n"
        )
        self.assertEqual(self.observe()["state"], "hold")

    def test_strict_input_contract(self):
        for bad in (True, -1, 1024**3 + 1, 1.5):
            with self.subTest(bad=bad), self.assertRaises(LongContextSpoolError):
                self.observe(requested_bytes=bad)
        with self.assertRaises(LongContextSpoolError):
            with patch("skeleton.ai.model_runtime.long_context_memory_envelope.sys.platform", "linux"):
                observe_memory_envelope(reserve_bytes=-1, reader=self.read, clock=self.clock)

    def test_unsupported_platform_never_claims_memory(self):
        with patch("skeleton.ai.model_runtime.long_context_memory_envelope.sys.platform", "win32"):
            result = observe_memory_envelope(reader=self.read, clock=self.clock)
        self.assertEqual(result["reason"], "unsupported_platform")
        self.assertFalse(result["is_admission_grant"])

    def test_cli_read_only_memory_observation(self):
        import contextlib
        from io import StringIO
        from unittest.mock import MagicMock
        from skeleton.ai.model_runtime.long_context_cli import main
        output = StringIO()
        receipt = self.observe(requested_bytes=512)
        with patch(
            "skeleton.ai.model_runtime.long_context_cli.observe_memory_envelope",
            return_value=receipt
        ) as sampler, patch(
            "skeleton.ai.model_runtime.long_context_cli.LongContextSpool",
            side_effect=AssertionError("must not open spool")
        ), contextlib.redirect_stdout(output):
            code = main(["--root", "/unused", "--tokenizer-digest", "a" * 64,
                         "head-observe-memory", "--request-bytes", "512"])
        self.assertEqual(code, 0)
        sampler.assert_called_once_with(requested_bytes=512)
        self.assertIn('"state":"observed_headroom"', output.getvalue())

    def test_parser_strictness(self):
        for bad in ("", "MemTotal: 1 kB\n", "MemTotal: 1 kB\nMemAvailable: 2 kB",
                    "MemTotal: 1 kB\nMemTotal: 1 kB\nMemAvailable: 1 kB"):
            with self.assertRaises(LongContextSpoolError):
                _meminfo(bad)
        for bad in ("-1", "", "max  ", "NaN", "999999999999999999999"):
            with self.assertRaises(LongContextSpoolError):
                _cgroup_counter(bad, optional_max=False)

    @unittest.skipUnless(os.name == "posix", "POSIX descriptor fence")
    def test_kernel_read_rejects_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo").write_text("MemTotal: 1 kB\n")
            self.assertIn("MemTotal:", _kernel_read(root, "meminfo"))
            (root / "meminfo").unlink()
            (root / "meminfo").symlink_to("/etc/passwd")
            with self.assertRaises(OSError):
                _kernel_read(root, "meminfo")
            (root / "meminfo").unlink()
            (root / "meminfo").write_bytes(b"x" * (16 * 1024 + 1))
            with self.assertRaises(LongContextSpoolError):
                _kernel_read(root, "meminfo")

    @unittest.skipUnless(os.name == "posix", "POSIX descriptor fence")
    def test_kernel_read_rejects_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "real"
            root.mkdir()
            (root / "meminfo").write_text("MemTotal: 1 kB\\n")
            alias = Path(directory) / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises((OSError, LongContextSpoolError)):
                _kernel_read(alias, "meminfo")

    @unittest.skipUnless(os.name == "posix", "POSIX descriptor fence")
    def test_kernel_read_rejects_replaced_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            (root / "meminfo").write_text("MemTotal: 1 kB\n")
            renamed = Path(directory) / "old"
            original_stat = os.stat
            def adversarial(path, *args, **kwargs):
                if path == root and not kwargs.get("follow_symlinks", True):
                    root.rename(renamed)
                    root.mkdir()
                    (root / "meminfo").write_text("MemTotal: 2 kB\n")
                return original_stat(path, *args, **kwargs)
            with patch("skeleton.ai.model_runtime.long_context_memory_envelope.os.stat", side_effect=adversarial):
                with self.assertRaises(LongContextSpoolError):
                    _kernel_read(root, "meminfo")


if __name__ == "__main__":
    unittest.main()
