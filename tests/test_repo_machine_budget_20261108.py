"""Independent finite-budget repository source inventory admission test.

The scanner's output must not report a complete inventory when max_files
truncates the last path, and no synthetic files can satisfy a source-release
qualification. The test uses a finite deterministic mock of os.walk only.
"""
from __future__ import annotations

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
                self.assertEqual([file.name for file in rows], names[:length])

    def test_live_config_maxima_are_finite_and_prohibit_oversize_files(self):
        config = load_machine_config(ROOT)
        self.assertGreater(config.max_files, 100000)
        self.assertLessEqual(config.max_files, 500000)
        self.assertGreater(config.max_file_bytes, 0)
        self.assertLessEqual(config.max_file_bytes, 2000000)


if __name__ == "__main__":
    main()
