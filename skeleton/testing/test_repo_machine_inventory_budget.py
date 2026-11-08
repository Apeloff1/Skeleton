"""Exact-bound repository machine inventory semantics on large source trees.

The production scanner must enumerate all permitted files up to the finite
configured limit, detect the first overflow, and never claim completeness
from a truncated working tree.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config


REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("cap", "expected_files", "expected_truncated"),
    [
        (1, 1, True),
        (2, 2, True),
        (3, 3, True),
        (4, 4, False),
        (5, 4, False),
    ],
)
def test_inventory_only_reports_complete_when_every_file_was_seen(
    cap, expected_files, expected_truncated,
):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        names = ["a.py", "b.py", "c.py", "d.py"]
        config = replace(load_machine_config(REPOSITORY), max_files=cap)
        scanner = RepositoryModelBuilder(root, config=config)
        # No source content is read. The real scanner's enumeration behavior
        # is tested without a 250,000-file fixture or local filesystem writes.
        with patch(
            "skeleton.repo_machine.builder.os.walk",
            return_value=iter([(str(root), [], names)]),
        ):
            inventory, truncated = scanner._iter_files()
        assert len(inventory) == expected_files
        assert truncated is expected_truncated
        assert [path.name for path in inventory] == names[:expected_files]


def test_repository_scan_capacity_remains_finite_and_not_under_live_ci_floor():
    config = load_machine_config(REPOSITORY)
    assert 100_000 < config.max_files <= 500_000
    assert config.max_file_bytes <= 2_000_000
