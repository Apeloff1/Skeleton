"""Independent stdlib regression for repository inventory truncation and finite budgets.

Tests the actual scanner behavior with mocked enumeration, never fabricated
proof that the whole 100k+ source tree was scanned by these small fixtures.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config


ROOT = Path(__file__).resolve().parents[1]


class RepositoryScanBudgetTests(unittest.TestCase):
    def test_configured_capacity_is_finite_and_above_repository_floor(self):
        config = load_machine_config(ROOT)
        self.assertGreater(config.max_files, 100_000)
        self.assertLessEqual(config.max_files, 500_000)
        self.assertGreater(config.max_file_bytes, 0)
        self.assertLessEqual(config.max_file_bytes, 2_000_000)

    def test_at_capacity_is_not_confused_with_complete_inventory(self):
        for cap in range(1, 6):
            with self.subTest(cap=cap):
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    names = ["a.py", "b.py", "c.py", "d.py"]
                    config = replace(load_machine_config(ROOT), max_files=cap)
                    machine = RepositoryModelBuilder(root, config=config)
                    with patch("skeleton.repo_machine.builder.os.walk",
                               return_value=iter([(str(root), [], names)])):
                        files, truncated = machine._iter_files()
                    self.assertEqual(len(files), min(cap, len(names)))
                    self.assertEqual([f.name for f in files], names[:cap])
                    self.assertIs(truncated, cap < len(names))

    def test_incomplete_inventory_never_qualifies_as_complete(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for cap in (1, 2, 3):
                config = replace(load_machine_config(ROOT), max_files=cap)
                machine = RepositoryModelBuilder(root, config=config)
                with patch("skeleton.repo_machine.builder.os.walk",
                           return_value=iter([(str(root), [], ["a.py", "b.py", "c.py", "d.py"])])):
                    files, truncated = machine._iter_files()
                self.assertTrue(truncated, f"{cap} would hide at least one source")
                self.assertLess(len(files), 4)


if __name__ == "__main__":
    unittest.main()
