"""Reconciled independent source-custody regressions from Jeeves and Dragon.

Artificial artifact fixtures never establish native model or release qualification.
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
                    self.assertEqual([item.name for item in listed], sorted(names)[:count])

    def test_oversized_file_limit_does_not_expand_permitted_model_bytes(self):
        config = load_machine_config(REPOSITORY)
        self.assertIs(type(config.max_file_bytes), int)
        self.assertGreater(config.max_file_bytes, 0)
        self.assertLessEqual(config.max_file_bytes, 2_000_000)


# Independent Dragon donor cases retained during integration.
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config


ROOT = Path(__file__).resolve().parents[1]


class RepositoryInventoryFiniteBudget(TestCase):
    def test_file_cap_preserves_exhaustiveness_flag(self):
        names = ["alpha.py", "beta.py", "gamma.py", "delta.py"]
        configuration = load_machine_config(ROOT)
        for cap, length, truncated in (
            (1, 1, True), (2, 2, True), (3, 3, True),
            (4, 4, False), (5, 4, False),
        ):
            with self.subTest(cap=cap), TemporaryDirectory() as temporary:
                root = Path(temporary)
                model = RepositoryModelBuilder(root, config=replace(configuration, max_files=cap))
                with patch("skeleton.repo_machine.builder.os.walk",
                           return_value=iter([(str(root), [], names)])):
                    rows, was_truncated = model._iter_files()
                self.assertEqual(len(rows), length)
                self.assertEqual(was_truncated, truncated)
                # Production scanner sorts paths before enforcing the cap.
                # Assert deterministic canonical order, not os.walk order.
                self.assertEqual([file.name for file in rows], sorted(names)[:length])

    def test_live_config_maxima_are_finite_and_prohibit_oversize_files(self):
        config = load_machine_config(ROOT)
        self.assertGreater(config.max_files, 100000)
        self.assertLessEqual(config.max_files, 500000)
        self.assertGreater(config.max_file_bytes, 0)
        self.assertLessEqual(config.max_file_bytes, 2000000)


if __name__ == "__main__":
    import unittest
    unittest.main()
