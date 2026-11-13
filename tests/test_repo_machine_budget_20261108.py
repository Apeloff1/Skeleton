"""Finite-capacity repository scanner regressions used by Draft19 source CI."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config


ROOT = Path(__file__).resolve().parents[1]


class RepositoryBudgetTests(unittest.TestCase):
    def test_live_repository_budget_is_finite_and_above_full_source_floor(self):
        config = load_machine_config(ROOT)
        self.assertGreater(config.max_files, 100000)
        self.assertLessEqual(config.max_files, 500000)
        self.assertGreater(config.max_file_bytes, 0)
        self.assertLessEqual(config.max_file_bytes, 2000000)

    def test_scanner_reports_first_truncation_before_claiming_completeness(self):
        names = ["a.py", "b.py", "c.py", "d.py"]
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for cap in (1, 2, 3, 4, 5):
                with self.subTest(cap=cap):
                    config = replace(load_machine_config(ROOT), max_files=cap)
                    scanner = RepositoryModelBuilder(root, config=config)
                    with patch(
                        "skeleton.repo_machine.builder.os.walk",
                        return_value=iter([(str(root), [], names)]),
                    ):
                        items, truncated = scanner._iter_files()
                    self.assertEqual(
                        [item.name for item in items], names[: min(cap, len(names))]
                    )
                    self.assertIs(truncated, cap < len(names))


if __name__ == "__main__":
    unittest.main()
