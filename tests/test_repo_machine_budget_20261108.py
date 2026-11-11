"""Fail-closed repository machine scan budget regression.

A larger deliberate finite budget is not a permission to ignore truncation.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config


ROOT = Path(__file__).resolve().parents[1]


class RepositoryMachineBudgetTests(unittest.TestCase):
    def test_bounded_budget_covers_latest_source_inventory(self):
        config = load_machine_config(ROOT)
        self.assertGreaterEqual(config.max_files, 125000)
        self.assertLessEqual(config.max_files, 250000)
        self.assertGreater(config.max_files, 100000)
        self.assertLessEqual(config.max_files, 250000)

    def test_at_exact_limit_is_not_truncated_but_next_file_is(self):
        config = replace(load_machine_config(ROOT), max_files=2)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.py").write_text("a=1\n", encoding="utf-8")
            (root / "b.py").write_text("b=2\n", encoding="utf-8")
            files, truncated = RepositoryModelBuilder(root, config=config)._iter_files()
            self.assertEqual(len(files), 2)
            self.assertFalse(truncated)
            (root / "c.py").write_text("c=3\n", encoding="utf-8")
            files, truncated = RepositoryModelBuilder(root, config=config)._iter_files()
            self.assertEqual(len(files), 2)
            self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
