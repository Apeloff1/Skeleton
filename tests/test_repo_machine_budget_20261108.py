"""Finite repo-machine scanning regressions for the 2026-11 first-install backlog.

No huge filesystem fixtures or runtime-selected Python imports. The scanner
must return a visible truncated verdict rather than claiming a partial tree
is a complete source review.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config

REPOSITORY = Path(__file__).resolve().parents[1]


class RepositoryBudgetTests(TestCase):
    def test_source_capacity_is_finite_and_compatible_with_live_repository(self):
        config = load_machine_config(REPOSITORY)
        self.assertGreater(config.max_files, 100_000)
        self.assertLessEqual(config.max_files, 500_000)
        self.assertLessEqual(config.max_file_bytes, 2_000_000)

    def test_finite_scan_never_silently_truncates(self):
        with TemporaryDirectory(prefix="skeleton-scanner-budget-") as directory:
            root = Path(directory)
            names = ["one.py", "two.py", "three.py", "four.py"]
            for cap, count, truncated in (
                (1, 1, True),
                (2, 2, True),
                (3, 3, True),
                (4, 4, False),
                (5, 4, False),
            ):
                with self.subTest(max_files=cap):
                    config = replace(load_machine_config(REPOSITORY), max_files=cap)
                    scanner = RepositoryModelBuilder(root, config=config)
                    with patch(
                        "skeleton.repo_machine.builder.os.walk",
                        return_value=iter([(str(root), [], names)]),
                    ):
                        listed, incomplete = scanner._iter_files()
                    self.assertEqual(len(listed), count)
                    self.assertEqual(incomplete, truncated)
                    self.assertEqual([item.name for item in listed], names[:count])

    def test_oversized_file_limit_does_not_expand_permitted_model_bytes(self):
        config = load_machine_config(REPOSITORY)
        self.assertIs(type(config.max_file_bytes), int)
        self.assertGreater(config.max_file_bytes, 0)
        self.assertLessEqual(config.max_file_bytes, 2_000_000)


if __name__ == "__main__":
    import unittest

    unittest.main()
