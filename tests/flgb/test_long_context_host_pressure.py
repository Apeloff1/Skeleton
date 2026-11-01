"""Fail-closed host PSI observation: fixtures are never hardware attestation."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.long_context_host_pressure import (
    _avg10, _read_psi, _secure_directory, observe_host_pressure,
)


@unittest.skipUnless(os.name == "posix" and Path("/proc/pressure").exists(),
                     "Linux PSI observation")
class TestLongContextHostPressure(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "pressure"
        self.root.mkdir(mode=0o700)
        self.write("cpu", 0)
        self.write("memory", 0)

    def write(self, name, avg):
        (self.root / name).write_bytes(
            ("some avg10=%.2f avg60=0.00 avg300=0.00 total=100\n"
             % avg).encode("ascii"))

    def observe(self):
        return observe_host_pressure(self.root)

    def test_normal_cpu_and_memory_never_authorize(self):
        result = self.observe()
        self.assertEqual(result["source"], "linux_proc_psi_observation")
        self.assertEqual(result["signals"]["cpu"], "normal")
        self.assertEqual(result["signals"]["memory"], "normal")
        self.assertEqual(result["signals"]["thermal"], "unknown")
        self.assertEqual(result["signals"]["energy"], "unknown")
        self.assertFalse(result["pressure_signals_attested"])
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["is_admission_grant"])
        self.assertFalse(result["is_execution_lease"])
        self.assertIn("thermal_unknown", result["hold_reasons"])

    def test_pressure_thresholds_are_conservative(self):
        for cpu, memory, expected_cpu, expected_memory in (
            (9.99, 4.99, "normal", "normal"),
            (10, 5, "elevated", "elevated"),
            (49.99, 19.99, "elevated", "elevated"),
            (50, 20, "critical", "critical"),
        ):
            with self.subTest(cpu=cpu, memory=memory):
                self.write("cpu", cpu)
                self.write("memory", memory)
                result = self.observe()
                self.assertEqual(result["signals"]["cpu"], expected_cpu)
                self.assertEqual(result["signals"]["memory"], expected_memory)

    def test_missing_and_symlinked_source_fail_closed(self):
        (self.root / "cpu").unlink()
        self.assertEqual(self.observe()["signals"]["cpu"], "unknown")
        (self.root / "cpu").symlink_to(self.root / "memory")
        self.assertEqual(self.observe()["source"], "unavailable")

    def test_malformed_duplicate_and_oversize_fail_closed(self):
        for raw in (
            b"some avg10=nan avg60=0.00 avg300=0.00 total=1\n",
            b"some avg10=-1 avg60=0.00 avg300=0.00 total=1\n",
            b"some avg10=101 avg60=0.00 avg300=0.00 total=1\n",
            b"some avg10=0.00 avg60=0.00 avg300=0.00 total=1\n" * 2,
            b"x" * 4097,
            b"",
        ):
            with self.subTest(raw=raw[:32]):
                (self.root / "cpu").write_bytes(raw)
                self.assertEqual(self.observe()["source"], "unavailable")
                self.assertEqual(self.observe()["signals"]["cpu"], "unknown")

    def test_symlinked_ancestor_is_rejected(self):
        link = Path(self.tmp.name) / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        result = observe_host_pressure(link)
        self.assertEqual(result["source"], "unavailable")
        self.assertEqual(result["signals"]["memory"], "unknown")

    def test_directory_identity_swap_fails_closed(self):
        original = _secure_directory
        count = [0]
        def swapped(path):
            count[0] += 1
            if count[0] == 2:
                other = Path(self.tmp.name) / "other"
                other.mkdir(mode=0o700)
                return original(other)
            return original(path)
        with patch("skeleton.ai.model_runtime.long_context_host_pressure._secure_directory",
                   side_effect=swapped):
            result = self.observe()
        self.assertEqual(result["source"], "unavailable")

    def test_invalid_psi_source_rejected_before_open(self):
        directory = _secure_directory(self.root)
        try:
            with self.assertRaises(ValueError):
                _read_psi(directory, "../memory")
        finally:
            os.close(directory)

    def test_parser_rejects_duplicate_some_and_non_ascii(self):
        for raw in (b"some avg10=0.00 avg60=0.00 avg300=0.00 total=1\n" * 2,
                    b"some avg10=0.00 avg60=0.00 avg300=0.00 total=1\xff"):
            with self.assertRaises(ValueError):
                _avg10(raw)


if __name__ == "__main__":
    unittest.main()
