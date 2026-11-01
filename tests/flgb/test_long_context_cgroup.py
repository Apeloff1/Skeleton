"""Cgroup-v2 observer: bounded descriptor custody and fail-closed fixtures."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.long_context_cgroup import (
    _read_counter, observe_cgroup_pressure,
)
from skeleton.ai.model_runtime.long_context_host_pressure import _secure_directory
from skeleton.ai.model_runtime.long_context_cli import main


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                     "POSIX descriptor custody")
class TestCgroupObservation(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "cgroup"
        self.root.mkdir(mode=0o700)
        self.psi("cpu", 0)
        self.psi("memory", 0)
        self.scalar("memory.current", "200")
        self.scalar("memory.max", "1000")

    def psi(self, name, value):
        (self.root / name).write_bytes(
            ("some avg10=%.2f avg60=0.00 avg300=0.00 total=1\n"
             % value).encode("ascii")
        )

    def scalar(self, name, value):
        (self.root / name).write_bytes((value + "\n").encode("ascii"))

    def observe(self):
        return observe_cgroup_pressure(self.root)

    def test_bounded_normal_is_still_not_admission(self):
        result = self.observe()
        self.assertEqual(result["source"], "cgroup_v2_root_observation")
        self.assertEqual(result["signals"]["cpu"], "normal")
        self.assertEqual(result["signals"]["memory"], "normal")
        self.assertEqual(result["signals"]["thermal"], "unknown")
        self.assertEqual(result["signals"]["energy"], "unknown")
        self.assertEqual(result["memory_current_bytes"], 200)
        self.assertEqual(result["memory_limit_bytes"], 1000)
        for key in ("is_admission_grant", "is_execution_lease",
                    "device_qualified", "pressure_signals_attested",
                    "scope_membership_attested", "cross_file_snapshot_atomic"):
            self.assertFalse(result[key])
        self.assertTrue(result["requires_live_backend_revalidation"])

    def test_ratio_thresholds_and_psi_severity(self):
        for current, expected in ((849, "normal"), (850, "elevated"),
                                  (949, "elevated"), (950, "critical"),
                                  (1100, "critical")):
            with self.subTest(current=current):
                self.scalar("memory.current", str(current))
                self.assertEqual(self.observe()["signals"]["memory"], expected)
        self.scalar("memory.current", "100")
        self.psi("memory", 20)
        self.assertEqual(self.observe()["signals"]["memory"], "critical")
        self.psi("cpu", 10)
        self.assertEqual(self.observe()["signals"]["cpu"], "elevated")

    def test_unlimited_memory_is_unknown_even_with_normal_psi(self):
        self.scalar("memory.max", "max")
        result = self.observe()
        self.assertEqual(result["signals"]["memory"], "unknown")
        self.assertIsNone(result["memory_limit_bytes"])
        self.assertIn("memory_unknown", result["hold_reasons"])

    def test_zero_limit_malformed_and_oversize_fail_closed(self):
        for bad in (b"0\n", b"-1\n", b"1.0\n", b"nan\n",
                    b"100\n100\n", b"9" * 129, b""):
            with self.subTest(bad=bad[:16]):
                (self.root / "memory.max").write_bytes(bad)
                result = self.observe()
                self.assertEqual(result["source"], "unavailable")
                self.assertEqual(result["signals"]["memory"], "unknown")
                self.assertIsNone(result["memory_current_bytes"])
                self.assertFalse(result["is_admission_grant"])

    def test_missing_symlink_and_hardlink_counter_fail_closed(self):
        counter = self.root / "memory.current"
        counter.unlink()
        self.assertEqual(self.observe()["source"], "unavailable")
        counter.symlink_to(self.root / "memory.max")
        self.assertEqual(self.observe()["source"], "unavailable")
        counter.unlink()
        self.scalar("memory.current", "200")
        os.link(counter, self.root / "counter.alias")
        self.assertEqual(self.observe()["source"], "unavailable")

    def test_symlinked_directory_ancestor_rejected(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.root, target_is_directory=True)
        result = observe_cgroup_pressure(link)
        self.assertEqual(result["source"], "unavailable")

    def test_in_place_counter_mutation_rejected(self):
        original = os.read
        mutated = [False]

        def change(fd, size):
            data = original(fd, size)
            if not mutated[0] and data == b"200\n":
                mutated[0] = True
                counter = self.root / "memory.current"
                info = counter.stat()
                counter.write_bytes(b"900\n")
                os.utime(counter, ns=(info.st_atime_ns,
                                       info.st_mtime_ns + 2_000_000_000))
            return data

        with patch("skeleton.ai.model_runtime.long_context_cgroup.os.read",
                   side_effect=change):
            result = self.observe()
        self.assertTrue(mutated[0])
        self.assertEqual(result["source"], "unavailable")

    def test_name_swap_after_open_rejected(self):
        original = os.read
        swapped = [False]

        def replace(fd, size):
            data = original(fd, size)
            if not swapped[0] and data == b"200\n":
                swapped[0] = True
                replacement = self.root / "counter.new"
                replacement.write_bytes(data)
                os.replace(replacement, self.root / "memory.current")
            return data

        with patch("skeleton.ai.model_runtime.long_context_cgroup.os.read",
                   side_effect=replace):
            result = self.observe()
        self.assertTrue(swapped[0])
        self.assertEqual(result["source"], "unavailable")

    def test_directory_replacement_rejected(self):
        original = _secure_directory
        count = [0]

        def swapped(path):
            count[0] += 1
            if count[0] == 2:
                other = Path(self.temp.name) / "other"
                other.mkdir(mode=0o700)
                return original(other)
            return original(path)

        with patch("skeleton.ai.model_runtime.long_context_cgroup._secure_directory",
                   side_effect=swapped):
            self.assertEqual(self.observe()["source"], "unavailable")

    def test_unsupported_counter_name_never_opened(self):
        fd = _secure_directory(self.root)
        try:
            with self.assertRaises(ValueError):
                _read_counter(fd, "../memory.max")
        finally:
            os.close(fd)

    def test_cli_observes_without_opening_spool(self):
        output = StringIO()
        with patch("skeleton.ai.model_runtime.long_context_cli.LongContextSpool",
                   side_effect=AssertionError("spool must stay closed")):
            with patch("skeleton.ai.model_runtime.long_context_cli.observe_cgroup_pressure",
                       return_value=self.observe()):
                with redirect_stdout(output):
                    code = main(["--root", str(self.root / "unused"),
                                 "--tokenizer-digest", "a" * 64,
                                 "head-observe-cgroup"])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "unused").exists())
        result = json.loads(output.getvalue())
        self.assertFalse(result["is_execution_lease"])


if __name__ == "__main__":
    unittest.main()
